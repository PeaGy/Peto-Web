"""Cấu hình của CLI: địa chỉ máy chủ, token và tên máy, lưu trong hồ sơ người dùng.

Token không bao giờ được in ra màn hình hay ghi vào nhật ký. ``PETO_AGENT_HOME`` đổi nơi lưu, dùng cho test.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

# Gói tải qua bộ cài một dòng (backend/agent_install.py) có kèm tệp này, chứa địa chỉ Peto đã cài từ đó.
# Bản cài từ mã nguồn không có tệp này.
DEFAULT_SERVER_FILE = Path(__file__).with_name("default_server.txt")


def home() -> Path:
    override = os.environ.get("PETO_AGENT_HOME")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PetoAgent"


def log_dir() -> Path:
    override = os.environ.get("PETO_AGENT_HOME")
    if override:
        return Path(override) / "logs"
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / ".local" / "state")
    return Path(base) / "PetoAgent" / "logs"


def sessions_dir() -> Path:
    """Nơi lưu hội thoại gần nhất của từng thư mục dự án, cạnh thư mục nhật ký."""
    return log_dir().parent / "sessions"


def screenshots_dir() -> Path:
    """Ảnh Peto chụp trang web, cạnh thư mục nhật ký, để người dùng mở xem đúng thứ Peto đã thấy."""
    return log_dir().parent / "screenshots"


def browser_profiles_dir() -> Path:
    """Hồ sơ trình duyệt riêng của từng dự án (giữ đăng nhập người dùng tự làm trong cửa sổ của Peto)."""
    return log_dir().parent / "browser"


def load() -> dict:
    try:
        data = json.loads((home() / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)


def default_server() -> str:
    try:
        return DEFAULT_SERVER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def device_name() -> str:
    return socket.gethostname() or "Máy chưa đặt tên"
