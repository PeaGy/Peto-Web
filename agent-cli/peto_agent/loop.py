"""Vòng làm việc của Peto Agent: gửi từng bước lên máy chủ, chạy công cụ trên máy, gửi kết quả ở bước sau."""

from __future__ import annotations

import contextlib
import json
import platform
import time
from datetime import datetime

from .client import ApiError, Client
from .config import log_dir
from .runner import cap_text
from .tools import Tools
from .ui import UI
from .workspace import Workspace

MAX_STEPS_PER_TASK = 40
KEPT_ITEM_TYPES = {"message", "function_call", "reasoning"}
STOPPED_RESULT = {"error": "Người dùng đã dừng yêu cầu bằng Ctrl+C."}


def cap_result(value):
    """Cắt chuỗi và danh sách dài trong kết quả công cụ mà vẫn giữ JSON hợp lệ."""
    if isinstance(value, str):
        return cap_text(value)
    if isinstance(value, list):
        return [cap_result(item) for item in value[:400]]
    if isinstance(value, dict):
        return {key: cap_result(item) for key, item in value.items()}
    return value


class TaskLog:
    """Nhật ký mỗi phiên, lưu trên máy người dùng. Không bao giờ chứa token."""

    def __init__(self, project: str):
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in project)[:40] or "du-an"
        try:
            folder = log_dir()
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / f"{safe}-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        except OSError:
            self.path = None

    def write(self, kind: str, **data) -> None:
        if self.path is None:
            return
        entry = {"time": round(time.time(), 3), "kind": kind, **data}
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass


class Session:
    def __init__(self, client: Client, workspace: Workspace, ui: UI, *, log: TaskLog | None = None):
        self.client = client
        self.ws = workspace
        self.ui = ui
        self.tools = Tools(workspace, ui)
        self.log = log
        self.items: list[dict] = []
        self.steps_used: int | None = None
        self.steps_limit: int | None = None

    def reset(self) -> None:
        self.items = []

    def _log(self, kind: str, **data) -> None:
        if self.log is not None:
            self.log.write(kind, **data)

    def run_task(self, text: str) -> None:
        self.tools.reset_task()
        self.items.append({"type": "message", "role": "user", "content": text})
        self._log("task", text=text)
        pending: list[dict] = []
        try:
            for _ in range(MAX_STEPS_PER_TASK):
                output = self._step()
                if output is None:
                    return
                self.items.extend(output)
                pending = [item for item in output if item.get("type") == "function_call"]
                if not pending:
                    break
                while pending:
                    call = pending[0]
                    result = cap_result(self.tools.call(str(call.get("name", "")), str(call.get("arguments", ""))))
                    encoded = json.dumps(result, ensure_ascii=False)
                    self._log("tool", name=call.get("name"), arguments=cap_text(str(call.get("arguments", "")), 2000),
                              result=cap_text(encoded, 4000))
                    self.items.append({"type": "function_call_output", "call_id": call.get("call_id", ""), "output": encoded})
                    pending.pop(0)
            else:
                self.ui.line(f'Peto đã làm {MAX_STEPS_PER_TASK} bước trong yêu cầu này nên tạm dừng. Gõ "làm tiếp" nếu '
                             "muốn Peto làm tiếp.", "yellow")
        except KeyboardInterrupt:
            # Lệnh gọi công cụ nào cũng phải có kết quả, không thì bước sau bị mô hình từ chối.
            for call in pending:
                self.items.append({"type": "function_call_output", "call_id": call.get("call_id", ""),
                                   "output": json.dumps(STOPPED_RESULT, ensure_ascii=False)})
            self.ui.line()
            self.ui.line("Đã dừng yêu cầu. Gõ yêu cầu mới, hoặc /thoat để thoát.", "yellow")
            self._log("stopped")
        finally:
            self._summary()

    def _step(self) -> list[dict] | None:
        body = {"input": self.items, "context": {
            "project": self.ws.root.name, "os": f"{platform.system()} {platform.release()}".strip()}}
        writing = thinking = False
        output = None
        try:
            with contextlib.closing(self.client.stream("/api/agent/step", body)) as events:
                for event in events:
                    kind = event.get("type")
                    if kind == "meta":
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    elif kind == "thinking" and not thinking and not writing:
                        thinking = True
                        self.ui.line("  … Peto đang nghĩ", "dim")
                    elif kind == "delta":
                        if not writing:
                            writing = True
                            self.ui.write("Peto › ", "cyan")
                        self.ui.write(str(event.get("text", "")))
                    elif kind == "done":
                        output = [item for item in event.get("output") or []
                                  if isinstance(item, dict) and item.get("type") in KEPT_ITEM_TYPES]
                    elif kind == "error":
                        message = str(event.get("message") or "Máy chủ báo lỗi ở bước này.")
                        if writing:
                            self.ui.line()
                        self.ui.failure(message)
                        self._log("error", message=message)
                        return None
        except ApiError as err:
            if writing:
                self.ui.line()
            self.ui.failure(err.message)
            self._log("error", message=err.message, status=err.status)
            return None
        if writing:
            self.ui.line()
        if output is None:
            self.ui.failure("Kết nối bị ngắt trước khi Peto làm xong bước này. Thử lại nhé.")
        return output

    def _summary(self) -> None:
        for rel, (added, removed) in self.tools.changes.items():
            self.ui.line(f"  Đã sửa: {rel} (+{added} −{removed})", "green")
        for command in self.tools.commands:
            ok = command["exit_code"] == 0 and not command["error"]
            state = command["error"] or ("xong" if ok else f"mã thoát {command['exit_code']}")
            self.ui.line(f"  Đã chạy: {command['command']} · {state}", "green" if ok else "yellow")
        if self.steps_used is not None and self.steps_limit is not None:
            self.ui.line(f"  Hôm nay còn {max(0, self.steps_limit - self.steps_used)}/{self.steps_limit} bước.", "dim")
        self._log("summary", changes=self.tools.changes, commands=self.tools.commands)
