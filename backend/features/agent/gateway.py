"""Cổng kiểu OpenAI Responses cho ứng dụng desktop Peto Agent (bản fork DeepSeek Harness, repo peto-harness).

Ứng dụng tự viết chỉ dẫn hệ thống và tự khai báo công cụ, như với mọi cổng tương thích OpenAI. Máy chủ chỉ:
- xác thực bằng token thiết bị ``peto_…`` mà ``peto login`` cấp (cùng ``device_auth`` với CLI);
- trừ bước trong hạn mức ngày như ``/api/agent/step`` (mức suy nghĩ × hệ số model), trả lại khi model chưa kịp phản
  hồi gì;
- gọi Grok, GPT hoặc Claude bằng khóa của máy chủ qua ``ai.agent.agent_step``, rồi phát lại đúng dạng sự kiện stream
  của OpenAI Responses để bộ nối ``openai-responses`` của pi-ai (``dsh-llm-pi-ai``) đọc như một cổng tương thích.

Không lưu hội thoại, không chèn prompt Peto, không bật tìm web phía máy chủ (ứng dụng có công cụ web riêng).

Thứ tự item: chữ và suy nghĩ được phát ngay khi tới, nên một item suy luận chỉ có ở kết quả cuối (GPT không gửi tóm
tắt suy nghĩ) có thể đứng sau item chữ trong lịch sử ứng dụng gửi lại. Mọi dịch vụ đều đặt suy luận trước các item
khác của cùng một lượt trả lời, nên ``_reasoning_first`` đưa suy luận lên đầu mỗi lượt trước khi gọi model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import storage as db
from ai import models as ai_models
from ai.agent import AgentEvent, agent_step
from ai.base import ProviderError
from core import usage_events
from core.config import AGENT_DAILY_STEPS, AGENT_MODEL, AGENT_REASONING, AGENT_STEP_TIMEOUT_SECONDS
from core.rate_limit import AdmissionDenied
from features.agent import budget
from features.agent.api import (
    MAX_ITEMS, MAX_STEP_IMAGES, STEP_COST, _count_images, _read_body, _today, admission, device_auth,
)

logger = logging.getLogger("peto_web.agent")
router = APIRouter(prefix="/api/agent/v1", tags=["agent-gateway"])

INSTRUCTION_ROLES = {"system", "developer"}
ITEM_TYPES = {"message", "function_call", "function_call_output", "reasoning"}
TOOL_CHOICES = {"auto", "none", "required"}
MAX_TOOLS = 128
EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
# Chờ sự kiện đầu tiên tối đa chừng này trước khi gửi header: lỗi xảy ra ngay (hết bước, khóa hỏng, giới hạn lượt)
# trả về đúng mã HTTP để SDK tự thử lại hoặc dừng. Quá lâu thì mở stream luôn, vì Cloudflare cắt kết nối chưa có
# header sau khoảng 100 giây.
FIRST_EVENT_SECONDS = 15.0
# Dòng chú thích SSE giữ kết nối qua Cloudflare khi model nghĩ lâu; SDK OpenAI bỏ qua dòng bắt đầu bằng ":".
PING_SECONDS = 15.0
SYSTEM_UPDATE = "System update:\n"
# Ô suy nghĩ cổng tự mở khi model gửi tóm tắt suy nghĩ; nếu kết quả cuối không có item suy luận, ô được đóng bằng
# item rỗng mang mã này. pi-ai gửi lại nguyên item đó ở lần sau, nên cổng bỏ nó (và tin assistant rỗng) khi nhận vào.
PLACEHOLDER_REASONING = "rs_peto_"


class GatewayError(Exception):
    """Lỗi trả về theo dạng ``{"error": {...}}`` của OpenAI.

    ``retry``: gửi header ``x-should-retry`` để pi-ai biết có nên tự gửi lại (lỗi tạm thời, bước đã được hoàn lại)
    hay không (hết hạn mức, lỗi đã tốn token).
    """

    def __init__(self, status: int, message: str, *, code: str | None = None,
                 kind: str = "invalid_request_error", retry: bool | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.kind = kind
        self.retry = retry


def _error_response(err: GatewayError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if err.retry is not None:
        headers["x-should-retry"] = "true" if err.retry else "false"
    return JSONResponse({"error": {"message": err.message, "type": err.kind, "code": err.code, "param": None}},
                        status_code=err.status, headers=headers)


def _from_http(err: HTTPException, kind: str = "invalid_request_error") -> GatewayError:
    return GatewayError(err.status_code, str(err.detail), kind=kind)


async def _device(request: Request) -> dict:
    try:
        return await device_auth(request)
    except HTTPException as err:
        raise GatewayError(err.status_code, str(err.detail), code="invalid_api_key",
                           kind="authentication_error") from None


@dataclass(frozen=True)
class Parsed:
    model: str
    items: list[dict]
    instructions: str
    tools: list[dict]
    tool_choice: str | None
    effort: str | None
    max_output_tokens: int | None


def _plain_text(content) -> str:
    """Chữ của một tin system/developer: chuỗi, hoặc danh sách phần chữ (``input_text``/``text``)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and all(
            isinstance(part, dict) and part.get("type") in {"input_text", "text"} and isinstance(part.get("text"), str)
            for part in content):
        return "\n".join(part["text"] for part in content)
    raise GatewayError(400, "Tin system hoặc developer chỉ được có chữ.")


