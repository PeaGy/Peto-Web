"""Hội thoại gần nhất của từng thư mục dự án, lưu trên máy người dùng để /resume mở lại.

- Mỗi thư mục một tệp trong ``sessions/`` (cạnh ``logs/``), ghi đè sau mỗi yêu cầu. Tệp cũ hơn 30 ngày được dọn.
- Tệp chứa cả nội dung tệp Peto đã đọc và output lệnh, nên chỉ nằm trên máy này. Không bao giờ chứa token.
- Mở lại không chạy lại gì. CLI quên các tệp đã đọc, nên muốn sửa tệp thì Peto phải đọc lại trước.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import sessions_dir

VERSION = 1
MAX_AGE_SECONDS = 30 * 24 * 3600
ITEM_TYPES = {"message", "function_call", "function_call_output", "reasoning"}
RECAP_CHARS = 160


@dataclass(frozen=True)
class Saved:
    saved_at: float
    items: list[dict]

    @property
    def message_count(self) -> int:
        return sum(1 for item in self.items if item.get("type", "message") == "message")


def _path(root: Path) -> Path:
    # Windows không phân biệt hoa thường trong đường dẫn: cùng một thư mục phải ra cùng một tệp.
    key = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()[:24]
    return sessions_dir() / f"{key}.json"


def save(root: Path, server: str, items: list[dict]) -> None:
    """Ghi đè hội thoại của thư mục. Ghi đĩa lỗi thì bỏ qua: mất bản lưu không được làm hỏng phiên đang chạy."""
    if not items:
        return
    target = _path(root)
    data = {"version": VERSION, "root": str(root), "server": server, "saved_at": time.time(), "items": items}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        return
    _prune(target)


def load(root: Path, server: str) -> Saved | None:
    """Hội thoại đã lưu của đúng thư mục và máy chủ này; không có, hỏng hay khác phiên bản thì None."""
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION or data.get("server") != server:
        return None
    if os.path.normcase(str(data.get("root") or "")) != os.path.normcase(str(root)):
        return None
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    if not all(isinstance(item, dict) and item.get("type", "message") in ITEM_TYPES for item in items):
        return None
    saved_at = data.get("saved_at")
    return Saved(saved_at=float(saved_at) if isinstance(saved_at, (int, float)) else 0.0, items=items)


def _prune(keep: Path) -> None:
    cutoff = time.time() - MAX_AGE_SECONDS
    try:
        for path in keep.parent.glob("*.json"):
            if path != keep and path.stat().st_mtime < cutoff:
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


def _text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, list):
        parts = [str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("text")]
        # Tin kèm ảnh của người dùng: phần đầu là chữ đã gõ, sau đó là nhãn và ảnh.
        content = parts[0] if item.get("role") == "user" and parts else " ".join(parts)
    text = " ".join(str(content or "").split())
    return text if len(text) <= RECAP_CHARS else text[: RECAP_CHARS - 1] + "…"


def recap(items: list[dict]) -> list[tuple[str, str]]:
    """Tin cuối của người dùng và câu trả lời cuối sau nó, để nhớ đang làm tới đâu."""
    messages = [item for item in items if item.get("type", "message") == "message"]
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") != "user":
            continue
        lines = [("Bạn", _text(messages[index]))]
        replies = [item for item in messages[index + 1:] if item.get("role") == "assistant" and _text(item)]
        if replies:
            lines.append(("Peto", _text(replies[-1])))
        return lines
    return []
