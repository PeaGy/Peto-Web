"""Nhà cung cấp giả — không gọi mạng, không cần credential.

Dùng để dựng và kiểm thử toàn bộ luồng chat (stream, lưu lịch sử, giới hạn
tải, báo lỗi) trước khi chốt nhà cung cấp AI thật.

Hai từ khóa dành riêng cho kiểm thử:
- ``__error__`` trong tin nhắn -> giả lập lỗi nhà cung cấp.
- ``__slow__`` trong tin nhắn -> trả lời rất chậm để thử timeout/hủy.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk
from chat_tools import execute_tool

_CHUNK_DELAY = 0.035

_GREETING = (
    "A, cậu đây rồi! Peto đợi mãi. Nay có gì vui kể nghe đi.",
    "Ê, chào cậu. Hôm nay thế nào rồi?",
)

_TOOL_REFUSAL = (
    "Ê, ở web này Peto chưa làm được vụ đó đâu, chưa có phần đó luôn. "
    "Ngồi kể chuyện suông với Peto vậy :))"
)

_IMAGE_REFUSAL = (
    "Muốn tạo ảnh thì mở tab Tạo ảnh rồi nhập mô tả cho Peto nhé. "
    "Còn sửa ảnh thì bấm Thêm ảnh, chọn ảnh gốc, kể Peto nghe muốn đổi gì "
    "rồi bấm Sửa ảnh."
)

_MATH = (
    "Ố, bài này phải ngồi tính đàng hoàng đây. Mà Peto đang chạy bằng phản hồi "
    "giả nên chưa giải thật được — cậu cắm nhà cung cấp AI vào rồi Peto làm cho."
)

_DEFAULT = (
    "Peto nghe rồi nha. Hiện tại Peto đang chạy bằng phản hồi giả để cậu thử "
    "giao diện, nên câu trả lời chưa phải của AI thật đâu. Luồng chat, lưu lịch "
    "sử và hiển thị chữ chảy dần thì đang hoạt động đúng rồi đó."
)

_IMAGE_WORDS = ("vẽ", "tạo ảnh", "vẽ ảnh", "sửa ảnh", "chỉnh ảnh", "chỉnh sửa ảnh", "generate image", "edit image")
_TOOL_WORDS = (
    "phát nhạc", "mở bài", "mở nhạc", "tìm ảnh",
    "search", "tìm kiếm", "tra web",
)


def _pick_reply(user_text: str, timezone: str | None = None) -> str:
    lowered = user_text.casefold().strip()
    if not lowered:
        return "Ủa, cậu gửi tin trống kìa. Gõ gì đi Peto nghe."
    if lowered in {"chào", "hi", "hello", "hey", "alo", "chao"}:
        return random.choice(_GREETING)
    if any(marker in lowered for marker in (
        "mấy giờ", "may gio", "ngày mấy", "ngay may", "ngày bao nhiêu", "thứ mấy",
        "hôm nay ngày", "hôm nay là ngày", "ngày giờ hiện tại", "current time", "what time",
    )):
        clock = execute_tool("get_current_datetime", "{}", timezone=timezone)
        if "error" in clock:
            return "Chưa xác định được múi giờ. Cậu nói rõ múi giờ muốn xem nhé."
        year, month, day = clock["date"].split("-")
        return (
            f"Bây giờ là {clock['time']}, {clock['weekday']}, ngày {day}/{month}/{year} "
            f"({clock['timezone']}, {clock['utc_offset']})."
        )
    if any(word in lowered for word in _IMAGE_WORDS):
        return _IMAGE_REFUSAL
    if any(word in lowered for word in _TOOL_WORDS):
        return _TOOL_REFUSAL
    from .routing import looks_like_math

    if looks_like_math(lowered):
        return _MATH
    return _DEFAULT


class MockProvider(ChatProvider):
    name = "mock"

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
        timezone: str | None = None,
    ) -> AsyncIterator[str | StreamChunk]:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        last_user = last.content if last else ""
        names = [item.name for item in last.attachments] if last else []

        if "__error__" in last_user:
            raise ProviderError(
                "Nhà cung cấp AI đang lỗi (giả lập). Thử lại sau nhé.",
                retryable=True,
            )
        if "__slow__" in last_user:
            await asyncio.sleep(3600)

        if not last_user.strip() and names:
            last_user = f"[đính kèm {', '.join(names)}]"

        reply = _pick_reply(last_user, timezone)
        if names:
            reply = (
                f"Peto thấy cậu gửi kèm {', '.join(names)}. "
                "Đang chạy phản hồi giả nên chưa đọc thật nội dung tệp đâu. "
            ) + reply

        await asyncio.sleep(_CHUNK_DELAY)
        yield StreamChunk("thinking", "Đọc tin nhắn rồi nghĩ cách trả lời…")

        # Cắt theo từ để giống nhịp stream thật, giữ nguyên dấu cách.
        buffer = ""
        for word in reply.split(" "):
            buffer = word if not buffer else buffer + " " + word
            if len(buffer) >= 12:
                await asyncio.sleep(_CHUNK_DELAY)
                yield buffer + " "
                buffer = ""
        if buffer:
            await asyncio.sleep(_CHUNK_DELAY)
            yield buffer
