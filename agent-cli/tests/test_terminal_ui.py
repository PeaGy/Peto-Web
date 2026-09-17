"""Khả năng đọc diff, streaming và fallback trong terminal hẹp hoặc không có màu."""

from __future__ import annotations

import io
import unicodedata

import pytest

from peto_agent import ui as display
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


@pytest.mark.parametrize("width", [32, 60, 100])
def test_numbered_diff_wraps_without_losing_code_or_vietnamese(width):
    out = io.StringIO()
    ui = display.UI(out=out, colors=False, width=width)
    changed = unicodedata.normalize("NFD", 'message = "Chào bạn, Peto đã sửa lỗi tiếng Việt 日本語"')
    ui.diff("Muốn sửa src/chào-bạn.py", "# đầu\nmessage = 'cũ'\n# cuối\n", f"# đầu\n{changed}\n# cuối\n")
    lines = out.getvalue().splitlines()
    assert all(sum(map(display.cell_width, line)) < width for line in lines)
    assert "\x1b" not in out.getvalue()
    added = next(index for index, line in enumerate(lines) if "│ + " in line)
    code = lines[added].split("│ + ", 1)[1]
    for line in lines[added + 1:]:
        if line.startswith(" " * 14 + "│ "):
            code += line.split("│ ", 1)[1]
        else:
            break
    assert code == changed, "ngắt dòng code phải giữ đủ dấu và khoảng trắng"
    assert "      2     │ − message = 'cũ'" in lines
    assert "    +1 thêm · −1 xóa" in lines


def test_paging_a_large_diff_does_not_approve_the_change(project):
    out = io.StringIO()
    answers = iter(["v", "v", "n"])
    ui = display.UI(out=out, colors=False, reader=lambda _: next(answers))
    tools = Tools(Workspace(project), ui)
    content = "".join(f"Dòng {number}\n" for number in range(260))
    result = tools.write_file("large.txt", content)
    assert "không đồng ý" in result["error"]
    assert not (project / "large.txt").exists()
    assert "Dòng 259" in out.getvalue() and "gõ v" in out.getvalue()
    assert tools.approve_all is False


def test_diff_shows_newline_only_change_and_escapes_control_characters():
    out = io.StringIO()
    ui = display.UI(out=out, colors=False)
    ui.diff("Muốn sửa notes.txt", "chào\x1b[2J", "chào\x1b[2J\n")
    text = out.getvalue()
    assert "+1 thêm · −1 xóa" in text
    assert "không có ký tự xuống dòng" in text
    assert "\\x1b[2J" in text and "\x1b" not in text


def test_partial_reply_is_visible_before_newline_and_final_text_is_complete():
    out = io.StringIO()
    ui = display.UI(out=out, colors=True, width=40)
    reply = ui.reply()
    reply.feed("Đang xem **lỗi** ")
    assert "Peto › Đang xem **lỗi** " in out.getvalue()
    reply.feed("tiếng Việt.\nĐã xong.")
    reply.finish()
    text = display.ANSI.sub("", out.getvalue())
    assert "Peto › Đang xem lỗi tiếng Việt.\n" in text
    assert text.endswith("Đã xong.\n")
    previous = out.getvalue()
    reply.finish()
    assert out.getvalue() == previous


def test_redirected_output_and_no_color_keep_a_readable_transcript(monkeypatch):
    pipe = display.UI(out=io.StringIO())
    pipe.command('python -c "print(1)"', "C:/Dự án", 120)
    pipe.command_progress(3, "Đang kiểm tra")
    pipe.command_result({"output": "\x1b[32mxin chào\x1b[0m\n", "seconds": 3, "exit_code": 0})
    assert "\x1b" not in pipe.out.getvalue()
    assert "xin chào" in pipe.out.getvalue() and "· xong" in pipe.out.getvalue()

    monkeypatch.setenv("NO_COLOR", "")
    monkeypatch.setattr(display, "enable_vt", lambda stream: True)
    mono = display.UI(out=io.StringIO(), width=32)
    assert mono.terminal and not mono.colors
    mono.status("Đang chạy lệnh · 999s · Ctrl+C dừng" * 5)
    rendered = display.ANSI.sub("", mono.out.getvalue()).lstrip("\r")
    assert sum(map(display.cell_width, rendered)) <= 31
    assert mono.paint("xong", "green") == "xong"
