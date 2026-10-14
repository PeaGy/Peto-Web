"""Màn hình toàn phần (tui/screen.py): ô nhập ghim ở đáy, Peto tự cuộn, đổi cỡ vẽ lại sạch, thoát ra terminal như cũ."""

from __future__ import annotations

import pytest

from peto_agent.line_editor import Key
from peto_agent.tui.screen import ScreenEngine
from peto_agent.tui.text import Line, S, highlight, parse_ansi, text_between
from peto_agent.tui.view import TerminalUI
from test_footer import Console, Editor, Screen, settle, type_text
from vt import Terminal


@pytest.fixture(autouse=True)
def rich_glyphs(monkeypatch):
    monkeypatch.setenv("WT_SESSION", "test")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("PETO_AGENT_FULL_REPAINT", raising=False)


class Run:
    def __init__(self, columns=80, rows=20):
        self.terminal = Terminal(columns, rows)
        self.terminal.feed("PS C:\\du-an> peto\r\n")
        self.size = (columns, rows)
        self.console = Console()
        self.interrupts: list[int] = []
        self.copied: list[str] = []
        self.ui = TerminalUI(out=Screen(self.terminal), colors=True)
        self.ui.terminal = True
        self.ui.editor = Editor(self.console, lambda: self.size)
        self.ui.engine = ScreenEngine(self.ui, self.ui.editor, size=lambda: self.size,
                                      interrupt=lambda: self.interrupts.append(1),
                                      copy=lambda text: self.copied.append(text) or True)
        self.ui.engine.start()

    def rows(self) -> list[str]:
        return [self.terminal.text(index) for index in range(self.terminal.rows)]

    def row_of(self, text: str) -> int:
        return next(index for index, row in enumerate(self.rows()) if text in row)

    def press(self, *keys: Key) -> None:
        engine = self.ui.engine
        for key in keys:
            drawn = engine._last_draw
            self.console.press(key)
            # Luồng phím lấy phím ra rồi vẽ lại; chờ lần vẽ đó xong mới kiểm màn hình.
            assert settle(lambda: not self.console.pending and engine._last_draw != drawn)
            with engine.lock:
                pass

    def resize(self, columns: int, rows: int) -> None:
        self.terminal.resize(columns, rows)
        self.size = (columns, rows)
        self.press(Key("resize"))

    def stop(self) -> None:
        if self.ui.engine is not None:
            self.ui.stop_footer()


@pytest.fixture
def run():
    runs = []

    def start(columns=80, rows=20):
        runs.append(Run(columns, rows))
        return runs[-1]

    yield start
    for item in runs:
        item.stop()


def test_header_on_top_prompt_at_the_bottom_and_the_terminal_comes_back_clean(run):
    screen = run(80, 24)
    screen.ui.session_header("0.19.0", "~\\du-an", model="Peto", effort="vừa")
    screen.ui.line("Đã bắt đầu hội thoại mới.", "dim")
    rows = screen.rows()
    assert any("Peto Agent 0.19.0" in row for row in rows[:14]), "đầu phiên ở trên cùng"
    assert "Nhờ Peto làm gì đó…" in "".join(rows[-6:]), "ô nhập ghim ở đáy"
    assert "▀" in rows[-2] or "▀" in rows[-1]
    assert not screen.terminal.scrollback, "màn hình phụ không đẩy gì vào lịch sử cuộn"
    screen.stop()
    assert screen.terminal.switches == ["vào", "ra"]
    after = [screen.terminal.text(index) for index in range(screen.terminal.rows)]
    assert after[0] == "PS C:\\du-an> peto", "thoát ra là terminal như trước khi gõ peto"
    assert not any("Peto Agent" in row or "Nhờ Peto" in row for row in after)


