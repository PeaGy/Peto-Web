"""AGENTS.md chung của người dùng (CLI 0.25.0, theo opencode): một tệp hướng dẫn áp cho mọi dự án.

Nằm trong hồ sơ của người dùng, cạnh config.json và permissions.json (``config.home()``), không bao giờ trong thư mục
dự án: một dự án tải về không được tự cài hướng dẫn chung cho người dùng. Mỗi bước đọc lại tệp, nên sửa xong là bước
sau đã dùng bản mới.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import home

# Cùng giới hạn với AGENTS.md của dự án (project_guide.MAX_GUIDE_CHARS).
MAX_CHARS = 32_000


def path() -> Path:
    return home() / "AGENTS.md"


# Chữ sẵn khi tệp chưa có: lưu mà không đổi gì thì không tạo tệp (external_editor.edit trả None).
TEMPLATE = ("# Hướng dẫn chung cho Peto\n\n"
            "<!-- Viết ở đây những gì Peto nên theo ở mọi dự án: cách xưng hô, trình quản lý gói, quy ước commit… "
            "AGENTS.md của từng dự án vẫn được ưu tiên về quy ước code. Peto đọc lại tệp này ở mỗi bước. -->\n")


def write(text: str) -> None:
    """Ghi tệp hướng dẫn chung qua tệp tạm rồi thay một lần, để tệp không bao giờ dở dang."""
    if len(text) > MAX_CHARS:
        raise ValueError(f"Hướng dẫn chung vượt {MAX_CHARS:,} ký tự; rút gọn rồi lưu lại.".replace(",", "."))
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, target)


def read() -> tuple[str, str | None]:
    """Nội dung để gửi kèm bước, và lời báo khi không gửi được (dài quá, đọc lỗi). Chưa có tệp thì ("", None)."""
    target = path()
    try:
        text = target.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return "", None
    except (OSError, UnicodeDecodeError):
        return "", f"Không đọc được hướng dẫn chung {target}; gõ /guide để sửa."
    if len(text) > MAX_CHARS:
        return "", f"Hướng dẫn chung dài quá {MAX_CHARS:,} ký tự nên chưa gửi cho Peto; gõ /guide để rút gọn.".replace(",", ".")
    return text.strip(), None