def _placeholder(item: dict) -> bool:
    """Item rỗng do chính cổng phát ra (xem ``PLACEHOLDER_REASONING``): không có gì để gửi lại cho model."""
    if item.get("type") == "reasoning":
        return str(item.get("id", "")).startswith(PLACEHOLDER_REASONING) and not item.get("encrypted_content")
    if item.get("type", "message") == "message" and item.get("role") == "assistant":
        content = item.get("content")
        if isinstance(content, str):
            return not content
        return isinstance(content, list) and not any(
            isinstance(part, dict) and (part.get("text") or part.get("refusal")) for part in content)
    return False


def _reasoning_first(items: list[dict]) -> list[dict]:
    """Đưa item suy luận lên đầu mỗi lượt trả lời, giữ nguyên thứ tự còn lại.

    Một lượt là chuỗi item liền nhau của model (suy luận, tin của assistant, lời gọi công cụ), ngăn cách bởi tin người
    dùng hoặc kết quả công cụ.
    """
    result: list[dict] = []
    turn: list[dict] = []

    def flush() -> None:
        result.extend(item for item in turn if item.get("type") == "reasoning")
        result.extend(item for item in turn if item.get("type") != "reasoning")
        turn.clear()

    for item in items:
        kind = item.get("type", "message")
        if kind == "reasoning" or kind == "function_call" or (kind == "message" and item.get("role") == "assistant"):
            turn.append(item)
        else:
            flush()
            result.append(item)
    flush()
    return result