def test_new_lines_follow_the_bottom_and_scrolling_shows_older_ones(run):
    screen = run(80, 20)
    for number in range(60):
        screen.ui.line(f"dòng {number:02d}")
    rows = screen.rows()
    assert any("dòng 59" in row for row in rows), "chữ mới nhất hiện ngay trên ô nhập"
    assert not any("dòng 00" in row for row in rows)
    screen.press(Key("wheel", "up"), Key("wheel", "up"))
    rows = screen.rows()
    assert not any("dòng 59" in row for row in rows)
    assert any("còn 6 dòng bên dưới" in row for row in rows), "báo còn bao nhiêu dòng khi đang cuộn lên"
    top = rows[0]
    screen.ui.line("dòng mới")
    assert screen.rows()[0] == top, "đang cuộn lên thì chữ mới không kéo màn hình đi"
    screen.press(Key("home", ctrl=True))
    assert "dòng 00" in "".join(screen.rows())
    screen.press(Key("end", ctrl=True))
    assert any("dòng mới" in row for row in screen.rows())
    assert not any("bên dưới" in row for row in screen.rows())
    screen.press(Key("pageup"))
    assert not any("dòng mới" in row for row in screen.rows()), "PgUp cuộn nửa màn hình"
    for _ in range(10):
        screen.console.press(Key("wheel", "down"))
    assert settle(lambda: any("dòng mới" in row for row in screen.rows())), "lăn xuống tới cuối thì bám cuối lại"


def test_resizing_redraws_everything_at_the_new_width_without_leftovers(run):
    screen = run(100, 24)
    screen.ui.plan([{"title": "Sửa lỗi checksum trong tệp lưu", "status": "running"},
                    {"title": "Chạy lại toàn bộ bài kiểm thử", "status": "pending"}])
    screen.ui.line("một dòng khá dài " * 8)
    for columns in (60, 44, 90):
        screen.resize(columns, 24)
        rows = screen.rows()
        assert sum("╹" in row for row in rows) == 1, "chỉ còn đúng một ô nhập, không sót khung cũ"
        assert sum("Việc cần làm" in row for row in rows) == 1
        assert all(len(row) < columns for row in rows)
    # Khung nền của khối việc cần làm rộng đúng bề ngang mới.
    plan_row = screen.row_of("Sửa lỗi checksum")
    assert len(screen.rows()[plan_row]) <= 89


def test_dragging_selects_text_and_copies_it_on_release(run):
    screen = run(80, 20)
    for number in range(5):
        screen.ui.line(f"dòng {number:02d} có chữ")
    first, second = screen.row_of("dòng 01"), screen.row_of("dòng 02")
    left = screen.rows()[first].index("dòng")
    screen.press(Key("mouse", "press", x=left, y=first), Key("mouse", "drag", x=left + 6, y=second),
                 Key("mouse", "release", x=left + 6, y=second))
    assert screen.copied == [f"dòng 01 có chữ\n{' ' * left}dòng 02"], "hàng sau giữ phần thụt lề như terminal"
    assert any("Đã chép" in row for row in screen.rows()), "báo đã chép"
    screen.ui.engine.busy = True
    screen.press(Key("interrupt"))
    assert screen.interrupts == [], "đang chọn chữ thì Ctrl+C là chép, không dừng Peto"
    assert len(screen.copied) == 2
    screen.press(Key("interrupt"))
    assert screen.interrupts == [1], "hết vùng chọn thì Ctrl+C dừng như trước"


def test_double_click_copies_a_word(run):
    screen = run(80, 20)
    screen.ui.line("mở tệp src/app/main.py:42 để xem")
    row = screen.row_of("main.py")
    column = screen.rows()[row].index("src")
    screen.press(Key("mouse", "double", x=column + 3, y=row), Key("mouse", "release", x=column + 3, y=row))
    assert screen.copied == ["src/app/main.py:42"]


def test_typing_and_sending_still_work_and_jump_back_to_the_bottom(run):
    screen = run(80, 20)
    for number in range(40):
        screen.ui.line(f"dòng {number:02d}")
    screen.press(Key("wheel", "up"))
    type_text(screen.console, "sửa lỗi")
    screen.press(Key("enter"))
    assert settle(lambda: not screen.ui.engine.submitted.empty())
    assert screen.ui.engine.follow, "gửi tin thì về cuối hội thoại"
    assert any("sửa lỗi" in row and "┃" in row for row in screen.rows()), "tin vừa gửi thành khung có thanh ┃"


def test_a_streaming_reply_is_one_block_redrawn_at_the_new_width(run):
    screen = run(100, 24)
    reply = screen.ui.reply()
    for chunk in ["Đã sửa **checksum** ", "trong `save.py:12` và chạy lại bài kiểm thử: ", "tất cả đều qua " * 6,
                  "\n\n| Tệp | Đổi |\n|---|---|\n| save.py | +3 −1 |\n"]:
        reply.feed(chunk)
    reply.finish()
    rows = screen.rows()
    assert any("Đã sửa checksum" in row for row in rows), "Markdown đã vẽ: không còn dấu **"
    assert any("save.py" in row and "│" in row for row in rows), "bảng đã kẻ khung"
    screen.resize(50, 24)
    rows = screen.rows()
    assert all(len(row) < 50 for row in rows)
    assert any("Đã sửa checksum" in row for row in rows)


