"""Phạm vi làm việc của Peto Agent: chỉ trong thư mục dự án đang mở.

Mọi đường dẫn được lấy đường dẫn thật (đi theo cả symlink và junction) rồi mới so với gốc, nên không thoát ra ngoài
được qua ``..`` hay một liên kết. Tệp có thể chứa bí mật bị chặn cả đọc lẫn ghi, vì nội dung đọc được sẽ đi qua máy
chủ Peto tới nhà cung cấp AI.
"""

from __future__ import annotations

import codecs
import fnmatch
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

BLOCKED_FILE_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
)
BLOCKED_DIRS = {".git"}
SKIPPED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache",
                ".mypy_cache", ".next"}
MAX_FILE_BYTES = 1_000_000
MAX_WALK_FILES = 5000
MAX_GITIGNORE_RULES = 500


class WorkspaceError(Exception):
    """Lỗi về đường dẫn hay tệp; nội dung được gửi lại cho Peto như kết quả công cụ."""


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    negate: bool
    directory_only: bool
    # Mẫu có "/" ở đầu hay ở giữa thì so với đường dẫn từ gốc dự án; còn lại so với tên ở mọi tầng, như git.
    anchored: bool


def parse_gitignore(text: str) -> list[IgnoreRule]:
    """Phần .gitignore đủ dùng để bỏ qua thư mục sinh ra (coverage/, target/, *.log…) khi liệt kê và tìm.

    Không làm hết luật của git: chỉ tệp ở gốc dự án, không đọc .gitignore của thư mục con hay cấu hình git toàn máy.
    Dòng "!" được tính, và dòng sau thắng dòng trước như git.
    """
    rules: list[IgnoreRule] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        line = line[1:] if negate else line
        directory_only = line.endswith("/")
        body = line.rstrip("/")
        anchored = body.startswith("/") or "/" in body
        pattern = body.lstrip("/")
        if pattern:
            rules.append(IgnoreRule(pattern, negate, directory_only, anchored))
        if len(rules) >= MAX_GITIGNORE_RULES:
            break
    return rules


def gitignored(rules: list[IgnoreRule], relative: str, is_dir: bool) -> bool:
    name = relative.rsplit("/", 1)[-1]
    result = False
    for rule in rules:
        if rule.directory_only and not is_dir:
            continue
        # fnmatch không phân biệt hoa thường trên Windows, giống git ở đó.
        if fnmatch.fnmatch(relative if rule.anchored else name, rule.pattern):
            result = not rule.negate
    return result


@dataclass(frozen=True)
class TextFile:
    text: str  # đã đổi mọi kiểu xuống dòng về \n
    newline: str  # kiểu xuống dòng gốc của tệp: "\r\n" hoặc "\n"
    bom: bool
    digest: str  # SHA-256 của byte trên đĩa lúc đọc


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def text_bytes(text: str, newline="\n", bom=False) -> bytes:
    body = text.replace("\r\n", "\n")
    if newline == "\r\n":
        body = body.replace("\n", "\r\n")
    return (codecs.BOM_UTF8 if bom else b"") + body.encode("utf-8")


