"""Cảm xúc Peto tự chọn cho mỗi câu trả lời Companion (Brain mục 2, chủ web chọn ngày 2026-09-27).

Như AIRI, model mở đầu câu trả lời bằng một thẻ, ví dụ <|EMOTE_HAPPY|>, với chín cảm xúc của AIRI. Máy chủ gỡ thẻ khỏi
chữ gửi về trình duyệt và khỏi lịch sử hiển thị, rồi báo cảm xúc bằng sự kiện SSE ``emotion`` kèm vị trí trong chữ.
Nhân vật giữ cảm xúc đầu tiên suốt câu trả lời. Câu lưu giữ nguyên thẻ để các lượt sau model thấy cách gắn thẻ.

Thẻ cảm xúc thêm trong câu cũ vẫn bị gỡ, nhưng không làm nhân vật đổi mặt; thẻ khác kiểu <|...|> cũng bị gỡ khỏi chữ.
"""

from __future__ import annotations

import re

from shared.reply_spacing import Spacing

EMOTIONS = ("happy", "sad", "angry", "think", "surprised", "awkward", "question", "curious", "neutral")
_ALIASES = {"surprise": "surprised", "thinking": "think", "thoughtful": "think", "confused": "question",
            "embarrassed": "awkward", "shy": "awkward", "idle": "neutral", "calm": "neutral"}
# Một thẻ ngắn trên một dòng: dài hơn thì không phải thẻ, trả lại thành chữ thường.
MAX_MARKER_CHARS = 40
_MARKER = re.compile(r"<\|([^|<>\n]{1,%d})\|>" % MAX_MARKER_CHARS)


def _body_ok(body: str, complete: bool) -> bool:
    """Phần giữa "<|" và "|>" có thể là thân một thẻ không (cùng luật với _MARKER)."""
    if len(body) > MAX_MARKER_CHARS or any(char in body for char in "\n<>|"):
        return False
    return bool(body) or not complete


def emotion_of(name: str) -> str | None:
    """Tên trong thẻ ra một trong EMOTIONS: EMOTE_HAPPY, EMOTION_HAPPY hay happy đều là "happy"."""
    word = name.strip().lower()
    for prefix in ("emote_", "emotion_", "emote:", "emotion:"):
        if word.startswith(prefix):
            word = word[len(prefix):]
            break
    word = _ALIASES.get(word, word)
    return word if word in EMOTIONS else None


def first(text: str) -> str | None:
    """Cảm xúc của thẻ cảm xúc đầu tiên trong câu, hoặc None."""
    for match in _MARKER.finditer(text):
        emotion = emotion_of(match.group(1))
        if emotion:
            return emotion
    return None


def strip(text: str) -> str:
    """Câu như người dùng thấy: đúng chữ bộ lọc stream phát ra (bỏ mọi thẻ <|...|>, khoảng trắng chỗ thẻ gộp lại)."""
    markers = MarkerFilter()
    return markers.feed(text) + markers.flush()


class MarkerFilter:
    """Gỡ thẻ khỏi chữ đang stream. Thẻ có thể bị cắt giữa hai mảnh ("<|EMO" rồi "TE_HAPPY|>"), nên từ "<" hay "<|"
    chưa khép thì giữ lại chờ mảnh sau; quá MAX_MARKER_CHARS hay gặp xuống dòng thì trả lại thành chữ thường."""

    def __init__(self, emotion: str | None = None) -> None:
        self._buffer = ""
        self._spacing = Spacing()
        # Khi thay bản nháp sau tra web, giữ cảm xúc đã chọn cho cùng lượt trả lời.
        self.emotion = emotion
        self._announced = False
        self._events: list[dict] = []
        self._offset = 0

    def take_events(self) -> list[dict]:
        """Chữ và cảm xúc theo đúng thứ tự; vị trí dùng UTF-16 như chuỗi trong trình duyệt."""
        events, self._events = self._events, []
        return events

    def _text(self, piece: str) -> str:
        text = self._spacing.text(piece)
        if text:
            self._events.append({"type": "delta", "text": text})
            self._offset += len(text.encode("utf-16-le", errors="surrogatepass")) // 2
        return text

    def take_emotion(self) -> str | None:
        """Cảm xúc vừa nhận ra, chỉ trả một lần cho mỗi câu."""
        if self.emotion and not self._announced:
            self._announced = True
            return self.emotion
        return None

    def feed(self, text: str) -> str:
        self._buffer += text
        out: list[str] = []
        while self._buffer:
            start = self._buffer.find("<")
            if start < 0:
                out.append(self._text(self._buffer))
                self._buffer = ""
                break
            out.append(self._text(self._buffer[:start]))
            rest = self._buffer[start:]
            if len(rest) == 1:
                self._buffer = rest  # chỉ có "<": chờ xem sau đó có phải "|" không
                break
            if rest[1] != "|":
                out.append(self._text("<"))
                self._buffer = rest[1:]
                continue
            end = rest.find("|>", 2)
            body = rest[2:end] if end >= 0 else rest[2:]
            # Thẻ bị cắt ngay trước ">" thì phần thân tạm có "|" ở cuối.
            if not _body_ok(body if end >= 0 or not body.endswith("|") else body[:-1], complete=end >= 0):
                out.append(self._text("<|"))
                self._buffer = rest[2:]
                continue
            if end < 0:
                self._buffer = rest  # thẻ chưa khép: chờ mảnh sau
                break
            emotion = emotion_of(body)
            if emotion and self.emotion is None:
                self.emotion = emotion
                self._events.append({"type": "emotion", "emotion": emotion, "offset": self._offset})
            self._buffer = rest[end + 2:]
            self._spacing.cut()
        return "".join(out)

    def flush(self) -> str:
        """Hết câu: phần còn giữ mà không thành thẻ là chữ thường."""
        rest, self._buffer = self._buffer, ""
        return self._text(rest)


def timeline(text: str) -> tuple[str, list[dict]]:
    """Chữ công khai và một cảm xúc cho cả câu, kể cả tin cũ có nhiều thẻ."""
    markers = MarkerFilter()
    visible = markers.feed(text) + markers.flush()
    cues = [{"emotion": event["emotion"], "offset": 0}
            for event in markers.take_events() if event["type"] == "emotion"]
    return visible, cues
