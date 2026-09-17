"""In-memory, byte-exact undo for direct file tools; never reset a Git checkout."""
from dataclasses import dataclass
import os
import tempfile

from .workspace import WorkspaceError, digest


@dataclass
class Change:
    before: bytes | None
    after: bytes


class Checkpoint:
    def __init__(self, workspace):
        self.ws = workspace
        self.files: dict[str, Change] = {}
        self.shell_used = False

    def record(self, path, before, after):
        rel = self.ws.relative(path)
        if rel in self.files:
            previous = self.files[rel]
            # An intervening external/shell edit must not be swallowed by undo.
            if before != previous.after:
                raise WorkspaceError(f"{rel} đã đổi ngoài công cụ sửa tệp; bắt đầu yêu cầu mới trước khi sửa tiếp.")
            before = previous.before
        self.files[rel] = Change(before, after)

    def check(self, path):
        previous = self.files.get(self.ws.relative(path))
        if previous and (not path.is_file() or path.read_bytes() != previous.after):
            raise WorkspaceError("Tệp đã đổi ngoài công cụ sửa tệp; bắt đầu yêu cầu mới trước khi sửa tiếp.")

    def show(self, ui):
        if not self.files:
            ui.line("  Chưa có thay đổi tệp trực tiếp trong yêu cầu gần nhất.", "dim")
        for rel, change in self.files.items():
            ui.review_diff(rel, (change.before or b"").decode("utf-8-sig"), change.after.decode("utf-8-sig"))
        if self.shell_used:
            ui.line("  Lệnh terminal đã chạy: /diff và /undo không bao gồm thay đổi do lệnh đó tạo ra.", "yellow")

    def undo(self):
        # Preflight every file before restoring any of them. Re-resolve paths to reject new symlinks.
        targets = {}
        for rel, change in self.files.items():
            path = self.ws.resolve(rel, must_exist=False)
            if self.ws.relative(path) != rel or not path.is_file() or path.read_bytes() != change.after:
                raise WorkspaceError(f"{rel} đã thay đổi hoặc bị xóa; không hoàn tác để bảo vệ thay đổi của bạn.")
            targets[rel] = path
        restored = []
        for rel, path in targets.items():
            change = self.files[rel]
            if self.ws.resolve(rel) != path or path.read_bytes() != change.after:
                raise WorkspaceError(f"{rel} vừa thay đổi; đã hoàn tác {len(restored)} tệp, dừng tại đây.")
            if change.before is None:
                path.unlink()
                self.ws.read_digests.pop(path, None)
            else:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".peto-undo-", delete=False) as handle:
                        temporary = handle.name
                        handle.write(change.before)
                    os.chmod(temporary, path.stat().st_mode)
                    if self.ws.resolve(rel) != path or path.read_bytes() != change.after:
                        raise WorkspaceError(f"{rel} vừa thay đổi; dừng hoàn tác.")
                    os.replace(temporary, path)
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
                self.ws.read_digests[path] = digest(change.before)
            del self.files[rel]
            restored.append(rel)
        return restored
