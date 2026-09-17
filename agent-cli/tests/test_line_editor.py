"""Ô nhập có bảng gợi ý lệnh: lọc lệnh, sửa chữ, bộ gõ tiếng Việt, dán, xếp hàng và vẽ lại tại chỗ."""

from __future__ import annotations

import contextlib
import io

import pytest

from peto_agent import line_editor
from peto_agent.commands import suggestions
from peto_agent.line_editor import INTERRUPT, SUBMIT, EditorState, Key, LineEditor, group_paste, layout, translate
from peto_agent.ui import UI

PROMPT = "Bạn › "


def typed(text: str) -> list[Key]:
    """Phím như console gửi: \\r là Enter, \\n là Ctrl+Enter, \\t là Tab."""
    special = {"\r": Key("enter"), "\n": Key("newline"), "\t": Key("tab")}
    return [special.get(char, Key("char", char)) for char in text]


def feed(state: EditorState, keys: list[Key]):
    result = None
    for key in keys:
        result = state.handle(key)
    return result


def labels(text: str) -> list[str]:
    return [item.label for item in suggestions(text)]


def test_suggestions_filter_commands_and_effort_levels():
    assert labels("/") == ["/moi", "/resume", "/effort", "/usage", "/help", "/thoat"]
    assert labels("/re") == ["/resume"]
    assert labels("/thoát") == ["/thoat"], "bộ gõ tiếng Việt thêm dấu vẫn khớp"
    assert labels("/sume") == ["/resume"], "gõ phần giữa tên lệnh cũng tìm ra"
    assert labels("/effort ") == ["thap", "vua", "cao"]
    assert [item.text for item in suggestions("/effort C")] == ["/effort cao"]
    for text in ("/effort cao thêm", "/moi ", "xin chào", "/moi\n"):
        assert labels(text) == []


def test_enter_runs_the_highlighted_command_only_after_something_was_typed():
    state = EditorState()
    feed(state, typed("/re"))
    assert state.selected == 0
    assert state.handle(Key("enter")) == (SUBMIT, "/resume")

    state.clear()
    feed(state, typed("/"))
    assert state.selected is None
    assert state.handle(Key("enter")) == (SUBMIT, "/"), "chỉ gõ / rồi Enter không tự chạy /moi"

    state.clear()
    feed(state, [*typed("/"), Key("down"), Key("down")])
    assert state.handle(Key("enter")) == (SUBMIT, "/resume")
    state.clear()
    feed(state, [*typed("/"), Key("up")])
    assert state.handle(Key("enter")) == (SUBMIT, "/thoat")

    state.clear()
    feed(state, typed("/eff\t"))
    assert state.text == "/effort " and [item.label for item in state.items()] == ["thap", "vua", "cao"]
    assert state.handle(Key("enter")) == (SUBMIT, "/effort "), "chưa chọn mức thì chỉ xem mức đang dùng"

    state.clear()
    feed(state, typed("/effort c"))
    assert state.handle(Key("enter")) == (SUBMIT, "/effort cao")

    state.clear()
    feed(state, [*typed("/re"), Key("escape")])
    assert state.items() == []
    assert state.handle(Key("enter")) == (SUBMIT, "/re"), "Esc ẩn gợi ý thì Enter gửi đúng chữ đã gõ"


def test_editing_keys_and_the_vietnamese_input_method():
    state = EditorState()
    # Unikey gõ Telex: "tiee" thành "tiê", rồi "s" sau "tiêng" thành "tiếng", bằng cách xóa rồi gửi lại cả cụm chữ.
    feed(state, [*typed("tie"), *group_paste([Key("backspace"), Key("char", "ê")]), *typed("ng"),
                 *group_paste([Key("backspace"), Key("backspace"), Key("backspace"), *typed("ếng")])])
    assert state.text == "tiếng"

    feed(state, [Key("left"), Key("left"), Key("delete"), *typed("n")])
    assert (state.text, state.cursor) == ("tiếng", 4)
    feed(state, [Key("home"), *typed("Học "), Key("end"), Key("backspace", ctrl=True)])
    assert state.text == "Học "
    feed(state, [Key("left", ctrl=True)])
    assert state.cursor == 0
    assert state.handle(Key("interrupt")) is None and state.text == "", "Ctrl+C khi có chữ thì chỉ xóa ô nhập"
    assert state.handle(Key("interrupt")) == (INTERRUPT, "")


def test_history_and_moving_between_lines():
    state = EditorState()
    for text in ("sửa lỗi đăng nhập", "/resume"):
        state.clear()
        feed(state, typed(text + "\r"))
    assert state.history == ["sửa lỗi đăng nhập", "/resume"]

    state.clear()
    feed(state, typed("nháp"))
    state.handle(Key("up"))
    assert state.text == "/resume"
    state.handle(Key("up"))
    assert state.text == "sửa lỗi đăng nhập", "đang duyệt lịch sử thì mũi tên không chuyển sang bảng gợi ý"
    state.handle(Key("down"))
    state.handle(Key("down"))
    assert state.text == "nháp"

    state.clear()
    feed(state, typed("dòng một\nhai"))
    state.handle(Key("up"))
    assert (state.text, state.cursor) == ("dòng một\nhai", 3)
    state.handle(Key("down"))
    assert state.cursor == len(state.text)


