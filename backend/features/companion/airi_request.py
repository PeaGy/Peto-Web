"""Đọc yêu cầu Chat Completions của bộ não AIRI và đổi thành input kiểu Responses cho ``ai.agent.agent_step``.

AIRI (``@xsai/stream-text``) gửi cả hội thoại mỗi lượt: tin system (thẻ nhân vật, mô-đun), tin user (chữ, có thể kèm
ảnh), tin assistant (chữ và ``tool_calls``) và tin ``role: "tool"`` mang kết quả công cụ mà trình duyệt đã chạy. Máy
chủ không chạy công cụ nào: chỉ chuyển khai báo công cụ cho model và trả lời gọi công cụ về trình duyệt.

Giới hạn ảnh lấy đúng của cổng Peto Agent bản desktop (``features/agent/gateway.py``: 50 ảnh, thân yêu cầu 32 MB) và
kiểm từng ảnh bằng ``_check_image`` của Peto Agent (data URL PNG/JPEG/GIF/WebP, tối đa 3 MB, đúng loại thật). Ảnh là
địa chỉ web thì từ chối: máy chủ không tải gì theo lệnh của trình duyệt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from fastapi import HTTPException

from features.agent import gateway as agent_gateway
from features.agent.api import _check_image
from prompts import COMPANION_CARD_RULE

# Trần đầu vào chữ của một lượt, chỉ chặn yêu cầu bất thường: AIRI gửi cả lịch sử cùng system prompt dài mỗi lượt, và
# mỗi vòng công cụ thêm hai tin. Giới hạn thật là trần 32 MB của thân yêu cầu và khung ngữ cảnh của model (vượt thì
# trình duyệt nhận HTTP 400 context_length_exceeded).
MAX_MESSAGES = 2_000
MAX_TOTAL_CHARS = 1_000_000
# Ảnh và thân yêu cầu: như cổng Peto Agent bản desktop.
MAX_IMAGES = agent_gateway.MAX_IMAGES
MAX_REQUEST_BYTES = agent_gateway.MAX_REQUEST_BYTES
TOO_LARGE = "Yêu cầu quá 32 MB. Hãy bắt đầu đoạn chat mới hoặc gửi ít ảnh hơn."
# Công cụ do trình duyệt khai báo: số lượng như cổng Peto Agent; tên theo quy tắc của OpenAI; kích thước khai báo có
# trần để một yêu cầu không nhồi cả chục MB schema vào prompt.
MAX_TOOLS = agent_gateway.MAX_TOOLS
TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_TOOL_SCHEMA_BYTES = 32 * 1024
MAX_TOOLS_TOTAL_BYTES = 256 * 1024
TOOL_CHOICES = {"auto", "none", "required"}
# Đầu khối ngữ cảnh chạy mà AIRI nối vào tin người dùng mới nhất (xem ``split_context``).
CONTEXT_MARK = "\n[Context]\n- "
REMOTE_IMAGE = "Peto chỉ nhận ảnh gửi kèm dạng data URL (PNG, JPEG, GIF hoặc WebP), không tải ảnh từ địa chỉ web."


class RequestError(Exception):
    """Yêu cầu sai: trả về HTTP ``status`` với lời báo tiếng Việt theo dạng lỗi của OpenAI."""

    def __init__(self, message: str, status: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Parsed:
    instructions: str
    items: list[dict]
    tools: list[dict]
    tool_choice: str | dict | None
    max_output_tokens: int | None
    stream: bool
    include_usage: bool
    # Tin cuối là kết quả công cụ: lượt tiếp nối của cùng một câu trả lời, không phải tin mới của người dùng.
    continuation: bool
    images: int


def _text_parts(content: object, allowed: set[str], what: str) -> str:
    """Chữ của một tin chỉ được có chữ (system, assistant): chuỗi, hoặc mảng phần ``text``/``refusal``."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise RequestError(f"Nội dung {what} không đúng định dạng.")
    texts = []
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind not in allowed:
            raise RequestError(f"{what[:1].upper()}{what[1:]} chỉ được có chữ.")
        value = part.get("text" if kind != "refusal" else "refusal")
        if not isinstance(value, str):
            raise RequestError(f"Nội dung {what} không đúng định dạng.")
        texts.append(value)
    return "".join(texts)


