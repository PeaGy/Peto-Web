"""Khung nhập: vùng nền, placeholder, vị trí con trỏ và dọn khung trước câu trả lời."""

from __future__ import annotations

import io
import re

import pytest

from peto_agent import line_editor
from peto_agent.line_editor import EditorState, Key, LineEditor, display_width, layout
from peto_agent.ui import UI
from test_line_editor import FakeConsole, SHOT, feed, typed


SGR = re.compile(r"\033\[[0-9;]*m")


def plain(lines):
    return [SGR.sub("", line) for line in lines]


def test_empty_composer_has_status_rules_placeholder_and_footer():
    """Bố cục chủ web chọn theo Claude Code: trạng thái canh phải, đường kẻ trên dưới, không tô nền."""
    ui = UI(out=io.StringIO(), colors=True)
    status = "◉ Peto · thấp"
    frame = layout(EditorState(), prompt="› ", width=80, height=24, paint=ui.paint,
                   boxed=True, footer="còn 193/200 bước", status=status)
    assert plain(frame.lines) == [
        " " * (79 - display_width(status)) + status,
        "─" * 79,
        "› Nhờ Peto làm gì đó…",
        "─" * 79,
        "  còn 193/200 bước",
    ]
    assert (frame.cursor_row, frame.cursor_col) == (2, 2)
    assert not any("48;5;" in line for line in frame.lines), "không còn khung nền xám"


@pytest.mark.parametrize("width,height", [(80, 24), (30, 12), (20, 5), (12, 3)])
def test_composer_cursor_and_content_stay_inside_small_terminal(width, height):
    state = EditorState()
    feed(state, typed("Tiếng Việt 日本語\nhai\nba\nbốn\nnăm"))
    for cursor in (0, 5, len(state.text)):
        state.cursor = cursor
        frame = layout(state, prompt="› ", width=width, height=height, boxed=True, footer="còn 193/200 bước",
                       status="◉ Peto · cao")
        assert len(frame.lines) < height
        assert all(display_width(line) < width for line in frame.lines)
        assert 0 <= frame.cursor_row < len(frame.lines)
        assert 2 <= frame.cursor_col < width
        assert "Nhờ Peto" not in "".join(frame.lines)


def test_suggestions_do_not_displace_cursor_or_overflow_short_screen():
    state = EditorState()
    feed(state, typed("/"))
    for height in (5, 8, 24):
        frame = layout(state, prompt="› ", width=80, height=height, boxed=True, footer="Peto · mức vừa")
        assert len(frame.lines) < height
        assert frame.lines[frame.cursor_row].rstrip() == "› /"
        assert frame.cursor_col == 3
    assert any("/resume" in line for line in frame.lines)
    assert any("/retry" in line for line in frame.lines)
    assert frame.lines[-1].strip() == "Peto · mức vừa"
    state.selected = len(state.items()) - 1
    small = layout(state, prompt="› ", width=40, height=5, boxed=True, footer="Peto · mức vừa")
    assert any("❯ /thoat" in line for line in small.lines), "menu hẹp phải cuộn theo lệnh đang chọn"


def test_submitting_removes_padding_placeholder_footer_and_suggestions():
    state = EditorState()
    feed(state, typed("/effort cao\r"))
    frame = layout(state, prompt="› ", width=80, height=24, boxed=True, footer="Peto · mức vừa")
    assert frame.lines == ["› /effort cao"]
    assert (frame.cursor_row, frame.cursor_col) == (0, 13)


def test_boxed_editor_keeps_pasted_text_images_and_cleans_up_before_permission():
    console = FakeConsole([[Key("paste", "dòng 1\ndòng 2\ndòng 3\ndòng 4")], [Key("image")],
                           typed(" sửa giúp"), [Key("enter")]])
    out = io.StringIO()
    editor = LineEditor(console, out, size=lambda: (60, 24), clipboard=lambda: [SHOT])
    ui = UI(out=out, reader=lambda _: "n", colors=True)
    ui.editor = editor
    assert ui.prompt(footer="Peto · mức vừa") == "dòng 1\ndòng 2\ndòng 3\ndòng 4[Ảnh 1]  sửa giúp"
    assert ui.attached == [(1, SHOT)]
    # Sau lần xóa khung cuối cùng chỉ còn nội dung gửi; không có đường kẻ hay footer trong vùng câu hỏi quyền.
    final_draw = out.getvalue().rsplit("\r\033[J", 1)[-1]
    assert "───" not in final_draw and "mức vừa" not in final_draw
    assert "Nhờ Peto" not in final_draw
    assert ui.ask_permission() == "n"


def test_read_error_restores_cursor_and_background():
    class FailedConsole(FakeConsole):
        def keys(self):
            raise OSError("lost console")

    out = io.StringIO()
    editor = LineEditor(FailedConsole([]), out, size=lambda: (80, 24))
    ui = UI(out=out, colors=True, reader=lambda _: "tiếp tục")
    ui.editor = editor
    assert ui.prompt() == "tiếp tục"
    assert ui.editor is None
    assert "\033[0m\033[?25h" in out.getvalue()


def test_ctrl_c_and_no_color_keep_the_existing_input_behavior():
    out = io.StringIO()
    console = FakeConsole([typed("nháp"), [Key("interrupt")], [Key("interrupt")]])
    ui = UI(out=out, colors=False)
    ui.editor = LineEditor(console, out, size=lambda: (80, 24))
    with pytest.raises(KeyboardInterrupt):
        ui.prompt(footer="Peto · mức vừa")
    assert "48;5;236" not in out.getvalue()
    assert "Nhờ Peto làm gì đó" in out.getvalue(), "Ctrl+C đầu tiên xóa nháp, trả lại placeholder"
    assert console.raw_entered == 1

    prompts = []
    plain_ui = UI(out=io.StringIO(), colors=False, reader=lambda prompt: prompts.append(prompt) or "xin chào")
    assert plain_ui.prompt() == "xin chào" and prompts == ["› "]
    assert not plain_ui.out.getvalue(), "pipe không chứa khung hay mã điều khiển"