def test_permission_panel_replaces_the_prompt_and_wheel_still_scrolls(run):
    import threading

    from peto_agent.events import Permission

    screen = run(90, 24)
    for number in range(50):
        screen.ui.line(f"dòng {number:02d}")
    answer = {}
    thread = threading.Thread(target=lambda: answer.setdefault(
        "value", screen.ui.ask(Permission("command", {"command": "npm test", "directory": "", "timeout": 60},
                                          allow_session=True))))
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    assert any("Cần bạn duyệt" in row for row in screen.rows())
    screen.press(Key("wheel", "up"))
    assert any("bên dưới" in row for row in screen.rows()), "lăn chuột vẫn cuộn hội thoại khi đang hỏi quyền"
    import time
    time.sleep(0.35)
    screen.press(Key("enter"))
    thread.join(timeout=3)
    assert answer["value"] == "y"


def test_shift_tab_switches_to_plan_mode_and_back(run):
    screen = run(90, 20)
    assert not any("Lập kế hoạch" in row for row in screen.rows())
    screen.press(Key("backtab"))
    assert screen.ui.mode == "plan"
    rows = screen.rows()
    assert any("Lập kế hoạch" in row for row in rows[-6:]), "nhãn chế độ thay chữ Peto ở hàng thông tin"
    assert any("shift+tab hoặc /plan về chế độ làm việc" in row for row in rows[-2:])
    screen.press(Key("backtab"))
    assert screen.ui.mode == "build" and not any("Lập kế hoạch" in row for row in screen.rows())


def test_the_list_chooser_picks_with_arrows_numbers_or_escape(run):
    import threading

    screen = run(90, 24)
    rows = [("Sửa lỗi checksum", "lúc 14:32 hôm nay · 12 tin"), ("Thêm lệnh done", "hôm qua · 6 tin"),
            ("Đổi sku", "ngày 10/10 · 30 tin · bị ngắt giữa chừng")]
    for keys, expected in (([Key("down"), Key("enter")], 1), ([Key("char", "3")], 2), ([Key("escape")], None)):
        answer = {}
        thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.choose("Mở lại hội thoại", rows)))
        thread.start()
        assert settle(lambda: screen.ui.engine.panel is not None)
        text = "\n".join(screen.rows())
        assert "Mở lại hội thoại" in text and "› " in text and "Thêm lệnh done" in text and "bị ngắt giữa chừng" in text
        import time
        time.sleep(0.35)
        screen.press(*keys)
        thread.join(timeout=3)
        assert answer["value"] == expected


def test_a_message_typed_while_busy_waits_then_lands_with_a_note(run):
    screen = run(90, 20)
    screen.ui.engine.busy = True
    type_text(screen.console, "đổi tên hàm luôn")
    screen.press(Key("enter"))
    assert settle(lambda: screen.ui.engine.steers)
    assert any("Nhắn thêm: đổi tên hàm luôn" in row for row in screen.rows())
    assert screen.ui.take_steers() == [("đổi tên hàm luôn", [])]
    rows = screen.rows()
    assert not any("Nhắn thêm:" in row for row in rows)
    assert any("đổi tên hàm luôn" in row and "┃" in row for row in rows)
    assert any("nhắn thêm lúc Peto đang làm" in row for row in rows)


def test_console_mouse_records_become_keys():
    """Bản ghi chuột ConPTY gửi (đo ngày 2026-10-12): bánh xe ở nửa trên của buttons, kéo là MOUSE_MOVED kèm nút trái."""
    from types import SimpleNamespace

    from peto_agent.line_editor import WindowsConsole, translate

    console = WindowsConsole.__new__(WindowsConsole)
    console._pressed = False

    def event(buttons, flags, x=9, y=4, state=0):
        return SimpleNamespace(buttons=buttons, flags=flags, x=x, y=y, state=state)

    assert console._mouse(event(0x00800000, 0x4)) == Key("wheel", "up", False, 9, 4)
    assert console._mouse(event(0xFF800000, 0x4)).text == "down"
    assert console._mouse(event(0, 0x1)) is None, "chuột lướt qua không thành phím"
    assert console._mouse(event(1, 0, 4, 2, state=0x08)) == Key("mouse", "press", True, 4, 2)
    assert console._mouse(event(1, 0x1, 7, 2)) == Key("mouse", "drag", False, 7, 2)
    assert console._mouse(event(0, 0, 7, 2)) == Key("mouse", "release", False, 7, 2)
    assert console._mouse(event(1, 0x2, 7, 2)).text == "double"
    assert translate(0x4C, "\x0c", 0x08) == Key("redraw")
    assert translate(0x09, "\t", 0x10) == Key("backtab") and translate(0x09, "\t", 0) == Key("tab"), "Shift+Tab"


