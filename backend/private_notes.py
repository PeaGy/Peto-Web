"""Ghi chú riêng của Peto trong tab Companion (chủ web chọn ngày 2026-09-27).

Model không giữ được gì giữa các lượt ngoài chữ của cuộc trò chuyện. Được bảo "chọn một số rồi nhớ", nó không có chỗ
nào để nhớ, nên bịa khi người dùng đoán rồi mới thú nhận (chủ web gặp đúng chuyện này). Prompt Companion cho Peto viết
điều cần giữ kín vào <private>…</private>. Máy chủ lưu nguyên câu trả lời để lượt sau model đọc lại được ghi chú,
nhưng lọc ghi chú khỏi mọi chữ gửi về trình duyệt (stream ``delta`` và lịch sử), nên người dùng không thấy và giọng đọc
không đọc.

Chỉ dùng cho hội thoại Companion: câu trả lời ở tab Trò chuyện có thể chứa "<private>" thật, ví dụ trong code XML.
"""

from __future__ import annotations

import re

OPEN = "<private>"
CLOSE = "</private>"
# Ghi chú chưa đóng thì ẩn tới hết câu trả lời: thà mất chữ còn hơn lộ bí mật.
_NOTE = re.compile(r"[ \t]*<private>.*?(?:</private>|$)[ \t]*", re.IGNORECASE | re.DOTALL)


def strip(text: str) -> str:
    """Câu trả lời như người dùng thấy: bỏ mọi ghi chú riêng, khoảng trắng chỗ ghi chú gộp lại."""
    if "<" not in text:
        return text
    cleaned, count = _NOTE.subn(" ", text)
    if not count:
        return text
    return re.sub(r" ?\n ?", "\n", re.sub(r" {2,}", " ", cleaned)).strip()


def _partial(text: str, tag: str) -> int:
    """Độ dài đoạn cuối của ``text`` có thể là phần đầu của ``tag`` (thẻ bị cắt giữa hai mảnh stream)."""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:size]):
            return size
    return 0


class NoteFilter:
    """Lọc ghi chú riêng khỏi chữ đang stream. Thẻ có thể bị cắt giữa hai mảnh ("<pri" rồi "vate>"), nên phần cuối một
    mảnh mà có thể là đầu thẻ thì giữ lại chờ mảnh sau."""

    def __init__(self) -> None:
        self._buffer = ""
        self._hidden = False
        self._last = ""
        self._after_note = False

    def feed(self, text: str) -> str:
        self._buffer += text
        out: list[str] = []
        while self._buffer:
            lower = self._buffer.lower()
            if self._hidden:
                end = lower.find(CLOSE)
                if end < 0:
                    # Bỏ phần ghi chú đã nhận, chỉ giữ đoạn có thể là đầu thẻ đóng.
                    self._buffer = self._buffer[len(self._buffer) - _partial(lower, CLOSE):]
                    break
                self._buffer = self._buffer[end + len(CLOSE):]
                self._hidden = False
                self._after_note = True
                continue
            start = lower.find(OPEN)
            if start < 0:
                keep = _partial(lower, OPEN)
                out.append(self._buffer[: len(self._buffer) - keep])
                self._buffer = self._buffer[len(self._buffer) - keep:]
                break
            out.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(OPEN):]
            self._hidden = True
        return self._emit("".join(out))

    def flush(self) -> str:
        """Hết câu trả lời: đoạn giữ lại mà không thành thẻ là chữ thường; ghi chú chưa đóng thì bỏ."""
        rest = "" if self._hidden else self._buffer
        self._buffer = ""
        return self._emit(rest)

    def _emit(self, text: str) -> str:
        # "one. <private>7</private> Go" thành "one. Go", không còn hai dấu cách liền nhau.
        if self._after_note and text:
            if not self._last or self._last[-1].isspace():
                text = text.lstrip(" \t")
            if text:
                self._after_note = False
        if text:
            self._last = text
        return text
