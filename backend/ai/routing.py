"""Chọn mức suy luận theo nội dung câu hỏi.

Rút gọn từ ``GrokChat._reasoning_effort_for_request`` trong bot Discord: nhẹ
cho chat thường, cao hơn cho toán và bài cần suy luận nhiều bước. Đã bỏ các
mốc chỉ có nghĩa với Discord (Limbus wiki, tra web, đọc link).

G2.2 (18/11/2026): khớp theo trọn từ chứ không theo chuỗi con ("thanh toán" không còn là toán, "rapid" không còn chứa
"api"), và thêm tín hiệu không phụ thuộc từ khóa cho tab Trò chuyện: có tệp đính kèm hay tệp dự án, chế độ tài liệu,
tin dài, có khối code, yêu cầu viết dài, so sánh hay đánh giá. Lời chào ngắn luôn ở mức thấp.
"""

from __future__ import annotations

import re
import unicodedata

_HIGH_MARKERS = (
    "logic nhiều bước", "suy luận nhiều bước", "chứng minh", "bài toán khó",
    "câu đố logic", "giải từng bước", "lời giải chi tiết",
    "competition math", "multi-step logic", "prove that",
)

# "toán" đứng một mình dễ nhầm ("thanh toán", "kế toán", "quyết toán"), nên chỉ tính khi đi kèm từ chỉ môn học.
_MATH_MARKERS = (
    "đạo hàm", "tích phân", "xác suất", "phương trình", "hàm số",
    "cực trị", "số phức", "hình học", "bài toán", "giải toán", "toán học", "môn toán", "đề toán",
    "chứng minh", "lượng giác", "đại số", "giải tích", "ma trận",
    "derivative", "integral", "probability",
    "equation", "theorem", "trigonometry", "algebra", "calculus", "matrix",
)

_TECHNICAL_MARKERS = (
    "traceback", "exception", "debug", "lỗi code", "source code",
    "python", "javascript", "typescript", "react", "api", "sqlite",
    "database", "kiến trúc", "tối ưu", "phân tích kỹ thuật",
    "algorithm", "architecture", "performance",
)

# Viết dài, so sánh, đánh giá: cần sắp ý trước khi viết.
_REASONING_MARKERS = (
    "bài luận", "tiểu luận", "nghị luận", "luận văn", "phân tích", "so sánh", "ưu nhược", "ưu điểm và nhược điểm",
    "đánh giá", "nhận xét", "review", "thẩm định", "lập kế hoạch", "kế hoạch chi tiết", "chiến lược",
    "essay", "analyze", "analyse", "analysis", "compare", "comparison", "pros and cons", "trade-off", "tradeoff",
    "evaluate", "evaluation",
)

_GREETINGS = (
    "chào", "xin chào", "chào bạn", "chào peto", "hello", "hi", "hey", "alo", "cảm ơn", "cám ơn", "thanks",
    "thank you", "ok", "oke", "okay", "good morning", "chúc ngủ ngon",
)

_TRIG_RE = re.compile(r"\b(?:sin|cos|tan|cot|sec|csc)\b")
_EXPR_RE = re.compile(r"(?:\d|[a-z])\s*(?:\^|=|≤|≥|[+*/])\s*(?:\d|[a-z])")
# "1500 chữ", "2000 từ", "800 words": yêu cầu viết dài khi từ 500 trở lên. Dò trên chữ đã bỏ dấu (chữ → chu, từ → tu).
_LENGTH_RE = re.compile(r"(\d[\d.,]*)\s*(?:chu|tu|words?)\b")
_CODE_RE = re.compile(r"```|^(?: {4}|\t)\S", re.MULTILINE)
LONG_MESSAGE_CHARS = 600


def _fold(text: str) -> str:
    """Viết thường và bỏ dấu, để "luong giac" khớp "lượng giác"."""
    lowered = unicodedata.normalize("NFD", str(text or "").casefold().replace("đ", "d"))
    return "".join(ch for ch in lowered if unicodedata.category(ch) != "Mn")


def _pattern(markers: tuple[str, ...]) -> re.Pattern:
    words = sorted({_fold(marker) for marker in markers}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(word) for word in words) + r")(?!\w)")


_HIGH = _pattern(_HIGH_MARKERS)
_MATH = _pattern(_MATH_MARKERS)
_TECHNICAL = _pattern(_TECHNICAL_MARKERS)
_REASONING = _pattern(_REASONING_MARKERS)
_GREETING = re.compile(r"^(?:" + "|".join(re.escape(_fold(word)) for word in sorted(_GREETINGS, key=len, reverse=True))
                       + r")(?:\s+(?:ban|peto|nha|nhe|a|oi|cau|may))*[\s!.?~]*$")


def looks_like_math(text: str) -> bool:
    # Biểu thức và hàm lượng giác dò trên chữ còn dấu: bỏ dấu thì "và/hoặc" thành "va/hoac", trông như phép chia a/h.
    lowered = str(text or "").casefold()
    return (
        bool(_MATH.search(_fold(lowered)))
        or bool(_TRIG_RE.search(lowered))
        or bool(_EXPR_RE.search(lowered))
    )


def _asks_for_length(folded: str) -> bool:
    for match in _LENGTH_RE.finditer(folded):
        digits = re.sub(r"[.,]", "", match.group(1))
        if digits.isdigit() and int(digits) >= 500:
            return True
    return False


def choose_effort(user_text: str, *, attachments: int = 0, document: bool = False) -> str:
    """Trả về "low" | "medium" | "high".

    ``attachments`` (số tệp gửi kèm hoặc tệp dự án được chọn) và ``document`` (chế độ soạn tài liệu) chỉ tab Trò chuyện
    truyền vào; Companion trả lời ngắn nên chỉ dựa vào chữ."""
    raw = str(user_text or "")
    folded = _fold(raw).strip()
    if _GREETING.match(folded) and not attachments and not document:
        return "low"
    if _HIGH.search(folded):
        return "high"
    if looks_like_math(raw) or _TECHNICAL.search(folded):
        return "medium"
    if _REASONING.search(folded) or _asks_for_length(folded):
        return "medium"
    if attachments or document or len(raw) >= LONG_MESSAGE_CHARS or _CODE_RE.search(raw):
        return "medium"
    return "low"