def test_text_helpers_for_selection_and_ansi():
    line = parse_ansi("\x1b[1mPeto\x1b[0m \x1b[2m0.19\x1b[0m \x1b[38;2;238;156;173mhồng\x1b[0m")
    assert line.text() == "Peto 0.19 hồng"
    assert line.spans[0][1].get("b") and line.spans[2][1].get("d")
    assert line.spans[4][1]["fg"] == "#ee9cad"
    plain = Line([S("ab"), S("cdef", "#ffffff")])
    assert text_between(plain, 1, 4) == "bcd"
    marked = highlight(plain, 1, 8, "#000000", "#ff0000")
    assert marked.text() == "abcdef  "
    assert [text for text, style in marked.spans if style.get("bg") == "#ff0000"] == ["b", "cdef", "  "]


# ---- CLI 0.22.0: /resume vẽ lại cả hội thoại, thanh tên, bảng hội thoại, /timeline

def _saved_items():
    import json

    from peto_agent.loop import user_message

    def call(call_id, name, **arguments):
        return {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)}

    def output(call_id, result):
        return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result, ensure_ascii=False)}

    def said(text):
        return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}

    return [
        user_message("Sửa lời chào trong app.py"),
        said("Đọc tệp trước."),
        call("a", "read_file", path="app.py", start_line=None, end_line=None),
        output("a", {"path": "app.py", "start_line": 1, "end_line": 1, "total_lines": 1, "content": "1"}),
        call("b", "edit_file", path="app.py", old_text='print("Hi")', new_text='print("Xin chào")', replace_all=None),
        output("b", {"ok": True, "path": "app.py", "added_lines": 1, "removed_lines": 1}),
        call("c", "run_command", command="py -m pytest -q", timeout_seconds=None, cwd=None, shell=None),
        output("c", {"exit_code": 0, "seconds": 1.4, "output": "3 passed", "outcome": "passed"}),
        said("Đã đổi lời chào thành **Xin chào**."),
        user_message("Thêm dấu chấm than"),
        said("Xong."),
    ]


def test_resume_draws_the_whole_conversation_with_the_live_blocks(run):
    screen = run(100, 60)
    screen.ui.session_header("0.22.0", "~\\du-an", model="Peto", effort="vừa")
    screen.ui.line("dòng cũ của hội thoại trước")
    assert screen.ui.clear_conversation()
    items = _saved_items()
    screen.ui.replay(items)
    text = "\n".join(screen.rows())
    assert "dòng cũ của hội thoại trước" not in text, "mở hội thoại khác thì xóa màn hình"
    assert "Peto Agent 0.22.0" in text, "đầu phiên vẫn ở trên cùng"
    assert "Sửa lời chào trong app.py" in text and "Thêm dấu chấm than" in text
    assert "→ Đọc app.py:1-1" in text, "lượt đọc như lúc chạy"
    assert "Sửa app.py" in text and "+1" in text and "−1" in text
    assert 'print("Xin chào")' in text and 'print("Hi")' in text, "khối sửa tệp có đoạn diff"
    edit_rows = [row for row in screen.rows() if 'print("Xin chào")' in row]
    assert not any(char.isdigit() for row in edit_rows for char in row.split("print")[0]), \
        "đoạn sửa không có số dòng thật nên không in số"
    assert "py -m pytest -q" in text and "3 passed" in text
    assert "Đã đổi lời chào thành Xin chào." in text and "**" not in text, "lời Peto vẽ Markdown"
    users = [item for item in items if item.get("role") == "user"]
    assert screen.ui.jump_to(users[0]) and screen.ui.jump_to(users[1])


