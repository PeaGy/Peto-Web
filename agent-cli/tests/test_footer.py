"""Chân cố định (tui/footer.py): ô nhập ở đáy suốt phiên, chữ mới in phía trên, lịch sử cuộn không mất dòng nào."""

from __future__ import annotations

import contextlib
import io
import threading
import time

import pytest

from peto_agent.events import Permission, RequestEnd
from peto_agent.line_editor import EditorState, Key
from peto_agent.tui.footer import FooterEngine
from peto_agent.tui.view import TerminalUI
from vt import Terminal


@pytest.fixture(autouse=True)
def rich_glyphs(monkeypatch):
    monkeypatch.setenv("WT_SESSION", "test")


class Console:
    """Console giả: phím đưa vào bằng ``press``; ``wait`` báo có phím như WaitForSingleObject."""

    def __init__(self):
        self.pending: list[Key] = []
        self.lock = threading.Lock()

    @contextlib.contextmanager
    def raw(self):
        yield

    def press(self, *keys: Key) -> None:
        with self.lock:
            self.pending.extend(keys)

    def wait(self, timeout_ms: int) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            with self.lock:
                if self.pending:
                    return True
            time.sleep(0.005)
        return False

    def keys(self) -> list[Key]:
        with self.lock:
            keys, self.pending = self.pending[:1], self.pending[1:]
        return keys


class Editor:
    def __init__(self, console, size):
        self.console = console
        self.state = EditorState()
        self.size = size
        self.clipboard = lambda: []
        self.files = lambda paths: []


class Screen(io.StringIO):
    """Output nối thẳng vào terminal ảo."""

    def __init__(self, terminal):
        super().__init__()
        self.terminal = terminal

    def write(self, text):
        self.terminal.feed(text)
        return super().write(text)


def session(columns=80, rows=24, *, start=True):
    terminal = Terminal(columns, rows)
    out = Screen(terminal)
    ui = TerminalUI(out=out, colors=True, width=columns, height=rows)
    ui.terminal = True
    console = Console()
    ui.editor = Editor(console, lambda: (columns, rows))
    interrupts = []
    if start:
        ui.engine = FooterEngine(ui, ui.editor, size=lambda: (columns, rows), interrupt=lambda: interrupts.append(1))
        ui.engine.start()
    return ui, console, terminal, interrupts


