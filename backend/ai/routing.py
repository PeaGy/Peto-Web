"""Chọn mức suy luận theo nội dung câu hỏi.

Rút gọn từ ``GrokChat._reasoning_effort_for_request`` trong bot Discord: nhẹ
cho chat thường, cao hơn cho toán và bài cần suy luận nhiều bước. Đã bỏ các
mốc chỉ có nghĩa với Discord (Limbus wiki, tra web, đọc link).
"""

from __future__ import annotations

import re

_HIGH_MARKERS = (
    "logic nhiều bước", "suy luận nhiều bước", "chứng minh", "bài toán khó",
    "câu đố logic", "giải từng bước", "lời giải chi tiết",
    "competition math", "multi-step logic", "prove that",
)

_MATH_MARKERS = (
    "đạo hàm", "tích phân", "xác suất", "phương trình", "hàm số",
    "cực trị", "số phức", "hình học", "toán", "chứng minh",
    "lượng giác", "luong giac", "đại số", "dai so", "giải tích", "giai tich",
    "ma trận", "ma tran", "derivative", "integral", "probability",
    "equation", "theorem", "trigonometry", "algebra", "calculus", "matrix",
)

_TECHNICAL_MARKERS = (
    "traceback", "exception", "debug", "lỗi code", "source code",
    "python", "javascript", "typescript", "react", "api", "sqlite",
    "database", "kiến trúc", "tối ưu", "phân tích kỹ thuật",
    "algorithm", "architecture", "performance",
)

_TRIG_RE = re.compile(r"\b(?:sin|cos|tan|cot|sec|csc)\b")
_EXPR_RE = re.compile(r"(?:\d|[a-z])\s*(?:\^|=|≤|≥|[+*/])\s*(?:\d|[a-z])")


def looks_like_math(text: str) -> bool:
    lowered = str(text or "").casefold()
    return (
        any(marker in lowered for marker in _MATH_MARKERS)
        or bool(_TRIG_RE.search(lowered))
        or bool(_EXPR_RE.search(lowered))
    )


def choose_effort(user_text: str) -> str:
    """Trả về "low" | "medium" | "high"."""
    lowered = str(user_text or "").casefold()
    if any(marker in lowered for marker in _HIGH_MARKERS):
        return "high"
    if looks_like_math(lowered):
        return "medium"
    if any(marker in lowered for marker in _TECHNICAL_MARKERS):
        return "medium"
    return "low"
