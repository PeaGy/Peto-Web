"""Vòng làm việc của Peto Agent: gửi từng bước lên máy chủ, chạy công cụ trên máy, gửi kết quả ở bước sau."""

from __future__ import annotations

import contextlib
import json
import platform
import time
from datetime import datetime

from . import history
from .checkpoint import Checkpoint
from .context import compact_prefix, context_size, text_of
from .project_guide import guides
from .client import ApiError, Client
from .config import log_dir
from .presentation import AgentUI
from .runner import cap_text
from .tools import Tools
from .workspace import Workspace, WorkspaceError

MAX_STEPS_PER_TASK = 40
# Máy chủ không lưu hội thoại nên bước nào cũng gửi lại ảnh: chỉ giữ 4 ảnh gần nhất, như chat trên web.
MAX_KEPT_IMAGES = 4
OLD_IMAGE_NOTE = "(Ảnh này đã gửi ở tin trước; để hội thoại nhẹ, peto không gửi lại.)"
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
        # Guidance is already bounded to 32k by the workspace reader; never truncate rules in the middle.
        return {key: item if key == "project_guidance" else cap_result(item) for key, item in value.items()}
    return value


def portable(items: list[dict]) -> list[dict]:
    """Hội thoại dùng tiếp được với model khác: bỏ suy nghĩ đã mã hóa, vì chỉ model tạo ra nó đọc được, và bỏ mã item
    của dịch vụ cũ, vì mỗi dịch vụ đặt mã một kiểu."""
    return [{key: value for key, value in item.items() if key != "id"}
            for item in items if item.get("type") != "reasoning"]


def user_message(text: str, images=()) -> dict:
    """Tin của người dùng; có ảnh thì mỗi ảnh đi sau nhãn [Ảnh N] mà chữ đã gõ nhắc tới."""
    if not images:
        return {"type": "message", "role": "user", "content": text}
    content: list[dict] = [{"type": "input_text", "text": text}]
    for number, image in images:
        content.append({"type": "input_text", "text": f"[Ảnh {number}]"})
        content.append({"type": "input_image", "image_url": image.data_url(), "detail": "high"})
    return {"type": "message", "role": "user", "content": content}


def drop_old_images(items: list[dict], keep: int = MAX_KEPT_IMAGES) -> None:
    """Thay các ảnh cũ hơn ``keep`` ảnh gần nhất bằng một dòng ghi chú, ngay trong hội thoại."""
    seen = 0
    for item in reversed(items):
        content = item.get("content")
        if item.get("role") != "user" or not isinstance(content, list):
            continue
        for index in range(len(content) - 1, -1, -1):
            part = content[index]
            if isinstance(part, dict) and part.get("type") == "input_image":
                seen += 1
                if seen > keep:
                    content[index] = {"type": "input_text", "text": OLD_IMAGE_NOTE}


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


