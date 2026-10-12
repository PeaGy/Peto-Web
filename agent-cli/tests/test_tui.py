"""Giao diện terminal kiểu OpenCode (tui/): dòng công cụ, khối diff và lệnh, khung duyệt, ô nhập, Markdown."""

from __future__ import annotations

import contextlib
import io
import json
import re
import time

import pytest

from peto_agent.events import Permission, RequestEnd
from peto_agent.line_editor import EditorState, Key
from peto_agent.tools import Tools
from peto_agent.tui import prompt as prompt_view
from peto_agent.tui.markdown import Markdown
from peto_agent.tui.text import ANSI, cells
from peto_agent.tui.theme import Theme
from peto_agent.tui.view import TerminalUI
from peto_agent.workspace import Workspace


@pytest.fixture(autouse=True)
def rich_glyphs(monkeypatch):
    monkeypatch.setenv("WT_SESSION", "test")
    monkeypatch.delenv("PETO_AGENT_THEME", raising=False)


def plain(text: str) -> str:
    return ANSI.sub("", text)


def make_ui(answers=(), *, width=100, height=30, colors=True) -> TerminalUI:
    replies = list(answers)

    def read(prompt):
        if not replies:
            raise EOFError
        return replies.pop(0)

    ui = TerminalUI(out=io.StringIO(), reader=read, colors=colors, width=width, height=height)
    ui.terminal = True
    return ui


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


class FakeConsole:
    """Phím của khung duyệt; mỗi lần đọc trả một nhóm phím, sau một khoảng chờ cho trước."""

    def __init__(self, batches, delay=0.35):
        self.batches = list(batches)
        self.delay = delay

    @contextlib.contextmanager
    def raw(self):
        yield

    def keys(self):
        if self.delay:
            time.sleep(self.delay)
        return self.batches.pop(0) if self.batches else [Key("escape")]


class FakeEditor:
    def __init__(self, console):
        self.console = console


def test_every_printed_row_stays_off_the_last_column(project):
    (project / "app.py").write_text("x = 1\n" * 3)
    for width in (40, 80, 120, 160):
        ui = make_ui(width=width)
        tools = Tools(Workspace(project), ui)
        tools.approve_all = True
        tools.read_file("app.py")
        tools.call("edit_file", args(path="app.py", old_text="x = 1\nx = 1\nx = 1", new_text="y = " + "2" * 300))
        reply = ui.reply()
        reply.feed("Đoạn văn rất dài " * 30 + "\n\n| a | b |\n|---|---|\n| " + "ô " * 80 + " | x |\n")
        reply.finish()
        ui.request_finished(RequestEnd("done", 3, {"app.py": [1, 3]}, [], model="Peto", context_share=0.2))
        for row in plain(ui.out.getvalue()).split("\n"):
            # Dòng trạng thái tạm vẽ đè bằng \r: mỗi lần vẽ là một đoạn riêng.
            for segment in row.split("\r"):
                assert cells(segment) <= width - 1, f"{width} cột: {segment!r}"


def test_reads_and_searches_in_a_row_become_one_explored_line(project):
    (project / "a.py").write_text("print(1)\n")
    (project / "b.py").write_text("print(2)\n")
    ui = make_ui()
    tools = Tools(Workspace(project), ui)
    tools.call("read_file", args(path="a.py", start_line=None, end_line=None))
    tools.call("search_files", args(pattern="print", path=None, glob=None))
    tools.call("read_file", args(path="b.py", start_line=None, end_line=None))
    assert "Đã xem" not in plain(ui.out.getvalue()), "nhóm chỉ in khi có phần khác bắt đầu"
    ui.request_finished(RequestEnd("done", 2, {}, []))
    text = plain(ui.out.getvalue())
    assert "→ Đã xem: 2 lần đọc, 1 lần tìm" in text
    assert 'a.py:1-1 · "print" 2 kết quả · b.py:1-1' in text