def test_the_title_bar_shows_the_conversation_name_and_folder(run):
    screen = run(90, 20)
    screen.ui.folder_name = "du-an"
    screen.ui.line("chữ đầu tiên")
    assert "chữ đầu tiên" in screen.rows()[0], "chưa có tên thì không có thanh"
    screen.ui.set_session_title("Sửa lỗi checksum khi lưu tệp")
    top = screen.rows()[0]
    assert "Sửa lỗi checksum khi lưu tệp" in top and top.rstrip().endswith("du-an")
    assert "chữ đầu tiên" in screen.rows()[1]
    assert screen.ui.tab_title("đang làm") == "Peto · đang làm · Sửa lỗi checksum khi lưu tệp"
    screen.ui.set_session_title(None)
    assert "chữ đầu tiên" in screen.rows()[0]
    assert screen.ui.tab_title() == "Peto · du-an"


def test_jumping_to_a_message_scrolls_it_to_the_top(run):
    from peto_agent.loop import user_message

    screen = run(90, 20)
    first = user_message("tin số một")
    screen.ui.replay([first])
    for number in range(80):
        screen.ui.line(f"dòng {number:02d}")
    assert not any("tin số một" in row for row in screen.rows())
    assert screen.ui.jump_to(first)
    assert "tin số một" in "".join(screen.rows()[:3])
    assert not screen.ui.jump_to(user_message("tin số một")), "chỉ đúng mục đã vẽ, không phải mục trùng chữ"
    screen.ui.clear_conversation()
    assert not screen.ui.jump_to(first), "xóa màn hình thì quên các khung cũ"


def test_the_session_dialog_searches_renames_and_deletes_twice(run):
    import threading
    import time as clock

    from peto_agent import history

    now = clock.time()
    sessions = [history.Saved(now - 60, [{"role": "user", "content": "a"}], id="s1", title="Sửa lỗi checksum"),
                history.Saved(now - 120, [{"role": "user", "content": "b"}], id="s2", title="Thêm lệnh done"),
                history.Saved(now - 86400 - 60, [{"role": "user", "content": "c"}], id="s3", title="Đổi sku",
                              interrupted=True)]
    renamed, deleted = [], []
    screen = run(90, 30)
    screen.ui.folder_name = "du-an"
    answer = {}
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.choose_session(
        sessions, "s1", rename=lambda sid, title: renamed.append((sid, title)),
        delete=lambda sid: deleted.append(sid) or True)), daemon=True)
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    clock.sleep(0.35)
    text = "\n".join(screen.rows())
    assert "Hội thoại của du-an" in text and "Hôm nay" in text and "Hôm qua" in text
    assert "đang mở" in text and "bị ngắt" in text
    screen.press(Key("ctrl", "d"))
    assert "Đang mở hội thoại này nên không xóa được." in "\n".join(screen.rows())
    screen.press(Key("down"), Key("ctrl", "d"))
    assert "bấm ctrl+d lần nữa để xóa" in "\n".join(screen.rows()) and not deleted
    screen.press(Key("ctrl", "d"))
    assert deleted == ["s2"] and "Thêm lệnh done" not in "\n".join(screen.rows())
    for char in "SKU":
        screen.press(Key("char", char))
    text = "\n".join(screen.rows())
    assert "Đổi sku" in text and "Sửa lỗi checksum" not in text, "tìm không phân biệt hoa thường"
    screen.press(Key("ctrl", "r"), *[Key("backspace")] * 3, *[Key("char", char) for char in "mã hàng"])
    assert "Đổi mã hàng▏" in "\n".join(screen.rows())
    screen.press(Key("enter"))
    assert renamed == [("s3", "Đổi mã hàng")]
    for _ in range(3):
        screen.press(Key("backspace"))
    screen.press(Key("down"), Key("enter"))
    thread.join(timeout=3)
    assert answer["value"].id == "s3" and answer["value"].title == "Đổi mã hàng", "mở với tên mới"


def test_fork_prefills_the_prompt_and_new_clears_the_screen(run):
    screen = run(90, 20)
    screen.ui.session_header("0.22.0", "~\\du-an", model="Peto", effort="vừa")
    screen.ui.line("câu trả lời cũ")
    screen.ui.prefill("sửa lại câu này")
    assert any("sửa lại câu này" in row for row in screen.rows()[-6:])
    screen.ui.clear_conversation()
    text = "\n".join(screen.rows())
    assert "câu trả lời cũ" not in text and "Peto Agent 0.22.0" in text
