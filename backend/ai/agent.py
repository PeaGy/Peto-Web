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

from config import AGENT_MODEL, AGENT_REASONING, AI_PROVIDER, XAI_API_BASE, XAI_MAX_OUTPUT_TOKENS

from .base import ProviderError

logger = logging.getLogger("peto_web.agent")


@dataclass(frozen=True)
class AgentEvent:
    kind: str  # "thinking" | "delta" | "done"
    text: str = ""
    output: tuple[dict, ...] = ()
    usage: dict = field(default_factory=dict)


async def agent_step(
    *, instructions: str, input_items: list[dict], tools: list[dict], effort: str = AGENT_REASONING
) -> AsyncIterator[AgentEvent]:
    if AI_PROVIDER == "mock":
        events = _mock_step(input_items)
    elif AI_PROVIDER == "xai":
        events = _xai_step(instructions, input_items, tools, effort)
    else:
        raise ProviderError("Nhà cung cấp AI hiện tại chưa hỗ trợ Peto Agent.")
    async for event in events:
        yield event


# --- xAI -----------------------------------------------------------------

_client = None
_auth = None


def _dump(item) -> dict:
    return item if isinstance(item, dict) else item.model_dump(mode="json", exclude_none=True)


async def _xai_step(instructions: str, items: list[dict], tools: list[dict], effort: str) -> AsyncIterator[AgentEvent]:
    # Import trễ như ai/__init__.py: chạy mock không cần SDK openai.
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError, RateLimitError

    from xai_auth import XaiAuth, XaiAuthError

    global _client, _auth
    if _client is None:
        _auth = XaiAuth()
        _client = AsyncOpenAI(api_key="pending", base_url=XAI_API_BASE)
    try:
        _client.api_key = await _auth.get_access_token()
    except XaiAuthError as err:
        raise ProviderError("Peto chưa được kết nối với dịch vụ AI. Người quản trị cần chạy lại lệnh đăng nhập.") from err

    stream = None
    try:
        stream = await _client.responses.create(
            model=AGENT_MODEL,
            instructions=instructions,
            input=items,
            tools=tools,
            max_output_tokens=XAI_MAX_OUTPUT_TOKENS,
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
                if getattr(response, "status", "completed") != "completed":
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
                raise ProviderError("Bước này chạm giới hạn độ dài của mô hình. Thử chia nhỏ yêu cầu nhé.")
            elif event_type in {"response.failed", "error"}:
                raise ProviderError("Mô hình gặp lỗi ở bước này. Thử lại nhé.")
        raise ProviderError("Kết nối tới AI bị ngắt trước khi xong bước này. Thử lại nhé.")
    except AuthenticationError as err:
        raise ProviderError("Kết nối AI của Peto đã hết hạn. Người quản trị cần đăng nhập lại.") from err
    except RateLimitError as err:
        raise ProviderError("Dịch vụ AI đang nhận nhiều yêu cầu quá. Đợi chút rồi thử lại nhé.") from err
    except APIConnectionError as err:
        raise ProviderError("Máy chủ Peto chưa kết nối được dịch vụ AI. Thử lại sau chút nhé.") from err
    except APIStatusError as err:
        logger.warning("xAI HTTP %s ở bước agent", err.status_code)
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


def _result(item: dict) -> dict:
    try:
        value = json.loads(item.get("output") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


async def _speak(text: str, calls: list[dict]) -> AsyncIterator[AgentEvent]:
    words = text.split(" ")
    for index, word in enumerate(words):
        await asyncio.sleep(_MOCK_DELAY)
        yield AgentEvent("delta", word if index == len(words) - 1 else word + " ")
    yield AgentEvent("done", output=(_message(text), *calls), usage={"input_tokens": 0, "output_tokens": 0})


async def _mock_step(items: list[dict]) -> AsyncIterator[AgentEvent]:
    last_user = max((index for index, item in enumerate(items) if item.get("role") == "user"), default=-1)
    task = _text_of(items[last_user]) if last_user >= 0 else ""
    if "__error__" in task:
        raise ProviderError("Nhà cung cấp AI đang lỗi (giả lập). Thử lại sau nhé.")
    results = [item for item in items[last_user + 1:] if item.get("type") == "function_call_output"]
    last = _result(results[-1]) if results else {}
    yield AgentEvent("thinking", "Đang xem bước tiếp theo…")

    if "__demo__" not in task:
        reply = ("Peto đang chạy bằng phản hồi giả nên chưa làm việc thật được. Gõ một yêu cầu có __demo__ để xem "
                 "thử một vòng đọc, sửa và chạy lệnh.")
        steps = _speak(reply, [])
    elif not results:
        steps = _speak("Để Peto xem README.md trước nha.",
                       [_call(0, "read_file", {"path": "README.md", "start_line": None, "end_line": None})])
    elif len(results) == 1:
        first = next((line for line in str(last.get("content", "")).splitlines() if line.strip()), "")
        if last.get("error") or not first:
            steps = _speak(f"Peto chưa đọc được README.md: {last.get('error') or 'tệp trống'}.", [])
        else:
            steps = _speak("Thêm một dấu vết nhỏ vào dòng đầu nhé.", [_call(1, "edit_file", {
                "path": "README.md", "old_text": first, "new_text": f"{first} (Peto đã ghé qua)"})])
    elif len(results) == 2:
        if last.get("error") or not last.get("ok"):
            steps = _speak(f"Chưa sửa được README.md nên Peto dừng ở đây: {last.get('error') or 'không rõ lý do'}.", [])
        else:
            steps = _speak("Giờ chạy thử một lệnh kiểm tra.", [_call(2, "run_command", {
                "command": "python -c \"print('ok')\"", "timeout_seconds": None})])
    elif last.get("exit_code") == 0:
        steps = _speak("Xong rồi nè: đã thêm một câu vào dòng đầu README.md, lệnh kiểm tra chạy ổn.", [])
    else:
        reason = last.get("error") or f"mã thoát {last.get('exit_code')}"
        steps = _speak(f"Đã sửa README.md nhưng lệnh kiểm tra chưa qua: {reason}.", [])
    async for event in steps:
        yield event