def test_pastes_are_grouped_and_long_ones_collapse():
    lines = ["Traceback (most recent call last):", '  File "app.py", line 3', "ValueError: sai", "    raise"]
    keys = group_paste(typed("\r".join(lines) + "\r"))
    assert [key.name for key in keys] == ["paste"], "Enter giữa đoạn dán nhiều dòng không gửi"
    state = EditorState()
    feed(state, [*typed("Sửa lỗi này: "), *keys])
    frame = layout(state, prompt=PROMPT, width=80, height=24)
    assert frame.lines == ["Bạn › Sửa lỗi này: [Đã dán 4 dòng]"]
    assert state.handle(Key("enter")) == (SUBMIT, "Sửa lỗi này: " + "\n".join(lines))

    assert group_paste(typed("abc\r")) == [Key("paste", "abc"), Key("enter")], "dán một dòng kèm Enter vẫn gửi"
    assert group_paste(typed("ok\r")) == typed("ok\r")
    assert group_paste([Key("enter"), Key("char", "x")]) == [Key("newline"), Key("char", "x")]

    state.clear()
    feed(state, group_paste(typed("một\rhai\tba")))
    assert state.text == "một\nhai\tba", "đoạn dán ngắn được chèn thẳng, giữ xuống dòng và tab"
    assert line_editor.clean("a\x1b[31mb\U00100000", keep="\n") == "a[31mb"


def test_console_key_events_are_translated():
    assert translate(0x0D, "\r", 0) == Key("enter")
    assert translate(0x0D, "\r", 0x10) == Key("newline"), "Shift+Enter xuống dòng"
    assert translate(0x4A, "\n", 0x08) == Key("newline")
    assert translate(0x08, "\x7f", 0x08) == Key("backspace", ctrl=True)
    assert translate(0x25, "\x00", 0) == Key("left")
    assert translate(0x25, "\x00", 0x04) == Key("left", ctrl=True)
    assert translate(0x43, "\x03", 0x08) == Key("interrupt")
    assert translate(0xE7, "ệ", 0) == Key("char", "ệ"), "bộ gõ gửi chữ có dấu qua VK_PACKET"
    assert translate(0x10, "\x00", 0x10) is None


def test_layout_wraps_before_the_last_column_and_draws_the_menu():
    state = EditorState()
    feed(state, typed("/re"))
    frame = layout(state, prompt=PROMPT, width=80, height=24)
    assert frame.lines == ["Bạn › /re", "  ❯ /resume  Mở lại hội thoại gần nhất của thư mục này"]
    assert (frame.cursor_row, frame.cursor_col) == (0, 9)

    state.clear()
    feed(state, typed("a" * 30))
    frame = layout(state, prompt=PROMPT, width=20, height=24)
    assert frame.lines == ["Bạn › " + "a" * 13, " " * 6 + "a" * 13, " " * 6 + "a" * 4]
    assert (frame.cursor_row, frame.cursor_col) == (2, 10)

    state.clear()
    feed(state, typed("文字" * 7))
    frame = layout(state, prompt=PROMPT, width=20, height=24)
    assert [line_editor.display_width(line) for line in frame.lines] == [18, 18, 10], "chữ rộng 2 cột không bị cắt đôi"

    state.clear()
    feed(state, typed("".join(f"dòng {number}\n" for number in range(10))))
    frame = layout(state, prompt=PROMPT, width=80, height=5)
    assert frame.lines == ["      dòng 7", "      dòng 8", "      dòng 9", "      "] and frame.cursor_row == 3


class FakeConsole:
    def __init__(self, batches):
        self.batches = list(batches)
        self.raw_entered = 0

    @contextlib.contextmanager
    def raw(self):
        self.raw_entered += 1
        yield

    def keys(self):
        return self.batches.pop(0)


def test_line_editor_redraws_in_place():
    console = FakeConsole([typed("/re"), [Key("enter")]])
    out = io.StringIO()
    editor = LineEditor(console, out, size=lambda: (80, 24))
    assert editor.read(PROMPT) == "/resume"
    text = out.getvalue()
    assert "Bạn › /re\r\n  ❯ /resume  Mở lại hội thoại gần nhất của thư mục này\033[1A\r\033[9C" in text
    assert text.endswith("\r\033[JBạn › /resume\r\033[13C\033[?25h\r\n"), "lần vẽ cuối xóa bảng gợi ý rồi xuống dòng"

    console = FakeConsole([typed("a" * 30), [Key("interrupt")], [Key("interrupt")]])
    editor = LineEditor(console, io.StringIO(), size=lambda: (20, 24))
    with pytest.raises(KeyboardInterrupt):
        editor.read(PROMPT)
    assert "\033[2A\r\033[J" in editor.out.getvalue(), "vẽ lại từ hàng dấu nhắc dù chữ đã xuống hàng"
    assert console.raw_entered == 1

    console = FakeConsole([typed("hi\ryo"), [Key("enter")]])
    editor = LineEditor(console, io.StringIO(), size=lambda: (80, 24))
    assert editor.read(PROMPT) == "hi"
    assert editor.read(PROMPT) == "yo", "phím tới sau Enter được giữ cho lượt nhập sau"


def test_falls_back_to_input_outside_a_console(monkeypatch):
    assert line_editor.create(io.StringIO(), lambda stream: True) is None
    monkeypatch.setenv("PETO_AGENT_SIMPLE_INPUT", "1")
    assert line_editor.simple_input_requested()
    monkeypatch.setenv("PETO_AGENT_SIMPLE_INPUT", "0")
    assert not line_editor.simple_input_requested()

    class BrokenEditor:
        def read(self, prompt, paint):
            raise OSError("console không cho đọc phím")

    ui = UI(out=io.StringIO(), reader=lambda prompt: "chữ gõ", colors=False)
    ui.editor = BrokenEditor()
    assert ui.prompt() == "chữ gõ" and ui.editor is None
