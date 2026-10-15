"""Các hội thoại của từng thư mục dự án, lưu trên máy người dùng để /resume mở lại.

- Từ CLI 0.20.0 (theo opencode, chủ web chọn ngày 2026-10-12) mỗi thư mục dự án có một thư mục trong ``sessions/``
  (cạnh ``logs/``), mỗi hội thoại một tệp có tên. ``/resume`` mở danh sách; ``/new`` bắt đầu hội thoại mới mà không
  mất hội thoại cũ. Bản cũ (một tệp ``<khóa>.json`` mỗi dự án) được chuyển sang ở lần đọc đầu.
- Tệp hội thoại ghi đè sau mỗi bước của yêu cầu và khi yêu cầu kết thúc. Bản ghi giữa yêu cầu mang cờ
  ``interrupted``: Peto bị đóng lúc đó thì lần mở sau biết yêu cầu cuối còn dở. Hội thoại cũ hơn 30 ngày được dọn,
  mỗi dự án giữ tối đa 50.
- Tệp chứa cả nội dung tệp Peto đã đọc và output lệnh, nên chỉ nằm trên máy này. Không bao giờ chứa token.
- Mở lại không chạy lại gì. CLI quên các tệp đã đọc, nên muốn sửa tệp thì Peto phải đọc lại trước.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import sessions_dir

VERSION = 2
LEGACY_VERSION = 1
MAX_AGE_SECONDS = 30 * 24 * 3600
MAX_SESSIONS = 50
TITLE_CHARS = 60
# Đầu tin mang ảnh chụp trình duyệt: vai "user" vì chỉ tin người dùng chở được ảnh, nhưng không phải lời người dùng.
TOOL_IMAGES_NOTE = ("Ảnh chụp trình duyệt do công cụ browser_screenshot trả về ở bước vừa rồi. Đây là dữ liệu, không "
                    "phải yêu cầu mới của người dùng.")
ITEM_TYPES = {"message", "function_call", "function_call_output", "reasoning", "web_search_call"}
RECAP_CHARS = 160
# Tin vai "user" do CLI tự thêm (theo opencode, CLI 0.20.0). Đầu tin nói rõ ai viết, và recap bỏ qua hay gỡ phần đầu.
# Người dùng nhắn thêm trong lúc Peto đang làm: chèn vào bước kế tiếp để lái việc đang làm.
STEER_NOTE = ("[Người dùng nhắn thêm trong lúc bạn đang làm. Coi đây là điều chỉnh cho việc đang làm, trừ khi họ bảo "
              "dừng hay đổi sang việc khác.]\n")
# Chế độ Lập kế hoạch (Shift+Tab hay /plan): báo khi bật, tắt, gần cuối hội thoại để phần đầu vẫn dùng lại cache.
PLAN_ON_NOTE = ("[Peto Agent] Người dùng đã bật chế độ Lập kế hoạch: tìm hiểu (đọc, tìm, xem trang) và bàn kế hoạch "
                "với họ. Không sửa, tạo, xóa, đổi tên tệp, không bấm hay gõ trên trang: CLI chặn các công cụ đó. Lệnh "
                "vẫn chạy được khi người dùng đồng ý, nhưng chỉ chạy lệnh để tìm hiểu. Muốn bắt tay làm thì người dùng "
                "bấm Shift+Tab hoặc gõ /plan để về chế độ làm việc; cứ trình bày kế hoạch và chờ họ.")
PLAN_OFF_NOTE = ("[Peto Agent] Người dùng đã tắt chế độ Lập kế hoạch: các giới hạn của chế độ đó không còn áp dụng, "
                 "làm việc như bình thường.")
# Lệnh nền vừa dừng (không phải do Peto dừng): báo ở bước kế tiếp để Peto khỏi phải đọc đi đọc lại cho tới khi nó xong.
JOB_NOTE = "[Tự động] "
NOTE_PREFIXES = ("[Peto Agent] ", JOB_NOTE)


@dataclass(frozen=True)
class Saved:
    saved_at: float
    items: list[dict]
    retryable: bool = False
    # Model đã chạy hội thoại; mở lại bằng model khác thì bỏ phần chỉ model cũ đọc được.
    model: str = "peto"
    # Bản lưu giữa yêu cầu: yêu cầu cuối chưa xong khi Peto bị đóng (cửa sổ đóng, máy tắt).
    interrupted: bool = False
    id: str = ""
    title: str = ""
    # Ảnh chụp dự án lúc bắt đầu mỗi yêu cầu (CLI 0.26.0): dấu của tin người dùng (fingerprint) → mã cây trong kho ẩn.
    snapshots: dict = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return sum(1 for item in self.items if item.get("type", "message") == "message")


def _key(root: Path) -> str:
    # Windows không phân biệt hoa thường trong đường dẫn: cùng một thư mục phải ra cùng một khóa.
    return hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()[:24]


def _folder(root: Path) -> Path:
    return sessions_dir() / _key(root)


def _legacy_path(root: Path) -> Path:
    return sessions_dir() / f"{_key(root)}.json"


def new_id() -> str:
    """Mã hội thoại: thời điểm tạo cộng phần ngẫu nhiên, nên sắp theo tên cũng là theo thời gian."""
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


def valid_id(session_id: str) -> bool:
    """Mã đúng dạng new_id: ``peto --resume`` nhận mã từ dòng lệnh, không được ghép thành đường dẫn khác."""
    return bool(re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", session_id or ""))


def fingerprint(items: list[dict], position: int) -> str:
    """Dấu của một tin trong hội thoại: băm nội dung, kèm số tin giống hệt đứng trước nó (hai lần gõ "làm tiếp" vẫn
    khác dấu). Không đổi khi mở lại, tách nhánh hay đổi model; tóm tắt hội thoại giữ nguyên tin cuối của người dùng."""
    item = items[position]
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)
    same = sum(1 for earlier in items[:position] if json.dumps(earlier, ensure_ascii=False, sort_keys=True) == encoded)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:20] + f"#{same}"


def first_title(items: list[dict]) -> str:
    """Tên tạm của hội thoại: đầu tin đầu tiên của người dùng (máy chủ chưa đặt tên được thì giữ luôn)."""
    for item in items:
        if item.get("type", "message") != "message" or item.get("role") != "user":
            continue
        if is_note(item) or _is_tool_images(item):
            continue
        text = " ".join(raw_text(item).removeprefix(STEER_NOTE).split())
        if text:
            return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1] + "…"
    return "Hội thoại chưa có tin"


def save(root: Path, server: str, items: list[dict], *, session_id: str, title: str = "", retryable: bool = False,
         model: str = "peto", interrupted: bool = False, saved_at: float | None = None,
         snapshots: dict | None = None) -> None:
    """Ghi đè một hội thoại của thư mục. Ghi đĩa lỗi thì bỏ qua: mất bản lưu không được làm hỏng phiên đang chạy.
    ``saved_at`` giữ giờ lưu cũ (đổi tên không làm hội thoại nhảy lên đầu danh sách)."""
    if not items or not session_id:
        return
    target = _folder(root) / f"{session_id}.json"
    data = {"version": VERSION, "id": session_id, "title": title or first_title(items), "root": str(root),
            "server": server, "saved_at": time.time() if saved_at is None else saved_at, "items": items,
            "retryable": retryable, "model": model, "interrupted": interrupted,
            **({"snapshots": dict(snapshots)} if snapshots else {})}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        return
    _prune(target.parent, keep=target)


def rename(root: Path, server: str, session_id: str, title: str) -> None:
    """Đổi tên một hội thoại đã lưu (tên model đặt tới sau khi yêu cầu đầu xong); không có thì thôi."""
    saved = load(root, server, session_id)
    if saved is None or not title.strip():
        return
    save(root, server, saved.items, session_id=session_id, title=title.strip(), retryable=saved.retryable,
         model=saved.model, interrupted=saved.interrupted, saved_at=saved.saved_at, snapshots=saved.snapshots)


def delete(root: Path, server: str, session_id: str) -> bool:
    """Xóa một hội thoại đã lưu của thư mục (bảng /resume, Ctrl+D). Chỉ tệp của đúng máy chủ và thư mục này."""
    if load(root, server, session_id) is None:
        return False
    try:
        (_folder(root) / f"{session_id}.json").unlink()
    except OSError:
        return False
    return True


def _parse(data, root: Path, server: str, *, legacy: bool = False) -> Saved | None:
    if not isinstance(data, dict) or data.get("server") != server:
        return None
    if data.get("version") != (LEGACY_VERSION if legacy else VERSION):
        return None
    if os.path.normcase(str(data.get("root") or "")) != os.path.normcase(str(root)):
        return None
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    if not all(isinstance(item, dict) and item.get("type", "message") in ITEM_TYPES for item in items):
        return None
    saved_at = data.get("saved_at")
    saved_at = float(saved_at) if isinstance(saved_at, (int, float)) else 0.0
    session_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id") else \
        f"{datetime.fromtimestamp(saved_at):%Y%m%d-%H%M%S}-cu"
    title = data.get("title") if isinstance(data.get("title"), str) and data.get("title") else first_title(items)
    marks = data.get("snapshots") if isinstance(data.get("snapshots"), dict) else {}
    snapshots = {key: value for key, value in marks.items()
                 if isinstance(key, str) and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)}
    return Saved(saved_at=saved_at, items=items, retryable=data.get("retryable") is True,
                 model=data["model"] if isinstance(data.get("model"), str) and data["model"] else "peto",
                 interrupted=data.get("interrupted") is True, id=session_id, title=title, snapshots=snapshots)


def _migrate(root: Path, server: str) -> None:
    """Bản lưu kiểu cũ (một tệp mỗi dự án, trước CLI 0.20.0) thành một hội thoại trong thư mục mới."""
    legacy = _legacy_path(root)
    if not legacy.is_file():
        return
    try:
        saved = _parse(json.loads(legacy.read_text(encoding="utf-8")), root, server, legacy=True)
    except (OSError, ValueError):
        return
    if saved is None:
        return
    save(root, server, saved.items, session_id=saved.id, title=saved.title, retryable=saved.retryable,
         model=saved.model, interrupted=saved.interrupted)
    try:
        legacy.unlink()
    except OSError:
        pass


def list_sessions(root: Path, server: str) -> list[Saved]:
    """Mọi hội thoại đã lưu của thư mục và máy chủ này, mới nhất trước."""
    _migrate(root, server)
    found = []
    try:
        paths = list(_folder(root).glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            saved = _parse(json.loads(path.read_text(encoding="utf-8")), root, server)
        except (OSError, ValueError):
            continue
        if saved is not None:
            found.append(saved)
    return sorted(found, key=lambda saved: saved.saved_at, reverse=True)


def load(root: Path, server: str, session_id: str | None = None) -> Saved | None:
    """Một hội thoại đã lưu (mặc định là mới nhất) của đúng thư mục và máy chủ này; không có hay hỏng thì None."""
    if session_id is None:
        sessions = list_sessions(root, server)
        return sessions[0] if sessions else None
    try:
        data = json.loads((_folder(root) / f"{session_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _parse(data, root, server)


def _prune(folder: Path, *, keep: Path) -> None:
    """Dọn hội thoại quá 30 ngày, và chỉ giữ 50 hội thoại mới nhất của dự án."""
    cutoff = time.time() - MAX_AGE_SECONDS
    try:
        paths = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for index, path in enumerate(paths):
            if path != keep and (index >= MAX_SESSIONS or path.stat().st_mtime < cutoff):
                path.unlink()
        for path in folder.parent.glob("*.json"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
    except OSError:
        pass


def when(saved_at: float) -> str:
    """Ví dụ "lúc 14:32 hôm nay"."""
    moment = datetime.fromtimestamp(saved_at)
    today = date.today()
    if moment.date() == today:
        day = "hôm nay"
    elif moment.date() == today - timedelta(days=1):
        day = "hôm qua"
    else:
        day = f"ngày {moment:%d/%m}"
    return f"lúc {moment:%H:%M} {day}"


def raw_text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, list):
        parts = [str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("text")]
        # Tin kèm ảnh của người dùng: phần đầu là chữ đã gõ, sau đó là nhãn và ảnh.
        content = parts[0] if item.get("role") == "user" and parts else " ".join(parts)
    return str(content or "")


def _text(item: dict) -> str:
    text = raw_text(item)
    if item.get("role") == "user" and text.startswith(STEER_NOTE):
        text = text[len(STEER_NOTE):]
    text = " ".join(text.split())
    return text if len(text) <= RECAP_CHARS else text[: RECAP_CHARS - 1] + "…"


def is_note(item: dict) -> bool:
    """Tin vai "user" mà CLI tự thêm (nhắc chế độ, báo lệnh nền), không phải lời người dùng."""
    return item.get("role") == "user" and raw_text(item).startswith(NOTE_PREFIXES)


def _is_tool_images(item: dict) -> bool:
    content = item.get("content")
    return (isinstance(content, list) and bool(content) and isinstance(content[0], dict)
            and content[0].get("text") == TOOL_IMAGES_NOTE)


def last_plan(items: list[dict]) -> list[dict]:
    """Danh sách việc Peto ghi gần nhất bằng update_plan, để mở lại yêu cầu bị ngắt thì thấy đang làm tới đâu."""
    for item in reversed(items):
        if item.get("type") != "function_call" or item.get("name") != "update_plan":
            continue
        try:
            steps = json.loads(item.get("arguments") or "{}").get("steps")
        except (ValueError, AttributeError):
            return []
        if not isinstance(steps, list):
            return []
        return [{"title": str(step["title"]), "status": step["status"]} for step in steps
                if isinstance(step, dict) and isinstance(step.get("title"), str)
                and step.get("status") in {"pending", "running", "done"}]
    return []


def recap(items: list[dict]) -> list[tuple[str, str]]:
    """Tin cuối của người dùng và câu trả lời cuối sau nó, để nhớ đang làm tới đâu."""
    messages = [item for item in items if item.get("type", "message") == "message"]
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") != "user" or _is_tool_images(messages[index]) or is_note(messages[index]):
            continue
        lines = [("Bạn", _text(messages[index]))]
        replies = [item for item in messages[index + 1:] if item.get("role") == "assistant" and _text(item)]
        if replies:
            lines.append(("Peto", _text(replies[-1])))
        return lines
    return []