def _image(part: dict) -> dict:
    """Phần ``image_url`` của Chat Completions thành ``input_image`` của Responses, sau khi kiểm như Peto Agent."""
    value = part.get("image_url")
    url = value.get("url") if isinstance(value, dict) else value
    detail = value.get("detail") if isinstance(value, dict) else None
    if isinstance(url, str) and url.lower().startswith(("http://", "https://")):
        raise RequestError(REMOTE_IMAGE)
    converted = {"type": "input_image", "image_url": url, **({"detail": detail} if detail is not None else {})}
    try:
        _check_image(converted)
    except HTTPException as err:
        raise RequestError(str(err.detail), err.status_code) from None
    return converted


def _rich_parts(content: object, what: str) -> tuple[str | list[dict], int, int]:
    """Nội dung tin user hoặc kết quả công cụ: chữ, hoặc mảng phần chữ và ảnh. Trả (nội dung Responses, số ký tự,
    số ảnh)."""
    if isinstance(content, str):
        return content, len(content), 0
    if not isinstance(content, list):
        raise RequestError(f"Nội dung {what} không đúng định dạng.")
    parts: list[dict] = []
    chars = images = 0
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind in {"text", "input_text"} and isinstance(part.get("text"), str):
            parts.append({"type": "input_text", "text": part["text"]})
            chars += len(part["text"])
        elif kind == "image_url":
            parts.append(_image(part))
            images += 1
        elif kind in {"input_audio", "file"}:
            raise RequestError("Peto chưa nhận âm thanh hay tệp gửi kèm qua cổng này; chỉ nhận chữ và ảnh.")
        else:
            raise RequestError(f"Nội dung {what} chỉ được có chữ và ảnh.")
    return parts, chars, images


def split_context(content: str | list[dict]) -> tuple[str | list[dict], str | None]:
    """Tách khối ngữ cảnh chạy của AIRI khỏi tin người dùng, để yêu cầu gửi model chỉ nối thêm giữa các lượt (cache).

    AIRI (``packages/core-agent/src/messages/render-context.ts``) nối ``"\\n[Context]\\n- nguồn: …"`` (cách dùng token
    cảm xúc ACT, danh sách cảm xúc…) vào cuối tin người dùng MỚI NHẤT, còn lịch sử thì lưu tin không có khối đó. xAI chỉ
    dùng lại cache khi CẢ yêu cầu trước là tiền tố của yêu cầu sau (đo ngày 16/11/2026), nên khối này không được nằm ở
    tin nào: ``_messages`` bỏ nó khỏi mọi tin người dùng và đặt khối của tin mới nhất vào instructions (giống nhau mọi
    lượt). Model nhận đúng những chữ ấy, chỉ khác chỗ đặt. Trả (nội dung còn lại, khối ngữ cảnh hoặc None).
    """
    if isinstance(content, str):
        at = content.rfind(CONTEXT_MARK)
        return (content, None) if at < 0 else (content[:at], content[at + 1:])
    for index in range(len(content) - 1, -1, -1):
        part = content[index]
        text = part.get("text") if part.get("type") == "input_text" else None
        at = text.rfind(CONTEXT_MARK) if isinstance(text, str) else -1
        if at >= 0:
            head = [{**part, "text": text[:at]}] if text[:at] else []
            return [*content[:index], *head, *content[index + 1:]], text[at + 1:]
    return content, None


