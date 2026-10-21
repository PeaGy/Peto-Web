"""Sao lưu hồ sơ người dùng khi đổi bản peto (lộ trình nhiều nguồn, M6).

Lần đầu một bản peto khác chạy trên máy (lên hay xuống bản), các tệp cấu hình trong hồ sơ được chép sang
``<hồ sơ>/backups/<thời điểm>-<bản cũ>-to-<bản mới>/`` trước khi bản mới ghi gì vào chúng, rồi ghi bản đang chạy vào
``config.json`` (``cli_version``, ``config_schema``). Giữ 5 bản sao lưu gần nhất.

Vì sao cần: từ 0.32 ``/model`` không còn đổi mặc định và ``config.json`` có thêm yêu thích, gần đây, mặc định riêng; từ
0.33 ``connections.json`` có kết nối ChatGPT và trường ``extra``. Bản cũ hơn đọc được các tệp này (bỏ qua phần không
hiểu) nhưng khi chính nó ghi lại thì phần đó mất. Quay về bản cũ thì chép các tệp trong bản sao lưu về hồ sơ; những gì
thêm sau lúc sao lưu (kết nối mới, mặc định mới) phải làm lại.

Không chép: ``credentials/`` (khóa và token mã hóa DPAPI, mỗi tệp theo mã kết nối và vẫn nằm nguyên chỗ cũ, không nhân
bản bí mật), hội thoại (mỗi tệp tự mang số bản: bản cũ bỏ qua hội thoại bản mới hơn chứ không ghi đè; nhật ký bền giữ
lược đồ 1 từ 0.29) và nhật ký công việc.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import config

# 1: trước 0.32. 2: mặc định riêng với /model, yêu thích/gần đây, connections.json có extra và ChatGPT (0.32–0.33).
SCHEMA = 2
FILES = ("config.json", "connections.json", "permissions.json", "AGENTS.md")
KEEP = 5


def backups_dir() -> Path:
    return config.home() / "backups"


def backup_on_change(version: str) -> Path | None:
    """Sao lưu nếu bản đang chạy khác bản đã ghi trong config.json; trả thư mục sao lưu (None khi không cần hay không
    có gì để chép). Lỗi đĩa không chặn peto: bỏ qua, lần sau thử lại."""
    home = config.home()
    settings = config.load()
    previous = settings.get("cli_version")
    if previous == version and settings.get("config_schema") == SCHEMA:
        return None
    present = [name for name in FILES if (home / name).is_file()]
    target = None
    try:
        if present:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            label = str(previous or "cu").replace("/", "_")[:20]
            target = backups_dir() / f"{stamp}-{label}-to-{version}"
            target.mkdir(parents=True, exist_ok=True)
            for name in present:
                shutil.copy2(home / name, target / name)
        settings = config.load()
        settings["cli_version"] = version
        settings["config_schema"] = SCHEMA
        config.save(settings)
        _prune()
    except OSError:
        return None
    return target


def _prune() -> None:
    folder = backups_dir()
    if not folder.is_dir():
        return
    kept = sorted((path for path in folder.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    for old in kept[KEEP:]:
        shutil.rmtree(old, ignore_errors=True)