def settle(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def type_text(console, text):
    console.press(*[Key("char", char) for char in text])


def test_printed_lines_reach_scrollback_once_and_in_order_while_the_footer_stays_at_the_bottom():
    ui, console, terminal, _ = session(rows=12)
    try:
        ui.engine.busy = True
        for number in range(40):
            ui.status(f"… Peto đang nghĩ · {number}s")
            ui.line(f"dòng {number:02d}")
            if number % 7 == 0:
                ui.engine.plan_line = f"việc {number}"
        lines = terminal.lines()
        printed = [line for line in lines if line.startswith("dòng")]
        assert printed == [f"dòng {number:02d}" for number in range(40)], "không mất, không lặp, đúng thứ tự"
        assert "▀" in lines[-1] or "esc" in lines[-1], "phần chân là các hàng cuối cùng"
        assert not any("dòng" in line for line in lines[-8:] if "▶" in line or "┃" in line)
    finally:
        ui.stop_footer() if ui.engine else None


def test_typing_while_peto_works_is_inserted_next_step_or_sent_after_the_request():
    """Tin gõ lúc Peto đang làm chờ chèn vào bước kế tiếp (CLI 0.20.0); yêu cầu xong trước thì thành yêu cầu kế tiếp.
    Lệnh gạch chéo thì chờ yêu cầu xong mới chạy."""
    ui, console, terminal, _ = session()
    try:
        type_text(console, "việc đầu")
        console.press(Key("enter"))
        assert ui.engine.take() == ("việc đầu", [])
        assert ui.engine.busy
        type_text(console, "/diff")
        console.press(Key("enter"))
        assert settle(lambda: ui.engine.queued)
        type_text(console, "việc sau")
        console.press(Key("enter"))
        assert settle(lambda: ui.engine.steers)
        # Tin vào hàng chờ trước, lần vẽ xong sau một chút: chờ màn hình chứ không đọc ngay.
        assert settle(lambda: any("Nhắn thêm: việc sau" in line for line in terminal.lines())
                      and any("Chờ chạy: /diff" in line for line in terminal.lines()))
        ui.line("Peto trả lời việc đầu.")
        ui.engine.idle(["Peto"], "")
        assert ui.engine.take() == ("việc sau", []), "tin nhắn thêm chưa kịp chèn thành yêu cầu kế tiếp"
        assert ui.engine.queued, "lệnh vẫn chờ tới lượt sau"
        lines = terminal.lines()
        assert lines.index(next(line for line in lines if "việc sau" in line and "┃" in line)) > \
            lines.index("Peto trả lời việc đầu."), "tin chờ chỉ vào lịch sử khi tới lượt"
    finally:
        ui.stop_footer()


def test_ctrl_c_stops_a_request_clears_text_or_exits_when_idle():
    ui, console, terminal, interrupts = session()
    try:
        ui.engine.busy = True
        console.press(Key("interrupt"))
        assert settle(lambda: interrupts == [1])
        ui.engine.idle(["Peto"], "")
        type_text(console, "abc")
        console.press(Key("interrupt"))
        assert settle(lambda: ui.engine.state.text == "" and not console.pending)
        console.press(Key("interrupt"))
        with pytest.raises(KeyboardInterrupt):
            ui.engine.take()
        assert interrupts == [1]
    finally:
        ui.stop_footer()


def test_escape_twice_stops_a_request_and_once_shows_a_hint():
    ui, console, terminal, interrupts = session()
    try:
        ui.engine.busy = True
        console.press(Key("escape"))
        assert settle(lambda: any("esc lần nữa để dừng" in line for line in terminal.lines()))
        assert not interrupts
        console.press(Key("escape"))
        assert settle(lambda: interrupts == [1])
    finally:
        ui.stop_footer()


def test_a_permission_replaces_the_prompt_until_answered_and_keeps_the_draft():
    ui, console, terminal, _ = session(rows=30)
    try:
        type_text(console, "nháp")
        assert settle(lambda: ui.engine.state.text == "nháp")
        result = {}

        def ask():
            result["answer"] = ui.ask(Permission("command", {"command": "npm test", "directory": "C:\\p",
                                                             "timeout": 120, "shell": "cmd"},
                                                 allow_session=True, allow_always=True))

        thread = threading.Thread(target=ask)
        thread.start()
        assert settle(lambda: any("Cần bạn duyệt" in line for line in terminal.lines()))
        console.press(Key("char", "y"))
        time.sleep(0.35)
        assert "answer" not in result, "phím tới ngay khi khung hiện không được tính"
        console.press(Key("right"), Key("enter"))
        thread.join(3)
        assert result["answer"] == "a"
        assert settle(lambda: not any("Cần bạn duyệt" in line for line in terminal.lines()[-12:]))
        assert ui.engine.state.text == "nháp", "chữ đang gõ dở vẫn còn sau câu hỏi"
    finally:
        ui.stop_footer()


def test_stopping_leaves_no_footer_behind():
    ui, console, terminal, _ = session()
    ui.line("lời cuối")
    ui.stop_footer()
    ui.line("Tạm biệt!")
    lines = terminal.lines()
    assert lines[-2:] == ["lời cuối", "Tạm biệt!"]


def test_a_whole_request_renders_through_the_footer_without_touching_the_last_column(project):
    from peto_agent.tools import Tools
    from peto_agent.workspace import Workspace

    (project / "app.py").write_text("x = 1\n")
    ui, console, terminal, _ = session(columns=60, rows=20)
    try:
        ui.engine.busy = True
        tools = Tools(Workspace(project), ui)
        tools.approve_all = True
        tools.read_file("app.py")
        tools.call("edit_file", '{"path": "app.py", "old_text": "x = 1", "new_text": "x = 2"}')
        reply = ui.reply()
        reply.feed("Đã đổi `x` thành 2 ở app.py:1.\n")
        reply.finish()
        ui.request_finished(RequestEnd("done", 2, tools.changes, [], model="Peto", context_share=0.1))
        text = "\n".join(terminal.lines())
        assert "← Sửa app.py" in text and "Đã đổi x thành 2" in text and "▣ Peto" in text
    finally:
        ui.stop_footer()
