"""Công cụ của Peto Web: kiểm tra đầu vào và chạy trong backend.

Hiện chỉ có đồng hồ, không đọc dữ liệu riêng hoặc thực hiện tác vụ bên ngoài.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import DEFAULT_TIMEZONE

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật")


class ToolInputError(ValueError):
    pass


def resolve_timezone(name: str | None = None) -> str:
    value = name if name is not None else DEFAULT_TIMEZONE
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ToolInputError("Múi giờ không hợp lệ. Dùng tên như Asia/Ho_Chi_Minh hoặc Europe/Paris.")
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolInputError("Không nhận diện được múi giờ. Dùng tên IANA như Asia/Ho_Chi_Minh.") from None
    return value


def current_datetime(timezone: str | None = None, *, now: datetime | None = None) -> dict:
    zone = resolve_timezone(timezone)
    instant = now if now is not None else datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Đồng hồ cần thời gian có múi giờ.")
    local = instant.astimezone(ZoneInfo(zone))
    offset = local.strftime("%z")
    return {
        "timezone": zone,
        "datetime": local.isoformat(timespec="seconds"),
        "date": local.date().isoformat(),
        "time": local.strftime("%H:%M:%S"),
        "weekday": WEEKDAYS[local.weekday()],
        "utc_offset": f"UTC{offset[:3]}:{offset[3:]}",
        "checked_at_utc": instant.astimezone(UTC).isoformat(timespec="seconds"),
    }


def time_context(timezone: str | None = None) -> str:
    clock = current_datetime(timezone)
    return (
        "## Thời gian được máy chủ xác minh cho lượt hiện tại\n"
        f"{clock['weekday']}, {clock['date']}, {clock['time']} "
        f"({clock['timezone']}, {clock['utc_offset']}).\n"
        "Đây là mốc thời gian mới của lượt này, ưu tiên hơn ngày giờ trong lịch sử. "
        "Múi giờ là lựa chọn của trình duyệt hoặc cấu hình web, không chứng minh vị trí người dùng. "
        "Dùng mốc này cho hôm nay, hôm qua, ngày mai. Không tự chèn ngày giờ vào mọi câu trả lời. "
        "Khi cần giờ mới nhất hoặc giờ ở nơi khác, gọi get_current_datetime; nếu địa danh mơ hồ thì hỏi rõ."
    )


TOOL_SCHEMAS = [{
    "type": "function",
    "name": "get_current_datetime",
    "description": "Lấy ngày, thứ và giờ hiện tại từ máy chủ theo múi giờ IANA, có tính giờ mùa hè. Không nhận thời gian do người dùng tự khai.",
    "parameters": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": ["string", "null"],
                "description": "Múi giờ IANA, ví dụ Asia/Ho_Chi_Minh, Asia/Barnaul, America/New_York. null dùng múi giờ của lượt chat.",
            },
        },
        "required": ["timezone"],
        "additionalProperties": False,
    },
    "strict": True,
}]


def execute_tool(name: str, arguments: str, *, timezone: str | None = None) -> dict:
    """Chỉ chạy công cụ đã đăng ký; không eval tên hàm hoặc đầu vào của model."""
    if name != "get_current_datetime":
        return {"error": "Công cụ này chưa có trên Peto Web."}
    try:
        if not isinstance(arguments, str) or len(arguments) > 2048:
            raise ToolInputError("Tham số công cụ không hợp lệ.")
        params = json.loads(arguments)
        if not isinstance(params, dict) or set(params) - {"timezone"}:
            raise ToolInputError("Chỉ nhận tham số timezone.")
        requested = params.get("timezone")
        return current_datetime(timezone if requested is None else requested)
    except (json.JSONDecodeError, ToolInputError) as err:
        return {"error": str(err) if isinstance(err, ToolInputError) else "Tham số công cụ không phải JSON hợp lệ."}