def test_a_single_read_is_its_own_line(project):
    (project / "a.py").write_text("1\n2\n3\n")
    ui = make_ui()
    Tools(Workspace(project), ui).read_file("a.py")
    ui.line("xong")
    assert "→ Đọc a.py:1-3" in plain(ui.out.getvalue())


def test_an_approved_edit_is_a_block_with_its_diff(project):
    (project / "app.py").write_text("def f():\n    return 1\n")
    ui = make_ui()
    tools = Tools(Workspace(project), ui)
    tools.approve_all = True
    tools.read_file("app.py")
    tools.call("edit_file", args(path="app.py", old_text="return 1", new_text="return 2"))
    text = plain(ui.out.getvalue())
    assert "← Sửa app.py  +1  −1" in text
    assert "2 −     return 1" in text and "2 +     return 2" in text


def test_a_refused_edit_says_so_and_writes_nothing(project):
    (project / "app.py").write_text("x = 1\n")
    ui = make_ui(["n"])
    tools = Tools(Workspace(project), ui)
    tools.read_file("app.py")
    result = tools.call("edit_file", args(path="app.py", old_text="x = 1", new_text="x = 2"))
    assert "không đồng ý" in result["error"]
    text = plain(ui.out.getvalue())
    assert "Cần bạn duyệt" in text and "[y] Cho phép  [a] Cả yêu cầu này  [n] Từ chối" in text
    assert "✗ Không sửa app.py" in text
    assert (project / "app.py").read_text() == "x = 1\n"


def test_the_panel_is_answered_with_arrows_and_enter_then_disappears():
    console = FakeConsole([[Key("right")], [Key("enter")]])
    ui = make_ui()
    ui.editor = FakeEditor(console)
    answer = ui.ask(Permission("command", {"command": "npm test", "directory": "C:\\p", "timeout": 120,
                                           "shell": "cmd"}, allow_session=True, allow_always=True))
    assert answer == "a", "→ chọn mục thứ hai (Cả yêu cầu này)"
    out = ui.out.getvalue()
    assert "Nhớ lệnh trong phiên" in plain(out) and "Luôn ở dự án" in plain(out)
    erased = re.search(r"\x1b\[(\d+)A\r\x1b\[J\x1b\[\?25h", out)
    assert erased and out.rfind("Cần bạn duyệt") < erased.start(), "trả lời xong thì khung bị xóa, con trỏ hiện lại"


def test_keys_typed_before_the_panel_opened_never_answer_it():
    console = FakeConsole([[Key("enter")], [Key("char", "n")]], delay=0)
    console_keys = console.keys

    def slow_after_first():
        batch = console_keys()
        if batch[0].name == "char":
            time.sleep(0.35)
        return batch

    console.keys = slow_after_first
    ui = make_ui()
    ui.editor = FakeEditor(console)
    assert ui.ask(Permission("file", {"path": "a.py", "before": "1\n", "after": "2\n", "title": "Muốn sửa a.py"})) == "n"


@pytest.mark.parametrize("key,expected", [(Key("escape"), "n"), (Key("char", "Y"), "y"), (Key("char", "l"), "l")])
def test_letters_and_escape_still_answer(key, expected):
    ui = make_ui()
    ui.editor = FakeEditor(FakeConsole([[key]]))
    assert ui.ask(Permission("page", {"origin": "http://localhost:5173", "action": "bấm nút Gửi"},
                             allow_session=True, allow_always=True, session_label="cả phiên")) == expected


def test_ctrl_c_in_the_panel_stops_the_request():
    ui = make_ui()
    ui.editor = FakeEditor(FakeConsole([[Key("interrupt")]]))
    with pytest.raises(KeyboardInterrupt):
        ui.ask(Permission("move", {"old": "a.py", "new": "b.py"}))


def test_a_long_diff_in_the_panel_pages_instead_of_overflowing_the_screen():
    before = "".join(f"dòng {number}\n" for number in range(200))
    after = before.replace("dòng 5\n", "năm\n").replace("dòng 150\n", "trăm rưỡi\n")
    ui = make_ui(height=20)
    permission = Permission("file", {"path": "a.txt", "before": before, "after": after, "title": "Muốn sửa a.txt"})
    lines, hidden = ui._panel(permission, ui._options(permission), 0, 0, 19)
    assert len(lines) <= 19 and hidden
    assert "v hoặc PgDn xem tiếp" in plain("".join(line.text() for line in lines))


