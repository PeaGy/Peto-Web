"""Các công cụ Peto gọi, chạy ngay trên máy người dùng trong phạm vi thư mục dự án.

Đọc, liệt kê và tìm thì tự làm. Sửa tệp, ghi tệp và chạy lệnh luôn hỏi người dùng trước (trừ khi họ chọn "có cho mọi
bước" trong yêu cầu đang chạy). Kết quả trả về là dict, sẽ được gửi lại cho Peto ở bước sau.
"""

from __future__ import annotations

import difflib
import fnmatch
import inspect
import json
import re
from pathlib import Path

from . import runner
from .presentation import AgentUI
from .workspace import SKIPPED_DIRS, Workspace, WorkspaceError

MAX_READ_LINES = 400
MAX_LIST_ENTRIES = 400
MAX_MATCHES = 100
REFUSED = "Người dùng không đồng ý {action}. Đừng lặp lại y nguyên; hỏi họ muốn làm khác thế nào."


def changed_lines(before: str, after: str) -> tuple[int, int]:
    added = removed = 0
    for line in list(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                       lineterm="", n=0))[2:]:
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


class Tools:
    def __init__(self, workspace: Workspace, ui: AgentUI):
        self.ws = workspace
        self.ui = ui
        self.approve_all = False
        self.changes: dict[str, list[int]] = {}
        self.commands: list[dict] = []
        self._handlers = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "search_files": self.search_files,
            "edit_file": self.edit_file,
            "write_file": self.write_file,
            "run_command": self.run_command,
        }

    def reset_task(self) -> None:
        self.approve_all = False
        self.changes = {}
        self.commands = []

    def call(self, name: str, arguments: str) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Peto Agent không có công cụ {name}."}
        try:
            params = json.loads(arguments or "{}")
        except (TypeError, ValueError):
            return {"error": "Tham số công cụ không phải JSON hợp lệ."}
        if not isinstance(params, dict):
            return {"error": "Tham số công cụ không hợp lệ."}
        try:
            inspect.signature(handler).bind(**params)
        except TypeError:
            return {"error": f"Tham số không đúng với công cụ {name}."}
        try:
            return handler(**params)
        except WorkspaceError as err:
            self.ui.failure(str(err))
            return {"error": str(err)}
        except OSError as err:
            message = f"Lỗi đọc ghi tệp: {err.strerror or type(err).__name__}."
            self.ui.failure(message)
            return {"error": message}

    def _approve(self) -> bool:
        if self.approve_all:
            return True
        answer = self.ui.ask_permission()
        if answer == "a":
            self.approve_all = True
        return answer in {"y", "a"}

    def _record(self, rel: str, before: str, after: str) -> tuple[int, int]:
        added, removed = changed_lines(before, after)
        total = self.changes.setdefault(rel, [0, 0])
        total[0] += added
        total[1] += removed
        return added, removed

    def list_files(self, path: str = ".", depth: int | None = None) -> dict:
        base = self.ws.resolve(path)
        if not base.is_dir():
            raise WorkspaceError(f"{self.ws.relative(base)} không phải thư mục.")
        max_depth = max(1, min(4, depth or 2))
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
                if child.name in SKIPPED_DIRS or not self.ws.inside(child) or self.ws.blocked(child):
                    continue
                is_dir = child.is_dir()
                entries.append(self.ws.relative(child) + ("/" if is_dir else ""))
                if len(entries) >= MAX_LIST_ENTRIES:
                    truncated = True
                    return
                if is_dir and level < max_depth:
                    walk(child, level + 1)

        walk(base, 1)
        self.ui.step(f"Xem thư mục {self.ws.relative(base)}")
        return {"path": self.ws.relative(base), "entries": entries, "truncated": truncated}

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        target = self.ws.resolve(path)
        rel = self.ws.relative(target)
        file = self.ws.read(target)
        self.ws.remember(target, file)
        lines = file.text.split("\n")
        if file.text.endswith("\n"):
            lines.pop()
        total = len(lines) if file.text else 0
        start = max(1, start_line or 1)
        if total and start > total:
            raise WorkspaceError(f"{rel} chỉ có {total} dòng.")
        end = max(0, min(total, end_line or total, start + MAX_READ_LINES - 1))
        self.ui.step(f"Đọc {rel} (dòng {start}–{end})" if total else f"Đọc {rel} (tệp trống)")
        return {"path": rel, "start_line": start, "end_line": end, "total_lines": total,
                "content": "\n".join(lines[start - 1:end])}

    def search_files(self, pattern: str, path: str | None = None, glob: str | None = None) -> dict:
        try:
            regex = re.compile(pattern)
        except re.error as err:
            raise WorkspaceError(f"Biểu thức tìm không hợp lệ: {err}.") from None
        base = self.ws.resolve(path or ".")
        files = [base] if base.is_file() else self.ws.iter_files(base)
        matches: list[str] = []
        truncated = False
        for file in files:
            rel = self.ws.relative(file)
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(file.name, glob)):
                continue
            try:
                text = self.ws.read(file).text
            except (WorkspaceError, OSError):
                continue
            for number, line in enumerate(text.split("\n"), 1):
                if regex.search(line):
                    matches.append(f"{rel}:{number}: {line.strip()[:300]}")
                    if len(matches) >= MAX_MATCHES:
                        truncated = True
                        break
            if truncated:
                break
        self.ui.step(f'Tìm "{pattern}" trong {self.ws.relative(base)}')
        return {"matches": matches, "truncated": truncated}

    def edit_file(self, path: str, old_text: str, new_text: str) -> dict:
        target = self.ws.resolve(path)
        rel = self.ws.relative(target)
        known = self.ws.read_digests.get(target)
        if known is None:
            raise WorkspaceError(f"Đọc {rel} bằng read_file trước khi sửa.")
        file = self.ws.read(target)
        if file.digest != known:
            raise WorkspaceError(f"{rel} đã thay đổi kể từ lần đọc gần nhất. Đọc lại rồi sửa nhé.")
        old = old_text.replace("\r\n", "\n")
        if not old:
            raise WorkspaceError("old_text đang trống; tạo tệp mới thì dùng write_file.")
        count = file.text.count(old)
        if count == 0:
            raise WorkspaceError(f"Không thấy old_text trong {rel}. Đọc lại đoạn cần sửa rồi chép nguyên văn.")
        if count > 1:
            raise WorkspaceError(f"old_text khớp {count} chỗ trong {rel}; thêm vài dòng xung quanh cho chỉ khớp một chỗ.")
        updated = file.text.replace(old, new_text.replace("\r\n", "\n"), 1)
        self.ui.diff(f"Muốn sửa {rel}", file.text, updated)
        if not self._approve():
            self.ui.failure(f"Không sửa {rel}")
            return {"error": REFUSED.format(action=f"sửa {rel}")}
        if self.ws.read(target).digest != file.digest:
            raise WorkspaceError(f"{rel} vừa bị đổi trong lúc chờ đồng ý. Đọc lại rồi sửa nhé.")
        self.ws.write(target, updated, newline=file.newline, bom=file.bom)
        added, removed = self._record(rel, file.text, updated)
        self.ui.success(f"Đã sửa {rel} (+{added} −{removed})")
        return {"ok": True, "path": rel, "added_lines": added, "removed_lines": removed}

    def write_file(self, path: str, content: str) -> dict:
        target = self.ws.resolve(path, must_exist=False)
        rel = self.ws.relative(target)
        if target.is_dir():
            raise WorkspaceError(f"{rel} là thư mục.")
        existed = target.exists()
        before, newline, bom, original = "", "\n", False, None
        if existed:
            file = self.ws.read(target)
            if self.ws.read_digests.get(target) != file.digest:
                raise WorkspaceError(f"{rel} đã có sẵn. Đọc tệp trước, rồi ưu tiên sửa bằng edit_file.")
            before, newline, bom, original = file.text, file.newline, file.bom, file.digest
        after = content.replace("\r\n", "\n")
        self.ui.diff(("Muốn ghi đè " if existed else "Muốn tạo ") + rel, before, after)
        if not self._approve():
            self.ui.failure(f"Không ghi {rel}")
            return {"error": REFUSED.format(action=f"ghi {rel}")}
        if (self.ws.read(target).digest != original) if existed else target.exists():
            raise WorkspaceError(f"{rel} vừa bị đổi trong lúc chờ đồng ý. Đọc lại rồi ghi nhé.")
        self.ws.write(target, after, newline=newline, bom=bom)
        added, removed = self._record(rel, before, after)
        self.ui.success(("Đã ghi đè " if existed else "Đã tạo ") + f"{rel} (+{added} −{removed})")
        return {"ok": True, "path": rel, "created": not existed, "added_lines": added, "removed_lines": removed}

    def run_command(self, command: str, timeout_seconds: int | None = None) -> dict:
        command = command.strip()
        if not command:
            raise WorkspaceError("Lệnh đang trống.")
        timeout = max(1, min(600, timeout_seconds or 120))
        self.ui.command(command, str(self.ws.root), timeout)
        if not self._approve():
            self.ui.failure("Không chạy lệnh")
            return {"error": REFUSED.format(action="chạy lệnh này")}
        try:
            result = runner.run(command, self.ws.root, timeout, on_progress=self.ui.command_progress)
        finally:
            self.ui.clear_status()
        self.commands.append({"command": command, "exit_code": result["exit_code"], "error": result.get("error")})
        self.ui.command_result(result)
        return result
