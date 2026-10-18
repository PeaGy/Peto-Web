"""Chính sách allow/ask/deny và quyền đã nhớ theo dự án, lưu trong hồ sơ người dùng (permissions.json cạnh config.json).

Từ 0.28.5, shell/edit mặc định allow. Người dùng đổi bằng /permissions; dự án không thể tự cấp quyền từ tệp của repo.
Ở chế độ ask, [l] vẫn chỉ nhớ đúng chuỗi lệnh, thư mục và shell, không có wildcard hay khớp phần đầu. Thời hạn chỉ là
mức trần nên không nằm trong khóa. Quyền deny luôn ưu tiên hơn [l], [s] và [a]. Quyền origin/site vẫn hỏi như trước.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import home
from .atomic_file import write_text

VERSION = 1
MAX_PER_PROJECT = 100
MAX_COMMAND_CHARS = 4000
SHELLS = {"cmd", "powershell", "python"}
POLICY_ACTIONS = ("shell", "edit")
POLICY_EFFECTS = {"allow", "ask", "deny"}


def _file() -> Path:
    return home() / "permissions.json"


def _key(root: Path) -> str:
    # Windows không phân biệt hoa thường trong đường dẫn: cùng một thư mục phải ra cùng một khóa, như history.
    return os.path.normcase(str(root))


def _document() -> dict | None:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": VERSION, "projects": {}}
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("projects"), dict):
        return None
    if "policies" in data and not isinstance(data["policies"], dict):
        return None
    return data


def _projects() -> dict:
    return (_document() or {}).get("projects", {})


def policy(root: Path, action: str) -> str:
    """Mặc định cho phép lệnh và sửa tệp; cấu hình hỏng thì hỏi, không bỏ qua một quyền deny bị mất."""
    if action not in POLICY_ACTIONS:
        raise ValueError(f"Loại quyền không hợp lệ: {action}")
    data = _document()
    if data is None:
        return "ask"
    rules = data.get("policies", {}).get(_key(root), {})
    if not isinstance(rules, dict):
        return "ask"
    effect = rules.get(action, "allow")
    return effect if isinstance(effect, str) and effect in POLICY_EFFECTS else "ask"


def set_policy(root: Path, effect: str, action: str | None = None) -> bool:
    """Cài quyền từ lệnh người dùng, lưu riêng theo dự án trong hồ sơ trên máy."""
    if effect not in POLICY_EFFECTS or (action is not None and action not in POLICY_ACTIONS):
        return False
    data = _document()
    if data is None:
        return False
    policies = data.setdefault("policies", {})
    current = policies.get(_key(root), {})
    current = dict(current) if isinstance(current, dict) else {}
    for target in (action,) if action else POLICY_ACTIONS:
        current[target] = effect
    policies[_key(root)] = current
    return _write_document(data)


def _items(root: Path) -> list[dict]:
    items = _projects().get(_key(root))
    return [item for item in items[-MAX_PER_PROJECT:] if isinstance(item, dict)] if isinstance(items, list) else []


def entries(root: Path) -> list[dict]:
    """Các lệnh luôn được cho phép trong dự án này, theo thứ tự thêm; mục hỏng thì bỏ qua."""
    return [item for item in _items(root)
            if isinstance(item.get("command"), str) and isinstance(item.get("directory"), str)
            and item.get("shell") in SHELLS]


def pages(root: Path) -> list[str]:
    """Các trang (origin, ví dụ http://localhost:5173) Peto luôn được bấm, gõ trong dự án này."""
    return [item["origin"] for item in _items(root) if isinstance(item.get("origin"), str)]


def page_allowed(root: Path, origin: str) -> bool:
    return origin in pages(root)


def sites(root: Path) -> list[str]:
    """Tên miền ngoài máy Peto luôn được xem (chỉ xem) trong dự án này, từ CLI 0.12.0; python.org gồm cả docs.python.org."""
    return [item["site"] for item in _items(root) if isinstance(item.get("site"), str)]


def add_site(root: Path, site: str) -> bool:
    """Nhớ một tên miền cho dự án. False khi không ghi được: lần này vẫn mở, lần sau Peto hỏi lại."""
    if not site or len(site) > 253:
        return False
    items = _items(root)
    if site not in sites(root):
        items.append({"site": site, "added_at": round(time.time())})
    projects = _projects()
    projects[_key(root)] = items[-MAX_PER_PROJECT:]
    return _write(projects)


def add_page(root: Path, origin: str) -> bool:
    """Nhớ một trang cho dự án. False khi không ghi được: lần này vẫn thao tác, lần sau Peto hỏi lại."""
    if not origin or len(origin) > 300:
        return False
    items = _items(root)
    if origin not in pages(root):
        items.append({"origin": origin, "added_at": round(time.time())})
    projects = _projects()
    projects[_key(root)] = items[-MAX_PER_PROJECT:]
    return _write(projects)


def allowed(root: Path, directory: str, command: str, shell: str) -> bool:
    """``directory`` là thư mục chạy lệnh, tương đối với gốc dự án ("." là gốc)."""
    return any(item["command"] == command and item["directory"] == directory and item["shell"] == shell
               for item in entries(root))


def add(root: Path, directory: str, command: str, shell: str) -> bool:
    """Nhớ một lệnh cho dự án. False khi không ghi được: lần này lệnh vẫn chạy, chỉ là lần sau sẽ hỏi lại."""
    if len(command) > MAX_COMMAND_CHARS or shell not in SHELLS:
        return False
    projects = _projects()
    current = _items(root)  # giữ cả các trang đã nhớ
    if not allowed(root, directory, command, shell):
        current.append({"directory": directory, "command": command, "shell": shell, "added_at": round(time.time())})
    projects[_key(root)] = current[-MAX_PER_PROJECT:]
    return _write(projects)


def clear(root: Path) -> int:
    """Xóa quyền đã nhớ và chính sách dự án, trở về mặc định allow; lỗi lưu không báo thành công."""
    removed = len(entries(root)) + len(pages(root)) + len(sites(root))
    data = _document()
    if data is None:
        raise OSError("Không đọc được permissions.json; chưa xóa quyền.")
    changed = _key(root) in data["projects"] or _key(root) in data.get("policies", {})
    data["projects"].pop(_key(root), None)
    data.get("policies", {}).pop(_key(root), None)
    if changed and not _write_document(data):
        raise OSError("Không lưu được permissions.json; chưa xóa quyền.")
    return removed


def _write(projects: dict) -> bool:
    data = _document()
    if data is None:
        return False
    data["projects"] = projects
    return _write_document(data)


def _write_document(data: dict) -> bool:
    path = _file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        return False
    return True
