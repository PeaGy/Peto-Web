"""Sự kiện hiển thị có cấu trúc: công cụ và vòng làm việc báo việc gì đang xảy ra, giao diện tự quyết định vẽ thế nào.

Công cụ không dựng chuỗi hiển thị nữa (giao diện kiểu OpenCode, chủ web chọn ngày 2026-10-12): một lần gọi công cụ là
``ToolCall`` lúc bắt đầu và ``ToolDone`` lúc xong. ``ToolDone.result`` đúng là thứ gửi cho model; ``meta`` chỉ để hiển
thị (diff, đường dẫn ảnh đầy đủ, lý do từ chối…) và không bao giờ đi lên máy chủ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PERMISSION_QUESTION = "    Đồng ý? [y] có  [n] không  [a] có cho mọi bước trong yêu cầu này › "


@dataclass
class ToolCall:
    call_id: str
    name: str
    args: dict


@dataclass
class ToolDone:
    call_id: str
    name: str
    args: dict
    result: dict
    # Chỉ để hiển thị. Khóa dùng chung: "refused" (người dùng từ chối), "raised" ("workspace", "guide", "os": lỗi
    # công cụ, kèm "message"), "stopped" (Ctrl+C giữa chừng).
    meta: dict = field(default_factory=dict)
    seconds: float = 0.0


@dataclass
class Permission:
    """Một câu hỏi quyền. ``kind``: file, move, command, background, page, site, mcp, mcp_enable, undo.

    ``ask`` trả "y", "n", "a", "s" hoặc "l" với đúng ý nghĩa cũ: a là cả yêu cầu, s là nhớ trong phiên, l là luôn cho
    phép ở dự án này (lưu trong hồ sơ người dùng, không bao giờ trong thư mục dự án).
    """

    kind: str
    body: dict = field(default_factory=dict)
    allow_session: bool = False
    allow_always: bool = False
    session_label: str = "nhớ lệnh này trong phiên"
    question: str = PERMISSION_QUESTION


@dataclass
class RequestEnd:
    """Cuối một yêu cầu: outcome là done, stopped, error hoặc limit."""

    outcome: str
    seconds: float
    changes: dict
    commands: list
    background_jobs: int = 0
    plan_left: int = 0
    context_tokens: int | None = None
    # Tên model người dùng thấy (6 Luna, Peto…).
    model: str = ""
    # Hội thoại đã tới đâu so với mức tự tóm tắt của CLI (0 tới 1); None khi chưa có hội thoại.
    context_share: float | None = None
    # Số tệp lệnh đã đổi trong yêu cầu, biết nhờ ảnh chụp dự án (CLI 0.26.0).
    command_files: int = 0
