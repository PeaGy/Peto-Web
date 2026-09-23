"""Vòng làm việc của Peto Agent: gửi từng bước lên máy chủ, chạy công cụ trên máy, gửi kết quả ở bước sau."""

from __future__ import annotations

import contextlib
import json
import platform
import time
from datetime import datetime

from . import approvals, history, mentions
from .checkpoint import Checkpoint
from .context import compact_prefix, context_size, text_of, efficient_input
from .project_guide import MAX_GUIDE_CHARS, MAX_NOTE_CHARS, add_note, guides
from .metrics import Metrics
from .client import ApiError, Client
from .config import log_dir
from .presentation import AgentUI
from .runner import cap_text
from .tools import FEATURES, Tools
from .workspace import Workspace, WorkspaceError

MAX_STEPS_PER_TASK = 40
# Mỗi lời Peto ghi vào nhật ký giữ tối đa ngần này ký tự (phần đầu và phần cuối), để nhật ký không phình theo code dài.
MAX_LOGGED_REPLY = 4000
# Máy chủ không lưu hội thoại nên bước nào cũng gửi lại ảnh: chỉ giữ 4 ảnh gần nhất, như chat trên web.
MAX_KEPT_IMAGES = 4
OLD_IMAGE_NOTE = "(Ảnh này đã gửi ở tin trước; để hội thoại nhẹ, peto không gửi lại.)"
# web_search_call do dịch vụ AI sinh ra khi Peto tra web: giữ lại để hội thoại gửi đi không hụt mục.
KEPT_ITEM_TYPES = {"message", "function_call", "reasoning", "web_search_call"}
STOPPED_RESULT = {"error": "Người dùng đã dừng yêu cầu bằng Ctrl+C."}
# Kết quả ghi thay trong bản lưu giữa yêu cầu cho lệnh gọi công cụ chưa xong. Peto bị đóng lúc đó thì /resume mở lại
# đúng bản này, nên nói rõ công cụ có thể đã chạy một phần.
INTERRUPTED_RESULT = {"error": "Peto bị đóng giữa chừng (cửa sổ terminal đóng hoặc máy tắt) trước khi có kết quả này. "
                               "Công cụ có thể đã chạy một phần: đọc lại tệp hoặc kiểm tra trạng thái trước khi làm tiếp."}
# Số mục nhiều nhất đưa vào lời nhờ của /init: đủ để thấy bố cục mà không thổi phồng bước đầu tiên.
MAX_INIT_ENTRIES = 200
INIT_TASK = """Hãy viết tệp AGENTS.md ở gốc dự án này.

AGENTS.md là hướng dẫn cho chính bạn ở những yêu cầu sau: mỗi bước của Peto Agent đều được gửi kèm nội dung tệp này.

Các việc cần làm:
1. Đọc README, các tệp cấu hình (package.json, pyproject.toml, Makefile, cấu hình CI…) và vài tệp mã tiêu biểu.
2. Viết AGENTS.md gồm: dự án này là gì và chạy bằng gì; lệnh cài, chạy, test, build, lint kèm thư mục phải đứng khi \
chạy; các thư mục chính dùng để làm gì; quy ước code và ngôn ngữ của comment cùng chuỗi hiển thị; những chỗ không \
được đụng vào.
3. Chỉ ghi điều kiểm chứng được trong dự án. Không chép mẫu chung, không đoán lệnh; mục nào không chắc thì bỏ.
4. Viết gọn, dưới 60 dòng, ưu tiên gạch đầu dòng. Tệp này đi kèm mọi bước sau nên dài là tốn ngữ cảnh của mọi yêu cầu.
5. Dùng ngôn ngữ mà tài liệu của dự án đang dùng.
6. Ghi tệp rồi tóm tắt ngắn những gì đã đưa vào. Không sửa tệp nào khác."""
INIT_EXISTING = ("Dự án đã có AGENTS.md: đọc trước, giữ những phần còn đúng và chỉ sửa chỗ sai hoặc thiếu bằng "
                 "edit_file.")