def _parse(raw: bytes) -> Parsed:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GatewayError(400, "Dữ liệu gửi lên không phải JSON hợp lệ.") from None
    if not isinstance(payload, dict):
        raise GatewayError(400, "Dữ liệu gửi lên không phải JSON hợp lệ.")
    if payload.get("stream") is not True:
        raise GatewayError(400, "Cổng này chỉ trả kết quả dạng stream. Gửi kèm stream: true.", code="stream_required")
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise GatewayError(400, "Thiếu tên model.", code="model_not_found")

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        raw_input = [{"role": "user", "content": raw_input}]
    if not isinstance(raw_input, list) or not raw_input:
        raise GatewayError(400, "Yêu cầu chưa có nội dung.")
    instructions = payload.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise GatewayError(400, "instructions phải là chuỗi.")
    parts = [instructions] if instructions else []
    items: list[dict] = []
    images = 0
    leading = True
    for item in raw_input:
        if not isinstance(item, dict):
            raise GatewayError(400, "Yêu cầu có mục không hợp lệ.")
        kind = item.get("type", "message")
        role = item.get("role")
        if kind == "message" and role in INSTRUCTION_ROLES:
            text = _plain_text(item.get("content"))
            if leading:
                parts.append(text)
            elif text.strip():
                # Chỉ dẫn hệ thống giữa hội thoại (pi-ai gửi khi cấu hình đổi): Claude không có vai này, nên đưa thành
                # tin người dùng có ghi rõ nguồn cho mọi model.
                items.append({"role": "user", "content": [{"type": "input_text", "text": SYSTEM_UPDATE + text}]})
            continue
        leading = False
        if kind not in ITEM_TYPES:
            raise GatewayError(400, f"Cổng chưa nhận mục loại {kind}.")
        if _placeholder(item):
            continue
        if kind == "message":
            if role not in {"user", "assistant"}:
                raise GatewayError(400, "Tin chỉ được có vai user, assistant, system hoặc developer.")
            if role == "user":
                try:
                    images += _count_images(item.get("content"))
                except HTTPException as err:
                    raise _from_http(err) from None
        items.append({key: value for key, value in item.items() if value is not None})
    if not items:
        raise GatewayError(400, "Yêu cầu chưa có tin nào ngoài chỉ dẫn hệ thống.")
    if len(items) > MAX_ITEMS:
        raise GatewayError(400, f"Hội thoại đã quá {MAX_ITEMS} mục. Hãy tóm tắt hoặc mở phiên mới.",
                           code="context_length_exceeded")
    if images > MAX_STEP_IMAGES:
        raise GatewayError(400, f"Mỗi lần gọi gửi kèm tối đa {MAX_STEP_IMAGES} ảnh.")

    tools = payload.get("tools") or []
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
        raise GatewayError(400, f"Danh sách công cụ không hợp lệ (tối đa {MAX_TOOLS}).")
    clean_tools = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function" or not isinstance(tool.get("name"), str):
            raise GatewayError(400, "Cổng chỉ nhận công cụ dạng function.")
        clean_tools.append({key: tool[key] for key in ("type", "name", "description", "parameters", "strict")
                            if tool.get(key) is not None})
    tool_choice = payload.get("tool_choice")
    if tool_choice is not None and (not isinstance(tool_choice, str) or tool_choice not in TOOL_CHOICES):
        raise GatewayError(400, "tool_choice chỉ nhận auto, none hoặc required.")

    reasoning = payload.get("reasoning")
    effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    if effort is not None and (not isinstance(effort, str) or effort not in EFFORT_ORDER):
        raise GatewayError(400, "Mức suy nghĩ không hợp lệ.")
    max_output = payload.get("max_output_tokens")
    if max_output is not None and (not isinstance(max_output, int) or isinstance(max_output, bool) or max_output < 1):
        raise GatewayError(400, "max_output_tokens phải là số nguyên dương.")
    return Parsed(model, _reasoning_first(items), "\n\n".join(part for part in parts if part), clean_tools,
                  tool_choice, effort, max_output)


def _effort(requested: str | None, model_key: str) -> str:
    """Mức gần nhất model hỗ trợ: pi-ai có mức "minimal" mà Peto không có, nên làm tròn thay vì từ chối."""
    supported = ai_models.supported_efforts(model_key)
    if requested is None:
        return AGENT_REASONING if AGENT_REASONING in supported else supported[0]
    if requested in supported:
        return requested
    rank = EFFORT_ORDER.index(requested)
    return min(supported, key=lambda effort: (abs(EFFORT_ORDER.index(effort) - rank), EFFORT_ORDER.index(effort)))


def _usage(usage: dict) -> dict:
    """Usage của Peto (dạng Responses, input đã gồm token cache) thành usage của một response OpenAI."""
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    details = {"cached_tokens": int(usage.get("cached_tokens") or 0)}
    if usage.get("cache_write_tokens"):
        details["cache_write_tokens"] = int(usage["cache_write_tokens"])
    return {"input_tokens": input_tokens, "input_tokens_details": details, "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": input_tokens + output_tokens}


