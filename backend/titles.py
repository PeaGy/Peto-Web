"""Đặt tên hội thoại bằng một câu tóm tắt ngắn, thay cho tin nhắn đầu bị cắt.

Các web chat lớn đều làm vậy: liếc thanh bên là biết cuộc đó nói gì, thay vì
đọc lại nguyên câu hỏi dài. Tên được sinh bằng một lượt gọi AI riêng rất ngắn,
chạy song song với câu trả lời chính nên người dùng không phải chờ thêm.

Hỏng, chậm hay bị hủy thì bỏ qua: hội thoại giữ nguyên tên cắt tạm từ tin nhắn
đầu, nên không bao giờ có hội thoại trống tên.
"""

from __future__ import annotations

import asyncio
import logging

from ai import ChatMessage, StreamChunk, get_provider

logger = logging.getLogger("peto_web.titles")

# Nhà cung cấp giả nhận ra lượt đặt tên nhờ câu này nằm trong system prompt.
TITLE_MARKER = "Bạn đang đặt tiêu đề cho một cuộc trò chuyện"

SYSTEM_PROMPT = f"""{TITLE_MARKER}.

Đọc tin nhắn đầu của người dùng rồi đặt tên cho cuộc đó:
- Cùng ngôn ngữ với người dùng.
- Tối đa 6 từ, nêu đúng chủ đề.
- Không ngoặc kép, không chấm cuối, không mở đầu bằng "Cuộc trò chuyện về".
- Chỉ trả về đúng cái tên, không thêm lời nào khác."""

MAX_TITLE_CHARS = 60
# Lượt đặt tên rất ngắn nên bình thường xong trước cả câu trả lời chính.
GENERATE_TIMEOUT = 15.0
# Trần chờ ở cuối lượt: thà giữ tên cắt tạm còn hơn bắt người dùng đợi.
WAIT_SECONDS = 8.0

# Ngoặc kép, ngoặc đơn, ngoặc kiểu sách và dấu nhấn markdown model hay thêm vào.
_TRIM = '"' + "'" + "“”‘’`*# "
_PREFIXES = ("tiêu đề:", "tên:", "title:")


def clean_title(raw: str) -> str:
    """Gọt những thứ model hay kèm theo: ngoặc kép, "Tiêu đề:", chấm cuối."""
    title = " ".join(raw.split())
    for prefix in _PREFIXES:
        if title.casefold().startswith(prefix):
            title = title[len(prefix):].strip()
    title = title.strip(_TRIM).rstrip(".…").strip(_TRIM)
    if len(title) > MAX_TITLE_CHARS:
        head = title[: MAX_TITLE_CHARS - 1]
        title = (head.rsplit(" ", 1)[0] or head).rstrip(",;:") + "…"
    return title


async def suggest_title(first_message: str, attachment_names: list[str] | None = None) -> str:
    """Tên gợi ý cho hội thoại; chuỗi rỗng nếu không lấy được. Không bao giờ raise."""
    content = " ".join(first_message.split())
    if attachment_names:
        content = f"{content} [đính kèm: {', '.join(attachment_names)}]".strip()
    if not content:
        return ""

    parts: list[str] = []
    try:
        async with asyncio.timeout(GENERATE_TIMEOUT):
            async for chunk in get_provider().stream(
                system_prompt=SYSTEM_PROMPT,
                messages=[ChatMessage(role="user", content=content[:2000])],
                effort="low",
                web_search="off",
            ):
                if isinstance(chunk, StreamChunk):
                    if chunk.kind == "text":
                        parts.append(chunk.text)
                else:
                    parts.append(chunk)
    except Exception as err:
        # Tên hội thoại là thứ có cũng được: hỏng thì ghi log rồi thôi.
        logger.warning("Không đặt được tên hội thoại: %s", type(err).__name__)
        return ""
    return clean_title("".join(parts))


async def resolve(task: asyncio.Task[str]) -> str:
    """Chờ lượt đặt tên đang chạy, nhưng không giữ lượt chat lại quá lâu."""
    try:
        return await asyncio.wait_for(task, WAIT_SECONDS)
    except Exception:
        task.cancel()
        return ""