OUTCOME_LABELS = {"done": "Xong trong", "stopped": "Đã dừng sau", "error": "Dừng vì lỗi sau", "limit": "Tạm dừng sau"}
OUTCOME_MARKS = {"done": "✓", "stopped": "■", "error": "✗", "limit": "■"}
# Nhãn trên tiêu đề cửa sổ, để người dùng làm việc khác vẫn thấy Peto xong chưa.
TITLE_LABELS = {"done": "xong", "stopped": "đã dừng", "error": "lỗi", "limit": "tạm dừng"}
# Yêu cầu lâu hơn ngần này giây thì kêu một tiếng khi xong; việc vài giây thì kêu chỉ tổ ồn.
BELL_AFTER_SECONDS = 10.0


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
    """Hội thoại dùng tiếp được với model khác: bỏ suy nghĩ đã mã hóa, vì chỉ model tạo ra nó đọc được, bỏ lượt tìm
    web của dịch vụ cũ, và bỏ mã item, vì mỗi dịch vụ đặt mã một kiểu."""
    return [{key: value for key, value in item.items() if key != "id"}
            for item in items if item.get("type") not in {"reasoning", "web_search_call"}]


def user_message(text: str, images=()) -> dict:
    """Tin của người dùng; có ảnh thì mỗi ảnh đi sau nhãn [Ảnh N] mà chữ đã gõ nhắc tới."""
    if not images:
        return {"type": "message", "role": "user", "content": text}
    content: list[dict] = [{"type": "input_text", "text": text}]
    for number, image in images:
        content.append({"type": "input_text", "text": f"[Ảnh {number}]"})
        content.append({"type": "input_image", "image_url": image.data_url(), "detail": "high"})
    return {"type": "message", "role": "user", "content": content}