class ResponseWriter:
    """Dựng chuỗi sự kiện stream của OpenAI Responses từ sự kiện của ``agent_step``.

    Suy nghĩ và chữ mở một ô (output_index) khi tới lần đầu; khi xong bước, mỗi item cuối khớp ô cùng loại đã mở theo
    thứ tự, item khác mở ô mới. pi-ai lấy nội dung cuối từ ``response.output_item.done``.
    """

    def __init__(self, model: str):
        self.id = "resp_" + secrets.token_hex(12)
        self.model = model
        self.created_at = int(time.time())
        self.sequence = 0
        self.next_index = 0
        self.open: dict[str, int] = {}
        self.item_ids: dict[int, str] = {}

    def _sse(self, payload: dict) -> str:
        payload = {**payload, "sequence_number": self.sequence}
        self.sequence += 1
        return f"event: {payload['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def response(self, status: str, output: list[dict] | None = None, usage: dict | None = None,
                 error: dict | None = None) -> dict:
        return {"id": self.id, "object": "response", "created_at": self.created_at, "status": status,
                "model": self.model, "output": output or [], "usage": usage, "error": error,
                "incomplete_details": None}

    def created(self) -> list[str]:
        return [self._sse({"type": "response.created", "response": self.response("in_progress")}),
                self._sse({"type": "response.in_progress", "response": self.response("in_progress")})]

    def _open(self, kind: str, item: dict) -> tuple[int, list[str]]:
        if kind in self.open:
            return self.open[kind], []
        index = self.next_index
        self.next_index += 1
        self.open[kind] = index
        self.item_ids[index] = item["id"]
        return index, [self._sse({"type": "response.output_item.added", "output_index": index, "item": item})]

    def feed(self, event: AgentEvent) -> list[str]:
        if event.kind == "thinking" and event.text:
            index, chunks = self._open("reasoning", {"type": "reasoning",
                                                     "id": PLACEHOLDER_REASONING + secrets.token_hex(12), "summary": []})
            chunks.append(self._sse({"type": "response.reasoning_summary_text.delta", "item_id": self.item_ids[index],
                                     "output_index": index, "summary_index": 0, "delta": event.text}))
            return chunks
        if event.kind == "delta" and event.text:
            index, chunks = self._open("message", {"type": "message", "id": "msg_" + secrets.token_hex(12),
                                                   "role": "assistant", "status": "in_progress", "content": []})
            chunks.append(self._sse({"type": "response.output_text.delta", "item_id": self.item_ids[index],
                                     "output_index": index, "content_index": 0, "delta": event.text}))
            return chunks
        return []

    def finish(self, output: list[dict], usage: dict) -> list[str]:
        chunks: list[str] = []
        unused = dict(self.open)
        placed: list[tuple[int, dict]] = []
        for item in output:
            kind = item.get("type")
            slot = "reasoning" if kind == "reasoning" else "message" if kind == "message" else None
            if slot is not None and slot in unused:
                index = unused.pop(slot)
            else:
                index = self.next_index
                self.next_index += 1
                skeleton = {**item, "arguments": ""} if kind == "function_call" else (
                    {**item, "content": []} if kind == "message" else item)
                chunks.append(self._sse({"type": "response.output_item.added", "output_index": index,
                                         "item": skeleton}))
            if kind == "function_call":
                arguments = str(item.get("arguments") or "")
                item_id = item.get("id") or item.get("call_id")
                if arguments:
                    chunks.append(self._sse({"type": "response.function_call_arguments.delta", "item_id": item_id,
                                             "output_index": index, "delta": arguments}))
                chunks.append(self._sse({"type": "response.function_call_arguments.done", "item_id": item_id,
                                         "output_index": index, "arguments": arguments}))
            chunks.append(self._sse({"type": "response.output_item.done", "output_index": index, "item": item}))
            placed.append((index, item))
        # Ô đã mở mà kết quả cuối không có item cùng loại (hiếm): đóng bằng item rỗng để pi-ai không giữ ô dở.
        for kind, index in unused.items():
            empty = ({"type": "reasoning", "id": self.item_ids[index], "summary": []} if kind == "reasoning" else
                     {"type": "message", "id": self.item_ids[index], "role": "assistant", "status": "completed",
                      "content": []})
            chunks.append(self._sse({"type": "response.output_item.done", "output_index": index, "item": empty}))
        final = [item for _, item in sorted(placed, key=lambda pair: pair[0])]
        chunks.append(self._sse({"type": "response.completed",
                                 "response": self.response("completed", final, _usage(usage))}))
        return chunks

    def failed(self, err: GatewayError) -> str:
        return self._sse({"type": "response.failed", "response": self.response(
            "failed", error={"code": err.code or err.kind, "message": err.message})})


