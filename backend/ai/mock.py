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
import json
from collections.abc import AsyncIterator

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk
from chat_tools import execute_tool
from document_tools import current_session

DOCUMENT_SAMPLE = '''# Giữ sự tử tế trong xã hội số

Trong một thế giới mà mỗi người có thể gửi đi hàng trăm tin nhắn mỗi ngày, sự tử tế không còn chỉ thể hiện ở những cuộc gặp trực tiếp. Nó còn nằm trong cách chúng ta đọc một lời tâm sự, phản hồi một ý kiến khác biệt và dừng lại trước khi chia sẻ điều chưa được kiểm chứng. Không gian số giúp con người đến gần nhau, nhưng khoảng cách phía sau màn hình cũng có thể khiến ta quên rằng bên kia là một con người có cảm xúc.

Sự tử tế là thái độ tôn trọng, biết quan tâm và có trách nhiệm với hành động của mình. Trên mạng, điều ấy bắt đầu từ những việc rất nhỏ: không chế giễu một người chỉ vì họ mắc lỗi, không biến nỗi đau của người khác thành trò vui, không dùng những lời cay nghiệt để giành phần thắng. Tử tế không có nghĩa là đồng ý với mọi quan điểm. Ta hoàn toàn có thể phản biện thẳng thắn mà vẫn giữ sự công bằng và tôn trọng đối phương.

Thực tế cho thấy nhiều người sẵn sàng giúp đỡ nhau qua những nhóm học tập, chia sẻ kiến thức và kết nối cộng đồng. Một lời động viên đúng lúc có thể giúp ai đó vượt qua ngày khó khăn. Tuy vậy, cũng có những cuộc tranh luận nhanh chóng trở thành công kích cá nhân. Khi số lượt thích được xem như thước đo duy nhất, con người dễ chạy theo những phát ngôn gây chú ý mà bỏ qua hậu quả của chúng.

Nguyên nhân không chỉ đến từ tính ẩn danh. Nhịp thông tin quá nhanh khiến chúng ta phản ứng trước khi suy nghĩ, trong khi những mẩu chuyện bị tách khỏi bối cảnh lại dễ tạo ra hiểu lầm. Vì vậy, trách nhiệm của người sử dụng mạng không dừng ở việc tránh nói lời xúc phạm. Mỗi người còn cần học cách kiểm tra thông tin, lắng nghe nhiều phía và thừa nhận khi mình sai.

Để giữ sự tử tế, trước hết hãy tạo một khoảng dừng trước khi bình luận hoặc chia sẻ. Tự hỏi lời nói của mình có đúng sự thật, có cần thiết và có giúp ích hay không. Gia đình và nhà trường cũng cần tạo cơ hội để người trẻ thực hành tranh luận văn minh, thay vì chỉ yêu cầu im lặng trước bất đồng. Các nền tảng trực tuyến cần có cách tiếp nhận phản ánh rõ ràng và hỗ trợ người bị quấy rối.

Xã hội số trở nên đáng sống hơn khi mỗi người nhìn thấy con người phía sau tài khoản. Một hành động nhỏ không thể giải quyết mọi vấn đề, nhưng nhiều lựa chọn có trách nhiệm sẽ tạo nên thói quen chung. Giữ sự tử tế vì thế là việc có thể bắt đầu ngay hôm nay, từ chính lời nói tiếp theo mà chúng ta gửi đi.
'''

_CHUNK_DELAY = 0.035

_GREETING = (
    "Chào bạn! Hôm nay mình giúp gì được cho bạn?",
    "Chào bạn, bạn cần mình hỗ trợ việc gì?",
)

_TOOL_REFUSAL = (
    "Web này chưa có công cụ cho việc đó nên mình chưa làm được. "
    "Nếu bạn muốn, mình có thể giúp theo cách khác."
)

_IMAGE_REFUSAL = (
    "Muốn tạo ảnh thì bạn mở tab Tạo ảnh rồi nhập mô tả nhé. "
    "Còn sửa ảnh thì bấm Thêm ảnh, chọn ảnh gốc, nhập điều muốn thay đổi "
    "rồi bấm Sửa ảnh."
)

_MATH = (
    "Bài này cần tính cẩn thận. Hiện Peto đang chạy bằng phản hồi giả nên chưa "
    "giải thật được; khi nối nhà cung cấp AI, mình sẽ giải từng bước."
)