def test_a_command_is_a_block_with_its_output_and_result(project):
    ui = make_ui()
    tools = Tools(Workspace(project), ui)
    tools.approve_all = True
    tools.call("run_command", args(command="echo xin chao", timeout_seconds=30, shell=None, cwd=None))
    text = plain(ui.out.getvalue())
    assert "$ echo xin chao" in text and "xin chao" in text and "✓ xong · " in text


def test_thinking_is_one_line_unless_asked_for():
    ui = make_ui()
    reply = ui.reply()
    reply.think("**Tìm hàm checksum**\nĐọc README trước.")
    reply.feed("Xong rồi.\n")
    reply.finish()
    text = plain(ui.out.getvalue())
    assert "+ Đã nghĩ: Tìm hàm checksum · " in text and "Đọc README trước" not in text
    assert text.index("Đã nghĩ") < text.index("Xong rồi.")

    ui = make_ui()
    assert ui.toggle_thoughts()
    reply = ui.reply()
    reply.think("**Tìm hàm checksum**\nĐọc README trước.")
    reply.finish()
    assert "Đọc README trước." in plain(ui.out.getvalue())


def test_the_request_ends_with_model_time_and_context_share():
    ui = make_ui(width=160)
    ui.request_finished(RequestEnd("done", 75, {"a.py": [1, 0]}, [{"classification": "passed"}],
                                   context_tokens=18_200, model="6 Luna", context_share=0.341))
    assert ("▣ Peto · 6 Luna · 1 phút 15 giây · sửa 1 tệp · chạy 1 lệnh · 18k token · 34% tới lúc tự tóm tắt"
            in plain(ui.out.getvalue()))
    ui = make_ui()
    ui.request_finished(RequestEnd("stopped", 4, {}, []))
    assert "■ Đã dừng sau 4 giây" in plain(ui.out.getvalue())


def test_markdown_wraps_lists_tables_and_code():
    theme = Theme("dark")
    markdown = Markdown(theme, 40)
    source = ["Một đoạn văn khá dài để thử xem chữ có tự xuống dòng đúng chỗ không.", "",
              "- mục một", "  - mục con", "1. bước đầu", "", "```python", "def f():", "    return 1", "```",
              "| Tên | Điểm |", "|---|---|", "| An | 9 |", "Hết."]
    lines = [line for raw in source for line in markdown.feed(raw)] + markdown.flush()
    text = [line.text() for line in lines]
    assert all(cells(row) <= 40 for row in text)
    assert text[0].startswith("   Một đoạn văn") and len([row for row in text if "dòng" in row]) == 1
    assert "   • mục một" in text and "     • mục con" in text and "   1. bước đầu" in text
    assert any(row.startswith("     python") for row in text), "nhãn ngôn ngữ ở đầu khối code"
    assert any("def f():" in row for row in text)
    assert "   ┌─────┬──────┐" in text and "   │ An  │ 9    │" in text
    assert text[-1] == "   Hết."
    code = next(line for line in lines if "def" in line.text())
    assert any(style["fg"] == theme.keyword for word, style in code.spans if word == "def")


def test_inline_markdown_marks_code_bold_and_file_lines():
    theme = Theme("dark")
    line = Markdown(theme, 80).feed("Sửa ở savetool/checksum.py:9, đổi `data[:-1]` thành **sum(data)**.")[0]
    styles = {text: style for text, style in line.spans}
    assert styles["savetool/checksum.py:9"]["u"] and styles["data[:-1]"]["fg"] == theme.inline_code
    assert styles["sum(data)"]["b"]


