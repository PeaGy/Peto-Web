"""One bounded local checkpoint per project, atomically replaced; never sent to the model."""
import hashlib
import json
import os
import tempfile
import time

from .config import log_dir
from .workspace import WorkspaceError

MAX_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_AGE = 30 * 86400


def folder():
    return log_dir().parent / "checkpoints"


def path_for(root):
    key = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()
    return folder() / f"{key}.json"


def prune(keep=None):
    base = folder().resolve()
    entries = []
    if not base.exists():
        return
    # A killed process may leave its temporary file behind. Never touch fresh writers or linked paths.
    for path in base.glob(".checkpoint-*"):
        if (path.is_file() and not path.is_symlink() and path.resolve().parent == base
                and time.time() - path.stat().st_mtime > 86400):
            path.unlink()
    for path in base.glob("*.json"):
        if path.is_symlink() or path.resolve().parent != base:
            continue
        stat = path.stat()
        if time.time() - stat.st_mtime > MAX_AGE and path != keep:
            path.unlink()
        else:
            entries.append((stat.st_mtime, path, stat.st_size))
    total = sum(entry[2] for entry in entries)
    for _, path, size in sorted(entries):
        if total <= MAX_TOTAL_BYTES:
            break
        if path != keep:
            path.unlink()
            total -= size


def save(root, files, shell_used):
    target = path_for(root)
    body = json.dumps({"version": 1, "root": str(root), "files": files,
                       "shell_used": shell_used}, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_BYTES:
        raise WorkspaceError("Bản hoàn tác vượt 16 MB. Chia yêu cầu thành các phần nhỏ hơn trước khi sửa tiếp.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".checkpoint-", delete=False) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    try:
        prune(keep=target.resolve())
    except OSError:
        pass  # Retention failure must not invalidate a successfully saved checkpoint.


def load(root):
    target = path_for(root)
    try:
        prune()
        if not target.exists():
            return None
        if target.is_symlink() or target.stat().st_size > MAX_BYTES:
            raise ValueError("invalid file")
        data = json.loads(target.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("version") != 1
                or os.path.normcase(str(data.get("root"))) != os.path.normcase(str(root))):
            raise ValueError("invalid header")
        return data
    except (ValueError, OSError) as err:
        raise WorkspaceError("Không đọc được bản hoàn tác đã lưu; không khôi phục tệp nào.") from err