def _tool_calls(raw: object) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RequestError("tool_calls phải là danh sách.")
    calls = []
    for call in raw:
        function = call.get("function") if isinstance(call, dict) else None
        call_id = call.get("id") if isinstance(call, dict) else None
        if (not isinstance(function, dict) or not isinstance(call_id, str) or not call_id
                or call.get("type", "function") != "function" or not isinstance(function.get("name"), str)):
            raise RequestError("Lời gọi công cụ trong lịch sử không đúng định dạng.")
        arguments = function.get("arguments")
        if arguments is None:
            arguments = ""
        if not isinstance(arguments, str):
            raise RequestError("Đối số lời gọi công cụ phải là chuỗi JSON.")
        calls.append({"type": "function_call", "call_id": call_id, "name": function["name"], "arguments": arguments})
    return calls


def _messages(raw: object) -> tuple[str, list[dict], int, bool]:
    if not isinstance(raw, list) or not raw:
        raise RequestError("Thiếu danh sách tin nhắn.")
    if len(raw) > MAX_MESSAGES:
        raise RequestError(f"Quá nhiều tin nhắn trong một lượt (tối đa {MAX_MESSAGES:,}).".replace(",", "."))
    system: list[str] = []
    items: list[dict] = []
    total = images = 0
    open_calls: dict[str, dict] = {}  # call_id -> lời gọi chưa có kết quả
    answered: set[str] = set()
    context: str | None = None  # khối "[Context]" của tin người dùng mới nhất có khối
    last_role = None
    for message in raw:
        if not isinstance(message, dict):
            raise RequestError("Tin nhắn không hợp lệ.")
        role = message.get("role")
        if role in {"system", "developer"}:
            text = _text_parts(message.get("content"), {"text", "input_text"}, "tin system")
            total += len(text)
            if text.strip():
                system.append(text)
            continue
        if role == "user":
            content, chars, count = _rich_parts(message.get("content"), "tin của người dùng")
            total += chars
            images += count
            content, found = split_context(content)
            if found:
                context = found  # tin sau đè tin trước: khối của tin người dùng mới nhất
            if content or count:
                items.append({"role": "user", "content": content})
        elif role == "assistant":
            text = _text_parts(message.get("content"), {"text", "output_text", "refusal"}, "tin của Peto")
            if not text and isinstance(message.get("refusal"), str):
                text = message["refusal"]
            calls = _tool_calls(message.get("tool_calls"))
            total += len(text) + sum(len(call["arguments"]) for call in calls)
            if text.strip():
                items.append({"role": "assistant", "content": text})
            for call in calls:
                if call["call_id"] in open_calls or call["call_id"] in answered:
                    raise RequestError("Lịch sử có hai lời gọi công cụ trùng mã.")
                open_calls[call["call_id"]] = call
                items.append(call)
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or call_id not in open_calls:
                raise RequestError("Kết quả công cụ không khớp lời gọi công cụ nào trước đó.")
            content, chars, count = _rich_parts(message.get("content"), "kết quả công cụ")
            total += chars
            images += count
            open_calls.pop(call_id)
            answered.add(call_id)
            items.append({"type": "function_call_output", "call_id": call_id, "output": content})
        else:
            raise RequestError("Vai trò tin nhắn không hợp lệ.")
        last_role = role
    if total > MAX_TOTAL_CHARS:
        raise RequestError(f"Lượt này quá dài (tối đa {MAX_TOTAL_CHARS:,} ký tự).".replace(",", "."))
    if images > MAX_IMAGES:
        raise RequestError(f"Mỗi lượt gửi kèm tối đa {MAX_IMAGES} ảnh.")
    if last_role not in {"user", "tool"} or not items:
        raise RequestError("Tin cuối cùng phải là của người dùng hoặc kết quả công cụ.")
    # Lời gọi không bao giờ có kết quả (trình duyệt dừng giữa chừng): dịch vụ AI từ chối lời gọi mồ côi, nên bỏ đi.
    if open_calls:
        items = [item for item in items if item.get("type") != "function_call" or item["call_id"] not in open_calls]
    # Khối ngữ cảnh vào instructions, giữa system của AIRI và luật cố định (luôn đứng cuối): nó giống nhau mọi lượt, còn
    # tin người dùng chỉ giữ chữ của người dùng, đúng như AIRI gửi lại trong lịch sử (xem ``split_context``).
    instructions = "\n\n".join([*system, *([context] if context else []), COMPANION_CARD_RULE])
    return instructions, items, images, last_role == "tool"


