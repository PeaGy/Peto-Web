"""Cổng kiểu OpenAI Chat Completions cho bộ não AIRI chạy trong trình duyệt (``/api/companion/v1``).

Bản AIRI stage-web phục vụ ở ``/airi/`` tự dựng prompt, phiên, thẻ nhân vật và tự chạy công cụ ngay trong trình duyệt;
máy chủ chỉ là điểm gọi model. Cổng này nhận đúng hình dạng Chat Completions mà ``@xsai/stream-text`` của AIRI gửi.

- Xác thực bằng cookie phiên Peto như ``POST /api/chat``: chưa đăng nhập là 401 theo dạng lỗi của OpenAI. Không có mã
  thiết bị, không tính hạn mức bước của Peto Agent, không có danh mục model của Agent: luôn là model Peto.
- Cả lượt chạy trong ``admission.slot(owner)`` của Chat. Lượt tiếp nối (tin cuối là kết quả công cụ do trình duyệt
  vừa chạy) bỏ qua thời gian chờ giữa hai tin, vì nó là phần sau của cùng một câu trả lời.
- Gọi model qua ``ai.agent.agent_step`` (đường Responses có công cụ do nơi gọi khai báo, như Peto Agent), không tra web.
  Model gọi công cụ thì cổng trả ``tool_calls`` với ``finish_reason: "tool_calls"``; trình duyệt chạy rồi gửi lại.
- System prompt là của AIRI gửi lên; máy chủ luôn nối thêm ``COMPANION_CARD_RULE`` (luật cố định dưới 18 tuổi).
- Lỗi trước byte đầu tiên là mã HTTP thật với thân ``{"error": {...}}``; lỗi giữa chừng là một dòng ``data:
  {"error": ...}`` mà xsai báo thành lỗi. Model im lâu thì gửi dòng chú thích ``: ping`` để Cloudflare không cắt.
- Trình duyệt ngắt kết nối (nút dừng của AIRI) thì lần gọi model bị hủy và suất chạy được trả ngay.
- Không lưu gì vào database, không ghi nội dung tin vào log. Mỗi lượt ghi số đo vào ``usage_events`` với
  ``surface="airi"`` để trang Quản trị tách riêng.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import replace

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ai import models as ai_models
from ai.agent import AgentEvent, agent_step
from ai.base import ProviderError
from core import usage_events
from core.config import AGENT_MODEL, RESPONSE_TIMEOUTS, SESSION_COOKIE, TURN_TIMEOUT_SECONDS
from core.rate_limit import AdmissionDenied, admission
from features.accounts.auth import session_owner
from features.agent.api import _read_body
from features.agent.gateway_images import prepare as prepare_images
from features.companion import airi_request
from features.companion.airi_request import Parsed, RequestError

logger = logging.getLogger("peto_web.airi")
router = APIRouter(prefix="/api/companion/v1")

MODEL_ID = "peto"
# Companion cần trả lời nhanh: mức suy nghĩ thấp như bản thử, thời gian chờ theo mức đó như Chat.
EFFORT = "low"
SURFACE = "airi"
# Như cổng Peto Agent: chờ sự kiện đầu tiên tối đa chừng này trước khi gửi header, để lỗi ngay (hết suất, khóa hỏng,
# giới hạn lượt) thành mã HTTP thật; quá lâu thì mở stream luôn vì Cloudflare cắt kết nối chưa có header sau ~100 giây.
FIRST_EVENT_SECONDS = 15.0
# Dòng chú thích SSE giữ kết nối qua Cloudflare khi model im lâu; xsai bỏ qua dòng bắt đầu bằng ":".
PING_SECONDS = 15.0
# Trước khi gửi header, cứ ngần này giây hỏi xem trình duyệt còn kết nối không (nút dừng của AIRI lúc model chưa nói gì).
DISCONNECT_POLL_SECONDS = 0.5


class GatewayError(Exception):
    def __init__(self, status: int, message: str, *, kind: str = "server_error", code: str | None = None,
                 retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.kind = kind
        self.code = code
        self.retry_after = retry_after

    def body(self) -> dict:
        return {"error": {"message": self.message, "type": self.kind, "code": self.code or self.status, "param": None}}


def _error_response(err: GatewayError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if err.retry_after is not None:
        headers["Retry-After"] = str(max(1, round(err.retry_after)))
    return JSONResponse(err.body(), status_code=err.status, headers=headers)


def _owner(request: Request) -> str:
    owner = session_owner(request.cookies.get(SESSION_COOKIE))
    if not owner:
        raise GatewayError(401, "Chưa đăng nhập Peto. Đăng nhập rồi mở lại trang này nhé.", kind="authentication_error",
                           code="invalid_api_key")
    return owner


def _failure(error: BaseException) -> tuple[str, GatewayError]:
    """Kết quả ghi số đo và lỗi trả cho trình duyệt."""
    if isinstance(error, AdmissionDenied):
        if error.reason == "queue_timeout":
            return error.reason, GatewayError(503, error.message, code="queue_timeout")
        return error.reason, GatewayError(429, error.message, kind="rate_limit_error", code=error.reason,
                                          retry_after=error.retry_after if error.reason == "cooldown" else None)
    if isinstance(error, ProviderError):
        logger.warning("Provider lỗi (AIRI): %s", error)
        if error.code == "context_overflow":
            return "context_overflow", GatewayError(400, str(error), kind="invalid_request_error",
                                                    code="context_length_exceeded")
        return "provider_error", GatewayError(503 if error.retryable else 502, str(error), code="provider_error")
    if isinstance(error, TimeoutError):
        return "timeout", GatewayError(504, "Peto chờ quá lâu mà dịch vụ AI không gửi gì thêm nên dừng lượt này.",
                                       code="timeout")
    logger.error("Lỗi không mong đợi ở cổng AIRI", exc_info=error)
    return "internal_error", GatewayError(500, "Có lỗi ở phía máy chủ. Thử lại sau nha.", code="server_error")


def _chat_usage(usage: dict) -> dict:
    """Usage của Peto (dạng Responses) thành usage của Chat Completions."""
    prompt = int(usage.get("input_tokens") or 0)
    completion = int(usage.get("output_tokens") or 0)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
            "prompt_tokens_details": {"cached_tokens": int(usage.get("cached_tokens") or 0)}}


class ChunkWriter:
    """Dựng các chunk ``chat.completion.chunk`` từ sự kiện của ``agent_step``.

    Chữ đi ngay khi tới. Lời gọi công cụ mở ngay khi model bắt đầu viết (mã và tên), nhưng đối số chỉ gửi một lần khi
    xong, lấy từ item cuối: các đoạn đối số giữa chừng có thể khác cách viết JSON của bản cuối, mà xsai nối mọi đoạn
    lại thành đối số, không thay được.
    """

    def __init__(self) -> None:
        self.id = "chatcmpl-" + uuid.uuid4().hex
        self.created = int(time.time())
        self.calls: dict[str, int] = {}  # call_id -> index trong tool_calls
        self.text_chars = 0
        self.started = False

    def _chunk(self, delta: dict, finish: str | None = None) -> str:
        body = {"id": self.id, "object": "chat.completion.chunk", "created": self.created, "model": MODEL_ID,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return "data: " + json.dumps(body, ensure_ascii=False) + "\n\n"

    def _role(self) -> list[str]:
        if self.started:
            return []
        self.started = True
        return [self._chunk({"role": "assistant", "content": ""})]

    def _open_call(self, call_id: str, name: str) -> list[str]:
        if call_id in self.calls:
            return []
        index = self.calls[call_id] = len(self.calls)
        return [self._chunk({"tool_calls": [{"index": index, "id": call_id, "type": "function",
                                             "function": {"name": name, "arguments": ""}}]})]

    def feed(self, event: AgentEvent) -> list[str]:
        if event.kind == "delta" and event.text:
            self.text_chars += len(event.text)
            return [*self._role(), self._chunk({"content": event.text})]
        call_id = event.item.get("call_id")
        if event.kind == "tool_start" and isinstance(call_id, str) and call_id:
            return [*self._role(), *self._open_call(call_id, str(event.item.get("name") or ""))]
        return []

    def finish(self, output: tuple[dict, ...], usage: dict | None) -> list[str]:
        chunks = self._role()
        if not self.text_chars:
            # Dịch vụ chỉ trả chữ ở kết quả cuối (không có đoạn nào trước đó): gửi nguyên chữ một lần.
            text = "".join(part.get("text", "") for item in output if item.get("type") == "message"
                           for part in (item.get("content") or []) if isinstance(part, dict))
            if text:
                self.text_chars = len(text)
                chunks.append(self._chunk({"content": text}))
        final_calls = [item for item in output if item.get("type") == "function_call" and item.get("call_id")]
        for item in final_calls:
            chunks += self._open_call(item["call_id"], str(item.get("name") or ""))
            chunks.append(self._chunk({"tool_calls": [{"index": self.calls[item["call_id"]], "function": {
                "arguments": str(item.get("arguments") or "")}}]}))
        missing = set(self.calls) - {item["call_id"] for item in final_calls}
        if missing:
            logger.warning("Cổng AIRI: %d lời gọi công cụ đã mở không có trong kết quả cuối", len(missing))
        chunks.append(self._chunk({}, "tool_calls" if final_calls else "stop"))
        if usage is not None:
            body = {"id": self.id, "object": "chat.completion.chunk", "created": self.created, "model": MODEL_ID,
                    "choices": [], "usage": _chat_usage(usage)}
            chunks.append("data: " + json.dumps(body, ensure_ascii=False) + "\n\n")
        chunks.append("data: [DONE]\n\n")
        return chunks


async def _pump(queue: asyncio.Queue, owner: str, parsed: Parsed) -> None:
    """Chạy một lần gọi model trong task riêng; đưa ("event", AgentEvent) rồi ("end", None) hoặc ("error",
    GatewayError) vào hàng. Bị hủy (trình duyệt ngắt kết nối) thì ném lại CancelledError sau khi ghi số đo."""
    started = time.monotonic()
    first_at: float | None = None
    outcome = "cancelled"
    completed = False
    failure: GatewayError | None = None
    try:
        async with admission.slot(owner, cooldown=not parsed.continuation):
            loop = asyncio.get_running_loop()
            idle = RESPONSE_TIMEOUTS.get(EFFORT, 180.0)
            hard = loop.time() + TURN_TIMEOUT_SECONDS
            async with asyncio.timeout_at(min(loop.time() + idle, hard)) as limit:
                events = agent_step(instructions=parsed.instructions, input_items=parsed.items, tools=parsed.tools,
                                    effort=EFFORT, model=MODEL_ID, web_search=False,
                                    max_output_tokens=parsed.max_output_tokens, tool_choice=parsed.tool_choice)
                try:
                    async for event in events:
                        # Mọi sự kiện, kể cả suy nghĩ và "pulse", cho biết dịch vụ AI còn sống.
                        limit.reschedule(min(loop.time() + idle, hard))
                        if event.kind == "done":
                            usage = dict(event.usage)
                            usage_events.record(
                                "call", service="xai", model=MODEL_ID, slug=AGENT_MODEL, surface=SURFACE,
                                purpose=SURFACE, effort=EFFORT, complete=True,
                                elapsed_ms=round((time.monotonic() - started) * 1000),
                                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                                cached_tokens=usage.get("cached_tokens"), cost_ticks=usage.pop("cost_ticks", None))
                            completed = True
                            outcome = "complete"
                            await queue.put(("event", AgentEvent("done", output=event.output, usage=usage)))
                            break
                        if event.kind in {"delta", "tool_start"}:
                            if first_at is None:
                                first_at = time.monotonic()
                            await queue.put(("event", event))
                finally:
                    with anyio.CancelScope(shield=True), suppress(Exception):
                        await events.aclose()
        if not completed:
            outcome = "empty"
            failure = GatewayError(502, "Mô hình kết thúc mà không trả kết quả. Thử lại nhé.", code="provider_error")
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - mọi lỗi đều thành lời báo cho trình duyệt
        outcome, failure = _failure(error)
    finally:
        elapsed = round((time.monotonic() - started) * 1000)
        first_ms = round((first_at - started) * 1000) if first_at is not None else None
        # Chỉ số đo, không nội dung tin.
        logger.info("airi_turn outcome=%s continuation=%s tools=%d images=%d items=%d first_text_ms=%s total_ms=%d",
                    outcome, parsed.continuation, len(parsed.tools), parsed.images, len(parsed.items), first_ms, elapsed)
        usage_events.record("turn", service="xai", model=MODEL_ID, slug=AGENT_MODEL, surface=SURFACE, purpose=SURFACE,
                            effort=EFFORT, outcome=outcome, complete=completed, elapsed_ms=elapsed,
                            first_text_ms=first_ms)
    await queue.put(("error", failure) if failure is not None else ("end", None))


async def _stream(writer: ChunkWriter, queue: asyncio.Queue, task: asyncio.Task, first,
                  include_usage: bool) -> AsyncIterator[str]:
    try:
        pending = first
        for chunk in writer._role():
            yield chunk
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
                chunks = (writer.finish(value.output, value.usage if include_usage else None) if value.kind == "done"
                          else writer.feed(value))
                for chunk in chunks:
                    yield chunk
            elif kind == "error":
                yield "data: " + json.dumps(value.body(), ensure_ascii=False) + "\n\n"
                return
            else:
                return
    finally:
        # Trình duyệt ngắt (nút dừng của AIRI) hay lượt xong: hủy lần gọi model nếu còn chạy, chờ nó trả suất chạy.
        if not task.done():
            task.cancel()
        with anyio.CancelScope(shield=True), suppress(BaseException):
            await task


async def _collect(queue: asyncio.Queue, task: asyncio.Task, first) -> JSONResponse:
    """``stream: false``: gom cả lượt thành một ``chat.completion``."""
    text: list[str] = []
    output: tuple[dict, ...] = ()
    usage: dict = {}
    try:
        pending = first
        while True:
            kind, value = pending if pending is not None else await queue.get()
            pending = None
            if kind == "error":
                return _error_response(value)
            if kind == "end":
                break
            if value.kind == "done":
                output, usage = value.output, value.usage
                continue
            if value.kind == "delta":
                text.append(value.text)
    finally:
        if not task.done():
            task.cancel()
        with anyio.CancelScope(shield=True), suppress(BaseException):
            await task
    content = "".join(text) or "".join(part.get("text", "") for item in output if item.get("type") == "message"
                                       for part in (item.get("content") or []) if isinstance(part, dict))
    calls = [{"id": item["call_id"], "type": "function", "function": {"name": item.get("name") or "",
                                                                       "arguments": str(item.get("arguments") or "")}}
             for item in output if item.get("type") == "function_call" and item.get("call_id")]
    message = {"role": "assistant", "content": content or None if calls else content,
               **({"tool_calls": calls} if calls else {})}
    writer = ChunkWriter()
    return JSONResponse({"id": writer.id, "object": "chat.completion", "created": writer.created, "model": MODEL_ID,
                         "choices": [{"index": 0, "message": message,
                                      "finish_reason": "tool_calls" if calls else "stop"}],
                         "usage": _chat_usage(usage)}, headers={"Cache-Control": "no-store"})


async def _first_event(request: Request, queue: asyncio.Queue):
    """Sự kiện đầu tiên, None nếu quá ``FIRST_EVENT_SECONDS`` (mở stream luôn), hoặc "disconnected" nếu trình duyệt đã
    ngắt trong lúc chờ: khi chưa gửi header, Starlette chưa theo dõi việc ngắt kết nối nên cổng tự hỏi định kỳ."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + FIRST_EVENT_SECONDS
    while (left := deadline - loop.time()) > 0:
        try:
            return await asyncio.wait_for(queue.get(), min(left, DISCONNECT_POLL_SECONDS))
        except TimeoutError:
            if await request.is_disconnected():
                return "disconnected"
    return None