def list_entries(workspace: "Workspace", base: Path, max_depth: int, limit: int) -> tuple[list[str], bool]:
    """Đường dẫn tương đối dưới ``base``, thư mục có dấu / ở cuối. Trả kèm cờ đã cắt bớt vì chạm giới hạn."""
    entries: list[str] = []
    truncated = False

    def walk(directory: Path, level: int) -> None:
        nonlocal truncated
        try:
            children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            return
        for child in children:
            if truncated:
                return
            if child.name in SKIPPED_DIRS or not workspace.inside(child) or workspace.blocked(child):
                continue
            is_dir = child.is_dir()
            if workspace.ignored(child, is_dir):
                continue
            entries.append(workspace.relative(child) + ("/" if is_dir else ""))
            if len(entries) >= limit:
                truncated = True
                return
            if is_dir and level < max_depth:
                walk(child, level + 1)

    walk(base, 1)
    return entries, truncated


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=True)
        # Mã băm của tệp ở lần đọc hoặc ghi gần nhất: sửa tệp chưa đọc hay đã bị đổi thì từ chối.
        self.read_digests: dict[Path, str] = {}
        # Luật .gitignore ở gốc, đọc lại khi tệp đổi (theo thời điểm sửa) để khỏi đọc đĩa ở mỗi mục được duyệt.
        self._ignore_stamp: float | None = None
        self._ignore_rules: list[IgnoreRule] = []

    def gitignore_rules(self) -> list[IgnoreRule]:
        path = self.root / ".gitignore"
        try:
            stamp = path.stat().st_mtime
        except OSError:
            self._ignore_stamp, self._ignore_rules = None, []
            return []
        if stamp != self._ignore_stamp:
            try:
                self._ignore_rules = parse_gitignore(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                self._ignore_rules = []
            self._ignore_stamp = stamp
        return self._ignore_rules

    def ignored(self, path: Path, is_dir: bool | None = None) -> bool:
        """Mục .gitignore bỏ qua thì không liệt kê, không tìm; đọc thẳng theo đường dẫn thì vẫn được."""
        rules = self.gitignore_rules()
        if not rules:
            return False
        return gitignored(rules, self.relative(path), path.is_dir() if is_dir is None else is_dir)

    def inside(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
        except (ValueError, OSError):
            return False
        return True

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() or "."

    def blocked(self, path: Path) -> bool:
        parts = [part.lower() for part in path.relative_to(self.root).parts]
        if any(part in BLOCKED_DIRS for part in parts):
            return True
        return bool(parts) and any(fnmatch.fnmatchcase(parts[-1], pattern) for pattern in BLOCKED_FILE_PATTERNS)

    def resolve(self, value: str | None, *, must_exist: bool = True) -> Path:
        candidate = Path((value or ".").strip() or ".")
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise WorkspaceError("Đường dẫn nằm ngoài thư mục dự án nên Peto không được đụng tới.") from None
        if self.blocked(resolved):
            raise WorkspaceError("Tệp này có thể chứa bí mật (.env, khóa, thư mục .git) nên Peto không đọc hay sửa.")
        if must_exist and not resolved.exists():
            raise WorkspaceError(f"Không tìm thấy {self.relative(resolved)}.")
        return resolved

    def read(self, path: Path) -> TextFile:
        rel = self.relative(path)
        if not path.is_file():
            raise WorkspaceError(f"{rel} không phải tệp.")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise WorkspaceError(f"{rel} lớn quá ({size // 1024} KB); Peto chỉ đọc tệp tới 1 MB.")
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            raise WorkspaceError(f"{rel} là tệp nhị phân nên Peto không đọc.")
        bom = raw.startswith(codecs.BOM_UTF8)
        try:
            text = raw[len(codecs.BOM_UTF8) if bom else 0:].decode("utf-8")
        except UnicodeDecodeError:
            raise WorkspaceError(f"{rel} không phải UTF-8 nên Peto chưa đọc được.") from None
        newline = "\r\n" if b"\r\n" in raw else "\n"
        return TextFile(text=text.replace("\r\n", "\n"), newline=newline, bom=bom, digest=digest(raw))

    def remember(self, path: Path, file: TextFile) -> None:
        self.read_digests[path] = file.digest

    def write(self, path: Path, text: str, *, newline: str = "\n", bom: bool = False) -> None:
        raw = text_bytes(text, newline, bom)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        self.read_digests[path] = digest(raw)

    def iter_files(self, base: Path) -> Iterator[Path]:
        """Duyệt tệp dưới base, bỏ thư mục nặng, mục .gitignore bỏ qua, liên kết ra ngoài dự án và tệp bị chặn."""
        stack, seen, count = [base], set(), 0
        while stack:
            directory = stack.pop()
            real = directory.resolve()
            if real in seen:
                continue
            seen.add(real)
            try:
                children = sorted(directory.iterdir(), key=lambda item: item.name.lower(), reverse=True)
            except OSError:
                continue
            for child in children:
                if child.name in SKIPPED_DIRS or not self.inside(child) or self.blocked(child):
                    continue
                is_dir = child.is_dir()
                if self.ignored(child, is_dir):
                    continue
                if is_dir:
                    stack.append(child)
                elif child.is_file():
                    yield child
                    count += 1
                    if count >= MAX_WALK_FILES:
                        return
