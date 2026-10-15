"""Ảnh chụp dự án bằng một kho git ẩn (CLI 0.26.0, theo snapshot.ts và revert.ts của opencode).

Bản hoàn tác (checkpoint.py) chỉ biết những lần Peto tự sửa tệp. Nhật ký thật của chủ web có 10/68 lệnh đổi tệp mà
/undo không thấy: dotnet ef migrations add, dotnet add package, copy, Copy-Item, del. Ở đây Peto chụp cả dự án trước và
sau mỗi lệnh, so hai ảnh để biết lệnh đã đổi tệp nào và nội dung trước, sau của chúng; các thay đổi đó vào bản hoàn tác
như lần Peto tự sửa. Ảnh đầu mỗi yêu cầu được nhớ theo tin của người dùng, để khôi phục tệp về lúc trước một tin cũ.

- Kho ẩn nằm trong hồ sơ người dùng (%LOCALAPPDATA%\\PetoAgent\\snapshots\\<khóa dự án>), chạy git với --git-dir trỏ
  vào đó và --work-tree là gốc dự án. Không bao giờ đụng .git của dự án, không bao giờ checkout vào thư mục dự án:
  khôi phục là Peto tự ghi từng tệp qua bản hoàn tác.
- Chạy được cả với thư mục chưa phải kho git, miễn máy có git. Không có git thì tắt, như trước 0.26.0.
- Bỏ qua: .gitignore của dự án (git tự đọc), info/exclude của kho ẩn (thư mục nặng và tệp bí mật của workspace.py,
  nên .env và khóa không bao giờ bị chép ra kho), tệp trên MAX_FILE_BYTES và symlink.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import log_dir
from .workspace import BLOCKED_FILE_PATTERNS, SKIPPED_DIRS

# Như opencode: tệp lớn hơn thế không chụp (thường là dữ liệu, ảnh, gói build).
MAX_FILE_BYTES = 2 * 1024 * 1024
# Mỗi lệnh git tối đa ngần này giây; quá giờ thì tắt ảnh chụp cho phiên. Băm tệp (update-index) được lâu hơn: lần chụp
# đầu ở một dự án băm cả dự án (Peto-Web, khoảng 950 tệp: 7–10 giây trên máy chủ web; các lần sau dưới nửa giây).
GIT_TIMEOUT = 20
HASH_TIMEOUT = 120
# Lần chụp đầu thấy quá nhiều tệp thì thôi, khỏi làm chậm mọi lệnh.
MAX_FILES = 50_000
GC_EVERY = 24 * 3600
KEEP_DAYS = 30
EXCLUDES = [f"/{name}/" if name == ".git" else f"{name}/" for name in sorted(SKIPPED_DIRS)] + list(BLOCKED_FILE_PATTERNS)


class SnapshotError(RuntimeError):
    pass


def folder() -> Path:
    return log_dir().parent / "snapshots"


def project_key(root: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:24]


class Snapshots:
    """Ảnh chụp của một dự án trong một phiên. ``available`` false là đã tắt (không có git, lỗi, quá lớn)."""

    def __init__(self, root: Path, *, git: str | None = None):
        self.root = Path(root)
        self.git = git if git is not None else shutil.which("git")
        self.dir = folder() / project_key(self.root)
        self.problem: str | None = None if self.git else "Máy chưa có git nên /undo chỉ gồm những lần Peto tự sửa tệp."
        self._ready = False
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.git is not None and self.problem is None

    def _git(self, *args: str, data: bytes | None = None, timeout: float = GIT_TIMEOUT) -> bytes:
        command = [self.git, f"--git-dir={self.dir}", f"--work-tree={self.root}", "-c", "core.autocrlf=false",
                   "-c", "core.safecrlf=false", "-c", "core.quotepath=false", "-c", "core.longpaths=true",
                   "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "core.hooksPath=", *args]
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
            env.pop(name, None)
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        try:
            done = subprocess.run(command, input=data, capture_output=True, timeout=timeout, cwd=self.root, env=env,
                                  **options)
        except subprocess.TimeoutExpired as err:
            raise SnapshotError(f"git chạy quá {int(timeout)} giây") from err
        except OSError as err:
            raise SnapshotError(f"không chạy được git: {err.strerror or type(err).__name__}") from err
        if done.returncode != 0:
            raise SnapshotError(done.stderr.decode("utf-8", errors="replace").strip()[:300] or "git báo lỗi")
        return done.stdout

    def _prepare(self) -> None:
        if self._ready:
            return
        if not (self.dir / "HEAD").exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            self._git("init", "--quiet")
        info = self.dir / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("\n".join(EXCLUDES) + "\n", encoding="utf-8")
        (self.dir / "peto-used").write_text(str(int(time.time())), encoding="utf-8")
        self._ready = True

    def _disable(self, reason: str) -> None:
        self.problem = f"Tắt ảnh chụp dự án cho phiên này ({reason}); /undo chỉ gồm những lần Peto tự sửa tệp."

    def capture(self) -> str | None:
        """Mã cây của cả dự án lúc này; tắt hay lỗi thì None (lần lỗi đầu tắt ảnh chụp cho cả phiên)."""
        if not self.available:
            return None
        with self._lock:
            try:
                self._prepare()
                listed = self._git("ls-files", "-z", "--others", "--modified", "--deleted", "--exclude-standard")
                paths = [name for name in listed.decode("utf-8", errors="surrogateescape").split("\0")
                         if name and not name.endswith("/")]
                if len(paths) > MAX_FILES:
                    self._disable(f"dự án có hơn {MAX_FILES:,} tệp".replace(",", "."))
                    return None
                add, drop = [], []
                for name in dict.fromkeys(paths):
                    target = self.root / name
                    try:
                        if target.is_symlink() or not target.exists():
                            # Không còn (hoặc là symlink): bỏ khỏi ảnh; update-index --remove lo tệp đã xóa.
                            (drop if target.is_symlink() else add).append(name)
                        elif target.is_file() and target.stat().st_size <= MAX_FILE_BYTES:
                            add.append(name)
                        else:
                            drop.append(name)
                    except OSError:
                        drop.append(name)
                if add:
                    self._git("update-index", "--add", "--remove", "-z", "--stdin",
                              data="\0".join(add).encode("utf-8", errors="surrogateescape") + b"\0",
                              timeout=HASH_TIMEOUT)
                if drop:
                    self._git("update-index", "--force-remove", "-z", "--stdin",
                              data="\0".join(drop).encode("utf-8", errors="surrogateescape") + b"\0")
                return self._git("write-tree").decode().strip()
            except (SnapshotError, OSError) as err:
                self._disable(str(err))
                return None

    def changed(self, before: str, after: str) -> list[str]:
        """Đường dẫn (tương đối, dùng "/") khác nhau giữa hai ảnh."""
        if before == after:
            return []
        out = self._git("diff-tree", "-r", "-z", "--no-renames", "--name-only", before, after)
        return [name for name in out.decode("utf-8", errors="surrogateescape").split("\0") if name]

    def content(self, tree: str, path: str) -> bytes | None:
        """Nội dung một tệp trong ảnh; không có thì None."""
        out = self._git("ls-tree", "-z", tree, "--", path)
        entry = out.decode("utf-8", errors="surrogateescape").split("\0")[0]
        if not entry:
            return None
        meta, _, _ = entry.partition("\t")
        mode, kind, blob = meta.split(" ")
        if kind != "blob" or mode == "120000":
            return None
        return self._git("cat-file", "blob", blob)

    def contents(self, tree: str, paths: list[str]) -> dict[str, bytes | None]:
        """Nội dung nhiều tệp trong một ảnh, một lần gọi git; tệp không có trong ảnh thì None."""
        if not paths:
            return {}
        request = "".join(f"{tree}:{path}\n" for path in paths).encode("utf-8", errors="surrogateescape")
        out = self._git("cat-file", "--batch", data=request)
        found: dict[str, bytes | None] = {}
        position = 0
        for path in paths:
            end = out.index(b"\n", position)
            header = out[position:end].decode("utf-8", errors="replace").split(" ")
            position = end + 1
            if header[-1] == "missing" or len(header) < 3:
                found[path] = None
                continue
            size = int(header[2])
            found[path] = out[position:position + size] if header[1] == "blob" else None
            position += size + 1
        return found

    def has(self, tree: str) -> bool:
        try:
            self._git("cat-file", "-e", f"{tree}^{{tree}}")
            return True
        except SnapshotError:
            return False


def maintain(git: str | None = None) -> None:
    """Dọn kho ẩn, tối đa một lần mỗi ngày, ở luồng nền đầu phiên: gc bỏ ảnh quá KEEP_DAYS ngày, xóa kho của dự án
    không dùng KEEP_DAYS ngày. Lỗi gì cũng bỏ qua."""
    git = git if git is not None else shutil.which("git")
    base = folder()
    stamp = base / "last-gc"
    try:
        if stamp.exists() and time.time() - stamp.stat().st_mtime < GC_EVERY:
            return
        base.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(int(time.time())), encoding="utf-8")
    except OSError:
        return

    def run() -> None:
        cutoff = time.time() - KEEP_DAYS * 24 * 3600
        for repository in base.iterdir() if base.exists() else []:
            try:
                used = repository / "peto-used"
                if not repository.is_dir() or repository.is_symlink():
                    continue
                if (used.stat().st_mtime if used.exists() else repository.stat().st_mtime) < cutoff:
                    shutil.rmtree(repository, ignore_errors=True)
                elif git:
                    subprocess.run([git, f"--git-dir={repository}", "gc", "--quiet", f"--prune={KEEP_DAYS}.days.ago"],
                                   capture_output=True, timeout=300,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            except (OSError, subprocess.SubprocessError):
                continue

    threading.Thread(target=run, name="peto-snapshot-gc", daemon=True).start()