def _tools(raw: object) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_TOOLS:
        raise RequestError(f"Danh sách công cụ không hợp lệ (tối đa {MAX_TOOLS} công cụ).")
    tools: list[dict] = []
    names: set[str] = set()
    total = 0
    for tool in raw:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict) or tool.get("type") != "function":
            raise RequestError("Cổng chỉ nhận công cụ dạng function.")
        name = function.get("name")
        if not isinstance(name, str) or not TOOL_NAME.fullmatch(name):
            raise RequestError("Tên công cụ chỉ được có chữ không dấu, số, gạch dưới và gạch ngang, tối đa 64 ký tự.")
        if name in names:
            raise RequestError(f"Công cụ {name} được khai báo hai lần.")
        names.add(name)
        description = function.get("description")
        parameters = function.get("parameters")
        strict = function.get("strict")
        if description is not None and not isinstance(description, str):
            raise RequestError(f"Mô tả của công cụ {name} phải là chuỗi.")
        if parameters is not None and not isinstance(parameters, dict):
            raise RequestError(f"Tham số của công cụ {name} phải là một JSON Schema dạng object.")
        if strict is not None and not isinstance(strict, bool):
            raise RequestError(f"strict của công cụ {name} phải là true hoặc false.")
        clean = {"type": "function", "name": name,
                 **({"description": description} if description else {}),
                 "parameters": parameters if parameters is not None else {"type": "object", "properties": {}},
                 **({"strict": strict} if strict is not None else {})}
        size = len(json.dumps(clean, ensure_ascii=False).encode("utf-8"))
        if size > MAX_TOOL_SCHEMA_BYTES:
            raise RequestError(f"Khai báo của công cụ {name} quá lớn (tối đa {MAX_TOOL_SCHEMA_BYTES // 1024} KB).")
        total += size
        tools.append(clean)
    if total > MAX_TOOLS_TOTAL_BYTES:
        raise RequestError(f"Khai báo công cụ quá lớn (tổng tối đa {MAX_TOOLS_TOTAL_BYTES // 1024} KB).")
    return tools


def _tool_choice(raw: object, tools: list[dict]) -> str | dict | None:
    """``auto``/``none``/``required``, hoặc ép một công cụ (dạng Chat Completions đổi sang dạng Responses)."""
    if raw is None or not tools:
        return None
    if isinstance(raw, str) and raw in TOOL_CHOICES:
        return raw
    function = raw.get("function") if isinstance(raw, dict) and raw.get("type") == "function" else None
    name = function.get("name") if isinstance(function, dict) else None
    if not isinstance(name, str):
        raise RequestError("tool_choice chỉ nhận auto, none, required hoặc một công cụ dạng function.")
    if name not in {tool["name"] for tool in tools}:
        raise RequestError(f"tool_choice chọn công cụ {name} không có trong danh sách công cụ.")
    return {"type": "function", "name": name}


def _max_tokens(payload: dict) -> int | None:
    value = payload.get("max_completion_tokens", payload.get("max_tokens"))
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RequestError("max_tokens phải là số nguyên dương.")
    return value


def parse(raw: bytes) -> Parsed:
    try:
        payload = json.loads(raw or b"null")
    except (UnicodeDecodeError, ValueError):
        raise RequestError("Thân yêu cầu không phải JSON.") from None
    if not isinstance(payload, dict):
        raise RequestError("Thân yêu cầu không hợp lệ.")
    instructions, items, images, continuation = _messages(payload.get("messages"))
    tools = _tools(payload.get("tools"))
    options = payload.get("stream_options")
    return Parsed(
        instructions=instructions, items=items, tools=tools, tool_choice=_tool_choice(payload.get("tool_choice"), tools),
        max_output_tokens=_max_tokens(payload), stream=payload.get("stream") is True,
        include_usage=isinstance(options, dict) and options.get("include_usage") is True,
        continuation=continuation, images=images,
    )