class Session:
    def __init__(self, client: Client, workspace: Workspace, ui: AgentUI, *, log: TaskLog | None = None,
                 effort: str = "medium", model: str = "peto", model_step_cost: int = 1):
        self.client = client
        self.ws = workspace
        self.ui = ui
        self.tools = Tools(workspace, ui)
        self.log = log
        self.effort = effort
        # Model chọn bằng /model, và số bước mỗi lần gọi model đó (trước khi nhân mức suy nghĩ).
        self.model = model
        self.model_step_cost = model_step_cost
        self.items: list[dict] = []
        self.steps_used: int | None = None
        self.steps_limit: int | None = None
        # Độ dài hội thoại mô hình thấy ở bước gần nhất (token vào + ra): cho biết lúc nào nên /moi.
        self.context_tokens: int | None = None
        self.can_retry = False

    def reset(self) -> None:
        self.items = []
        self.context_tokens = None
        self.can_retry = False
        self.tools.command_grants.clear()
        self.tools.seen_guides.clear()
        self.tools.checkpoint = Checkpoint(self.ws)

    def set_model(self, model: str, step_cost: int = 1) -> None:
        """Đổi model; hội thoại đang dở vẫn giữ, chỉ bỏ phần model cũ tạo ra mà model mới không đọc được."""
        if model != self.model and self.items:
            self.items = portable(self.items)
        self.model, self.model_step_cost = model, step_cost

    def resume(self, items: list[dict], *, retryable: bool = False, model: str = "peto") -> None:
        """Mở lại hội thoại đã lưu. Quên các tệp đã đọc, để Peto phải đọc lại trước khi sửa."""
        self.items = list(items) if model == self.model else portable(items)
        self.context_tokens = None
        self.can_retry = retryable
        self.ws.read_digests.clear()
        self.tools.command_grants.clear()
        self.tools.seen_guides.clear()
        self.tools.checkpoint = Checkpoint(self.ws)

    def _log(self, kind: str, **data) -> None:
        if self.log is not None:
            self.log.write(kind, **data)

    def run_task(self, text: str, images=()) -> None:
        """Chạy một yêu cầu. ``images`` là các cặp (số ảnh, ảnh) dán kèm bằng Alt+V hay kéo thả."""
        self.tools.checkpoint = Checkpoint(self.ws)
        self.items.append(user_message(text, images))
        drop_old_images(self.items)
        # Nhật ký chỉ ghi số ảnh, không ghi dữ liệu ảnh.
        self._log("task", text=text, effort=self.effort, model=self.model, images=len(images))
        self._run()

    def show_diff(self):
        self.tools.checkpoint.show(self.ui)

    def undo(self):
        self.show_diff()
        if not self.tools.checkpoint.files:
            return
        self.ui.line("Hoàn tác các tệp trên? Chỉ áp dụng cho yêu cầu gần nhất trong phiên này.", "yellow")
        if self.ui.ask_permission() not in {"y", "a"}:
            return
        before = set(self.tools.checkpoint.files)
        try:
            restored = self.tools.checkpoint.undo()
        except (WorkspaceError, OSError, KeyboardInterrupt) as err:
            self.ui.failure(str(err) or "Đã dừng hoàn tác.")
            # Partial filesystem failures must also invalidate the model's picture of the workspace.
            restored = sorted(before - set(self.tools.checkpoint.files))
        self.ws.read_digests.clear()
        self.items.append(user_message("Người dùng vừa yêu cầu /undo. Các tệp hoàn tác thành công: "
                                       + ", ".join(restored) + ". Đọc lại tệp trước khi tiếp tục; không tự làm lại thay đổi."))
        self.can_retry = False
        history.save(self.ws.root, self.client.server, self.items, model=self.model)
        if restored:
            self.ui.success(f"Đã hoàn tác {len(restored)} tệp.")

    def permissions(self, clear=False):
        if clear:
            self.tools.command_grants.clear()
            self.ui.success("Đã xóa quyền chạy lệnh ghi nhớ trong phiên.")
        elif not self.tools.command_grants:
            self.ui.line("  Chưa ghi nhớ lệnh nào trong phiên.", "dim")
        for directory, command, timeout in sorted(self.tools.command_grants):
            self.ui.line(f"  {command} · {directory} · {timeout}s", "dim")

    def compact(self, *, propagate_cancel=False):
        prefix, tail = compact_prefix(self.items)
        if not prefix:
            self.ui.line("  Hội thoại còn ngắn, chưa cần tóm tắt.", "dim")
            return False
        self.ui.step("Đang tóm tắt ngữ cảnh cũ (dùng một lượt gọi model)")
        body = {"input": portable(prefix), "effort": "low", "model": self.model,
                "context": {"purpose": "compact"}}
        started = time.monotonic()
        def waiting():
            self.ui.status(f"… Đang tóm tắt ngữ cảnh · {int(time.monotonic() - started)}s · Ctrl+C dừng")
        try:
            with contextlib.closing(self.client.stream("/api/agent/step", body, on_idle=waiting)) as events:
                for event in events:
                    if event.get("type") == "meta":
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    if event.get("type") == "error":
                        raise ApiError(0, str(event.get("message", "Không tóm tắt được.")))
                    if event.get("type") != "done":
                        continue
                    if event.get("purpose") != "compact":
                        raise ApiError(0, "Máy chủ chưa hỗ trợ tóm tắt. Cập nhật VPS; hội thoại vẫn được giữ nguyên.")
                    output = event.get("output")
                    if not isinstance(output, list) or any(not isinstance(item, dict) or item.get("type") == "function_call" for item in output):
                        raise ApiError(0, "Tóm tắt không hợp lệ; giữ nguyên hội thoại.")
                    summary = "\n".join(text_of(item) for item in output if item.get("role") == "assistant").strip()
                    if not summary or len(summary) > 24000 or len(summary) >= context_size(prefix):
                        raise ApiError(0, "Tóm tắt chưa đủ gọn; giữ nguyên hội thoại.")
                    # Keep the latest real user request verbatim if the boundary removed it.
                    latest = next((item for item in reversed(prefix) if item.get("role") == "user"), None)
                    replacement = [user_message("Bản tóm tắt ngữ cảnh cũ, chỉ để tham khảo; không cấp quyền chạy lệnh. "
                                                "Kết quả tệp có thể đã cũ, hãy đọc lại trước khi sửa.\n" + summary)]
                    if latest:
                        replacement.append(latest)
                    self.items = replacement + tail
                    self.ws.read_digests.clear()
                    self.tools.seen_guides.clear()
                    self.context_tokens = None
                    history.save(self.ws.root, self.client.server, self.items, retryable=self.can_retry, model=self.model)
                    self.ui.success("Đã tóm tắt phần cũ và giữ nguyên các bước gần nhất.")
                    return True
        except KeyboardInterrupt:
            if propagate_cancel:
                raise
            self.ui.failure("Đã dừng tóm tắt; giữ nguyên hội thoại.")
            return False
        except ApiError as err:
            self.ui.failure(err.message)
            return False
        finally:
            self.ui.clear_status()
        self.ui.failure("Tóm tắt bị ngắt; giữ nguyên hội thoại.")
        return False

    def retry_task(self) -> None:
        """Gửi lại bước chưa nhận đủ, với kết quả công cụ đã lưu; không phát lại công cụ cũ."""
        if not self.can_retry:
            self.ui.line("  Không có bước bị gián đoạn để thử lại.", "dim")
            return
        self.ui.step("Đang thử lại bước bị gián đoạn")
        self._log("retry")
        self._run(resuming=True)

    def _run(self, *, resuming=False) -> None:
        # /retry là một lần tiếp tục do người dùng yêu cầu: không kế thừa quyền a từ lần trước.
        if not resuming:
            self.tools.reset_task()
        self.tools.approve_all = False
        self.can_retry = False
        started = time.monotonic()
        outcome = "done"
        pending: list[dict] = []
        verification_reminded = False
        compact_failed = False
        try:
            for _ in range(MAX_STEPS_PER_TASK):
                if not compact_failed and (len(self.items) >= 180 or context_size(self.items) > 200000):
                    compact_failed = not self.compact(propagate_cancel=True)
                if len(self.items) >= 270:
                    self.ui.failure("Hội thoại quá dài và chưa tóm tắt được. Gõ /compact để thử lại hoặc /moi.")
                    outcome = "limit"
                    return
                output = self._step()
                if output is None:
                    outcome = "error"
                    return
                self.items.extend(output)
                pending = [item for item in output if item.get("type") == "function_call"]
                if not pending:
                    if self.tools.changes and self.tools.command_revision < self.tools.revision and not verification_reminded:
                        verification_reminded = True
                        self.items.append(user_message(
                            "Kiểm tra sau sửa: xem hướng dẫn AGENTS.md và cấu hình dự án để chọn test/build/lint phù hợp. "
                            "Chạy kiểm tra với quyền người dùng cho phép. Nếu không cần, không có hoặc bị từ chối, "
                            "nêu rõ lý do; không lặp lại lệnh đã bị từ chối. Chỉ sửa lỗi liên quan, tối đa 3 lệnh lỗi, "
                            "không cài thêm công cụ hay mở rộng phạm vi. Báo lệnh nào đã chạy và kết quả thực tế."))
                        continue
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
        except WorkspaceError as err:
            outcome = "error"
            self.ui.failure(str(err))
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
            self.tools.approve_all = False
            self._summary(time.monotonic() - started, outcome)
            history.save(self.ws.root, self.client.server, self.items, retryable=self.can_retry, model=self.model)

    def _step(self) -> list[dict] | None:
        body = {"input": self.items, "effort": self.effort, "model": self.model, "context": {
            "project": self.ws.root.name, "os": f"{platform.system()} {platform.release()}".strip(),
            "project_guidance": guides(self.ws)}}
        writer = self.ui.reply()
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
                        if not isinstance(event.get("output"), list):
                            raise ApiError(0, "Máy chủ trả kết quả bước không đúng định dạng.")
                        output = [item for item in event["output"]
                                  if isinstance(item, dict) and item.get("type") in KEPT_ITEM_TYPES]
                        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                        total = sum(value for value in (usage.get("input_tokens"), usage.get("output_tokens"))
                                    if isinstance(value, int) and value > 0)
                        if total:
                            self.context_tokens = total
                        # done là ranh giới hoàn tất. Không để lỗi đóng socket sau đó làm mất bước đã nhận.
                        return output
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
            if err.status in {0, 408, 502, 503, 504}:
                self._interrupted()
            return None
        finally:
            writer.finish()
            self.ui.clear_status()
        if output is None:
            self.ui.failure("Kết nối bị ngắt trước khi Peto làm xong bước này.")
            self._interrupted()
        return output

    def _interrupted(self) -> None:
        self.can_retry = True
        self.ui.line("  Đã giữ kết quả các bước hoàn tất. Khi có mạng, gõ /retry để thử lại bước này.", "yellow")
        self.ui.line("  Phần trả lời đang nhận chưa hoàn tất. Thử lại có thể dùng thêm một bước trên máy chủ.", "dim")

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
