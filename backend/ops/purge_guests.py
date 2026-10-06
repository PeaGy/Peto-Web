"""Xóa sạch dữ liệu của các tài khoản khách cũ (owner ``guest:…``).

Ngày 6/10/2026 chủ web bỏ đăng nhập khách (thay bằng GitHub). Khóa ``guest:`` không còn đăng nhập được nữa, nên dữ liệu
của chúng không ai mở lại được: lệnh này dọn nó. Mặc định chỉ đếm (chạy thử); thêm ``--yes`` mới xóa.

Xóa mọi hàng có cột ``owner`` bắt đầu bằng ``guest:`` ở mọi bảng (tin nhắn, phiên bản tài liệu, tệp dự án… đi theo bằng
khóa ngoại ON DELETE CASCADE), rồi xóa tệp tải lên và ảnh tạo của chúng nằm trong thư mục tải lên. Tệp ngoài thư mục đó
không bao giờ bị đụng. Nên chạy ``ops.backup`` trước.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

GUEST = "guest:%"
FILE_TABLES = ("attachments", "imagine_images")


def owner_tables(db) -> list[str]:
    names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return [name for name in names
            if any(column[1] == "owner" for column in db.execute(f'PRAGMA table_info("{name}")'))]


def plan(db) -> tuple[dict[str, int], list[str]]:
    """(số hàng của khách theo bảng, đường dẫn tệp của khách)."""
    counts = {}
    for name in owner_tables(db):
        count = db.execute(f'SELECT COUNT(*) FROM "{name}" WHERE owner LIKE ?', (GUEST,)).fetchone()[0]
        if count:
            counts[name] = count
    paths = []
    for name in FILE_TABLES:
        if name in counts:
            paths += [row[0] for row in db.execute(f'SELECT path FROM "{name}" WHERE owner LIKE ?', (GUEST,))]
    return counts, paths


def _inside(path: str, root: Path) -> Path | None:
    target = Path(path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def purge(db_path: Path, uploads: Path) -> tuple[dict[str, int], int, int]:
    """Xóa thật. Trả về (hàng đã xóa theo bảng, số tệp đã xóa, số tệp bỏ qua vì nằm ngoài thư mục tải lên)."""
    with closing(sqlite3.connect(db_path, timeout=30)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        counts, paths = plan(db)
        with db:
            # Bảng con trước bảng cha cũng được: khóa ngoại tự xóa phần còn lại.
            for name in counts:
                db.execute(f'DELETE FROM "{name}" WHERE owner LIKE ?', (GUEST,))
    removed = skipped = 0
    for path in paths:
        target = _inside(path, uploads)
        if target is None:
            skipped += 1
            continue
        try:
            target.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return counts, removed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Xóa dữ liệu của tài khoản khách cũ.")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument("--yes", action="store_true", help="Xóa thật. Thiếu cờ này thì chỉ đếm.")
    args = parser.parse_args()
    from core.config import DB_PATH, UPLOAD_DIR
    db_path, uploads = args.db or DB_PATH, args.uploads or UPLOAD_DIR
    if not db_path.is_file():
        print(f"Không thấy database: {db_path}")
        return 1
    try:
        if not args.yes:
            with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                counts, paths = plan(db)
            if not counts:
                print("Không còn dữ liệu khách nào.")
                return 0
            print("Chạy thử, chưa xóa gì. Dữ liệu khách sẽ bị xóa:")
            for name, count in counts.items():
                print(f"  {name}: {count} hàng (kèm hàng con theo khóa ngoại)")
            print(f"  tệp tải lên và ảnh: {len(paths)}")
            print("Chạy lại với --yes để xóa. Nên sao lưu bằng ops.backup trước.")
            return 0
        counts, removed, skipped = purge(db_path, uploads)
        print(f"Đã xóa {sum(counts.values())} hàng ở {len(counts)} bảng và {removed} tệp của tài khoản khách.")
        if skipped:
            print(f"Bỏ qua {skipped} tệp nằm ngoài thư mục tải lên.")
        return 0
    except (OSError, sqlite3.Error) as error:
        print(f"Không dọn được dữ liệu khách: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
