"""Sao lưu dữ liệu và diễn tập khôi phục, không ghi đè dữ liệu đang dùng."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile

FORMAT = "peto-data-v1"
ARCHIVE_NAME = re.compile(r"peto-data-\d{8}T\d{12}Z-[0-9a-f]{8}\.zip\Z")


def readonly(path: Path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def table_counts(db) -> dict[str, int]:
    names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}


def check_database(path: Path) -> dict[str, int]:
    with closing(readonly(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Database không vượt qua kiểm tra toàn vẹn.")
        counts = table_counts(db)
        if not {"conversations", "messages"} <= counts.keys():
            raise ValueError("Đây không phải database hội thoại Peto.")
        return counts


def references(db):
    tables = table_counts(db)
    for table in ("attachments", "imagine_images"):
        if table in tables:
            yield table, db.execute(f"SELECT rowid, path FROM {table}").fetchall()


def relative_upload(raw: str, root: Path) -> Path:
    path = Path(raw).resolve()
    try:
        return path.relative_to(root.resolve())
    except ValueError:
        raise ValueError("Database tham chiếu tệp ngoài thư mục tải lên; cần sửa cấu hình trước khi sao lưu.") from None


def check_references(db_path: Path, upload_root: Path) -> None:
    with closing(readonly(db_path)) as db:
        for _, rows in references(db):
            for _, raw in rows:
                relative = relative_upload(raw, upload_root)
                if not (upload_root / relative).is_file():
                    raise ValueError("Có tệp đính kèm hoặc ảnh trong database bị thiếu trên đĩa.")


def create_backup(db_path: Path, uploads: Path, output: Path, *, offline: bool, keep: int = 7) -> Path:
    """Người chạy phải dừng mọi tiến trình ghi dữ liệu trước khi gọi."""
    if not offline:
        raise ValueError("Dừng Peto và mọi tiến trình ghi dữ liệu, rồi thêm --offline.")
    if keep < 1:
        raise ValueError("Số bản giữ lại phải từ 1 trở lên.")
    db_path, uploads, output = db_path.resolve(), uploads.resolve(), output.resolve()
    if not db_path.is_file():
        raise ValueError("Không tìm thấy database; không tạo bản sao rỗng.")
    if uploads.exists() and not uploads.is_dir():
        raise ValueError("Đường dẫn tải lên phải là thư mục.")
    if output == uploads or uploads in output.parents or output == db_path.parent:
        raise ValueError("Đặt thư mục sao lưu bên ngoài thư mục dữ liệu đang dùng.")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = output / ".peto-backup-lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError("Đang có lượt sao lưu khác hoặc khóa cũ chưa được xử lý.") from None
    partial = None
    try:
        with tempfile.TemporaryDirectory(prefix="peto-backup-", dir=output) as folder:
            snapshot = Path(folder) / "peto_web.db"
            with closing(readonly(db_path)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            counts = check_database(snapshot)
            check_references(snapshot, uploads)
            files = {"database/peto_web.db": snapshot}
            if uploads.exists():
                for path in uploads.rglob("*"):
                    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                        raise ValueError("Không sao lưu liên kết tượng trưng hoặc junction trong thư mục tải lên.")
                    if path.is_file():
                        files["uploads/" + path.relative_to(uploads).as_posix()] = path
            manifest = {
                "format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                "upload_root": str(uploads), "tables": counts,
                "files": {name: {"size": path.stat().st_size, "sha256": digest(path)} for name, path in files.items()},
            }
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            final = output / f"peto-data-{stamp}-{uuid.uuid4().hex[:8]}.zip"
            partial = final.with_suffix(".partial")
            with partial.open("xb") as stream:
                os.chmod(partial, 0o600)
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, path in files.items():
                        archive.write(path, name)
                    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
                stream.flush()
                os.fsync(stream.fileno())
            verify_backup(partial)
            partial.rename(final)
        # Chỉ bỏ bản cũ do công cụ này tạo, sau khi bản mới kiểm tra thành công.
        older = sorted((p for p in output.iterdir() if ARCHIVE_NAME.fullmatch(p.name) and not p.is_symlink()), reverse=True)
        for path in older[keep:]:
            verify_backup(path)
            path.unlink()
        return final
    finally:
        if partial is not None and partial.exists():
            partial.unlink()
        lock.rmdir()


def unpack_verified(archive_path: Path, destination: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("Bản sao có tên tệp trùng hoặc thiếu danh sách kiểm tra.")
        if archive.getinfo("manifest.json").file_size > 16 * 1024 * 1024:
            raise ValueError("Danh sách kiểm tra quá lớn.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), dict):
            raise ValueError("Định dạng bản sao không được hỗ trợ.")
        files = manifest["files"]
        if set(names) != set(files) | {"manifest.json"} or "database/peto_web.db" not in files:
            raise ValueError("Danh sách tệp trong bản sao không khớp.")
        case_names = set()
        for name, info in files.items():
            path = PurePosixPath(name)
            if (path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/"))
                    or "\\" in name or ":" in name or not name.startswith(("database/", "uploads/"))
                    or name.casefold() in case_names):
                raise ValueError("Bản sao chứa đường dẫn không an toàn.")
            case_names.add(name.casefold())
            entry = archive.getinfo(name)
            if entry.file_size != info["size"] or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Kích thước hoặc loại tệp trong bản sao không hợp lệ.")
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(name) as source, target.open("xb") as output:
                os.chmod(target, 0o600)
                shutil.copyfileobj(source, output)
            if digest(target) != info["sha256"]:
                raise ValueError("Bản sao bị hỏng: mã kiểm tra tệp không khớp.")
    database = destination / "database/peto_web.db"
    if check_database(database) != manifest["tables"]:
        raise ValueError("Số dòng trong database không khớp bản sao.")
    old_root = Path(manifest["upload_root"])
    with closing(readonly(database)) as db:
        for _, rows in references(db):
            for _, raw in rows:
                relative = relative_upload(raw, old_root)
                if not (destination / "uploads" / relative).is_file():
                    raise ValueError("Bản sao thiếu tệp mà database tham chiếu.")
    return manifest


def verify_backup(archive_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="peto-verify-") as folder:
        return unpack_verified(archive_path, Path(folder))


def restore_backup(archive_path: Path, destination: Path) -> dict:
    """Diễn tập vào thư mục mới; đổi đường dẫn tệp trong bản database được khôi phục."""
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Chỉ khôi phục vào thư mục mới, không ghi đè dữ liệu hiện có.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="peto-restore-", dir=destination.parent) as folder:
        stage = Path(folder) / "result"
        stage.mkdir(mode=0o700)
        manifest = unpack_verified(archive_path, stage)
        database = stage / "database/peto_web.db"
        with closing(sqlite3.connect(database)) as db:
            for table, rows in references(db):
                for rowid, raw in rows:
                    new_path = destination / "uploads" / relative_upload(raw, Path(manifest["upload_root"]))
                    db.execute(f"UPDATE {table} SET path=? WHERE rowid=?", (str(new_path), rowid))
            db.commit()
        (stage / "uploads").mkdir(exist_ok=True, mode=0o700)
        stage.rename(destination)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Sao lưu và diễn tập khôi phục dữ liệu Peto.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Sao lưu khi mọi tiến trình ghi dữ liệu đã dừng.")
    create.add_argument("--db", type=Path)
    create.add_argument("--uploads", type=Path)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--offline", action="store_true")
    create.add_argument("--keep", type=int, default=7)
    verify = commands.add_parser("verify", help="Kiểm tra toàn bộ bản sao.")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="Khôi phục vào thư mục mới để kiểm tra.")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            from core.config import DB_PATH, UPLOAD_DIR
            result = create_backup(args.db or DB_PATH, args.uploads or UPLOAD_DIR, args.output, offline=args.offline, keep=args.keep)
            print(f"Đã sao lưu và kiểm tra thành công: {result}")
        elif args.command == "verify":
            manifest = verify_backup(args.archive)
            print(f"Bản sao hợp lệ: {len(manifest['files'])} tệp, {len(manifest['tables'])} bảng.")
        else:
            restore_backup(args.archive, args.destination)
            print(f"Đã khôi phục vào thư mục riêng: {args.destination.resolve()}")
        return 0
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, KeyError, TypeError) as error:
        print(f"Không hoàn thành thao tác sao lưu: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
