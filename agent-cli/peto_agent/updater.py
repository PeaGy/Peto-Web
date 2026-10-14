"""/update: cập nhật peto bằng install.ps1 của máy chủ rồi mở lại đúng hội thoại (CLI 0.22.0, theo /update của opencode).

Chỉ tự cập nhật bản do install.ps1 cài (venv trong %LOCALAPPDATA%\\PetoAgent, hoặc PETO_AGENT_INSTALL_DIR): bản chạy
từ mã nguồn mà cài đè thì cài vào chỗ khác, peto đang chạy không đổi gì. install.ps1 đã biết dời peto.exe đang chạy sang
tên khác, nên cài được ngay trong lúc peto mở.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from . import runner

# pip tải và cài lại gói thường mất dưới một phút; mạng chậm thì lâu hơn.
INSTALL_TIMEOUT = 600


def install_root() -> Path:
    custom = os.environ.get("PETO_AGENT_INSTALL_DIR", "").strip()
    if custom:
        return Path(custom)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "PetoAgent"


def installed(prefix: str | None = None) -> bool:
    """Bản đang chạy là bản install.ps1 cài: Python của nó nằm trong venv của thư mục cài."""
    try:
        return Path(prefix or sys.prefix).resolve() == (install_root() / "venv").resolve()
    except OSError:
        return False


def launcher() -> Path:
    return install_root() / "bin" / "peto.exe"


def install_script(server: str) -> str:
    """Lệnh PowerShell tải và chạy install.ps1 của đúng máy chủ đang đăng nhập (dấu ' trong địa chỉ được nhân đôi).
    PETO_AGENT_UPDATING báo bộ cài đây là cập nhật, nên nó không in các bước đăng nhập và bắt đầu."""
    return "$env:PETO_AGENT_UPDATING = '1'; & { irm '" + server.rstrip("/").replace("'", "''") + "/install.ps1' | iex }"


def install(server: str, *, on_progress: Callable[[float, str], None] | None = None) -> dict:
    """Chạy install.ps1; trả kết quả như run_command (exit_code, seconds, output). Ctrl+C dừng cả cây tiến trình."""
    return runner.run(install_script(server), Path.home(), INSTALL_TIMEOUT, shell="powershell", on_progress=on_progress)


def restart_argv(session_id: str | None) -> list[str]:
    """Mở lại peto bản mới trong cùng cửa sổ, tiếp tục hội thoại đang mở (nếu có)."""
    return [str(launcher()), *(["--resume", session_id] if session_id else [])]
