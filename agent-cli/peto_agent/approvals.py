"""Lệnh được "luôn cho phép" trong từng dự án, lưu trong hồ sơ người dùng (``permissions.json`` cạnh config.json).

Không bao giờ đọc quyền từ thư mục dự án: một repo tải về có thể kèm sẵn tệp cấp quyền để lệnh chạy mà không hỏi, nên
quyền chỉ nằm trên máy người dùng và chỉ được thêm khi chính họ chọn [l] ở câu hỏi đồng ý. Khớp đúng từng chữ của
lệnh, thư mục chạy và shell, không có ký tự đại diện hay khớp phần đầu, để "npm test && …" không lọt qua quyền của
"npm test". Thời hạn không nằm trong khóa: đó chỉ là mức trần và Ctrl+C vẫn dừng được lệnh, còn model đổi thời hạn giữa
các lần chạy thì quyền không nên mất.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import home

VERSION = 1
MAX_PER_PROJECT = 100
MAX_COMMAND_CHARS = 4000
SHELLS = {"cmd", "powershell"}


def _file() -> Path:
    return home() / "permissions.json"


def _key(root: Path) -> str:
    # Windows không phân biệt hoa thường trong đường dẫn: cùng một thư mục phải ra cùng một khóa, như history.
    return os.path.normcase(str(root))


def _projects() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("projects"), dict):
        return {}
    return data["projects"]


def entries(root: Path) -> list[dict]:
    """Các lệnh luôn được cho phép trong dự án này, theo thứ tự thêm; mục hỏng thì bỏ qua."""
    items = _projects().get(_key(root))
    if not isinstance(items, list):
        return []
    return [item for item in items[-MAX_PER_PROJECT:]
            if isinstance(item, dict) and isinstance(item.get("command"), str)
            and isinstance(item.get("directory"), str) and item.get("shell") in SHELLS]


def allowed(root: Path, directory: str, command: str, shell: str) -> bool:
    """``directory`` là thư mục chạy lệnh, tương đối với gốc dự án ("." là gốc)."""
    return any(item["command"] == command and item["directory"] == directory and item["shell"] == shell
               for item in entries(root))


def add(root: Path, directory: str, command: str, shell: str) -> bool:
    """Nhớ một lệnh cho dự án. False khi không ghi được: lần này lệnh vẫn chạy, chỉ là lần sau sẽ hỏi lại."""
    if len(command) > MAX_COMMAND_CHARS or shell not in SHELLS:
        return False
    projects = _projects()
    current = entries(root)
    if not allowed(root, directory, command, shell):
        current.append({"directory": directory, "command": command, "shell": shell, "added_at": round(time.time())})
    projects[_key(root)] = current[-MAX_PER_PROJECT:]
    return _write(projects)


def clear(root: Path) -> int:
    """Bỏ mọi lệnh đã nhớ của dự án này; trả về số lệnh đã bỏ."""
    removed = len(entries(root))
    projects = _projects()
    if projects.pop(_key(root), None) is not None:
        _write(projects)
    return removed


def _write(projects: dict) -> bool:
    path = _file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": VERSION, "projects": projects}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return False
    return True
