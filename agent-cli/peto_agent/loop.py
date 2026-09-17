"""Vòng làm việc của Peto Agent: gửi từng bước lên máy chủ, chạy công cụ trên máy, gửi kết quả ở bước sau."""

from __future__ import annotations

import contextlib
import json
import platform
import time
from datetime import datetime

from . import history
from .client import ApiError, Client
from .config import log_dir
from .runner import cap_text
from .tools import Tools
from .ui import UI
from .workspace import Workspace

MAX_STEPS_PER_TASK = 40
KEPT_ITEM_TYPES = {"message", "function_call", "reasoning"}
STOPPED_RESULT = {"error": "Người dùng đã dừng yêu cầu bằng Ctrl+C."}
OUTCOME_LABELS = {"done": "Xong trong", "stopped": "Đã dừng sau", "error": "Dừng vì lỗi sau", "limit": "Tạm dừng sau"}


def cap_result(value):
    """Cắt chuỗi và danh sách dài trong kết quả công cụ mà vẫn giữ JSON hợp lệ."""
    if isinstance(value, str):
        return cap_text(value)
    if isinstance(value, list):
        return [cap_result(item) for item in value[:400]]
    if isinstance(value, dict):
        return {key: cap_result(item) for key, item in value.items()}
    return value


def format_duration(seconds: float) -> str:
    minutes, rest = divmod(max(0, round(seconds)), 60)
    if not minutes:
        return f"{rest} giây"
    return f"{minutes} phút {rest} giây" if rest else f"{minutes} phút"


def format_tokens(count: int) -> str:
    """850, 1.2k, 18k, 1.3M."""
    if count < 1000:
        return str(count)
    if count < 9950:
        return f"{count / 1000:.1f}k".replace(".0k", "k")
    if count < 999_500:
        return f"{round(count / 1000)}k"
    return f"{count / 1_000_000:.1f}M".replace(".0M", "M")


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


class ReplyWriter:
    """In chữ Peto đang viết theo từng dòng hoàn chỉnh, để tô được chữ đậm và mã. Dòng đầu mang nhãn "Peto › "."""

    def __init__(self, ui: UI):
        self.ui = ui
        self.pending = ""
        self.started = False

    def feed(self, text: str) -> None:
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._emit(line)

    def finish(self) -> None:
        if self.pending:
            self._emit(self.pending)
            self.pending = ""
        self.started = False
        self.ui.end_markdown()

    def _emit(self, line: str) -> None:
        label = "" if self.started else self.ui.paint("Peto › ", "cyan")
        self.started = True
        self.ui.line(label + self.ui.markdown(line.rstrip("\r")))


