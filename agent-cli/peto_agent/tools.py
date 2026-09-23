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

from . import approvals, browser, runner
from .background import Jobs
from .checkpoint import Checkpoint
from .command_outcome import classify, command_kind
from .images import Image
from .metrics import Metrics
from .project_guide import GuideUpdate, guides
from .presentation import AgentUI
from .workspace import Workspace, WorkspaceError, digest, list_entries, text_bytes

MAX_READ_LINES = 400
MAX_LIST_ENTRIES = 400
MAX_MATCHES = 100
MAX_PLAN_STEPS = 10
MAX_PLAN_TITLE = 120
PLAN_STATUS = ("pending", "running", "done")
REFUSED = "Người dùng không đồng ý {action}. Đừng lặp lại y nguyên; hỏi họ muốn làm khác thế nào."
# Khả năng báo cho máy chủ trong context của mỗi bước, để máy chủ chỉ gửi công cụ và tham số bản CLI này hiểu
# (agent_tools.py): "cwd" từ 0.9.8, "browser" (xem trang trên máy) từ 0.10.0.
FEATURES = ("cwd", "browser")


def _seconds(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " giây"


def _count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


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
        self.checkpoint = Checkpoint(workspace)
        # Lệnh nền sống qua nhiều yêu cầu, chỉ bị dừng khi Peto dừng hoặc khi đóng phiên.
        self.jobs = Jobs()
        # Quyền chạy lệnh nhớ trong phiên: (thư mục, lệnh, thời hạn, shell).
        self.command_grants: set[tuple[str, str, int, str]] = set()
        self.seen_guides: dict[str, str] = {}
        # Danh sách việc Peto tự ghi cho yêu cầu đang chạy; rỗng nghĩa là yêu cầu ngắn, không cần.
        self.plan: list[dict] = []
        # Trình duyệt ẩn, mở khi Peto xem trang lần đầu và sống tới hết phiên. Ảnh chụp trong một bước chờ ở
        # captured để vòng làm việc gửi cho Peto sau kết quả các công cụ của bước đó.
        self.browser: browser.Browser | None = None
        self.captured: list[tuple[str, Image]] = []
        self.failed_commands = 0
        self.command_failures: dict[str, int] = {}
        self.metrics = Metrics()
        self.revision = 0
        self.command_revision = -1
        self._handlers = {
            "update_plan": self.update_plan,
            "list_files": self.list_files,
            "read_file": self.read_file,
            "search_files": self.search_files,
            "edit_file": self.edit_file,
            "write_file": self.write_file,
            "delete_file": self.delete_file,
            "move_file": self.move_file,
            "run_command": self.run_command,
            "start_command": self.start_command,
            "read_command_output": self.read_command_output,
            "stop_command": self.stop_command,
            "browser_open": self.browser_open,
            "browser_screenshot": self.browser_screenshot,
            "browser_read": self.browser_read,
        }

    def reset_task(self) -> None:
        self.approve_all = False
        self.plan = []
        self.captured = []
        self.changes = {}
        self.commands = []
        self.failed_commands = 0
        self.command_failures = {}
        self.revision = 0
        self.command_revision = -1

    def _guidance(self, target, *, reading=False):
        current = guides(self.ws, target)
        changed = any(self.seen_guides.get(item['path']) != item['digest'] for item in current)
        for item in current:
            self.seen_guides[item['path']] = item['digest']
        if changed and not reading:
            raise GuideUpdate(current)
        return current

    def call(self, name: str, arguments: str) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Peto Agent không có công cụ {name}."}
        if self.failed_commands >= 3 and name in {"edit_file", "write_file", "delete_file", "move_file"}:
            return {"error": "Đã có 3 lần kiểm tra thất bại. Dừng sửa tiếp, báo phần còn lại và đợi yêu cầu mới."}
        try:
            params = json.loads(arguments or "{}")
        except (TypeError, ValueError):
            return {"error": "Tham số công cụ không phải JSON hợp lệ."}
        if not isinstance(params, dict):
            return {"error": "Tham số công cụ không hợp lệ."}
        signature = inspect.signature(handler)
        # Máy chủ mới hơn có thể thêm tham số tùy chọn bản này chưa biết. Schema strict bắt model gửi null cho tham số
        # không dùng, mà null nghĩa là mặc định, nên bỏ qua được; giá trị thật thì vẫn báo sai tham số.
        params = {key: value for key, value in params.items() if key in signature.parameters or value is not None}
        try:
            signature.bind(**params)
        except TypeError:
            return {"error": f"Tham số không đúng với công cụ {name}."}
        try:
            return handler(**params)
        except GuideUpdate as err:
            self.ui.step(str(err))
            return {"error": str(err), "project_guidance": err.guidance}
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
        with self.metrics.measure("permission"):
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

    def update_plan(self, steps: list) -> dict:
        """Danh sách việc cho yêu cầu dài. Không đụng tệp nào nên không hỏi quyền, chỉ hiện ra cho người dùng theo dõi."""
        if not isinstance(steps, list) or not steps:
            raise WorkspaceError("steps phải là danh sách ít nhất một việc.")
        if len(steps) > MAX_PLAN_STEPS:
            raise WorkspaceError(f"Danh sách việc tối đa {MAX_PLAN_STEPS} mục; gộp các việc nhỏ lại.")
        plan = []
        for step in steps:
            title = step.get("title") if isinstance(step, dict) else None
            if not isinstance(title, str) or not title.strip() or step.get("status") not in PLAN_STATUS:
                raise WorkspaceError("Mỗi việc cần title là chữ và status là pending, running hoặc done.")
            plan.append({"title": title.strip()[:MAX_PLAN_TITLE], "status": step["status"]})
        self.plan = plan
        self.ui.plan(plan)
        return {"ok": True, "steps": len(plan), "left": sum(1 for step in plan if step["status"] != "done")}

    def list_files(self, path: str = ".", depth: int | None = None) -> dict:
        base = self.ws.resolve(path)
        if not base.is_dir():
            raise WorkspaceError(f"{self.ws.relative(base)} không phải thư mục.")
        entries, truncated = list_entries(self.ws, base, max(1, min(4, depth or 2)), MAX_LIST_ENTRIES)
        self.ui.step(f"Xem thư mục {self.ws.relative(base)}")
        return {"path": self.ws.relative(base), "entries": entries, "truncated": truncated}

    def guidance_for(self, target) -> list[dict]:
        """Hướng dẫn AGENTS.md áp dụng cho một tệp, và ghi nhận là đã thấy.

        Dùng cho tệp người dùng đính kèm bằng @: nội dung tệp đã nằm trong tin nhắn, nên hướng dẫn của thư mục cũng
        phải tới cùng lúc, không thì lần sửa đầu tiên lại tốn một bước chỉ để nhận hướng dẫn.
        """
        return self._guidance(target, reading=True)

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
        limit = MAX_READ_LINES if end_line is not None else 160
        end = max(0, min(total, end_line or total, start + limit - 1))
        self.ui.step(f"Đọc {rel} (dòng {start}–{end})" if total else f"Đọc {rel} (tệp trống)")
        return {"path": rel, "start_line": start, "end_line": end, "total_lines": total,
                "content": "\n".join(lines[start - 1:end]), "project_guidance": self._guidance(target, reading=True),
                **({"next_start_line": end + 1, "truncated": True} if end < total else {})}

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
        self._guidance(target)
        self.checkpoint.check(target)
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
        self._guidance(target)
        raw = target.read_bytes()
        self.checkpoint.record(target, raw, text_bytes(updated, file.newline, file.bom))
        self.ws.write(target, updated, newline=file.newline, bom=file.bom)
        self.revision += 1
        added, removed = self._record(rel, file.text, updated)
        self.ui.success(f"Đã sửa {rel} (+{added} −{removed})")
        return {"ok": True, "path": rel, "added_lines": added, "removed_lines": removed}

    def write_file(self, path: str, content: str) -> dict:
        target = self.ws.resolve(path, must_exist=False)
        self._guidance(target)
        self.checkpoint.check(target)
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
        self._guidance(target)
        raw = target.read_bytes() if existed else None
        self.checkpoint.record(target, raw, text_bytes(after, newline, bom))
        self.ws.write(target, after, newline=newline, bom=bom)
        self.revision += 1
        added, removed = self._record(rel, before, after)
        self.ui.success(("Đã ghi đè " if existed else "Đã tạo ") + f"{rel} (+{added} −{removed})")
        return {"ok": True, "path": rel, "created": not existed, "added_lines": added, "removed_lines": removed}

    def _undoable(self, target):
        """Đọc tệp sắp bị xóa hay chuyển đi. Bản nhớ hoàn tác chỉ giữ được tệp chữ, nên tệp nào không đọc được thì
        không đụng tới: xóa mà không hoàn tác được thì tệ hơn là không xóa."""
        try:
            return self.ws.read(target)
        except WorkspaceError as err:
            raise WorkspaceError(f"{err} Bản hoàn tác chỉ giữ được tệp chữ đọc được, nên Peto không xóa hay chuyển "
                                 "tệp này; nhờ người dùng tự làm nếu họ muốn.") from None

    def delete_file(self, path: str) -> dict:
        """Xóa một tệp chữ. Đi qua bản nhớ hoàn tác, khác hẳn lệnh xóa của hệ điều hành."""
        target = self.ws.resolve(path)
        self._guidance(target)
        self.checkpoint.check(target)
        rel = self.ws.relative(target)
        if target.is_dir():
            raise WorkspaceError(f"{rel} là thư mục; Peto chỉ xóa được từng tệp.")
        file = self._undoable(target)
        self.ui.diff(f"Muốn xóa {rel}", file.text, "")
        if not self._approve():
            self.ui.failure(f"Không xóa {rel}")
            return {"error": REFUSED.format(action=f"xóa {rel}")}
        raw = target.read_bytes()
        if digest(raw) != file.digest:
            raise WorkspaceError(f"{rel} vừa bị đổi trong lúc chờ đồng ý. Đọc lại rồi tính tiếp nhé.")
        self._guidance(target)
        self.checkpoint.record(target, raw, None)
        target.unlink()
        self.ws.read_digests.pop(target, None)
        self.revision += 1
        added, removed = self._record(rel, file.text, "")
        self.ui.success(f"Đã xóa {rel} (−{removed})")
        return {"ok": True, "path": rel, "deleted": True, "removed_lines": removed}

    def move_file(self, path: str, new_path: str) -> dict:
        """Đổi tên hoặc chuyển tệp trong dự án; nội dung giữ nguyên nên không hiện diff."""
        source = self.ws.resolve(path)
        destination = self.ws.resolve(new_path, must_exist=False)
        old_rel, new_rel = self.ws.relative(source), self.ws.relative(destination)
        self._guidance(source)
        self._guidance(destination)
        self.checkpoint.check(source)
        self.checkpoint.check(destination)
        if old_rel == new_rel:
            raise WorkspaceError("Đường dẫn mới trùng đường dẫn cũ.")
        if source.is_dir():
            raise WorkspaceError(f"{old_rel} là thư mục; Peto chỉ chuyển được từng tệp.")
        if destination.exists():
            raise WorkspaceError(f"{new_rel} đã có sẵn; chọn tên khác, hoặc sửa tệp đó rồi xóa tệp cũ.")
        file = self._undoable(source)
        self.ui.line()
        self.ui.line(f"  ✎ Muốn đổi tên {old_rel} → {new_rel}", "blue")
        self.ui.line("    Nội dung giữ nguyên.", "dim")
        if not self._approve():
            self.ui.failure(f"Không đổi tên {old_rel}")
            return {"error": REFUSED.format(action=f"đổi tên {old_rel}")}
        raw = source.read_bytes()
        if digest(raw) != file.digest or destination.exists():
            raise WorkspaceError(f"{old_rel} hoặc {new_rel} vừa bị đổi trong lúc chờ đồng ý. Đọc lại rồi tính tiếp nhé.")
        self._guidance(source)
        self._guidance(destination)
        self.checkpoint.record_move(source, destination, raw)
        self.ws.read_digests.pop(source, None)
        self.ws.read_digests[destination] = file.digest
        self.revision += 1
        self._record(old_rel, file.text, "")
        self._record(new_rel, "", file.text)
        self.ui.success(f"Đã đổi tên {old_rel} → {new_rel}")
        return {"ok": True, "path": new_rel, "moved_from": old_rel}

    def start_command(self, command: str, shell: str | None = None, cwd: str | None = None) -> dict:
        """Chạy lệnh nền và trả về ngay. Hỏi quyền như run_command, và nói rõ lệnh sống lâu hơn yêu cầu này."""
        command = command.strip()
        if not command:
            raise WorkspaceError("Lệnh đang trống.")
        shell = self._shell(shell)
        directory = self._cwd(cwd)
        self.ui.command(command, str(directory), 0, shell=shell, background=True)
        if not self._approve_command(command, directory, 0, shell):
            self.ui.failure("Không chạy lệnh nền")
            return {"error": REFUSED.format(action="chạy lệnh nền này")}
        self.checkpoint.shell_used = True
        job = self.jobs.start(command, directory, shell)
        where = self.ws.relative(directory)
        self.ui.success(f"Đã chạy nền #{job.id}: {command}" + (f" (trong {where})" if where != "." else ""))
        return {"ok": True, "id": job.id, "command": command, "cwd": where,
                "note": "Lệnh chạy tiếp sau khi yêu cầu này xong. Đọc output bằng read_command_output, dừng bằng "
                        "stop_command."}

    def read_command_output(self, job_id: str, wait_seconds: int | None = None) -> dict:
        result = self.jobs.read(str(job_id), wait_seconds)
        state = "đang chạy" if result["running"] else f"đã dừng, mã thoát {result['exit_code']}"
        self.ui.step(f"Đọc output lệnh nền #{result['id']} ({state})")
        return result

    def stop_command(self, job_id: str) -> dict:
        result = self.jobs.stop(str(job_id))
        self.ui.success(f"Đã dừng lệnh nền #{result['id']}: {result['command']}")
        return result

    def _browser(self) -> browser.Browser:
        if self.browser is None:
            self.browser = browser.Browser()
        return self.browser

    def close_browser(self) -> None:
        if self.browser is not None:
            self.browser.close()
            self.browser = None

    def browser_open(self, url: str, viewport: str | None = None) -> dict:
        """Mở trang chạy trên máy trong trình duyệt ẩn. Không hỏi quyền, theo lựa chọn của chủ web ngày 2026-09-23:
        chỉ trang localhost, trong hồ sơ riêng, và đợt này chưa bấm hay gõ gì nên không đổi được gì."""
        page = self._browser().open(url, viewport)
        details = [f"Tải xong {_seconds(page['seconds'])}" if page["loaded"]
                   else f"Chưa tải xong sau {_seconds(page['seconds'])}"]
        if page["status"] and page["status"] >= 400:
            details.append(f"HTTP {page['status']}")
        details.append(f"\"{page['title']}\"" if page["title"] else "không có tiêu đề")
        details.append(f"{len(page['problems'])} lỗi" if page["problems"] else "không lỗi")
        self.ui.page(f"Xem trang {page['url']} · {browser.viewport_label(page['viewport'])}", " · ".join(details),
                     page["problems"])
        return {"ok": True, **page, "size": browser.viewport_label(page["viewport"]).split()[-1],
                "note": "Chưa có ảnh: gọi browser_screenshot khi cần nhìn bố cục, màu sắc; browser_read để đọc chữ."}

    def browser_screenshot(self, viewport: str | None = None, full_page: bool | None = None) -> dict:
        page = self._browser()
        shot = page.screenshot(viewport, bool(full_page))
        saved = browser.store(self.ws.root.name, shot)
        problems = page.late_problems()
        label = browser.viewport_label(shot.viewport) + (" · cả trang" if shot.full_page else "")
        if shot.cut:
            label += f" (cắt ở {shot.height}px)"
        self.ui.page(f"Chụp trang · {label}", "", problems, path=str(saved) if saved else None)
        self.captured.append((f"Ảnh chụp {page.url} · {label}", Image(shot.data, shot.mime, shot.width, shot.height)))
        result = {"ok": True, "url": page.url, "viewport": shot.viewport, "width": shot.width, "height": shot.height,
                  "full_page": shot.full_page,
                  "note": "Ảnh nằm trong tin kế tiếp, sau kết quả các công cụ của bước này."}
        if shot.cut:
            result["cut"] = f"Trang dài hơn {shot.height}px; ảnh chỉ tới đó."
        if problems:
            result["problems"] = problems
        if saved:
            # Chỉ tên tệp, không đường dẫn đầy đủ (có tên tài khoản Windows): đủ để Peto nói cho người dùng biết.
            result["file"] = saved.name
        return result

    def browser_read(self, selector: str | None = None) -> dict:
        page = self._browser()
        read = page.read(selector)
        problems = page.late_problems()
        what = f"Đọc chữ trong {selector}" if selector else "Đọc chữ trên trang"
        self.ui.page(f"{what} ({_count(read['chars'])} ký tự)", "", problems)
        result = {"ok": True, **read}
        if problems:
            result["problems"] = problems
        return result

    def _shell(self, shell: str | None) -> str:
        chosen = (shell or "cmd").strip().lower()
        if chosen not in runner.SHELLS:
            raise WorkspaceError(f"shell chỉ nhận {' hoặc '.join(runner.SHELLS)}.")
        return chosen

    def _cwd(self, cwd: str | None) -> Path:
        """Thư mục chạy lệnh: gốc dự án, hoặc một thư mục con có thật trong dự án (không ra ngoài, không vào .git)."""
        if cwd is None or str(cwd).strip() in {"", "."}:
            return self.ws.root
        directory = self.ws.resolve(str(cwd))
        if not directory.is_dir():
            raise WorkspaceError(f"{self.ws.relative(directory)} không phải thư mục nên không chạy lệnh trong đó được.")
        return directory

    def _approve_command(self, command: str, directory: Path, timeout: int, shell: str) -> bool:
        """Hỏi quyền chạy lệnh. Nhớ được đúng lệnh đó trong phiên ([s]) hoặc luôn trong dự án này ([l]).

        Quyền [l] nằm trong hồ sơ người dùng (approvals.py), không bao giờ trong thư mục dự án.
        """
        grant = (str(directory), command, timeout, shell)
        if self.approve_all or grant in self.command_grants:
            return True
        where = self.ws.relative(directory)
        if approvals.allowed(self.ws.root, where, command, shell):
            self.ui.line("  Lệnh này đã được luôn cho phép trong dự án · /permissions để xem hoặc xóa.", "dim")
            return True
        with self.metrics.measure("permission"):
            answer = self.ui.ask_permission(allow_session=True, allow_always=True)
        if answer == "a":
            self.approve_all = True
        elif answer == "s":
            self.command_grants.add(grant)
            self.ui.line("  Đã nhớ đúng lệnh, thư mục và thời hạn này trong phiên. /permissions để xem hoặc xóa.", "dim")
        elif answer == "l":
            if approvals.add(self.ws.root, where, command, shell):
                self.ui.line("  Từ giờ đúng lệnh này chạy không cần hỏi trong dự án này. /permissions để xem hoặc xóa.",
                             "dim")
            else:
                self.ui.line("  Không lưu được quyền lên máy; lần này vẫn chạy, lần sau Peto sẽ hỏi lại.", "yellow")
        return answer in {"y", "a", "s", "l"}

    def run_command(self, command: str, timeout_seconds: int | None = None, shell: str | None = None,
                    cwd: str | None = None) -> dict:
        command = command.strip()
        if not command:
            raise WorkspaceError("Lệnh đang trống.")
        timeout = max(1, min(600, timeout_seconds or 120))
        shell = self._shell(shell)
        directory = self._cwd(cwd)
        if self.failed_commands >= 3 and command_kind(command) == "check":
            return {"error": "Đã có 3 lần kiểm tra thất bại. Dừng thử sửa/kiểm tra tiếp và báo kết quả cho người dùng."}
        if self.command_failures.get(command, 0) >= 3:
            return {"error": "Lệnh này đã lỗi 3 lần; không lặp lại y nguyên. Đọc lỗi và báo nguyên nhân hoặc chọn cách khác."}
        self.ui.command(command, str(directory), timeout, shell=shell)
        if not self._approve_command(command, directory, timeout, shell):
            self.ui.failure("Không chạy lệnh")
            return {"error": REFUSED.format(action="chạy lệnh này")}
        try:
            self.checkpoint.shell_used = True
            with self.metrics.measure("commands"):
                result = runner.run(command, directory, timeout, shell=shell,
                                    on_progress=self.ui.command_progress)
        except FileNotFoundError:
            raise WorkspaceError(f"Máy này không chạy được {shell}. Thử lại bằng shell khác nhé.") from None
        finally:
            self.ui.clear_status()
        classification = classify(command, result)
        result["classification"] = classification
        if directory != self.ws.root:
            result["cwd"] = self.ws.relative(directory)
        self.commands.append({"command": command, "exit_code": result["exit_code"], "error": result.get("error"),
                              "classification": classification})
        if classification in {"passed", "check_failed"}:
            self.command_revision = self.revision
        if classification == "check_failed":
            self.failed_commands += 1
        if classification not in {"passed", "success", "no_match"}:
            self.command_failures[command] = self.command_failures.get(command, 0) + 1
        self.ui.command_result(result)
        return result