def _provider_failure(err: ProviderError) -> GatewayError:
    if err.code == "context_overflow":
        return GatewayError(400, str(err), code="context_length_exceeded", retry=False)
    if err.retryable:
        return GatewayError(503, str(err), code="server_error", kind="server_error", retry=True)
    return GatewayError(502, str(err), code="provider_error", kind="server_error", retry=False)


@router.get("/models")
async def list_models(request: Request):
    try:
        device = await _device(request)
    except GatewayError as err:
        return _error_response(err)
    data = []
    for model in ai_models.usable(device["owner"], "agent"):
        limits = budget.limits(model.key)
        data.append({"id": model.key, "object": "model", "created": 0, "owned_by": "peto",
                     "display_name": model.label, "context_window": limits["context"],
                     "max_output_tokens": limits["output"],
                     # Ngoài chuẩn OpenAI: để app chỉ hiện các mức suy nghĩ model này thật sự nhận.
                     "reasoning_efforts": list(ai_models.supported_efforts(model.key))})
    return JSONResponse({"object": "list", "data": data}, headers={"Cache-Control": "no-store"})


@router.post("/responses")
async def create_response(request: Request):
    try:
        device = await _device(request)
        try:
            raw = await _read_body(request)
        except HTTPException as err:
            raise _from_http(err) from None
        parsed = _parse(raw)
        owner = device["owner"]
        try:
            model = ai_models.resolve(owner, parsed.model, "agent")
        except ai_models.ModelUnavailable as err:
            raise GatewayError(err.status if err.status != 400 else 404, err.message, code="model_not_found") from None
        effort = _effort(parsed.effort, model.key)
        day = _today()
        cost = STEP_COST[effort] * model.step_cost
        if await db.take_agent_step(owner, day, AGENT_DAILY_STEPS, cost) is None:
            left = max(0, AGENT_DAILY_STEPS - await db.get_agent_steps(owner, day))
            message = (f"Mỗi lần gọi {model.label} ở mức suy nghĩ này tính {cost} bước, nhưng hôm nay chỉ còn {left} "
                       "bước." if 0 < left < cost else
                       f"Hôm nay tài khoản đã dùng hết {AGENT_DAILY_STEPS} bước Peto Agent. Lượt mới bắt đầu lúc 0 giờ.")
            raise GatewayError(429, message, code="insufficient_quota", kind="insufficient_quota", retry=False)
    except GatewayError as err:
        return _error_response(err)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_pump(queue, owner=owner, day=day, cost=cost, model=model, effort=effort,
                                     parsed=parsed))
    try:
        try:
            first = await asyncio.wait_for(queue.get(), FIRST_EVENT_SECONDS)
        except TimeoutError:
            first = None
    except BaseException:
        task.cancel()
        raise
    if first is not None and first[0] == "error":
        await task
        return _error_response(first[1])
    writer = ResponseWriter(model.key)
    return StreamingResponse(_body(writer, queue, task, first), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


async def _body(writer: ResponseWriter, queue: asyncio.Queue, task: asyncio.Task, first) -> AsyncIterator[str]:
    try:
        for chunk in writer.created():
            yield chunk
        pending = first
        while True:
            if pending is None:
                try:
                    pending = await asyncio.wait_for(queue.get(), PING_SECONDS)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
            kind, value = pending
            pending = None
            if kind == "event":
                chunks = (writer.finish(list(value.output), value.usage) if value.kind == "done"
                          else writer.feed(value))
                for chunk in chunks:
                    yield chunk
            elif kind == "error":
                yield writer.failed(value)
                return
            else:
                return
    finally:
        if not task.done():
            task.cancel()
        with anyio.CancelScope(shield=True), suppress(BaseException):
            await task


async def _pump(queue: asyncio.Queue, *, owner: str, day: str, cost: int, model, effort: str, parsed: Parsed) -> None:
    """Chạy một lần gọi model trong task riêng; đưa sự kiện, rồi ("end", None) hoặc ("error", GatewayError), vào hàng.

    Hoàn bước khi lỗi xảy ra trước phản hồi đầu tiên, như /api/agent/step. Bị hủy (ứng dụng ngắt kết nối) thì cũng
    hoàn nếu chưa có gì, rồi ném lại CancelledError.
    """
    produced = False
    completed = False
    outcome = "cancelled"
    failure: GatewayError | None = None
    started = time.monotonic()
    first_at: float | None = None
    slug = model.slug or AGENT_MODEL
    try:
        async with admission.slot(f"agent:{owner}"):
            async with asyncio.timeout(AGENT_STEP_TIMEOUT_SECONDS):
                async for event in agent_step(instructions=parsed.instructions, input_items=parsed.items,
                                              tools=parsed.tools, effort=effort, model=model.key, web_search=False,
                                              max_output_tokens=parsed.max_output_tokens,
                                              tool_choice=parsed.tool_choice):
                    if event.kind == "search":
                        continue
                    if not produced:
                        first_at = time.monotonic()
                    produced = True
                    if event.kind == "done":
                        usage = dict(event.usage)
                        cost_ticks = usage.pop("cost_ticks", None)
                        with anyio.CancelScope(shield=True):
                            await db.add_agent_tokens(owner, day, usage.get("input_tokens", 0),
                                                      usage.get("output_tokens", 0))
                        usage_events.record(
                            "call", service=model.service, model=model.key, slug=slug, surface="agent",
                            purpose="agent", complete=True, elapsed_ms=round((time.monotonic() - started) * 1000),
                            input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                            cached_tokens=usage.get("cached_tokens"), cache_write_tokens=usage.get("cache_write_tokens"),
                            cost_ticks=cost_ticks,
                        )
                        completed = True
                        outcome = "complete"
                        await queue.put(("event", AgentEvent("done", output=event.output, usage=usage)))
                        break
                    await queue.put(("event", event))
        if not completed:
            outcome = "empty"
            failure = GatewayError(502, "Mô hình kết thúc mà không trả kết quả. Thử lại nhé.", code="server_error",
                                   kind="server_error", retry=not produced)
    except AdmissionDenied as denied:
        outcome = denied.reason
        failure = (GatewayError(429, "Peto Agent đang bận với nhiều người, thử lại sau chút nhé.",
                                code="rate_limit_exceeded", kind="rate_limit_error", retry=True)
                   if denied.reason == "queue_full" else
                   GatewayError(503, "Đợi lâu quá nên Peto bỏ lần gọi này. Thử lại nhé.", code="server_error",
                                kind="server_error", retry=True))
    except ProviderError as err:
        outcome = "provider_error"
        logger.warning("Cổng agent lỗi từ nhà cung cấp: %s", err)
        failure = _provider_failure(err)
    except TimeoutError:
        outcome = "timeout"
        failure = GatewayError(504, "Lần gọi này chạy quá lâu nên Peto dừng lại.", code="timeout",
                               kind="server_error", retry=False)
    except asyncio.CancelledError:
        raise
    except Exception:
        outcome = "internal_error"
        logger.exception("Lỗi không mong đợi ở cổng agent")
        failure = GatewayError(500, "Có lỗi ở phía máy chủ. Thử lại sau nhé.", code="server_error",
                               kind="server_error", retry=False)
    finally:
        if (failure is not None or outcome == "cancelled") and not produced:
            with anyio.CancelScope(shield=True):
                await db.refund_agent_step(owner, day, cost)
        elapsed = time.monotonic() - started
        first_ms = round((first_at - started) * 1000) if first_at is not None else None
        logger.info("agent_timing model=%s effort=%s mode=gateway first_text_ms=%s total_ms=%d complete=%s outcome=%s",
                    model.key, effort, first_ms, round(elapsed * 1000), completed, outcome)
        usage_events.record("turn", service=model.service, model=model.key, slug=slug, surface="agent",
                            purpose="agent", outcome=outcome, complete=completed, elapsed_ms=round(elapsed * 1000),
                            first_text_ms=first_ms)
    if failure is not None and failure.retry and produced:
        # Đã có phản hồi nên bước không được hoàn: không để pi-ai tự gửi lại lần gọi đã tính.
        failure.retry = False
    await queue.put(("error", failure) if failure is not None else ("end", None))
