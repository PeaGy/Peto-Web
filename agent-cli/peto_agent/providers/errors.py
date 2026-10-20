"""Phân loại lỗi của lượt gọi model theo nhóm chung cho mọi nguồn (mốc M1).

Nhóm chỉ dùng để chẩn đoán và để nguồn sau này chọn cách xử lý; lời báo cho người dùng vẫn là thông báo tiếng Việt của
nguồn. Không đưa nội dung phản hồi thô hay bí mật vào đây.
"""

from __future__ import annotations

CATEGORIES = ("authentication", "permission", "quota", "rate_limit", "context_overflow", "capability",
              "invalid_request", "network", "server", "canceled", "incomplete", "provider")

# Mã trạng thái HTTP của nguồn Peto (backend/features/agent/api.py). 429 ở /step là hết bước trong ngày.
_STATUS = {401: "authentication", 403: "permission", 404: "capability", 408: "network", 413: "capability",
           429: "quota", 400: "invalid_request", 0: "network", 502: "network", 503: "network", 504: "network"}


# Mã lỗi nguồn trực tiếp gắn vào sự kiện error (providers/openai_key.py).
_CODES = {"authentication": "authentication", "permission": "permission", "quota": "quota",
          "capability": "capability", "invalid_request": "invalid_request", "network": "network",
          "rate_limit": "rate_limit", "server": "server"}


def classify(*, status: int | None = None, code: str | None = None, retryable: bool = False) -> str:
    """Nhóm của một lỗi: ``status`` là mã HTTP (0 là không kết nối được), ``code`` và ``retryable`` lấy từ sự kiện
    error của luồng trả lời."""
    if code == "context_overflow":
        return "context_overflow"
    if code in _CODES:
        return _CODES[code]
    if code == "queue_full" or retryable:
        return "rate_limit"
    if status is None:
        return "provider"
    if status in _STATUS:
        return _STATUS[status]
    return "server" if status >= 500 else "provider"