@router.get("/models")
async def list_models(request: Request):
    try:
        _owner(request)
    except GatewayError as err:
        return _error_response(err)
    return JSONResponse({"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0,
                                                     "owned_by": "peto",
                                                     "display_name": ai_models.MODELS[MODEL_ID].label}]},
                        headers={"Cache-Control": "no-store"})


@router.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        owner = _owner(request)
        try:
            raw = await _read_body(request, airi_request.MAX_REQUEST_BYTES, airi_request.TOO_LARGE)
        except HTTPException as err:
            raise GatewayError(err.status_code, str(err.detail), kind="invalid_request_error") from None
        try:
            parsed = airi_request.parse(raw)
        except RequestError as err:
            raise GatewayError(err.status, err.message, kind="invalid_request_error", code=err.code) from None
        # Như Peto Agent: ảnh trong kết quả công cụ thành một tin user ngay sau; xAI chỉ nhận PNG/JPEG nên đổi WebP/GIF.
        items = await anyio.to_thread.run_sync(prepare_images, parsed.items, "xai")
        parsed = replace(parsed, items=items)
    except GatewayError as err:
        return _error_response(err)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_pump(queue, owner, parsed))
    try:
        first = await _first_event(request, queue)
    except BaseException:
        task.cancel()
        raise
    if first == "disconnected":
        # Trình duyệt bỏ yêu cầu trước khi có gì để gửi: hủy lần gọi model, trả suất chạy ngay.
        task.cancel()
        with anyio.CancelScope(shield=True), suppress(BaseException):
            await task
        return Response(status_code=499)
    if first is not None and first[0] == "error":
        with suppress(BaseException):
            await task
        return _error_response(first[1])
    if not parsed.stream:
        return await _collect(queue, task, first)
    return StreamingResponse(_stream(ChunkWriter(), queue, task, first, parsed.include_usage),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
