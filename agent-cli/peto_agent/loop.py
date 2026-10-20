"""Vòng làm việc của Peto Agent: gửi từng bước lên máy chủ, chạy công cụ trên máy, gửi kết quả ở bước sau."""

from __future__ import annotations

import contextlib
import copy
import json
import platform
import threading
import time
import uuid
from datetime import datetime

from . import approvals, continuation, history, mentions, recall, subagent, user_guide
from .journal import Journal, DurabilityError
from .observer import observe
from .runtime_client import RuntimeClient
from .task_state import TaskState
from .checkpoint import Change, Checkpoint
from .context import compact_prefix, compact_input, context_size, text_of, efficient_input
from .events import Permission, RequestEnd
from .formats import format_duration, format_tokens  # noqa: F401 - evals/report.py và __main__ lấy từ đây
from .project_guide import MAX_GUIDE_CHARS, MAX_NOTE_CHARS, add_note, guides
from .metrics import Metrics
from .client import ApiError, Client
from .budget import Tracker, estimate, ceiling
from .config import log_dir
from .presentation import AgentUI
from .runner import cap_text
from .tools import Tools
from .session_protocol import INTERRUPTED_RESULT, interrupted_items
from .workspace import Workspace, WorkspaceError

# Hội thoại tới ngần này mục hoặc ngần này ký tự thì Peto tự tóm tắt phần cũ trước bước kế tiếp.
COMPACT_ITEMS = 180
COMPACT_CHARS = 200_000
# Phần cuối output gửi kèm tin báo lệnh nền vừa dừng; muốn hơn thì Peto đọc bằng read_command_output.
MAX_JOB_NOTE_CHARS = 4000
# Đặt tên hội thoại (CLI 0.21.0, chủ web chọn ngày 2026-10-12): một lượt Peto mức thấp (1 bước), gửi đầu tin đầu tiên
# và đầu câu trả lời; tên dài quá thì cắt.
TITLE_SOURCE_CHARS = (2000, 1000)
MAX_TITLE_CHARS = 60
# Mỗi lời Peto ghi vào nhật ký giữ tối đa ngần này ký tự (phần đầu và phần cuối), để nhật ký không phình theo code dài.
MAX_LOGGED_REPLY = 4000
# Máy chủ không lưu hội thoại nên bước nào cũng gửi lại ảnh: chỉ giữ 4 ảnh gần nhất, như chat trên web.
MAX_KEPT_IMAGES = 4
OLD_IMAGE_NOTE = "(Ảnh này đã gửi ở tin trước; để hội thoại nhẹ, peto không gửi lại.)"
# web_search_call do dịch vụ AI sinh ra khi Peto tra web: giữ lại để hội thoại gửi đi không hụt mục.
KEPT_ITEM_TYPES = {"message", "function_call", "reasoning", "web_search_call"}
STOPPED_RESULT = {"error": "Người dùng đã dừng yêu cầu bằng Ctrl+C."}
# /btw hỏi lúc Peto đang làm: lệnh gọi công cụ chưa xong được ghi thế này trong bản gửi đi, để hội thoại vẫn hợp lệ.
PENDING_RESULT = {"error": "Công cụ này đang chạy, chưa có kết quả (câu hỏi /btw được gửi giữa chừng)."}
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
# Nhãn trên tiêu đề cửa sổ, để người dùng làm việc khác vẫn thấy Peto xong chưa.
TITLE_LABELS = {"done": "xong", "stopped": "đã dừng", "error": "lỗi", "limit": "tạm dừng"}
# Yêu cầu lâu hơn ngần này giây thì kêu một tiếng khi xong; việc vài giây thì kêu chỉ tổ ồn.
BELL_AFTER_SECONDS = 10.0
# Tự thử lại (CLI 0.25.0, theo opencode): lỗi tạm thời mà bước chưa có phản hồi (máy chủ đã hoàn lại bước, hoặc chưa
# tới được máy chủ) thì chờ ngần này giây rồi gửi lại, tối đa ba lần. opencode chờ 2–10 giây, tối đa mười lần.
RETRY_WAITS = (2, 5, 10)
# Lỗi kết nối tới máy chủ Peto (0: không nối được; 502–504: Cloudflare hay VPS đang khởi động lại) trước sự kiện đầu
# tiên: bước chưa được tính nên gửi lại không tốn gì.
RETRY_STATUSES = {0, 502, 503, 504}
# Khóa mà công cụ đã tự giới hạn, không được cắt giữa chừng: hướng dẫn dự án, và nội dung tệp gửi kèm lời từ chối sửa
# tệp chưa đọc (``current``, cùng giới hạn như read_file).
BOUNDED_KEYS = frozenset({"project_guidance", "skill_guidance", "current"})
# read_file với "read_more" trả tới 32.000 ký tự, quá mức 20.000 chung của cap_text: cắt phần giữa thì mất code.
READ_BOUNDED_KEYS = BOUNDED_KEYS | {"content"}


def cap_result(value, bounded=BOUNDED_KEYS):
    """Cắt chuỗi và danh sách dài trong kết quả công cụ mà vẫn giữ JSON hợp lệ."""
    if isinstance(value, str):
        return cap_text(value)
    if isinstance(value, list):
        return [cap_result(item) for item in value[:400]]
    if isinstance(value, dict):
        # Guidance is already bounded by its reader; never truncate rules in the middle.
        return {key: item if key in bounded else cap_result(item) for key, item in value.items()}
    return value


class _ContextOverflow(Exception):
    pass


