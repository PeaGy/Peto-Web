"""Công cụ của Peto Web: kiểm tra đầu vào và chạy trong backend.

Hiện chỉ có đồng hồ, không đọc dữ liệu riêng hoặc thực hiện tác vụ bên ngoài.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import DEFAULT_TIMEZONE

logger = logging.getLogger("peto_web.chat_tools")

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
        # Kèm giá trị nhận được: thiếu nó thì lỗi này không chẩn được, người
        # dùng chỉ thấy "không nhận diện được" mà không biết trình duyệt của
        # mình đã gửi gì.
        raise ToolInputError(
            f"Không nhận diện được múi giờ {value!r}. Dùng tên IANA như Asia/Ho_Chi_Minh."
        ) from None
    return value


def resolve_browser_timezone(name: str | None) -> str:
    """Múi giờ do trình duyệt gửi kèm mỗi lượt chat — thứ tốt nhất có được, không
    phải yêu cầu của người dùng.

    Hỏng thì rơi về mặc định thay vì chặn cả tin nhắn: gửi rỗng vốn đã được rơi
    về mặc định rồi, nên chặn cứng trường hợp "có gửi nhưng dạng lạ" là bất đối
    xứng, mà cái giá là cả một loại thiết bị không chat được.

    Công cụ ``get_current_datetime`` KHÔNG dùng hàm này: ở đó model đòi đúng một
    múi giờ cụ thể, đưa nhầm thì phải được báo lỗi chứ không được lặng lẽ đổi.
    """
    return browser_timezone_selection(name)[0]


def browser_timezone_selection(name: str | None) -> tuple[str, str]:
    """Giữ nguồn lựa chọn múi giờ; hợp lệ về cú pháp không chứng minh vị trí thiết bị."""
    if name is None:
        return resolve_timezone(None), 'server_default_missing'
    try:
        return resolve_timezone(name), 'client_iana_validated'
    except ToolInputError:
        fallback = resolve_timezone(None)
        logger.warning(
            "Trình duyệt gửi múi giờ %r không nhận diện được — dùng %s cho lượt này.",
            name, fallback,
        )
        return fallback, 'server_default_invalid'


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
        f"{TIME_HEADER_EN}\n"
        f"{clock['datetime']} ({clock['timezone']}, {clock['utc_offset']}).\n"
        "Use this fresh time over historical timestamps for relative dates. The configured/browser timezone "
        "does not prove the user's location. Do not add timestamps to every reply. For fresh time or another "
        "timezone, use get_current_datetime; clarify ambiguous place names."
    )


def agent_time_context(timezone: str | None = None) -> str:
    """Mốc thời gian cho Peto Agent, làm tròn xuống giờ.

    Agent gửi lại cả lịch sử ở mỗi bước. Giờ chính xác đến giây đổi system prompt ở mọi bước, nên prompt caching
    (Claude, và cache tự động của OpenAI/xAI) không bao giờ đọc lại được phần lịch sử phía sau. Làm tròn theo giờ thì
    các bước trong cùng một giờ dùng chung cache; giờ chính xác thì Agent chạy lệnh trên máy.
    """
    # Định dạng nằm ở features/agent/assembly.py, dùng chung với CLI (nguồn trực tiếp tự lấy giờ trên máy).
    from features.agent.assembly import time_text

    clock = current_datetime(timezone)
    return time_text(clock["date"], clock["time"][:2], clock["timezone"], clock["utc_offset"])


TIME_HEADER_EN = "## Server-verified current time"
# Khối thời gian luôn là đúng ba dòng: tiêu đề, mốc giờ, một dòng hướng dẫn (time_context, agent_time_context).
_TIME_BLOCK = re.compile(rf"(?:\n\n)?({re.escape(TIME_HEADER_EN)}\n[^\n]*\n[^\n]*)")


def split_time_context(text: str) -> tuple[str, str]:
    """(phần còn lại, khối thời gian). Để provider đặt khối hay đổi này sau cùng, sau điểm đánh dấu cache."""
    match = _TIME_BLOCK.search(text)
    if not match:
        return text, ""
    rest = text[:match.start()] + text[match.end():]
    if match.start() == 0:
        rest = rest.lstrip("\n")
    return rest, match.group(1)


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
