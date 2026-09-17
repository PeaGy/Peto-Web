"""Một bước gọi mô hình cho Peto Agent.

CLI trên máy người dùng giữ toàn bộ hội thoại và chạy công cụ. Mỗi lần gọi máy chủ chỉ là một bước: gửi input hiện
có, nhận suy nghĩ tóm tắt, chữ đang viết và danh sách item cuối (tin nhắn, lệnh gọi công cụ, suy luận đã mã hóa) để
CLI nối vào lần sau. Máy chủ không lưu hội thoại (``store=False``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anyio

from config import (AGENT_MODEL, AGENT_REASONING, AI_PROVIDER, OPENAI_API_KEY, OPENAI_MAX_OUTPUT_TOKENS, XAI_API_BASE,
                    XAI_MAX_OUTPUT_TOKENS)

from .base import ProviderError

logger = logging.getLogger("peto_web.agent")


@dataclass(frozen=True)
class AgentEvent:
    kind: str  # "thinking" | "delta" | "done"
    text: str = ""
    output: tuple[dict, ...] = ()
    usage: dict = field(default_factory=dict)


async def agent_step(
    *, instructions: str, input_items: list[dict], tools: list[dict], effort: str = AGENT_REASONING,
    model: str = "peto",
) -> AsyncIterator[AgentEvent]:
    """``model`` đã được ``ai_models.resolve`` kiểm quyền: Peto đi qua xAI, các model khác qua OpenAI."""
    if AI_PROVIDER == "mock":
        events = _mock_step(input_items)
    elif AI_PROVIDER == "xai":
        events = (_xai_step(instructions, input_items, tools, effort) if model == "peto"
                  else _openai_step(instructions, input_items, tools, effort, model))
    else:
        raise ProviderError("Nhà cung cấp AI hiện tại chưa hỗ trợ Peto Agent.")
    async for event in events:
        yield event


# --- xAI -----------------------------------------------------------------

_client = None
_auth = None
_openai_client = None


def _dump(item) -> dict:
    return item if isinstance(item, dict) else item.model_dump(mode="json", exclude_none=True)


# Lý do lỗi xAI trả về chỉ ghi vào log máy chủ, để chủ web biết vì sao một bước hỏng (hội thoại quá dài, item bị từ
# chối, khai báo công cụ sai...). Người dùng vẫn chỉ thấy câu báo tiếng Việt.
MAX_LOGGED_REASON = 500


def _clip(value) -> str:
    return " ".join(str(value or "").split())[:MAX_LOGGED_REASON] or "không rõ lý do"


def _describe(error) -> str:
    return _clip(f"{getattr(error, 'code', '') or ''} {getattr(error, 'message', '') or ''}")


async def _xai_step(instructions: str, items: list[dict], tools: list[dict], effort: str) -> AsyncIterator[AgentEvent]:
    # Import trễ như ai/__init__.py: chạy mock không cần SDK openai.
    from openai import AsyncOpenAI

    from xai_auth import XaiAuth, XaiAuthError

    global _client, _auth
    if _client is None:
        _auth = XaiAuth()
        _client = AsyncOpenAI(api_key="pending", base_url=XAI_API_BASE)
    try:
        _client.api_key = await _auth.get_access_token()
    except XaiAuthError as err:
        raise ProviderError("Peto chưa được kết nối với dịch vụ AI. Người quản trị cần chạy lại lệnh đăng nhập.") from err
    async for event in _responses_step(
        _client, "xAI", AGENT_MODEL, XAI_MAX_OUTPUT_TOKENS, instructions, items, tools, effort,
        auth_message="Kết nối AI của Peto đã hết hạn. Người quản trị cần đăng nhập lại.",
        rate_message="Dịch vụ AI đang nhận nhiều yêu cầu quá. Đợi chút rồi thử lại nhé.",
    ):
        yield event


async def _openai_step(instructions: str, items: list[dict], tools: list[dict], effort: str,
                       model: str) -> AsyncIterator[AgentEvent]:
    from openai import AsyncOpenAI

    from ai_models import MODELS

    global _openai_client
    if not OPENAI_API_KEY:
        raise ProviderError("Máy chủ Peto chưa có khóa OpenAI. Gõ /model peto để làm tiếp nhé.")
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    info = MODELS[model]
    async for event in _responses_step(
        _openai_client, "OpenAI", info.slug, OPENAI_MAX_OUTPUT_TOKENS, instructions, items, tools, effort,
        auth_message="Khóa OpenAI của máy chủ Peto không dùng được. Gõ /model peto để làm tiếp nhé.",
        rate_message=f"{info.label} đang bị OpenAI giới hạn lượt hoặc đã hết hạn mức. Gõ /model peto để làm tiếp, "
                     "hoặc thử lại sau nhé.",
    ):
        yield event


async def _responses_step(client, service: str, model: str, max_output_tokens: int, instructions: str,
                          items: list[dict], tools: list[dict], effort: str, *, auth_message: str,
                          rate_message: str) -> AsyncIterator[AgentEvent]:
    """Một lần gọi Responses API. xAI và OpenAI chỉ khác client, tên model và lời báo lỗi."""
    from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

    stream = None
    try:
        stream = await client.responses.create(
            model=model,
            instructions=instructions,
            input=items,
            tools=tools,
            max_output_tokens=max_output_tokens,
            reasoning={"effort": effort},
            include=["reasoning.encrypted_content"],
            store=False,
            stream=True,
        )
        async for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.reasoning_summary_text.delta":
                if delta := getattr(event, "delta", ""):
                    yield AgentEvent("thinking", delta)
            elif event_type == "response.output_text.delta":
                if delta := getattr(event, "delta", ""):
                    yield AgentEvent("delta", delta)
            elif event_type == "response.completed":
                response = event.response
                status = getattr(response, "status", "completed")
                if status != "completed":
                    logger.warning("%s kết thúc bước agent với trạng thái %s", service, _clip(status))
                    raise ProviderError("Mô hình chưa làm xong bước này. Thử lại nhé.")
                usage = getattr(response, "usage", None)
                yield AgentEvent(
                    "done",
                    output=tuple(_dump(item) for item in (response.output or [])),
                    usage={
                        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                    },
                )
                return
            elif event_type == "response.incomplete":
                details = getattr(getattr(event, "response", None), "incomplete_details", None)
                logger.warning("%s dừng bước agent giữa chừng: %s", service, _clip(getattr(details, "reason", "")))
                raise ProviderError("Bước này chạm giới hạn độ dài của mô hình. Thử chia nhỏ yêu cầu nhé.")
            elif event_type in {"response.failed", "error"}:
                error = getattr(getattr(event, "response", None), "error", None) if event_type == "response.failed" else event
                logger.warning("%s báo lỗi trong bước agent: %s", service, _describe(error))
                raise ProviderError("Mô hình gặp lỗi ở bước này. Thử lại nhé.")
        raise ProviderError("Kết nối tới AI bị ngắt trước khi xong bước này. Thử lại nhé.")
    except AuthenticationError as err:
        # Không ghi lời báo: lỗi xác thực có thể kèm một phần khóa.
        logger.warning("%s từ chối xác thực ở bước agent (HTTP %s)", service, err.status_code)
        raise ProviderError(auth_message) from err
    except RateLimitError as err:
        logger.warning("%s giới hạn lượt ở bước agent: %s", service, _clip(err.message))
        raise ProviderError(rate_message) from err
    except APIConnectionError as err:
        logger.warning("Không kết nối được %s ở bước agent: %s", service, _clip(err.message))
        raise ProviderError("Máy chủ Peto chưa kết nối được dịch vụ AI. Thử lại sau chút nhé.") from err
    except APIStatusError as err:
        logger.warning("%s trả lỗi HTTP %s ở bước agent: %s", service, err.status_code, _clip(err.message))
        if err.status_code == 400:
            raise ProviderError("Dịch vụ AI không nhận nội dung bước này. Gõ /moi để bắt đầu hội thoại mới nhé.") from err
        raise ProviderError("Peto gặp lỗi kết nối với dịch vụ AI. Thử lại sau nhé.") from err
    finally:
        if stream is not None:
            with anyio.CancelScope(shield=True):
                await stream.close()


# --- Giả lập -------------------------------------------------------------
# Không gọi mạng. Yêu cầu có "__demo__" chạy một vòng đọc README.md → sửa dòng đầu → chạy lệnh → tóm tắt, dựa trên
# kết quả công cụ CLI gửi lên; "__error__" giả lập lỗi nhà cung cấp.

_MOCK_DELAY = 0.01


def _message(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def _call(stage: int, name: str, arguments: dict) -> dict:
    return {
        "type": "function_call",
        "call_id": f"call_demo_{stage}",
        "name": name,
        "arguments": json.dumps(arguments, ensure_ascii=False),
    }


def _text_of(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def _images_of(item: dict) -> list[str]:
    """Mô tả ngắn các ảnh trong một tin, ví dụ "PNG 240 KB", để phản hồi giả xác nhận đã nhận ảnh."""
    content = item.get("content")
    found = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict) and part.get("type") == "input_image":
            header, _, encoded = str(part.get("image_url", "")).partition(",")
            kind = header.removeprefix("data:image/").removesuffix(";base64").upper()
            found.append(f"{kind} {max(1, round(len(encoded) * 3 / 4 / 1024))} KB")
    return found


def _result(item: dict) -> dict:
    try:
        value = json.loads(item.get("output") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


async def _speak(text: str, calls: list[dict], items: list[dict]) -> AsyncIterator[AgentEvent]:
    words = text.split(" ")
    for index, word in enumerate(words):
        await asyncio.sleep(_MOCK_DELAY)
        yield AgentEvent("delta", word if index == len(words) - 1 else word + " ")
    # Ước lượng thô khoảng 4 ký tự một token, để dòng token của CLI có số khi chạy bằng phản hồi giả.
    usage = {"input_tokens": len(json.dumps(items, ensure_ascii=False)) // 4, "output_tokens": len(text) // 4 + 1}
    yield AgentEvent("done", output=(_message(text), *calls), usage=usage)


async def _mock_step(items: list[dict]) -> AsyncIterator[AgentEvent]:
    last_user = max((index for index, item in enumerate(items) if item.get("role") == "user"), default=-1)
    task = _text_of(items[last_user]) if last_user >= 0 else ""
    if "__error__" in task:
        raise ProviderError("Nhà cung cấp AI đang lỗi (giả lập). Thử lại sau nhé.")
    results = [item for item in items[last_user + 1:] if item.get("type") == "function_call_output"]
    last = _result(results[-1]) if results else {}
    yield AgentEvent("thinking", "Đang xem bước tiếp theo…")

    def speak(text: str, calls: list[dict]) -> AsyncIterator[AgentEvent]:
        return _speak(text, calls, items)

    if "__demo__" not in task:
        reply = ("Peto đang chạy bằng phản hồi giả nên chưa làm việc thật được. Gõ một yêu cầu có __demo__ để xem "
                 "thử một vòng đọc, sửa và chạy lệnh.")
        if images := _images_of(items[last_user]):
            reply = f"Peto đã nhận {len(images)} ảnh ({', '.join(images)}) nhưng phản hồi giả không xem được ảnh."
        steps = speak(reply, [])
    elif not results:
        steps = speak("Để Peto xem README.md trước nha.",
                       [_call(0, "read_file", {"path": "README.md", "start_line": None, "end_line": None})])
    elif len(results) == 1:
        first = next((line for line in str(last.get("content", "")).splitlines() if line.strip()), "")
        if last.get("error") or not first:
            steps = speak(f"Peto chưa đọc được README.md: {last.get('error') or 'tệp trống'}.", [])
        else:
            steps = speak("Thêm một dấu vết nhỏ vào dòng đầu nhé.", [_call(1, "edit_file", {
                "path": "README.md", "old_text": first, "new_text": f"{first} (Peto đã ghé qua)"})])
    elif len(results) == 2:
        if last.get("error") or not last.get("ok"):
            steps = speak(f"Chưa sửa được README.md nên Peto dừng ở đây: {last.get('error') or 'không rõ lý do'}.", [])
        else:
            steps = speak("Giờ chạy thử một lệnh kiểm tra.", [_call(2, "run_command", {
                "command": "python -c \"print('ok')\"", "timeout_seconds": None})])
    elif last.get("exit_code") == 0:
        steps = speak("Xong rồi nè: đã thêm một câu vào dòng đầu README.md, lệnh kiểm tra chạy ổn.", [])
    else:
        reason = last.get("error") or f"mã thoát {last.get('exit_code')}"
        steps = speak(f"Đã sửa README.md nhưng lệnh kiểm tra chưa qua: {reason}.", [])
    async for event in steps:
        yield event