class _Retry(Exception):
    """Lỗi tạm thời của một bước mà bước chưa có phản hồi: _step chờ rồi gửi lại."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
                 effort: str = "medium", model: str = "peto", model_step_cost: int = 1,
                 max_steps: int | None = None):
        if max_steps is not None and (type(max_steps) is not int or max_steps < 1):
            raise ValueError("Giới hạn bước phải là số nguyên dương hoặc None.")
        self.client = client
        self.ws = workspace
        self.ui = observe(ui)
        self.tools = Tools(workspace, self.ui)
        self.task_state = TaskState(workspace)
        self.tools.acceptance = self.task_state
        self._store = None
        self._active_step = None
        self._active_ordinal = None
        self._settled = set()
        self._published_output = None
        self._logical_step = None
        self._compaction_step = None
        self.tools.record_result = self._record_tool
        self.log = log
        self.effort = effort
        # Phiên thường không giới hạn bước; bộ chấm có thể đặt ngân sách riêng cho mỗi yêu cầu của phiên đó.
        self.max_steps = max_steps
        # Model chọn bằng /model, và số bước mỗi lần gọi model đó (trước khi nhân mức suy nghĩ).
        self.model = model
        self.model_step_cost = model_step_cost
        # Tên model hiện cho người dùng ở dòng cuối yêu cầu; phiên đặt lại theo danh sách model của máy chủ.
        self.model_label = model
        self.items: list[dict] = []
        self.steps_used: int | None = None
        self.steps_limit: int | None = None
        # Độ dài hội thoại mô hình thấy ở bước gần nhất (token vào + ra): cho biết lúc nào nên /new.
        self.context_tokens: int | None = None
        self.context_budget = Tracker()
        self.can_retry = False
        self.metrics = self.tools.metrics
        self._running = False
        self.active_seconds = 0.0
        # Chế độ (làm việc hay Lập kế hoạch) Peto được báo gần nhất trong hội thoại; đổi thì báo lại ở bước kế tiếp.
        self._announced_mode = "build"
        # Hội thoại đang mở trong danh sách /resume (CLI 0.20.0): mã sinh ở lần lưu đầu, tên tạm là đầu tin đầu tiên.
        self.session_id: str | None = None
        self.title: str | None = None
        # Model đặt tên hội thoại sau yêu cầu đầu (cần máy chủ có "title"); bài thi tắt để khỏi tốn bước.
        self.auto_title = True
        self._titling = False
        self._save_lock = threading.RLock()
        # Lời báo gần nhất về AGENTS.md chung (dài quá, đọc lỗi): chỉ in lại khi đổi, khỏi lặp mỗi bước.
        self._guide_problem: str | None = None
        # Ảnh chụp dự án lúc bắt đầu mỗi yêu cầu (CLI 0.26.0): dấu của tin → mã cây, lưu cùng hội thoại.
        self.snapshot_marks: dict[str, str] = {}
        # Agent con explore (CLI 0.27.0) dùng máy chủ, model và ngữ cảnh bước của phiên này.
        self.tools.explorer = self._explore
        self.tools.history_reader = self._read_history
        self.client = RuntimeClient(client, self._journal, self._publish_model,
                                    lambda purpose: self._logical_step if purpose in {'work', 'wrapup'}
                                    else self._compaction_step if purpose == 'compact' else None)
        # UI chỉ giữ callback nhận đầu vào, không giữ quyền sở hữu transcript hay kết quả công cụ.
        bind = getattr(ui, 'bind_runtime', None)
        if bind:
            bind(self.enqueue, self.pending_input)

    def _journal(self):
        with self._save_lock:
            if self.session_id is None:
                self.session_id = history.new_id()
            if self._store is None or self._store.identity['id'] != self.session_id:
                self._store = Journal(self.ws.root, self.client.server, self.session_id)
            return self._store

    def _runtime_data(self, items=None, **flags):
        return {'version': history.VERSION, 'id': self.session_id, 'title': self.title or '', 'model': self.model,
                'model_identity': self.context_budget.catalog.get(self.model, {}).get('identity', ''),
                'saved_at': time.time(), 'items': self.items if items is None else items,
                'retryable': self.can_retry, 'interrupted': False, 'snapshots': self.snapshot_marks,
                'task_state': self.task_state.data,
                'pending_images': tool_images(self.tools.captured) if self.tools.captured else None, **flags}

    def _publish_output(self, output, *, journal=None, request_id=None, response=None):
        journal = journal or self._journal()
        step = self._logical_step or uuid.uuid4().hex
        candidate = self.items + output
        calls = [item for item in output if item.get('type') == 'function_call']
        journal.publish_step(step, calls, self._runtime_data(candidate), request_id=request_id, response=response)
        self.items = candidate
        self._active_step, self._settled = step, set()
        self._published_output = output

    def _publish_model(self, journal, request_id, event):
        output = [item for item in event['output'] if isinstance(item, dict) and item.get('type') in KEPT_ITEM_TYPES]
        self._publish_output(output, journal=journal, request_id=request_id, response=event)

    def _record_tool(self, done):
        if self._active_step is None or self._active_ordinal is None or self._active_ordinal in self._settled:
            return
        output = cap_result(done.result, READ_BOUNDED_KEYS if done.name in {'read_file', 'read_history'} else BOUNDED_KEYS)
        evidence_id = f'{self._active_step}:{self._active_ordinal}'
        self.task_state.record(evidence_id, done.name, done.args, output)
        if 'task_state' in self.tools.features:
            output = {**output, 'evidence_id': evidence_id}
        candidate = self.items + [{'type': 'function_call_output', 'call_id': done.call_id,
                                   'output': json.dumps(output, ensure_ascii=False)}]
        try:
            self._journal().tool_finished(self._active_step, self._active_ordinal, output,
                                          self._runtime_data(candidate), task_state=self.task_state.data)
        except BaseException:
            self.task_state.data = self._task_state_before
            raise
        self.items = candidate
        done.result.clear(); done.result.update(output)
        self._settled.add(self._active_ordinal)

    def enqueue(self, text, images=(), *, delivery='steer', item_id=None):
        packed = [{'number': number, 'data': image.data_url(), 'width': image.width, 'height': image.height}
                  for number, image in images]
        journal = self._journal()
        if journal.read() is None:
            journal.snapshot(self._runtime_data())
        return journal.enqueue({'text': text, 'images': packed}, delivery, item_id)

    def pending_input(self):
        return self._journal().pending() if self._store is not None else []

    def ack_control(self, text):
        entries = [row for row in self.pending_input() if row['data']['text'].strip() == text]
        if entries:
            self._journal().deliver([entries[0]['id']], self._runtime_data())

    def show_pending(self):
        entries = self.pending_input()
        if not entries:
            self.ui.line('Không có tin đang chờ.', 'dim')
            return
        chosen = self.ui.choose('Tin đã lưu, chưa đưa vào hội thoại',
                                [(row['data']['text'][:100], row['delivery']) for row in entries])
        if chosen is None:
            return
        row = entries[chosen]
        text = row['data']['text']
        self.ui.line(text)
        images = self._inbox_images(row['data'])
        if images:
            self.ui.line('Ảnh đính kèm: ' + ', '.join(f'[Ảnh {number}]' for number, _ in images), 'dim')
        control = text.lstrip().startswith('/')
        action = self.ui.choose('Xử lý tin đang chờ',
                                [('Đưa vào ô nhập' if control else 'Gửi tin đã lưu',
                                  'bấm Enter để chạy lệnh' if control else 'tiếp tục với đúng ảnh đính kèm'),
                                 ('Xóa tin', 'không chạy')])
        if action == 0:
            if control:
                self.ui.prefill(text)
            else:
                self.run_task(text, images)
        elif action == 1:
            self._journal().cancel_input(row['id'])

    def reset(self) -> None:
        self._store = None
        self._active_step = self._active_ordinal = None
        self._published_output = None
        self._logical_step = None
        self.task_state = TaskState(self.ws)
        self.tools.acceptance = self.task_state
        self.snapshot_marks = {}
        self.tools.skills.loaded.clear()
        self.tools.reset_task()
        self.metrics = self.tools.metrics = Metrics()
        self.active_seconds = 0.0
        self.items = []
        self.context_tokens = None
        self.context_budget.reset()
        self.can_retry = False
        self.tools.command_grants.clear()
        self.tools.seen_guides.clear()
        self.tools.checkpoint = Checkpoint(self.ws)
        self._announced_mode = "build"
        # /new: hội thoại mới có mã mới, hội thoại cũ vẫn nằm trong /resume.
        self.session_id = self.title = None
        self._announce_title()

    def shown_title(self) -> str | None:
        """Tên hội thoại để hiện: tên đã đặt, hoặc đầu tin đầu tiên của người dùng; hội thoại trống thì chưa có tên."""
        if self.title:
            return self.title
        if any(item.get("role") == "user" and not history.is_note(item) for item in self.items):
            return history.first_title(self.items)
        return None

    def _announce_title(self) -> None:
        self.ui.set_session_title(self.shown_title())

    def save(self, items: list[dict] | None = None, **flags) -> bool:
        """Lưu hội thoại đang mở để /resume mở lại (``flags``: retryable, interrupted)."""
        with self._save_lock:
            if self.session_id is None:
                self.session_id = history.new_id()
            saved = history.save(self.ws.root, self.client.server, self.items if items is None else items,
                                session_id=self.session_id, title=self.title or "", model=self.model,
                                model_identity=self.context_budget.catalog.get(self.model, {}).get('identity', ''),
                                snapshots=self.snapshot_marks, runtime_managed=True, **flags)
            if saved:
                try:
                    self._journal().snapshot(self._runtime_data(**flags))
                except DurabilityError:
                    return False
            return saved

    def _name_conversation(self) -> None:
        """Sau yêu cầu đầu của một hội thoại: nhờ model đặt tên cho danh sách /resume, ở luồng nền để người dùng gõ
        tiếp ngay. Lỗi, hết bước hay máy chủ cũ thì giữ tên tạm (đầu tin đầu tiên)."""
        if (not self.auto_title or self.title or self._titling or "title" not in self.tools.features
                or self.session_id is None):
            return
        first = next((history.raw_text(item) for item in self.items if item.get("role") == "user"
                      and not history.is_note(item) and history.raw_text(item).strip()), "")
        reply = next((text_of(item) for item in self.items if item.get("role") == "assistant" and text_of(item)), "")
        if not first:
            return
        session_id = self.session_id
        title_journal = self._journal()
        title_client = RuntimeClient(self.client.client, lambda: title_journal, self._publish_model)
        prompt = (f"Tin đầu của người dùng:\n{first[:TITLE_SOURCE_CHARS[0]]}\n\n"
                  f"Đầu câu trả lời của Peto:\n{reply[:TITLE_SOURCE_CHARS[1]]}")
        body = {"input": [user_message(prompt)], "effort": "low", "model": "peto", "context": {"purpose": "title"}}
        self._titling = True

        def run() -> None:
            try:
                with contextlib.closing(title_client.stream("/api/agent/step", body)) as events:
                    for event in events:
                        if event.get("type") != "done" or event.get("purpose") != "title":
                            continue
                        text = " ".join(text_of(item) for item in event.get("output") or []
                                        if item.get("role") == "assistant").strip()
                        title = " ".join(text.splitlines()[0].split()).strip("\"' ") if text else ""
                        if not title:
                            continue
                        title = title if len(title) <= MAX_TITLE_CHARS else title[:MAX_TITLE_CHARS - 1] + "…"
                        if self.session_id == session_id:
                            self.title = title
                            self._announce_title()
                            if not self._running:
                                self.save()
                        else:  # đã /new hay /resume sang hội thoại khác: ghi tên vào tệp của hội thoại cũ
                            with self._save_lock:
                                history.rename(self.ws.root, self.client.server, session_id, title)
                        self._log("title", title=title)
            except (ApiError, OSError, ValueError, DurabilityError):
                pass
            finally:
                self._titling = False

        threading.Thread(target=run, name="peto-title", daemon=True).start()

    def side_question(self, question: str) -> str:
        """/btw (CLI 0.23.0, theo opencode): hỏi bên lề về hội thoại đang mở bằng model đang dùng, mức thấp, một lượt
        không công cụ. Câu hỏi và câu trả lời không vào hội thoại, tệp lưu hay nhật ký. Gọi được từ luồng khác lúc Peto
        đang làm: chỉ đọc một bản chụp của hội thoại. Lỗi ném ApiError (hết bước, máy chủ cũ, mất kết nối)."""
        items = list(self.items)
        answered = {item.get("call_id") for item in items if item.get("type") == "function_call_output"}
        for item in list(items):
            if item.get("type") == "function_call" and item.get("call_id") not in answered:
                items.append({"type": "function_call_output", "call_id": item.get("call_id", ""),
                              "output": json.dumps(PENDING_RESULT, ensure_ascii=False)})
        effort = "low" if "low" in getattr(self, "supported_efforts", ["low"]) else self.effort
        body = {"input": [*efficient_input(items), user_message(question)], "effort": effort, "model": self.model,
                "context": {"purpose": "btw", "project": self.ws.root.name}}
        with contextlib.closing(self.client.stream("/api/agent/step", body)) as events:
            for event in events:
                if event.get("type") == "meta":
                    self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                if event.get("type") == "error":
                    raise ApiError(0, str(event.get("message") or "Không hỏi được câu này."))
                if event.get("type") != "done":
                    continue
                if event.get("purpose") != "btw":
                    raise ApiError(0, "Máy chủ chưa hỗ trợ /btw. Cập nhật máy chủ Peto rồi thử lại.")
                answer = "\n\n".join(text for item in event.get("output") or []
                                       if isinstance(item, dict) and item.get("role") == "assistant"
                                       and (text := text_of(item).strip()))
                return answer or "(Peto không trả lời gì.)"
        raise ApiError(0, "Kết nối tới máy chủ Peto bị ngắt trước khi có câu trả lời.")

    def context_share(self) -> float | None:
        """Mức dùng ngân sách token trước compact; máy chủ cũ dùng ngưỡng mục/ký tự của CLI."""
        if not self.items:
            return None
        if self._model_budget():
            return self.context_budget.share(self.model, efficient_input(self.items), self._budget_extra())
        return max(len(self.items) / COMPACT_ITEMS, context_size(self.items) / COMPACT_CHARS)

    def configure_models(self, models, transport=None):
        self.context_budget.configure(models, transport)

    def _model_budget(self):
        return self.context_budget.catalog.get(self.model) if 'context_budget' in self.tools.features else None

    def _budget_extra(self):
        return max(0, estimate(self._step_context()) - self.context_budget.context.get(self.model, 0))

    def _compact_due(self):
        if not self._model_budget():
            return len(self.items) >= COMPACT_ITEMS or context_size(self.items) > COMPACT_CHARS
        # Transport ceiling is separate from the model window: the server accepts at most 300 items.
        request_size = len(json.dumps({'input': efficient_input(self.items), 'context': self._step_context()},
                                      ensure_ascii=False).encode('utf-8'))
        return (len(self.items) >= 240 or (self.context_share() or 0) >= 1
                or request_size >= self.context_budget.max_request_bytes * .8)

    def set_model(self, model: str, step_cost: int = 1) -> None:
        """Đổi model; hội thoại đang dở vẫn giữ, chỉ bỏ phần model cũ tạo ra mà model mới không đọc được."""
        if model != self.model:
            if self.items:
                self.items = portable(self.items)
            self.context_budget.reset()
            self.context_tokens = None
        self.model, self.model_step_cost = model, step_cost

    def resume(self, items: list[dict], *, retryable: bool = False, model: str = "peto", session_id: str | None = None,
               title: str | None = None, snapshots: dict | None = None, model_identity: str = "") -> None:
        """Mở lại hội thoại đã lưu. Quên các tệp đã đọc, để Peto phải đọc lại trước khi sửa."""
        self.snapshot_marks = dict(snapshots or {})
        self.tools.skills.loaded.clear()
        self.tools.reset_task()
        self.metrics = self.tools.metrics = Metrics()
        self.active_seconds = 0.0
        identity = self.context_budget.catalog.get(self.model, {}).get('identity')
        compatible = model == self.model and (identity is None or identity == model_identity)
        self.items = list(items) if compatible else portable(items)
        self.context_tokens = None
        self.context_budget.reset()
        self.can_retry = retryable
        self.ws.read_digests.clear()
        self.tools.command_grants.clear()
        self.tools.seen_guides.clear()
        self.tools.checkpoint = Checkpoint(self.ws)
        self.session_id, self.title = session_id, title
        self._active_step = self._active_ordinal = self._published_output = self._logical_step = None
        self.task_state = TaskState(self.ws)
        self.tools.acceptance = self.task_state
        self._store = None
        if session_id:
            journal = self._journal()
            journal.claim()
            try:
                journal.recover()
                durable = journal.read()
                if durable:
                    compatible = model == self.model and (identity is None or identity == durable.get('model_identity'))
                    self.items = durable['items'] if compatible else portable(durable['items'])
                    self.task_state = TaskState(self.ws, durable.get('task_state'))
                    self.tools.acceptance = self.task_state
                if entries := journal.pending():
                    self.ui.notice(f'Đã khôi phục {len(entries)} tin đang chờ. /pending để xem; chưa tự chạy tin nào.', 'yellow')
            finally:
                journal.release()
        self._announce_title()
        notes = [history.raw_text(item) for item in self.items if history.is_note(item)]
        self._announced_mode = "build"
        for text in notes:
            if text == history.PLAN_ON_NOTE:
                self._announced_mode = "plan"
            elif text == history.PLAN_OFF_NOTE:
                self._announced_mode = "build"

    def _log(self, kind: str, **data) -> None:
        if self.log is not None:
            self.log.write(kind, **data)

    def _inbox(self, *, steers: bool = True, exclude=None) -> bool:
        """Những gì tới trong lúc Peto làm, chèn vào hội thoại trước bước kế tiếp (theo opencode, CLI 0.20.0):

        - chế độ vừa đổi (Shift+Tab hay /plan) thì một tin nhắc chế độ;
        - lệnh nền vừa tự dừng thì một tin báo kèm phần output chưa đọc, để Peto khỏi đọc đi đọc lại chờ nó xong;
        - tin người dùng nhắn thêm (Enter lúc Peto đang làm), để lái việc đang làm thay vì chờ tới lượt sau.

        Trả True khi có tin nhắn thêm: model định kết thúc thì vẫn chạy thêm một bước để đọc nó.
        """
        mode = getattr(self.ui, "mode", "build")
        if mode != self._announced_mode:
            self.items.append(user_message(history.PLAN_ON_NOTE if mode == "plan" else history.PLAN_OFF_NOTE))
            self._announced_mode = mode
            self._log("mode", mode=mode)
        for job in self.tools.jobs.finished():
            code = job["exit_code"]
            output = job["output"].strip()
            if len(output) > MAX_JOB_NOTE_CHARS:
                output = "…\n" + output[-MAX_JOB_NOTE_CHARS:]
            text = (f"{history.JOB_NOTE}Lệnh nền #{job['id']} ({job['command']}) đã tự dừng sau "
                    f"{format_duration(job['seconds'])}, mã thoát {code}."
                    + (f" Output chưa đọc:\n{output}" if output else " Không có output mới."))
            self.items.append(user_message(text))
            self.ui.notice(f"Lệnh nền #{job['id']} đã dừng · mã thoát {code}", "yellow" if code else "dim")
            self._log("job_finished", id=job["id"], exit_code=code)
        take = getattr(self.ui, "take_steers", None) if steers else None
        steered = False
        # UI cũ cũng được hỗ trợ: nhận rồi lưu ngay; UI mới đã ghi trước khi xác nhận Enter.
        for text, images in take() if take else []:
            self.enqueue(text, images)
        pending = self.pending_input()
        for entry in pending:
            if entry['delivery'] != 'steer' or entry['id'] == exclude:
                continue
            text = entry['data']['text']
            images = self._inbox_images(entry['data'])
            attached = mentions.attach(self.ws, self.tools, text)
            for step in attached.steps:
                self.ui.step(step)
            message = user_message(history.STEER_NOTE + attached.text, images)
            self._journal().deliver([entry['id']], self._runtime_data(self.items + [message]))
            self.items.append(message)
            self.ui.link_user_entry(self.items[-1])
            drop_old_images(self.items)
            self._log("steer", text=text, images=len(images))
            steered = True
        return steered

    @staticmethod
    def _inbox_images(data):
        import base64
        from .images import Image
        return [(row['number'], Image(base64.b64decode(row['data'].partition(',')[2]),
                 row['data'].partition(';')[0].removeprefix('data:'), row['width'], row['height']))
                for row in data.get('images', [])]

    def run_task(self, text: str, images=()) -> None:
        """Chạy một yêu cầu. ``images`` là các cặp (số ảnh, ảnh) dán kèm bằng Alt+V hay kéo thả."""
        # Giữ lease suốt cả nhận yêu cầu, tool và finalization; mở hai CLI không được chạy trùng phiên.
        journal = self._journal()
        journal.claim()
        try:
            self._run_task(text, images)
        finally:
            journal.release()

    def _run_task(self, text, images=()):
        self.tools.checkpoint = Checkpoint(self.ws)
        image_keys = [(number, image.data_url()) for number, image in images]
        existing = next((row for row in self.pending_input() if row['data']['text'].strip() == text.strip()
                         and row['delivery'] in {'input', 'queue', 'steer'}
                         and [(image['number'], image['data']) for image in row['data'].get('images', [])] == image_keys), None)
        if existing:
            item_id = existing['id']
        else:
            item_id = self.enqueue(text, images, delivery='input')
        attached = mentions.attach(self.ws, self.tools, text)
        for step in attached.steps:
            self.ui.step(step)
        for notice in attached.notices:
            self.ui.line(f"  {notice}", "yellow")
        # Đổi chế độ, lệnh nền dừng trong lúc rảnh: báo trước tin của người dùng, như opencode chèn lời nhắc chế độ.
        self._inbox(steers=False, exclude=item_id)
        message = user_message(attached.text, images)
        self.task_state.data['goal'] = text[:8000]
        self._journal().deliver([item_id], self._runtime_data(self.items + [message]))
        self.items.append(message)
        self._mark_request(len(self.items) - 1)
        self.ui.link_user_entry(self.items[-1])
        drop_old_images(self.items)
        if not self.title:
            self._announce_title()
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
        """/remember: ghi một điều cần nhớ vào mục "Ghi nhớ" của AGENTS.md ở gốc dự án.

        Ghi ngay trên máy, không gọi model nên không tốn bước; AGENTS.md gốc đi kèm mọi bước nên Peto nhớ từ yêu cầu
        tới. Chính người dùng gõ nội dung nên không hỏi lại. Không đưa vào bản hoàn tác, để /undo vẫn là lần sửa của
        Peto.
        """
        note = " ".join(text.split())
        if not note:
            self.ui.line("  Gõ /remember kèm điều Peto cần nhớ về dự án, ví dụ: /remember chạy test bằng python -m pytest", "dim")
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
        self._guide_written(path, written)
        self._log("note", text=note)
        self.ui.success(f"Đã ghi vào AGENTS.md, mục Ghi nhớ: {note}")

    def _guide_written(self, path, written: str) -> None:
        # Tệp đổi ngoài công cụ sửa tệp: Peto phải đọc lại trước khi tự sửa AGENTS.md, như mọi tệp khác.
        self.ws.read_digests.pop(path, None)
        # Bước kế tiếp mang theo bản AGENTS.md mới, nên coi như Peto đã thấy nó; không thì lần sửa tệp tới bị chặn vì
        # "hướng dẫn vừa đổi" và tốn thêm một bước.
        if "AGENTS.md" in self.tools.seen_guides:
            self.tools.seen_guides["AGENTS.md"] = written

    def write_project_guide(self, text: str) -> bool:
        """/guide: ghi AGENTS.md ở gốc dự án bằng chữ người dùng vừa soạn (CLI 0.25.0). Như /remember: không hỏi lại,
        không vào bản hoàn tác, giữ CRLF/BOM của tệp cũ."""
        if len(text) > MAX_GUIDE_CHARS:
            self.ui.failure("AGENTS.md vượt 32.000 ký tự; rút gọn rồi lưu lại.")
            return False
        try:
            path = self.ws.resolve("AGENTS.md", must_exist=False)
            file = self.ws.read(path) if path.exists() else None
            self.ws.write(path, text.replace("\r\n", "\n"), newline=file.newline if file else "\n",
                          bom=file.bom if file else False)
            written = self.ws.read(path).digest
        except WorkspaceError as err:
            self.ui.failure(str(err))
            return False
        except OSError as err:
            self.ui.failure(f"Không ghi được AGENTS.md: {err.strerror or type(err).__name__}.")
            return False
        self._guide_written(path, written)
        self._log("guide", target="project")
        self.ui.success("Đã lưu AGENTS.md của dự án; bước sau Peto dùng bản mới.")
        return True

    def write_user_guide(self, text: str) -> bool:
        """/guide: ghi AGENTS.md chung trong hồ sơ người dùng (CLI 0.25.0)."""
        try:
            user_guide.write(text)
        except ValueError as err:
            self.ui.failure(str(err))
            return False
        except OSError as err:
            self.ui.failure(f"Không ghi được hướng dẫn chung: {err.strerror or type(err).__name__}.")
            return False
        self._guide_problem = None
        self._log("guide", target="user")
        if "user_guide" in self.tools.features:
            self.ui.success("Đã lưu hướng dẫn chung; mọi dự án dùng bản mới từ bước sau.")
        else:
            self.ui.line("  Đã lưu hướng dẫn chung, nhưng máy chủ Peto chưa nhận loại hướng dẫn này: Peto sẽ dùng khi máy "
                         "chủ được cập nhật.", "yellow")
        return True

    def _explore(self, task: str, depth: str, progress) -> dict:
        result = subagent.run(self, task, depth, progress)
        self._log("explore", task=cap_text(task, 500), depth=depth, steps=result.get("steps"),
                  files=result.get("files_read"), error=result.get("error"))
        return result

    def _mark_request(self, position: int) -> None:
        """Chụp dự án lúc bắt đầu yêu cầu, ở luồng nền trong lúc chờ model (như opencode chụp khi request đang bay).
        Thao tác đổi tệp đầu tiên đợi ảnh này xong (Tools.wait_snapshot)."""
        shots = self.tools.snapshots()
        if shots is None or not shots.available:
            return
        key = history.fingerprint(self.items, position)

        def capture() -> None:
            tree = shots.capture()
            if tree:
                self.snapshot_marks[key] = tree

        thread = threading.Thread(target=capture, name="peto-snapshot", daemon=True)
        self.tools.pending_snapshot = thread
        thread.start()

    def restore_point(self, position: int) -> str | None:
        """Mã ảnh chụp lúc trước tin ở ``position``; không có (tắt ảnh chụp, tin cũ hơn 0.26.0) thì None."""
        if self.tools.snapshots() is None:
            return None
        return self.snapshot_marks.get(history.fingerprint(self.items, position))

    def restore_files(self, tree: str, label: str) -> None:
        """Đưa tệp trong dự án về đúng ảnh ``tree`` (theo revert.ts của opencode). Liệt kê tệp sẽ đổi, kể cả tệp người
        dùng tự sửa sau đó, rồi hỏi. Ghi bằng bản hoàn tác nên /undo ngay sau đó trả lại như trước khi khôi phục."""
        shots = self.tools.snapshots()
        self.tools.wait_snapshot()
        if shots is None or not shots.available:
            self.ui.failure(shots.problem if shots and shots.problem else "Ảnh chụp dự án đang tắt.")
            return
        if not shots.has(tree):
            self.ui.failure("Ảnh chụp của tin này đã bị dọn (giữ 30 ngày) nên không khôi phục được.")
            return
        now = shots.capture()
        if now is None:
            self.ui.failure(shots.problem or "Không chụp được dự án lúc này.")
            return
        try:
            names = shots.changed(tree, now)
            old, current = shots.contents(tree, names), shots.contents(now, names)
        except Exception as err:  # noqa: BLE001 - lỗi git nào cũng chỉ báo, không đụng tệp
            self.ui.failure(f"Không đọc được ảnh chụp: {err}")
            return
        names = [name for name in names if old.get(name) != current.get(name)]
        if not names:
            self.ui.line("  Các tệp trong dự án đã giống lúc đó.", "dim")
            return
        self.ui.line(f"  Khôi phục về lúc trước tin \"{label}\" sẽ đổi {len(names)} tệp:", "dim")
        for name in names[:15]:
            state = " (xóa)" if old.get(name) is None else " (tạo lại)" if current.get(name) is None else ""
            self.ui.line(f"    {name}{state}", "dim")
        if len(names) > 15:
            self.ui.line(f"    … và {len(names) - 15} tệp nữa", "dim")
        self.ui.line("  Tệp .gitignore bỏ qua, tệp lớn hơn 2 MB và .env không nằm trong ảnh chụp nên giữ nguyên.", "dim")
        choice = self.ui.choose(f"Khôi phục {len(names)} tệp?", [
            ("Khôi phục", "kể cả thay đổi bạn tự làm sau tin đó; /undo ngay sau đó trả lại như bây giờ"),
            ("Thôi", "không đổi tệp nào")])
        if choice != 0:
            return
        plan = Checkpoint(self.ws)
        plan.files = {name: Change(old.get(name), current.get(name), "restore") for name in names}
        try:
            restored = plan.undo()
        except (WorkspaceError, OSError, KeyboardInterrupt) as err:
            self.ui.failure(str(err) or "Đã dừng khôi phục.")
            restored = [name for name in names if name not in plan.files]
        back = Checkpoint(self.ws)
        back.files = {name: Change(current.get(name), old.get(name), "restore") for name in restored}
        back.commands_covered = True
        try:
            back.persist()
        except (WorkspaceError, OSError):
            pass
        self.tools.checkpoint = back
        self.ws.read_digests.clear()
        if restored:
            self.items.append(user_message(
                f"Người dùng vừa khôi phục {len(restored)} tệp về lúc trước tin \"{label}\": " + ", ".join(restored[:30])
                + ("…" if len(restored) > 30 else "") + ". Đọc lại tệp trước khi tiếp tục; không tự làm lại thay đổi cũ."))
            self.save()
            self.ui.success(f"Đã khôi phục {len(restored)} tệp. Gõ /undo để trả lại như trước khi khôi phục.")

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
        self.ui.line("Hoàn tác các tệp trên? Đây là lần sửa gần nhất được lưu cho dự án này (của Peto, của lệnh "
                     "Peto chạy, hay lần khôi phục).", "yellow")
        if self.ui.ask(Permission("undo", {"files": sorted(self.tools.checkpoint.files)})) not in {"y", "a"}:
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
        self.save()
        if restored:
            self.ui.success(f"Đã hoàn tác {len(restored)} tệp.")

    def permissions(self, clear=False, *, value=""):
        """/permissions: chính sách allow/ask/deny và các quyền đã nhớ, chỉ đổi khi người dùng gõ lệnh."""
        tools = self.tools
        if value == "clear":
            clear = True
        elif value:
            parts = value.split()
            action = None
            if len(parts) == 1 and parts[0] in approvals.POLICY_EFFECTS:
                effect = parts[0]
            elif len(parts) == 2 and parts[0] in approvals.POLICY_ACTIONS and parts[1] in approvals.POLICY_EFFECTS:
                action, effect = parts
            else:
                self.ui.line("Dùng /permissions [allow|ask|deny|clear], hoặc /permissions shell|edit allow|ask|deny.",
                             "yellow")
                return
            if not approvals.set_policy(self.ws.root, effect, action):
                self.ui.failure("Không lưu được chính sách quyền. Kiểm tra permissions.json trong hồ sơ người dùng.")
                return
            tools.approve_all = False
            self.ui.success("Đã lưu chính sách quyền cho dự án này.")
        if clear:
            try:
                removed = approvals.clear(self.ws.root)
            except OSError as err:
                self.ui.failure(str(err))
                return
            for grants in (tools.command_grants, tools.page_session_grants, tools.page_grants,
                           tools.site_session_grants, tools.site_grants):
                grants.clear()
            tools.approve_all = False
            self.ui.success("Đã xóa quyền nhớ trong phiên" +
                            (f" và {removed} quyền luôn cho phép ở dự án này." if removed else "."))
            self.ui.line("  Đã về mặc định: tự chạy lệnh và thay đổi tệp. /permissions ask để hỏi trước.", "dim")
        labels = {"allow": "tự thực hiện", "ask": "hỏi trước (trừ quyền đã nhớ)", "deny": "chặn"}
        for action, title in (("shell", "Chạy lệnh"), ("edit", "Thay đổi tệp")):
            effect = approvals.policy(self.ws.root, action)
            self.ui.line(f"  {title}: {labels[effect]} ({effect})", "dim")
        saved, pages, sites = (approvals.entries(self.ws.root), approvals.pages(self.ws.root),
                               approvals.sites(self.ws.root))
        in_session = tools.command_grants or tools.page_session_grants or tools.site_session_grants
        if not in_session and not saved and not pages and not sites:
            self.ui.line("  Chưa nhớ lệnh, trang hay tên miền nào: trong phiên chọn [s], luôn cho phép ở dự án này chọn "
                         "[l].", "dim")
        if in_session:
            self.ui.line("  Nhớ trong phiên:", "dim")
        for directory, command, timeout, shell in sorted(tools.command_grants):
            self.ui.item(f"{command} · {directory} · {timeout}s" + (f" · {shell}" if shell != "cmd" else ""))
        for origin in sorted(tools.page_session_grants):
            self.ui.item(f"bấm, gõ trên {origin}")
        for site in sorted(tools.site_session_grants):
            self.ui.item(f"xem trang ngoài {site}")
        if saved or pages or sites:
            self.ui.line("  Luôn cho phép ở dự án này (lưu trên máy):", "dim")
        for item in saved:
            where = "" if item["directory"] == "." else f" · trong {item['directory']}"
            self.ui.item(f"{item['command']}{where}" + (f" · {item['shell']}" if item["shell"] != "cmd" else ""))
        for origin in pages:
            self.ui.item(f"bấm, gõ trên {origin}")
        for site in sites:
            self.ui.item(f"xem trang ngoài {site}")

    def browser_window(self, value: str = "") -> None:
        """/browser hiện hoặc ẩn cửa sổ trình duyệt của Peto (chủ web chọn ngày 2026-09-23: ẩn, hiện khi cần);
        /browser clear quên đăng nhập và dữ liệu trang đã lưu trong hồ sơ của dự án."""
        if value == "xoa":
            if self.tools.forget_browser():
                self.ui.success("Đã xóa hồ sơ trình duyệt của dự án này: đăng nhập, cookie và dữ liệu trang đã lưu.")
            else:
                self.ui.failure("Hồ sơ trình duyệt của dự án này đang được một phiên peto khác dùng; đóng phiên đó rồi "
                                "thử lại.")
            return
        try:
            visible = self.tools.toggle_browser_window()
        except WorkspaceError as err:
            self.ui.failure(str(err))
            return
        page = self.tools.browser
        if not visible:
            self.ui.success("Đã ẩn cửa sổ. Peto vẫn xem và thao tác được.")
            return
        where = f" · {page.origin.split('://', 1)[-1]}" if page.url else ""
        self.ui.success(f"Đã hiện cửa sổ {page.name} của Peto{where}")
        self.ui.line("    Peto bấm, gõ ở đâu bạn thấy ở đó. Gõ /browser lần nữa để ẩn, hoặc đóng cửa sổ.", "dim")

    def compact(self, *, propagate_cancel=False):
        metrics = self.metrics if self._running else Metrics()
        try:
            return self._compact(metrics, propagate_cancel=propagate_cancel)
        finally:
            if not self._running and metrics.calls["compact"]:
                self._log("compaction_metrics", metrics=metrics.snapshot())

    def _compact(self, metrics, *, propagate_cancel=False):
        self._compaction_step = uuid.uuid4().hex
        info = self._model_budget()
        keep_tokens = min(15_000, max(0, (ceiling(info) - self.context_budget.overhead.get(self.model, 8000)) // 2)) if info else None
        prefix, tail = compact_prefix(self.items, keep_tokens=keep_tokens)
        if not prefix:
            self.ui.line("  Hội thoại còn ngắn, chưa cần tóm tắt.", "dim")
            return False
        self.ui.step("Đang tóm tắt ngữ cảnh cũ (dùng một lượt gọi model)")
        checkpoint = continuation.capture(self.items)
        started = time.monotonic()
        def waiting():
            self.ui.status(f"… Đang tóm tắt ngữ cảnh · {int(time.monotonic() - started)}s · Ctrl+C dừng")
        try:
            attempt, shrinks = 0, 0
            info = self._model_budget()
            target = int(ceiling(info) / 1.15) - min(12000, max(1024, ceiling(info) // 10)) if info else None
            rejected_size = None
            while attempt < 2:
                prompt = continuation.request(checkpoint, retry=bool(attempt))
                source = portable(prefix)
                if target is not None:
                    room = int(self.context_budget.max_request_bytes * .8) - len(prompt.encode('utf-8')) - 2000
                    source = compact_input(source, max(1, target - estimate(prompt)), force=bool(shrinks), max_bytes=room)
                else:
                    source = efficient_input(source)
                body = {"input": [*source, user_message(prompt)],
                        "effort": "medium" if attempt else "low", "model": self.model,
                        "context": {"purpose": "compact", **({"features": ["context_budget"]} if info else {})}}
                metrics.calls["compact"] += 1
                completed = None
                try:
                    with metrics.measure("compact"), contextlib.closing(self.client.stream("/api/agent/step", body, on_idle=waiting)) as events:
                        for event in events:
                            if event.get("type") == "meta":
                                self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                            if event.get("type") == "error":
                                if info and event.get("code") == "context_overflow":
                                    raise _ContextOverflow()
                                raise ApiError(0, str(event.get("message", "Không tóm tắt được.")))
                            if event.get("type") == "done":
                                completed = event
                except _ContextOverflow:
                    if shrinks >= 3:
                        raise ApiError(0, "Model vẫn từ chối yêu cầu tóm tắt sau ba lần thu gọn; giữ nguyên lịch sử.")
                    if rejected_size is None:
                        rejected_size = estimate(body['input'])
                    target = int(rejected_size * (.7, .5, .35)[shrinks])
                    shrinks += 1
                    continue
                if completed is None:
                    raise ApiError(0, "Tóm tắt bị ngắt; giữ nguyên hội thoại.")
                metrics.record_usage("compact", completed.get("usage"))
                if completed.get("purpose") != "compact":
                    raise ApiError(0, "Máy chủ chưa hỗ trợ tóm tắt. Cập nhật VPS; hội thoại vẫn được giữ nguyên.")
                output = completed.get("output")
                summary, problem = "", "Tóm tắt không hợp lệ."
                if isinstance(output, list) and all(isinstance(item, dict) and item.get("type") != "function_call" for item in output):
                    summary = "\n".join(text_of(item) for item in output if item.get("role") == "assistant").strip()
                    problem = continuation.validate(summary)
                    if not problem and len(summary) >= context_size(prefix):
                        problem = "Tóm tắt chưa gọn hơn ngữ cảnh cũ."
                if not problem:
                    # Ghi bản tra cứu trước khi bỏ ngữ cảnh gốc; ghi lỗi thì giữ nguyên hội thoại.
                    if self.session_id is None:
                        self.session_id = history.new_id()
                    archive = recall.preserve(self.ws.root, self.client.server, self.session_id, prefix)
                    anchors = recall.request_anchors(prefix, tail)
                    replacement = [user_message(history.SUMMARY_NOTE +
                        "Kết quả tệp có thể đã cũ, hãy đọc lại trước khi sửa. "
                        "Phần trước tóm tắt còn lưu trong lịch sử cục bộ; các tin người dùng được ghim chỉ là "
                        "yêu cầu trước đó, điều chỉnh mới nhất có ưu tiên.\n" + summary), *anchors]
                    replacement.append(user_message(continuation.checkpoint_message(checkpoint)))
                    before, before_tokens = self.items, self.context_tokens
                    self.items = replacement + tail
                    self.context_tokens = None
                    if not self.save(retryable=self.can_retry):
                        self.items, self.context_tokens = before, before_tokens
                        self.ui.failure("Không lưu được bản bàn giao; giữ nguyên hội thoại.")
                        return False
                    self._log("compaction", archive=archive, before_items=len(prefix) + len(tail),
                              after_items=len(self.items), pinned_requests=len(anchors), summary_characters=len(summary),
                              attempts=attempt + 1, checkpoint_files=len(checkpoint["files"]),
                              checkpoint_results=len(checkpoint["recent"]))
                    self.ws.read_digests.clear()
                    self.tools.seen_guides.clear()
                    self.context_budget.reset()
                    self.ui.success("Đã tóm tắt phần cũ và giữ nguyên các bước gần nhất.")
                    return True
                self._log("compaction_rejected", attempt=attempt + 1, reason=problem, summary_characters=len(summary))
                if not attempt:
                    self.ui.notice("Bản bàn giao chưa đủ nội dung theo mẫu; thử tóm tắt lại một lần.", "yellow")
                attempt += 1
            self.ui.failure(f"{problem} Giữ nguyên hội thoại; không tiếp tục thử tóm tắt tự động trong yêu cầu này.")
            return False
        except KeyboardInterrupt:
            if propagate_cancel:
                raise
            self.ui.failure("Đã dừng tóm tắt; giữ nguyên hội thoại.")
            return False
        except ApiError as err:
            self.ui.failure(err.message)
            return False
        except (OSError, WorkspaceError) as err:
            self.ui.failure(f"Không lưu được lịch sử trước tóm tắt; giữ nguyên hội thoại. {err}")
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
        journal = self._journal()
        if journal.lease is None:
            journal.claim()
            try:
                return self._run(resuming=resuming)
            finally:
                journal.release()
        # /retry là một lần tiếp tục do người dùng yêu cầu: không kế thừa quyền a từ lần trước.
        if not resuming:
            self.tools.reset_task()
            self.metrics = self.tools.metrics = Metrics()
            self.active_seconds = 0.0
        self._running = True
        execution_id = journal.execution_started()
        self.ui.title(self.ui.tab_title("đang làm"))
        self.tools.approve_all = False
        self.can_retry = False
        started = time.monotonic()
        outcome = "done"
        crashed = False
        pending: list[dict] = []
        verification_reminded = False
        compact_failed = False
        step_limit = self.max_steps
        steps = 0
        try:
            # Nhận yêu cầu phải được lưu trước lần gọi model đầu, kể cả khi đóng cửa sổ lúc đang chờ phản hồi.
            self._save_progress()
            while step_limit is None or steps < step_limit:
                steps += 1
                if not compact_failed and self._compact_due():
                    compact_failed = not self.compact(propagate_cancel=True)
                if len(self.items) >= 270:
                    self.ui.failure("Hội thoại quá dài và chưa tóm tắt được. Gõ /compact để thử lại hoặc /new.")
                    outcome = "limit"
                    return
                output = self._step()
                if output is None:
                    outcome = "error"
                    return
                reply = "\n".join(text_of(item) for item in output
                                  if item.get("type") == "message" and item.get("role") == "assistant").strip()
                if reply:
                    # Nhật ký là bản xem nhanh; lời đầy đủ còn trong session hoặc archive trước tóm tắt.
                    self._log("reply", text=cap_text(reply, MAX_LOGGED_REPLY))
                if self._published_output != output:
                    self._publish_output(output)
                self._published_output = None
                self._logical_step = None
                pending = [item for item in output if item.get("type") == "function_call"]
                if not pending:
                    if self._inbox():
                        # Người dùng nhắn thêm lúc Peto vừa viết xong: chạy thêm một bước để Peto đọc tin đó.
                        self._save_progress()
                        continue
                    if not verification_reminded and self._remind_to_check():
                        verification_reminded = True
                        continue
                    break
                self._save_progress()
                self.tools.start_step()
                results = []
                while pending:
                    call = pending[0]
                    self._active_ordinal = len(self._settled)
                    self._journal().tool_started(self._active_step, self._active_ordinal)
                    self.tools.call_id = str(call.get("call_id", ""))
                    self._task_state_before = copy.deepcopy(self.task_state.data)
                    name = str(call.get("name", ""))
                    with self.metrics.measure("tools"):
                        result = cap_result(self.tools.call(name, str(call.get("arguments", ""))),
                                            READ_BOUNDED_KEYS if name in {"read_file", "read_history"} else BOUNDED_KEYS)
                    results.append((str(call.get("name", "")), result))
                    encoded = json.dumps(result, ensure_ascii=False)
                    self._log("tool", name=call.get("name"), arguments=cap_text(str(call.get("arguments", "")), 2000),
                              result=cap_text(encoded, 4000))
                    if self._active_ordinal not in self._settled:
                        from .events import ToolDone
                        self._record_tool(ToolDone(str(call.get('call_id', '')), name, {}, result))
                    pending.pop(0)
                    self._save_progress()
                if self.tools.captured:
                    self.items.append(tool_images(self.tools.captured))
                    self.tools.captured = []
                    drop_old_images(self.items)
                steered = self._inbox()
                # Câu trả lời cuối gửi kèm lần đánh dấu xong cả danh sách việc: yêu cầu đã xong, khỏi tốn thêm một bước
                # chỉ để model đọc {"ok": true}. Bài thi ngày 2026-10-13: 6 Luna dành 29/96 lượt cho update_plan đứng
                # riêng. Lời mở đầu kèm kế hoạch còn việc dở (thói quen của Grok) vẫn đi tiếp như thường.
                if reply and not steered and all(name == "update_plan" and result.get("left") == 0
                                                 for name, result in results):
                    if not verification_reminded and self._remind_to_check():
                        verification_reminded = True
                        continue
                    break
            else:
                outcome = "limit"
                self._wrap_up()
                self.ui.line(f'Peto đã làm {step_limit} bước trong yêu cầu này nên tạm dừng. Gõ "làm tiếp" nếu '
                             "muốn Peto làm tiếp.", "yellow")
        except WorkspaceError as err:
            outcome = "error"
            self.ui.failure(str(err))
        except KeyboardInterrupt:
            outcome = "stopped"
            # Lệnh gọi công cụ nào cũng phải có kết quả, không thì bước sau bị mô hình từ chối.
            for offset, call in enumerate(pending):
                if self._active_ordinal is not None and self._active_ordinal + offset in self._settled:
                    continue
                self.items.append({"type": "function_call_output", "call_id": call.get("call_id", ""),
                                   "output": json.dumps(STOPPED_RESULT, ensure_ascii=False)})
            self.ui.line()
            self.ui.line("Đã dừng yêu cầu. Gõ yêu cầu mới, hoặc /exit để thoát.", "yellow")
            self._log("stopped")
        except Exception as err:
            # Không biến lỗi lập trình thành thành công; giữ traceback và bản lưu hợp lệ để /resume làm tiếp.
            outcome, crashed = "error", True
            self._log("internal_error", error_type=type(err).__name__)
            raise
        finally:
            self._active_ordinal = None
            self.tools.approve_all = False
            self.active_seconds += time.monotonic() - started
            self._running = False
            # Ảnh chụp đầu yêu cầu (CLI 0.26.0) phải vào bản lưu, kể cả khi yêu cầu không đổi tệp nào.
            self.tools.wait_snapshot()
            # Lúc đã dừng, kết quả bị ngắt phải có cả trong bộ nhớ; yêu cầu mới không gửi lại lời gọi thiếu kết quả.
            self.items, missing = interrupted_items(self.items)
            self.can_retry = self.can_retry and not missing
            saved = self.save(retryable=self.can_retry, interrupted=crashed or bool(missing))
            if not saved:
                outcome = "error"
                self.ui.failure("Không lưu được hội thoại. Giữ cửa sổ này và kiểm tra dung lượng/quyền ghi trước khi làm tiếp.")
            journal.execution_finished(execution_id, outcome)
            self._summary(self.active_seconds, outcome)
            if outcome == "done":
                self._name_conversation()

    def _wrap_up(self) -> None:
        """Chạm ngân sách được đặt riêng: một lượt không công cụ để Peto tóm tắt đã làm gì, còn gì.
        Tốn một bước như thường; máy chủ cũ không có lượt này thì chỉ in lời nhắc như trước."""
        if "wrapup" not in self.tools.features:
            return
        output = self._step(purpose="wrapup")
        if not output:
            return
        # Máy chủ đã cấm gọi công cụ; lời gọi nào lọt qua thì bỏ, khỏi để lại lời gọi không có kết quả.
        output = [item for item in output if item.get("type") != "function_call"]
        reply = "\n".join(text_of(item) for item in output
                          if item.get("type") == "message" and item.get("role") == "assistant").strip()
        if reply:
            self._log("reply", text=cap_text(reply, MAX_LOGGED_REPLY))
        self.items.extend(output)

    def _remind_to_check(self) -> bool:
        """Peto định xong mà còn tệp sửa chưa kiểm tra: thêm lời nhắc "Kiểm tra sau sửa" để chạy thêm một bước."""
        rows = self.task_state.data['acceptance']
        if rows and not self.task_state.accepted():
            self.items.append(user_message('[Peto Agent] Recorded acceptance criteria are still failed, unverified '
                              'or stale. Check the task state and resolve them if possible; otherwise explicitly '
                              'state the remaining limitation. Do not repeat a successful check outside its scope.'))
            return True
        if self.task_state.accepted() or not (self.tools.changes and self.tools.checked_revision < self.tools.revision):
            return False
        self.items.append({"type": "message", "role": "assistant", "content": (
            "Kiểm tra sau sửa: xem hướng dẫn AGENTS.md và cấu hình dự án để chọn test/build/lint phù hợp. "
            "Với tệp dữ liệu, định dạng nhị phân, media hay ứng dụng không có bộ test, chọn phép kiểm tra đúng "
            "kết quả người dùng cần: thử một mẫu nhỏ bằng bộ đọc độc lập hoặc ứng dụng đích trước khi áp dụng rộng. "
            "Script chạy xong, checksum đúng hay hai tệp giống nhau chưa chứng minh ứng dụng dùng được. "
            "Chạy kiểm tra với quyền người dùng cho phép. Nếu không cần, không có hoặc bị từ chối, "
            "nêu rõ lý do; không lặp lại lệnh đã bị từ chối. Chỉ sửa lỗi liên quan, tối đa 3 lần kiểm tra thất bại, "
            "không tự cấp quyền hay mở rộng phạm vi. Báo lệnh nào đã chạy, kiểm tra được điều gì và còn gì chưa "
            "xác nhận. Khi chỉ người dùng thử được trong ứng dụng, đưa bước thử cụ thể và chờ kết quả; không báo "
            "đã hoạt động trước khi có bằng chứng đó.")})
        return True

    def _read_history(self, pattern=None, start_entry=None, start_character=None) -> dict:
        if self.session_id is None:
            return {"entries": [], "next_entry": None, "note": "Phiên này chưa có lịch sử trước tóm tắt."}
        return recall.read(self.ws.root, self.client.server, self.session_id, pattern=pattern,
                           start_entry=start_entry, start_character=start_character)

    def _save_progress(self) -> bool:
        """Lưu hội thoại giữa yêu cầu, để đóng cửa sổ giữa chừng thì /resume vẫn còn những gì Peto đã làm.

        Cửa sổ console đóng thì Windows tắt Python ngay, khối finally của _run không chạy (thử trong ConPTY ngày
        2026-09-23), nên chỉ lưu lúc xong yêu cầu là mất cả yêu cầu đang dở. Lệnh gọi công cụ chưa có kết quả được ghi
        INTERRUPTED_RESULT trong bản lưu, để bước kế tiếp sau /resume vẫn hợp lệ với model.
        """
        items, _ = interrupted_items(self.items)
        saved = self.save(items, interrupted=True)
        if not saved:
            raise WorkspaceError("Không lưu được tiến độ nên Peto đã dừng trước công cụ/bước tiếp theo. "
                                 "Giữ cửa sổ này và kiểm tra dung lượng/quyền ghi trước khi làm tiếp.")
        return saved

    def _step_context(self) -> dict:
        context = {"project": self.ws.root.name, "os": f"{platform.system()} {platform.release()}".strip(),
                   "project_guidance": guides(self.ws), "features": list(self.tools.features),
                   "skills": self.tools.skills.catalog(), "mcp_servers": self.tools.mcp.catalog()}
        if 'task_state' in self.tools.features:
            context['task_state'] = self.task_state.view()
        if "recall" in self.tools.features:
            context["check_observations"] = {"current_revision": self.tools.revision,
                "observations": list(self.tools.checks),
                "recent_commands": [{**row, "command": row["command"][:1200]} for row in self.tools.commands[-6:]]}
        if "user_guide" in self.tools.features:
            text, problem = user_guide.read()
            if problem and problem != self._guide_problem:
                self.ui.line(f"  {problem}", "yellow")
            self._guide_problem = problem
            if text:
                context["user_guidance"] = text
        return context

    def _step(self, *, purpose: str | None = None) -> list[dict] | None:
        """Một lượt gọi model. Lỗi tạm thời trước khi có phản hồi thì tự chờ rồi gửi lại (RETRY_WAITS); Ctrl+C lúc
        chờ thì dừng yêu cầu như mọi khi."""
        self._logical_step = uuid.uuid4().hex
        recovered_context = False
        for attempt in range(len(RETRY_WAITS) + 1):
            try:
                return self._attempt(purpose, may_retry=attempt < len(RETRY_WAITS))
            except _ContextOverflow:
                if recovered_context or not self.compact(propagate_cancel=True):
                    self.ui.failure('Không đủ chỗ trong ngữ cảnh sau tóm tắt; giữ lịch sử để bạn /compact hoặc /new.')
                    return None
                recovered_context = True
                return self._attempt_after_compact(purpose)
            except _Retry as retry:
                wait = RETRY_WAITS[attempt]
                self._log("retry_auto", attempt=attempt + 1, seconds=wait, message=retry.message)
                deadline = time.monotonic() + wait
                try:
                    while (left := deadline - time.monotonic()) > 0:
                        self.ui.status(f"… {retry.message} · thử lại lần {attempt + 1}/{len(RETRY_WAITS)} sau "
                                       f"{max(1, round(left))}s · Ctrl+C dừng")
                        time.sleep(min(0.2, left))
                finally:
                    self.ui.clear_status()
        return None

    def _attempt_after_compact(self, purpose):
        try:
            return self._attempt(purpose, may_retry=False)
        except _ContextOverflow:
            self.ui.failure('Model vẫn từ chối ngữ cảnh sau một lần tóm tắt. Đã giữ lịch sử; không tự thử lại.')
            return None

    def _attempt(self, purpose: str | None, *, may_retry: bool) -> list[dict] | None:
        context = self._step_context()
        if purpose:
            context["purpose"] = purpose
        body = {"input": efficient_input(self.items), "effort": self.effort, "model": self.model, "context": context}
        writer = self.ui.reply()
        received = False
        started = time.monotonic()
        phase = "nghĩ"
        output = None
        searching = False
        produced = False

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
                    produced = produced or kind in {'delta', 'thinking', 'search'}
                    received = True
                    if kind == "meta":
                        if 'context_budget' in self.tools.features:
                            self.context_budget.observe(self.model, event.get('context_budget'), context)
                        self.steps_used, self.steps_limit = event.get("steps_used"), event.get("steps_limit")
                    elif kind == "search":
                        # Tìm web chạy ở phía dịch vụ AI; ở đây chỉ báo cho người dùng biết bước này có tra web.
                        if event.get("text") == "searching" and not searching:
                            searching = True
                            phase = "tìm web"
                            self.ui.search("searching")
                            self._log("search")
                        waiting()
                    elif kind == "thinking":
                        # Tóm tắt suy nghĩ đến liên tục thì client không còn lúc rảnh để gọi waiting(): gọi ở đây để
                        # dòng "Peto đang nghĩ · Ns" vẫn đếm giây.
                        writer.think(str(event.get("text", "")))
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
                        observed = self.items if self._published_output == output else self.items + output
                        self.context_budget.measured(self.model, efficient_input(observed), usage)
                        # done là ranh giới hoàn tất. Không để lỗi đóng socket sau đó làm mất bước đã nhận.
                        return output
                    elif kind == "error":
                        message = str(event.get("message") or "Máy chủ báo lỗi ở bước này.")
                        if event.get('code') == 'context_overflow' and 'context_budget' in self.tools.features and not produced:
                            writer.finish()
                            raise _ContextOverflow()
                        # Máy chủ chỉ gắn retryable khi bước chưa có phản hồi và đã được hoàn lại.
                        if event.get("retryable") is True and may_retry and not writer.started:
                            writer.finish()
                            raise _Retry(message.rstrip(". ") or "Lỗi tạm thời")
                        writer.finish()
                        self.ui.failure(message)
                        self._log("error", message=message)
                        return None
        except ApiError as err:
            if output is not None:
                return output
            writer.finish()
            if err.status in RETRY_STATUSES and not received and may_retry:
                raise _Retry("Mất kết nối tới máy chủ Peto") from err
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
        self.ui.title(self.ui.tab_title(TITLE_LABELS[outcome]))
        if elapsed >= BELL_AFTER_SECONDS:
            self.ui.bell()
        self.ui.request_finished(RequestEnd(
            outcome, elapsed, dict(self.tools.changes), list(self.tools.commands),
            background_jobs=len(self.tools.jobs.running()),
            plan_left=sum(1 for step in self.tools.plan if step.get("status") != "done"),
            context_tokens=self.context_tokens, model=self.model_label, context_share=self.context_share(),
            command_files=len(self.tools.command_changes), acceptance=copy.deepcopy(self.task_state.data['acceptance'])))
        if unresolved := [row for row in self.task_state.data['acceptance'] if row['status'] != 'passed']:
            self.ui.notice(f'Còn {len(unresolved)} tiêu chí chưa đạt hoặc chưa xác minh.', 'yellow')
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