def tool_images(captured) -> dict:
    """Ảnh chụp trình duyệt của một bước, gửi cho Peto sau kết quả các công cụ của bước đó.

    Kết quả công cụ chỉ chở chữ, còn ảnh phải nằm trong tin vai user; đoạn mở đầu nói rõ đây là dữ liệu công cụ, và
    history.recap bỏ qua tin này. Ảnh chụp tính chung vào 4 ảnh gần nhất được giữ như ảnh người dùng dán.
    """
    content: list[dict] = [{"type": "input_text", "text": history.TOOL_IMAGES_NOTE}]
    for label, image in captured:
        content.append({"type": "input_text", "text": f"[{label}]"})
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
        self.metrics = self.tools.metrics
        self._running = False
        self.active_seconds = 0.0

    def reset(self) -> None:
        self.tools.reset_task()
        self.metrics = self.tools.metrics = Metrics()
        self.active_seconds = 0.0
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
        self.tools.reset_task()
        self.metrics = self.tools.metrics = Metrics()
        self.active_seconds = 0.0
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
        attached = mentions.attach(self.ws, self.tools, text)
        for step in attached.steps:
            self.ui.step(step)
        for notice in attached.notices:
            self.ui.line(f"  {notice}", "yellow")
        self.items.append(user_message(attached.text, images))
        drop_old_images(self.items)
        # Nhật ký chỉ ghi số ảnh và đường dẫn đính kèm, không ghi dữ liệu ảnh hay nội dung tệp.
        self._log("task", text=text, effort=self.effort, model=self.model, images=len(images),
                  **({"mentions": attached.paths} if attached.paths else {}))
        self._run()

    def init_guide(self) -> None:
        """/init: khảo sát dự án rồi viết AGENTS.md. Chạy như một yêu cầu thường nên tốn vài bước, và mọi lần ghi tệp
        vẫn hỏi người dùng."""
        existing = (self.ws.root / "AGENTS.md").exists()
        try:
            listing = self.tools.list_files(".", 3)
        except (WorkspaceError, OSError) as err:
            self.ui.failure(str(err) or "Không đọc được thư mục dự án.")
            return
        entries = listing.get("entries", [])[:MAX_INIT_ENTRIES]
        lines = [INIT_TASK]
        if existing:
            lines.append(INIT_EXISTING)
        lines.append("Cấu trúc thư mục (đã bỏ node_modules, .venv, .git…):\n" + "\n".join(entries))
        self.ui.line("  Peto sẽ xem qua dự án rồi đề xuất AGENTS.md; bạn vẫn duyệt như mọi lần ghi tệp.", "dim")
        self.run_task("\n\n".join(lines))

    def note(self, text: str) -> None:
        """/nho: ghi một điều cần nhớ vào mục "Ghi nhớ" của AGENTS.md ở gốc dự án.

        Ghi ngay trên máy, không gọi model nên không tốn bước; AGENTS.md gốc đi kèm mọi bước nên Peto nhớ từ yêu cầu
        tới. Chính người dùng gõ nội dung nên không hỏi lại. Không đưa vào bản hoàn tác, để /undo vẫn là lần sửa của
        Peto.
        """
        note = " ".join(text.split())
        if not note:
            self.ui.line("  Gõ /nho kèm điều Peto cần nhớ về dự án, ví dụ: /nho chạy test bằng python -m pytest", "dim")
            return
        if len(note) > MAX_NOTE_CHARS:
            self.ui.line(f"  Ghi chú dài quá {MAX_NOTE_CHARS} ký tự; viết gọn lại nhé.", "yellow")
            return
        try:
            path = self.ws.resolve("AGENTS.md", must_exist=False)
            file = self.ws.read(path) if path.exists() else None
            updated = add_note(file.text if file else "", note)
            if len(updated) > MAX_GUIDE_CHARS:
                raise WorkspaceError("AGENTS.md sẽ vượt 32.000 ký tự; rút gọn tệp trước khi ghi thêm.")
            self.ws.write(path, updated, newline=file.newline if file else "\n", bom=file.bom if file else False)
            written = self.ws.read(path).digest
        except WorkspaceError as err:
            self.ui.failure(str(err))
            return
        except OSError as err:
            self.ui.failure(f"Không ghi được AGENTS.md: {err.strerror or type(err).__name__}.")
            return
        # Tệp đổi ngoài công cụ sửa tệp: Peto phải đọc lại trước khi tự sửa AGENTS.md, như mọi tệp khác.
        self.ws.read_digests.pop(path, None)
        # Bước kế tiếp mang theo bản AGENTS.md mới, nên coi như Peto đã thấy nó; không thì lần sửa tệp tới bị chặn vì
        # "hướng dẫn vừa đổi" và tốn thêm một bước.
        if "AGENTS.md" in self.tools.seen_guides:
            self.tools.seen_guides["AGENTS.md"] = written
        self._log("note", text=note)
        self.ui.success(f"Đã ghi vào AGENTS.md, mục Ghi nhớ: {note}")

    def show_diff(self):
        if not self.tools.checkpoint.files:
            try:
                self.tools.checkpoint = Checkpoint.restore(self.ws)
            except WorkspaceError as err:
                self.ui.failure(str(err))
                return
        self.tools.checkpoint.show(self.ui)

    def undo(self):
        self.show_diff()
        if not self.tools.checkpoint.files:
            return
        self.ui.line("Hoàn tác các tệp trên? Đây là bản sửa trực tiếp gần nhất được lưu cho dự án này.", "yellow")
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
        """/permissions: lệnh nhớ trong phiên ([s]) và lệnh luôn cho phép ở dự án này ([l], lưu trên máy)."""
        if clear:
            self.tools.command_grants.clear()
            removed = approvals.clear(self.ws.root)
            self.ui.success("Đã xóa quyền chạy lệnh nhớ trong phiên" +
                            (f" và {removed} lệnh luôn cho phép ở dự án này." if removed else "."))
            return
        saved = approvals.entries(self.ws.root)
        if not self.tools.command_grants and not saved:
            self.ui.line("  Chưa nhớ lệnh nào: trong phiên chọn [s], luôn cho phép ở dự án này chọn [l].", "dim")
        if self.tools.command_grants:
            self.ui.line("  Nhớ trong phiên:", "dim")
        for directory, command, timeout, shell in sorted(self.tools.command_grants):
            self.ui.item(f"{command} · {directory} · {timeout}s" + (f" · {shell}" if shell != "cmd" else ""))
        if saved:
            self.ui.line("  Luôn cho phép ở dự án này (lưu trên máy):", "dim")
        for item in saved:
            where = "" if item["directory"] == "." else f" · trong {item['directory']}"
            self.ui.item(f"{item['command']}{where}" + (f" · {item['shell']}" if item["shell"] != "cmd" else ""))

    def compact(self, *, propagate_cancel=False):
        metrics = self.metrics if self._running else Metrics()
        try:
            return self._compact(metrics, propagate_cancel=propagate_cancel)
        finally:
            if not self._running and metrics.calls["compact"]:
                self._log("compaction_metrics", metrics=metrics.snapshot())

    def _compact(self, metrics, *, propagate_cancel=False):
        prefix, tail = compact_prefix(self.items)
        if not prefix:
            self.ui.line("  Hội thoại còn ngắn, chưa cần tóm tắt.", "dim")
            return False
        self.ui.step("Đang tóm tắt ngữ cảnh cũ (dùng một lượt gọi model)")
        body = {"input": efficient_input(portable(prefix)), "effort": "low", "model": self.model,
                "context": {"purpose": "compact"}}
        started = time.monotonic()
        def waiting():
            self.ui.status(f"… Đang tóm tắt ngữ cảnh · {int(time.monotonic() - started)}s · Ctrl+C dừng")
        try:
            metrics.calls["compact"] += 1
            with metrics.measure("compact"), contextlib.closing(self.client.stream("/api/agent/step", body, on_idle=waiting)) as events:
                for event in events:
                    if event.get("type") == "meta":
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    if event.get("type") == "error":
                        raise ApiError(0, str(event.get("message", "Không tóm tắt được.")))
                    if event.get("type") != "done":
                        continue
                    metrics.record_usage("compact", event.get("usage"))
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
            self.metrics = self.tools.metrics = Metrics()
            self.active_seconds = 0.0
        self._running = True
        self.ui.title(f"Peto · đang làm · {self.ws.root.name}")
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
                reply = "\n".join(text_of(item) for item in output
                                  if item.get("type") == "message" and item.get("role") == "assistant").strip()
                if reply:
                    # Ghi cả lời Peto để nhật ký đọc được như một bản chép lại; tệp hội thoại cho /resume chỉ giữ lần
                    # gần nhất của mỗi dự án nên không dùng để xem lại những lần cũ được.
                    self._log("reply", text=cap_text(reply, MAX_LOGGED_REPLY))
                self.items.extend(output)
                pending = [item for item in output if item.get("type") == "function_call"]
                if not pending:
                    if self.tools.changes and self.tools.command_revision < self.tools.revision and not verification_reminded:
                        verification_reminded = True
                        self.items.append({"type": "message", "role": "assistant", "content": (
                            "Kiểm tra sau sửa: xem hướng dẫn AGENTS.md và cấu hình dự án để chọn test/build/lint phù hợp. "
                            "Chạy kiểm tra với quyền người dùng cho phép. Nếu không cần, không có hoặc bị từ chối, "
                            "nêu rõ lý do; không lặp lại lệnh đã bị từ chối. Chỉ sửa lỗi liên quan, tối đa 3 lần kiểm tra thất bại, "
                            "không cài thêm công cụ hay mở rộng phạm vi. Báo lệnh nào đã chạy và kết quả thực tế.")})
                        continue
                    break
                self._save_progress()
                while pending:
                    call = pending[0]
                    with self.metrics.measure("tools"):
                        result = cap_result(self.tools.call(str(call.get("name", "")), str(call.get("arguments", ""))))
                    encoded = json.dumps(result, ensure_ascii=False)
                    self._log("tool", name=call.get("name"), arguments=cap_text(str(call.get("arguments", "")), 2000),
                              result=cap_text(encoded, 4000))
                    self.items.append({"type": "function_call_output", "call_id": call.get("call_id", ""), "output": encoded})
                    pending.pop(0)
                    self._save_progress()
                if self.tools.captured:
                    self.items.append(tool_images(self.tools.captured))
                    self.tools.captured = []
                    drop_old_images(self.items)
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
            self.active_seconds += time.monotonic() - started
            self._running = False
            self._summary(self.active_seconds, outcome)
            history.save(self.ws.root, self.client.server, self.items, retryable=self.can_retry, model=self.model)

    def _save_progress(self) -> None:
        """Lưu hội thoại giữa yêu cầu, để đóng cửa sổ giữa chừng thì /resume vẫn còn những gì Peto đã làm.

        Cửa sổ console đóng thì Windows tắt Python ngay, khối finally của _run không chạy (thử trong ConPTY ngày
        2026-09-23), nên chỉ lưu lúc xong yêu cầu là mất cả yêu cầu đang dở. Lệnh gọi công cụ chưa có kết quả được ghi
        INTERRUPTED_RESULT trong bản lưu, để bước kế tiếp sau /resume vẫn hợp lệ với model.
        """
        answered = {item.get("call_id") for item in self.items if item.get("type") == "function_call_output"}
        items = list(self.items)
        for item in self.items:
            if item.get("type") == "function_call" and item.get("call_id") not in answered:
                items.append({"type": "function_call_output", "call_id": item.get("call_id", ""),
                              "output": json.dumps(INTERRUPTED_RESULT, ensure_ascii=False)})
        history.save(self.ws.root, self.client.server, items, model=self.model, interrupted=True)

    def _step(self) -> list[dict] | None:
        body = {"input": efficient_input(self.items), "effort": self.effort, "model": self.model, "context": {
            "project": self.ws.root.name, "os": f"{platform.system()} {platform.release()}".strip(),
            "project_guidance": guides(self.ws), "features": list(FEATURES)}}
        writer = self.ui.reply()
        started = time.monotonic()
        phase = "nghĩ"
        output = None
        searching = False

        def waiting() -> None:
            # Dòng tạm chỉ hiện tới khi Peto in được dòng chữ đầu tiên của bước này.
            if not writer.started:
                self.ui.status(f"… Peto đang {phase} · {int(time.monotonic() - started)}s")

        waiting()
        try:
            self.metrics.calls["model"] += 1
            with self.metrics.measure("model"), contextlib.closing(self.client.stream("/api/agent/step", body, on_idle=waiting)) as events:
                for event in events:
                    kind = event.get("type")
                    if kind == "meta":
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    elif kind == "search":
                        # Tìm web chạy ở phía dịch vụ AI; ở đây chỉ báo cho người dùng biết bước này có tra web.
                        if event.get("text") == "searching" and not searching:
                            searching = True
                            phase = "tìm web"
                            self.ui.step("Tìm trên web")
                            self._log("search")
                        waiting()
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
                        self.metrics.record_usage("model", usage)
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
        self.ui.title(f"Peto · {TITLE_LABELS[outcome]} · {self.ws.root.name}")
        if elapsed >= BELL_AFTER_SECONDS:
            self.ui.bell()
        # Một dòng duy nhất, theo bản phác chủ web chọn ngày 2026-09-22: số bước còn lại đã nằm dưới ô nhập, còn thời
        # gian từng phần và token chi tiết thì ghi vào nhật ký và xem bằng /usage.
        parts = [f"{OUTCOME_MARKS[outcome]} {OUTCOME_LABELS[outcome]} {format_duration(elapsed)}"]
        if self.tools.changes:
            parts.append(f"sửa {len(self.tools.changes)} tệp")
        if self.tools.commands:
            failed = sum(1 for command in self.tools.commands
                         if command.get("classification") not in {"passed", "success", "no_match"})
            parts.append(f"chạy {len(self.tools.commands)} lệnh" + (f" ({failed} lỗi)" if failed else ""))
        if running := self.tools.jobs.running():
            parts.append(f"đang chạy {len(running)} lệnh nền")
        if left := sum(1 for step in self.tools.plan if step.get("status") != "done"):
            parts.append(f"còn {left} việc chưa xong")
        if self.context_tokens:
            parts.append(f"hội thoại {format_tokens(self.context_tokens)} token")
        self.ui.line("  " + " · ".join(parts), "dim")
        self._log("summary", outcome=outcome, seconds=round(elapsed, 1), changes=self.tools.changes,
                  commands=self.tools.commands, metrics=self.metrics.snapshot())

    def show_metrics(self, metrics: Metrics | None = None) -> None:
        """Thời gian từng phần và token của yêu cầu gần nhất, cho /usage; cuối mỗi yêu cầu không in những dòng này."""
        metrics = metrics or self.metrics
        seconds = metrics.seconds
        self.ui.line(f"  Thời gian yêu cầu · AI/kết nối {seconds['model']:.1f}s · chạy lệnh {seconds['commands']:.1f}s"
                     f" · công cụ khác {seconds['tools']:.1f}s · tóm tắt {seconds['compact']:.1f}s"
                     f" · chờ bạn {seconds['permission']:.1f}s", "dim")
        for phase, label in (("model", "làm việc"), ("compact", "tóm tắt")):
            calls = metrics.calls[phase]
            if not calls:
                continue
            usage = metrics.usage[phase]
            missing = calls - usage["reported"]
            if not usage["reported"]:
                detail = "chưa có số liệu token"
            else:
                detail = f"{format_tokens(usage['input_tokens'])} vào / {format_tokens(usage['output_tokens'])} ra"
                if missing:
                    detail += f" · thiếu số liệu {missing} lượt"
            self.ui.line(f"  Token {label} · {calls} lượt gọi · {detail}", "dim")