def test_the_prompt_frame_has_the_bar_meta_row_cap_and_popup_above():
    theme = Theme("dark")
    state = EditorState()
    state.handle(Key("char", "/"))
    state.handle(Key("char", "r"))
    frame = prompt_view.frame(state, theme, width=80, height=24, meta=["Peto", "6 Luna", "thấp"], footer="còn 10/200 bước")
    rows = [plain(line) for line in frame.lines]
    assert rows[0].startswith("  ┃ /resume") and "▀▀▀" in rows[-2] and rows[-1] == "  còn 10/200 bước"
    assert any(row.startswith("  ┃  /r") for row in rows) and any("Peto · 6 Luna · thấp" in row for row in rows)
    assert all(cells(row) <= 79 for row in rows)
    assert rows[frame.cursor_row].startswith("  ┃  /r") and frame.cursor_col == 2 + 3 + 2


def test_a_low_window_keeps_the_text_row_and_the_cap():
    frame = prompt_view.frame(EditorState(), Theme("dark"), width=60, height=3, meta=["Peto", "Luna", "thấp"],
                              footer="x")
    rows = [plain(line) for line in frame.lines]
    assert len(rows) <= 2 and "Nhờ Peto" in rows[0] and "▀" in rows[-1]


def test_the_sent_message_stays_as_a_word_wrapped_panel():
    state = EditorState()
    state.handle(Key("paste", "Chạy test của save-tool thấy đỏ ở phần checksum"))
    state.finished = True
    rows = [plain(line) for line in prompt_view.frame(state, Theme("dark"), width=40, height=24, meta=[]).lines]
    assert rows[0].strip() == "┃" and rows[-1].strip() == "┃"
    assert all(not row.rstrip().endswith("chec") for row in rows), "không bẻ giữa từ"
    assert "".join(row.replace("┃", "").strip() + " " for row in rows).split() == \
        "Chạy test của save-tool thấy đỏ ở phần checksum".split()


def test_no_color_keeps_the_layout_without_colour_codes(project):
    ui = make_ui(colors=False)
    ui.request_finished(RequestEnd("done", 1, {}, [], model="Peto"))
    assert "38;2;" not in ui.out.getvalue() and "48;2;" not in ui.out.getvalue()
    assert "▣ Peto · Peto · 1 giây" in plain(ui.out.getvalue())


def test_terminal_ui_is_used_only_in_a_real_terminal(monkeypatch):
    from peto_agent import __main__ as cli

    monkeypatch.setattr(cli, "enable_vt", lambda stream: True)
    assert isinstance(cli.create_ui(), TerminalUI)
    monkeypatch.setenv("PETO_AGENT_UI", "classic")
    assert not isinstance(cli.create_ui(), TerminalUI)
    monkeypatch.delenv("PETO_AGENT_UI")
    monkeypatch.setattr(cli, "enable_vt", lambda stream: False)
    assert not isinstance(cli.create_ui(), TerminalUI)


def test_find_files_joins_the_explored_line_and_approximate_edits_are_flagged(project):
    from peto_agent.tools import FEATURES

    (project / "app.py").write_text("def f():\n        return 1\n")
    ui = make_ui(["y"])
    tools = Tools(Workspace(project), ui)
    tools.features = [*FEATURES, "explore_v2", "edit_v2"]
    tools.call("find_files", args(pattern="**/*.py", path=None))
    tools.call("read_file", args(path="app.py", start_line=None, end_line=None))
    ui.editor = None
    tools.call("edit_file", args(path="app.py", old_text="def f():\n    return 1", new_text="def f():\n    return 2",
                                 replace_all=None))
    text = plain(ui.out.getvalue())
    assert "→ Đã xem: 1 lần đọc, 1 lần tìm tệp" in text and '"**/*.py" 1 tệp' in text
    assert "khớp gần đúng: bỏ qua khoảng trắng đầu và cuối dòng" in text


def test_the_loop_question_offers_continue_or_stop():
    ui = make_ui()
    ui.editor = FakeEditor(FakeConsole([[Key("right")], [Key("enter")]]))
    answer = ui.ask(Permission("loop", {"name": "read_file", "count": 3, "arguments": {"path": "a.py"}}))
    assert answer == "n" and "Cho gọi tiếp" in plain(ui.out.getvalue())