class Session:
    def __init__(self, client: Client, workspace: Workspace, ui: UI, *, log: TaskLog | None = None,
                 effort: str = "medium"):
        self.client = client
        self.ws = workspace
        self.ui = ui
        self.tools = Tools(workspace, ui)
        self.log = log
        self.effort = effort
        self.items: list[dict] = []
        self.steps_used: int | None = None
        self.steps_limit: int | None = None
        # Độ dài hội thoại mô hình thấy ở bước gần nhất (token vào + ra): cho biết lúc nào nên /moi.
        self.context_tokens: int | None = None

    def reset(self) -> None:
        self.items = []
        self.context_tokens = None

    def resume(self, items: list[dict]) -> None:
        """Mở lại hội thoại đã lưu. Quên các tệp đã đọc, để Peto phải đọc lại trước khi sửa."""
        self.items = list(items)
        self.context_tokens = None
        self.ws.read_digests.clear()

    def _log(self, kind: str, **data) -> None:
        if self.log is not None:
            self.log.write(kind, **data)

    def run_task(self, text: str) -> None:
        self.tools.reset_task()
        self.items.append({"type": "message", "role": "user", "content": text})
        self._log("task", text=text, effort=self.effort)
        started = time.monotonic()
        outcome = "done"
        pending: list[dict] = []
        try:
            for _ in range(MAX_STEPS_PER_TASK):
                output = self._step()
                if output is None:
                    outcome = "error"
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
                outcome = "limit"
                self.ui.line(f'Peto đã làm {MAX_STEPS_PER_TASK} bước trong yêu cầu này nên tạm dừng. Gõ "làm tiếp" nếu '
                             "muốn Peto làm tiếp.", "yellow")
        except KeyboardInterrupt:
            outcome = "stopped"
            # Lệnh gọi công cụ nào cũng phải có kết quả, không thì bước sau bị mô hình từ chối.
            for call in pending:
                self.items.append({"type": "function_call_output", "call_id": call.get("call_id", ""),
                                   "output": json.dumps(STOPPED_RESULT, ensure_ascii=False)})
            self.ui.line()
            self.ui.line("Đã dừng yêu cầu. Gõ yêu cầu mới, hoặc /thoat để thoát.", "yellow")
            self._log("stopped")
        finally:
            self._summary(time.monotonic() - started, outcome)
            history.save(self.ws.root, self.client.server, self.items)

    def _step(self) -> list[dict] | None:
        body = {"input": self.items, "effort": self.effort, "context": {
            "project": self.ws.root.name, "os": f"{platform.system()} {platform.release()}".strip()}}
        writer = ReplyWriter(self.ui)
        started = time.monotonic()
        phase = "nghĩ"
        output = None

        def waiting() -> None:
            # Dòng tạm chỉ hiện tới khi Peto in được dòng chữ đầu tiên của bước này.
            if not writer.started:
                self.ui.status(f"… Peto đang {phase} · {int(time.monotonic() - started)}s")

        waiting()
        try:
            with contextlib.closing(self.client.stream("/api/agent/step", body, on_idle=waiting)) as events:
                for event in events:
                    kind = event.get("type")
                    if kind == "meta":
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    elif kind == "delta":
                        phase = "viết"
                        writer.feed(str(event.get("text", "")))
                        waiting()
                    elif kind == "done":
                        output = [item for item in event.get("output") or []
                                  if isinstance(item, dict) and item.get("type") in KEPT_ITEM_TYPES]
                        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                        total = sum(value for value in (usage.get("input_tokens"), usage.get("output_tokens"))
                                    if isinstance(value, int) and value > 0)
                        if total:
                            self.context_tokens = total
                    elif kind == "error":
                        message = str(event.get("message") or "Máy chủ báo lỗi ở bước này.")
                        writer.finish()
                        self.ui.failure(message)
                        self._log("error", message=message)
                        return None
        except ApiError as err:
            writer.finish()
            self.ui.failure(err.message)
            self._log("error", message=err.message, status=err.status)
            return None
        finally:
            writer.finish()
            self.ui.clear_status()
        if output is None:
            self.ui.failure("Kết nối bị ngắt trước khi Peto làm xong bước này. Thử lại nhé.")
        return output

    def _summary(self, elapsed: float, outcome: str) -> None:
        parts = [f"{OUTCOME_LABELS[outcome]} {format_duration(elapsed)}"]
        if self.tools.changes:
            parts.append(f"sửa {len(self.tools.changes)} tệp")
        if self.tools.commands:
            failed = sum(1 for command in self.tools.commands if command["exit_code"] != 0 or command["error"])
            parts.append(f"chạy {len(self.tools.commands)} lệnh" + (f" ({failed} lỗi)" if failed else ""))
        if self.context_tokens:
            parts.append(f"hội thoại {format_tokens(self.context_tokens)} token")
        if self.steps_used is not None and self.steps_limit is not None:
            parts.append(f"hôm nay còn {max(0, self.steps_limit - self.steps_used)}/{self.steps_limit} bước")
        self.ui.line("  " + " · ".join(parts), "dim")
        self._log("summary", outcome=outcome, seconds=round(elapsed, 1), changes=self.tools.changes,
                  commands=self.tools.commands)
