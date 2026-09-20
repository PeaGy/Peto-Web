"""Byte-exact local checkpoints for direct file tools; never reset a Git checkout."""
from dataclasses import dataclass
import os
import tempfile
import base64
import binascii

from . import checkpoint_store

from .workspace import WorkspaceError, digest


@dataclass
class Change:
    # None nghĩa là tệp không tồn tại ở đầu (before) hay ở cuối (after) thao tác: tạo mới thì before None, xóa thì
    # after None, đổi tên là một cặp xóa chỗ cũ và tạo chỗ mới.
    before: bytes | None
    after: bytes | None


class Checkpoint:
    def __init__(self, workspace):
        self.ws = workspace
        self.files: dict[str, Change] = {}
        self.shell_used = False

    def persist(self):
        encode = lambda value: base64.b64encode(value).decode("ascii") if value is not None else None
        checkpoint_store.save(self.ws.root, {rel: {"before": encode(change.before), "after": encode(change.after)}
                                            for rel, change in self.files.items()}, self.shell_used)

    @classmethod
    def restore(cls, workspace):
        checkpoint = cls(workspace)
        data = checkpoint_store.load(workspace.root)
        if data is None:
            return checkpoint
        try:
            files = data["files"]
            if not isinstance(files, dict) or len(files) > 400:
                raise ValueError()
            for rel, item in files.items():
                if not isinstance(rel, str) or not isinstance(item, dict):
                    raise ValueError()
                path = workspace.resolve(rel, must_exist=False)
                if workspace.relative(path) != rel:
                    raise ValueError()
                before = None if item["before"] is None else base64.b64decode(item["before"], validate=True)
                after = None if item["after"] is None else base64.b64decode(item["after"], validate=True)
                for raw in (before, after):
                    if raw is not None:
                        raw.decode("utf-8-sig")
                checkpoint.files[rel] = Change(before, after)
            checkpoint.shell_used = data.get("shell_used") is True
        except (ValueError, TypeError, KeyError, binascii.Error) as err:
            raise WorkspaceError("Bản hoàn tác hỏng hoặc có đường dẫn không hợp lệ; không khôi phục tệp nào.") from err
        return checkpoint

    def record(self, path, before, after):
        rel = self.ws.relative(path)
        if rel in self.files:
            previous = self.files[rel]
            # An intervening external/shell edit must not be swallowed by undo.
            if before != previous.after:
                raise WorkspaceError(f"{rel} đã đổi ngoài công cụ sửa tệp; bắt đầu yêu cầu mới trước khi sửa tiếp.")
            before = previous.before
        previous = self.files.get(rel)
        self.files[rel] = Change(before, after)
        try:
            self.persist()
        except (OSError, WorkspaceError):
            if previous is None:
                self.files.pop(rel, None)
            else:
                self.files[rel] = previous
            raise

    def matches(self, path, expected):
        """Tệp trên đĩa có đúng trạng thái công cụ để lại không; expected None nghĩa là tệp phải không còn."""
        if expected is None:
            return not path.exists()
        return path.is_file() and path.read_bytes() == expected

    def check(self, path):
        previous = self.files.get(self.ws.relative(path))
        if previous and not self.matches(path, previous.after):
            raise WorkspaceError("Tệp đã đổi ngoài công cụ sửa tệp; bắt đầu yêu cầu mới trước khi sửa tiếp.")

    def show(self, ui):
        if not self.files:
            ui.line("  Chưa có thay đổi tệp trực tiếp trong yêu cầu gần nhất.", "dim")
        for rel, change in self.files.items():
            label = rel + (" (đã xóa)" if change.after is None else " (tạo mới)" if change.before is None else "")
            ui.review_diff(label, (change.before or b"").decode("utf-8-sig"),
                           (change.after or b"").decode("utf-8-sig"))
        if self.files or self.shell_used:
            ui.line("  /diff và /undo chỉ gồm sửa tệp trực tiếp, không bao gồm thay đổi do lệnh terminal tạo ra.", "yellow")

    def record_move(self, source, destination, raw):
        """Ghi nhận rồi đổi tên tệp: chỗ cũ thành không còn, chỗ mới thành tệp vừa tới.

        Đổi tên hỏng giữa chừng thì trả sổ về đúng như trước, để bản hoàn tác không mô tả sai những gì trên đĩa.
        """
        old_rel = self.ws.relative(source)
        previous = self.files.get(old_rel)
        self.record(source, raw, None)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
        except OSError:
            if previous is None:
                self.files.pop(old_rel, None)
            else:
                self.files[old_rel] = previous
            try:
                self.persist()
            except (OSError, WorkspaceError):
                pass
            raise
        self.record(destination, None, raw)

    def undo(self):
        # Preflight every file before restoring any of them. Re-resolve paths to reject new symlinks.
        targets = {}
        for rel, change in self.files.items():
            path = self.ws.resolve(rel, must_exist=False)
            if self.ws.relative(path) != rel or not self.matches(path, change.after):
                raise WorkspaceError(f"{rel} không còn như lúc Peto để lại; không hoàn tác để bảo vệ thay đổi của bạn.")
            targets[rel] = path
        restored = []
        for rel, path in targets.items():
            change = self.files[rel]
            if self.ws.resolve(rel, must_exist=False) != path or not self.matches(path, change.after):
                raise WorkspaceError(f"{rel} vừa thay đổi; đã hoàn tác {len(restored)} tệp, dừng tại đây.")
            if change.before is None:
                # Tệp Peto tạo ra thì bỏ đi; tệp Peto tạo rồi xóa trong cùng yêu cầu thì vốn đã không còn.
                if change.after is not None:
                    path.unlink()
                self.ws.read_digests.pop(path, None)
            else:
                temporary = None
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".peto-undo-", delete=False) as handle:
                        temporary = handle.name
                        handle.write(change.before)
                    # Tệp đã bị xóa thì không còn quyền cũ để chép lại; tệp còn đó thì giữ nguyên quyền của nó.
                    if path.exists():
                        os.chmod(temporary, path.stat().st_mode)
                    if self.ws.resolve(rel, must_exist=False) != path or not self.matches(path, change.after):
                        raise WorkspaceError(f"{rel} vừa thay đổi; dừng hoàn tác.")
                    os.replace(temporary, path)
                    temporary = None
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
                self.ws.read_digests[path] = digest(change.before)
            del self.files[rel]
            restored.append(rel)
            self.persist()
        return restored
