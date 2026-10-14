"""Đọc lại một hội thoại đã lưu thành các sự kiện theo thứ tự (CLI 0.22.0).

``/resume`` dùng chúng để vẽ lại cả hội thoại như lúc đang làm, theo opencode (trước đây chỉ in mờ tin cuối);
``/export`` (0.23.0) dùng chúng để viết Markdown. Mỗi lời gọi công cụ được ghép với kết quả của nó theo ``call_id``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import history, mentions

# Lời nhắc "Kiểm tra sau sửa" do CLI thêm vào hội thoại dưới vai Peto: không phải lời Peto nói.
CHECK_REMINDER = "Kiểm tra sau sửa:"
SUMMARY_PREFIX = "Bản tóm tắt ngữ cảnh cũ"
ATTACHED = re.compile(r"^\[(?:Tệp|Thư mục) đính kèm: (.+?) · ", re.MULTILINE)
IMAGE_LABEL = re.compile(r"^\[Ảnh \d+\]$")


@dataclass
class Event:
    """``kind``: user, steer, summary, note, reply hay tool.

    - user, steer: ``text`` là chữ người dùng gõ; ``images`` là nhãn ảnh; ``files`` là các tệp đính kèm bằng @.
    - summary: ``text`` là bản tóm tắt phần cũ.
    - note: ``text`` là dòng đầu của tin báo tự động (lệnh nền tự dừng).
    - reply: ``text`` là chữ của Peto.
    - tool: ``name``, ``args`` và ``result`` (None khi chưa có kết quả).
    """

    kind: str
    text: str = ""
    images: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    name: str = ""
    args: dict = field(default_factory=dict)
    result: dict | None = None
    # Mục gốc trong hội thoại (tin của bạn): /timeline tìm lại khung tin của nó trên màn hình.
    item: dict | None = None


def _content_parts(item: dict) -> list[dict]:
    content = item.get("content")
    if isinstance(content, list):
        return [part for part in content if isinstance(part, dict)]
    return [{"type": "input_text", "text": str(content or "")}]


def _user(item: dict, kind: str) -> Event:
    parts = _content_parts(item)
    text = str(parts[0].get("text", "")) if parts else ""
    if kind == "steer":
        text = text.removeprefix(history.STEER_NOTE)
    typed, _, attached = text.partition("\n\n" + mentions.HEADER)
    images = [str(part.get("text")) for part in parts[1:]
              if part.get("type") == "input_text" and IMAGE_LABEL.match(str(part.get("text", "")))]
    return Event(kind, typed, images=images, files=ATTACHED.findall(attached), item=item)


def _json(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {"value": data}


def typed_text(item: dict) -> str:
    """Chữ người dùng đã gõ trong một tin (bỏ phần đầu của tin nhắn thêm và các tệp đính kèm bằng @)."""
    return _user(item, "steer" if history.raw_text(item).startswith(history.STEER_NOTE) else "user").text


def is_user(item: dict) -> bool:
    """Tin người dùng thật (kể cả tin nhắn thêm), không phải ghi chú, ảnh chụp trang hay bản tóm tắt."""
    if item.get("type", "message") != "message" or item.get("role") != "user":
        return False
    if history._is_tool_images(item) or history.is_note(item):
        return False
    return not history.raw_text(item).startswith(SUMMARY_PREFIX)


def events(items: list[dict]) -> list[Event]:
    outputs = {item.get("call_id"): item.get("output") for item in items if item.get("type") == "function_call_output"}
    out: list[Event] = []
    for item in items:
        kind = item.get("type", "message")
        if kind == "function_call":
            call_id = item.get("call_id")
            result = _json(outputs[call_id]) if call_id in outputs else None
            out.append(Event("tool", name=str(item.get("name", "")), args=_json(item.get("arguments")), result=result))
            continue
        if kind != "message":
            continue  # reasoning, web_search_call, function_call_output: đã ghép ở trên hoặc không có chữ để vẽ
        role = item.get("role")
        if role == "assistant":
            text = history.raw_text(item)
            if text.strip() and not text.startswith(CHECK_REMINDER):
                out.append(Event("reply", text))
            continue
        if role != "user" or history._is_tool_images(item):
            continue
        text = history.raw_text(item)
        if text.startswith(SUMMARY_PREFIX):
            out.append(Event("summary", text.partition("\n")[2]))
        elif text.startswith(history.STEER_NOTE):
            out.append(_user(item, "steer"))
        elif text.startswith(history.JOB_NOTE):
            out.append(Event("note", text.removeprefix(history.JOB_NOTE).split("\n", 1)[0]))
        elif history.is_note(item):
            continue  # tin nhắc chế độ Lập kế hoạch: lúc chạy cũng không hiện
        else:
            out.append(_user(item, "user"))
    return out