_DEFAULT = (
    "Mình đã nhận tin nhắn. Hiện Peto đang chạy bằng phản hồi giả để thử giao "
    "diện, nên câu trả lời này chưa phải của AI thật. Luồng chat, lưu lịch sử và "
    "hiển thị chữ chảy dần đang hoạt động bình thường."
)

_IMAGE_WORDS = ("vẽ", "tạo ảnh", "vẽ ảnh", "sửa ảnh", "chỉnh ảnh", "chỉnh sửa ảnh", "generate image", "edit image")
_TOOL_WORDS = (
    "phát nhạc", "mở bài", "mở nhạc", "tìm ảnh",
    "search", "tìm kiếm", "tra web",
)


def _pick_reply(user_text: str, timezone: str | None = None) -> str:
    lowered = user_text.casefold().strip()
    if not lowered:
        return "Tin nhắn đang trống. Bạn nhập nội dung rồi gửi lại nhé."
    if lowered in {"chào", "hi", "hello", "hey", "alo", "chao"}:
        return random.choice(_GREETING)
    if any(marker in lowered for marker in (
        "mấy giờ", "may gio", "ngày mấy", "ngay may", "ngày bao nhiêu", "thứ mấy",
        "hôm nay ngày", "hôm nay là ngày", "ngày giờ hiện tại", "current time", "what time",
    )):
        clock = execute_tool("get_current_datetime", "{}", timezone=timezone)
        if "error" in clock:
            return "Chưa xác định được múi giờ. Bạn cho mình biết múi giờ muốn xem nhé."
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

    def __init__(self, model: str = "peto") -> None:
        # Model người dùng chọn; phản hồi giả không đổi theo model, nhưng test đọc được lượt nào đi vào model nào.
        self.model = model

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
        timezone: str | None = None,
        web_search: str = "auto",
    ) -> AsyncIterator[str | StreamChunk]:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        last_user = last.content if last else ""
        names = [item.name for item in last.attachments] if last else []

        # Lượt đặt tên hội thoại: trả về tên gọn lấy từ chính tin nhắn, để bản
        # chạy thử vẫn thấy đúng kiểu web thật đặt tên.
        from titles import TITLE_MARKER  # import muộn cho khỏi vòng import

        if TITLE_MARKER in system_prompt:
            title = " ".join(last_user.split()[:6]) or "Trò chuyện mới"
            yield title[:1].upper() + title[1:]
            return

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
        session = current_session.get()
        lowered = last_user.casefold()
        # Only the offline mock uses keyword routing. The real provider chooses its tool.
        create_requested = '[PETO_DOCUMENT_CREATE]' in system_prompt or (
            any(word in lowered for word in ('tạo', 'xuất', 'create', 'generate')) and
            any(word in lowered for word in ('docx', 'pdf', 'word', 'tài liệu', 'file')))
        if session and create_requested:
            format = 'pdf' if 'pdf' in lowered and 'docx' not in lowered else 'docx'
            yield StreamChunk('document_status', 'Đang soạn và dàn trang tài liệu…')
            result = await session.create(json.dumps({'title': 'Giữ sự tử tế trong xã hội số', 'content': DOCUMENT_SAMPLE,
                'format': format, 'style': 'essay'}, ensure_ascii=False))
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
                yield StreamChunk('document_status', '')
                yield 'Đã tạo tệp mẫu chứa bài nghị luận **Giữ sự tử tế trong xã hội số**.\n\nBạn có thể xem từng trang và tải tệp bên dưới. Đây là nội dung mẫu của chế độ kiểm thử, chưa dùng AI thật.'
            else:
                yield StreamChunk('document_status', '')
                yield 'Chưa tạo được tệp: ' + result['error']
            return
        search_requested = web_search == "on" or any(word in last_user.casefold() for word in ("tìm kiếm", "tìm web", "tra web", "tra cứu", "mới nhất", "search"))
        if search_requested:
            reply = (
                "Tìm web đang tắt cho lượt này. Peto chưa xác minh thông tin mới."
                if web_search == "off" else
                "Peto đang chạy bằng phản hồi giả nên chưa tìm web thật và chưa có nguồn đã xác minh. "
                "Khi kết nối AI thật, Peto sẽ tra cứu và hiện nguồn ngay dưới câu trả lời."
            )
        if names:
            reply = (
                f"Mình thấy bạn gửi kèm {', '.join(names)}. "
                "Bộ đọc xử lý tệp riêng; đang chạy phản hồi giả nên mình chưa phân tích nội dung bằng AI thật. "
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
