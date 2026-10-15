"""Bấm chuột trên màn hình toàn phần (CLI 0.24.0, như opencode): nút trong khung, dòng Đã nghĩ, nhóm Đã xem, diff và
output bị cắt, tin của bạn, danh sách lệnh, "còn N dòng bên dưới". Rê chuột qua chỗ bấm được thì nó sáng lên."""

from __future__ import annotations

import threading
import time

from conftest import FakeUI
from test_footer import settle, type_text
from test_screen import rich_glyphs, run  # noqa: F401 - fixture màn hình giả

from peto_agent import __main__ as cli
from peto_agent.events import Permission, ToolDone
from peto_agent.line_editor import Key
from peto_agent.loop import user_message
from peto_agent.tui.prompt import Sent  # noqa: F401 - kiểu tin đã gửi
from peto_agent.tui.text import Line, S, clickable, hovered, target_at, Target


def find(screen, text: str) -> tuple[int, int]:
    """Ô (x, y) của chữ ``text`` trên màn hình."""
    for y, row in enumerate(screen.rows()):
        if text in row:
            return row.index(text), y
    raise AssertionError(f"không thấy {text!r} trên màn hình:\n" + "\n".join(screen.rows()))


def mouse(screen, kind: str, x: int, y: int) -> None:
    screen.console.press(Key("mouse", kind, False, x, y))
    assert settle(lambda: not screen.console.pending)
    time.sleep(0.05)
    with screen.ui.engine.lock:
        pass


def click(screen, text: str) -> None:
    x, y = find(screen, text)
    mouse(screen, "move", x, y)
    mouse(screen, "press", x, y)
    mouse(screen, "release", x, y)


def rows(screen) -> str:
    return "\n".join(screen.rows())


def test_targets_are_found_by_column_and_hover_only_touches_their_spans():
    target = Target(("thử",), lambda: None)
    line = Line([S("   ")] + clickable([S("+ Đã nghĩ", "#ffaa00")], target) + [S("  khác", "#888888")])
    assert target_at(line, 2) is None and target_at(line, 3) is target and target_at(line, 11) is target
    assert target_at(line, 12) is None and target_at(None, 3) is None
    lit = hovered(line, ("thử",), text="#ffffff", bg="#222222")
    assert lit.spans[1][1]["u"] and lit.spans[1][1]["fg"] == "#ffffff" and not lit.spans[2][1]["u"]
    assert hovered(line, ("khác",), text="#ffffff", bg="#222222") is line
    block = Line(clickable([S("tin", "#ffffff", "#111111")], Target(("tin",), lambda: None, look="bg")))
    assert hovered(block, ("tin",), text=None, bg="#333333").spans[0][1]["bg"] == "#333333"


def test_clicking_thinking_opens_it_in_place_and_hover_lights_it(run):  # noqa: F811
    screen = run(100, 30)
    writer = screen.ui.reply()
    writer.think("**Đọc app.py**\nTìm hàm greet.\n\n**Đổi lời chào**\nSang tiếng Việt.")
    writer.feed("Đã đổi lời chào.")
    writer.finish()
    assert "Tìm hàm greet." not in rows(screen)
    x, y = find(screen, "+ Đã nghĩ")
    mouse(screen, "move", x + 2, y)
    assert screen.ui.engine.hover_key is not None, "rê qua thì dòng đó sáng lên"
    click(screen, "+ Đã nghĩ")
    text = rows(screen)
    assert "− Đã nghĩ: Đổi lời chào" in text and "Tìm hàm greet." in text and "Sang tiếng Việt." in text
    click(screen, "− Đã nghĩ")
    assert "Tìm hàm greet." not in rows(screen) and "+ Đã nghĩ" in rows(screen)


def test_dragging_across_a_clickable_line_selects_text_instead(run):  # noqa: F811
    screen = run(100, 30)
    writer = screen.ui.reply()
    writer.think("**Đọc app.py**\nTìm hàm greet.")
    writer.feed("Xong.")
    writer.finish()
    x, y = find(screen, "+ Đã nghĩ")
    mouse(screen, "press", x, y)
    mouse(screen, "drag", x + 6, y)
    mouse(screen, "release", x + 6, y)
    assert screen.copied and "Tìm hàm greet." not in rows(screen), "kéo là chọn chữ, không mở suy nghĩ"


def test_jump_to_latest_from_the_more_below_line(run):  # noqa: F811
    screen = run(90, 20)
    for number in range(60):
        screen.ui.line(f"dòng {number:02d}")
    screen.press(Key("wheel", "up"), Key("wheel", "up"))
    assert "dòng 59" not in rows(screen)
    click(screen, "còn 6 dòng bên dưới")
    assert "dòng 59" in rows(screen) and screen.ui.engine.follow


def test_explored_groups_and_long_blocks_open_and_close(run):  # noqa: F811
    screen = run(110, 60)
    ui = screen.ui
    ui._group = [("read", "src/app.py:1-40"), ("read", "src/util.py:1-9"), ("search", '"greet" 3 kết quả')]
    ui._flush_group()
    assert "Đọc src/util.py:1-9" not in rows(screen)
    click(screen, "Đã xem:")
    text = rows(screen)
    assert "Đọc src/app.py:1-40" in text and "Đọc src/util.py:1-9" in text and 'Tìm "greet" 3 kết quả' in text

    before = "".join(f"dòng {number}\n" for number in range(60))
    after = "".join(f"dòng mới {number}\n" for number in range(59)) + "dòng năm mươi\n"
    ui.preview("file", {"path": "a.txt", "before": before, "after": after, "title": "Muốn sửa a.txt"})
    ui.tool_finished(ToolDone("c1", "edit_file", {"path": "a.txt"},
                              {"ok": True, "path": "a.txt", "added_lines": 2, "removed_lines": 2}, {}))
    assert "bấm để xem đủ" in rows(screen) and "dòng năm mươi" not in rows(screen)
    click(screen, "bấm để xem đủ")
    assert "dòng năm mươi" in rows(screen) and "▴ thu gọn" in rows(screen)
    click(screen, "▴ thu gọn")
    assert "dòng năm mươi" not in rows(screen)

    output = "".join(f"kết quả {number:02d}\n" for number in range(30))
    ui.preview("command", {"command": "py -m pytest", "shell": "cmd"})
    ui.tool_finished(ToolDone("c2", "run_command", {"command": "py -m pytest"},
                              {"exit_code": 1, "seconds": 2.0, "output": output}, {}))
    assert "(20 dòng trước đó · bấm để xem đủ)" in rows(screen) and "kết quả 03" not in rows(screen)
    click(screen, "(20 dòng trước đó")
    assert "kết quả 03" in rows(screen)


def test_permission_buttons_follow_the_mouse_and_answer_on_click(run):  # noqa: F811
    screen = run(100, 26)
    answer = {}
    permission = Permission("command", {"command": "npm test", "directory": "", "timeout": 60}, allow_session=True)
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.ask(permission)), daemon=True)
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    time.sleep(0.35)
    x, y = find(screen, "Từ chối")
    mouse(screen, "move", x + 2, y)
    screen.press(Key("enter"))
    thread.join(timeout=3)
    assert answer["value"] == "n", "rê qua nút là chọn nó, như opencode"

    answer.clear()
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.ask(permission)), daemon=True)
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    time.sleep(0.35)
    click(screen, " Cả yêu cầu này ")
    thread.join(timeout=3)
    assert answer["value"] == "a"


def test_list_rows_and_the_escape_hint_are_clickable(run):  # noqa: F811
    screen = run(100, 26)
    rows_shown = [("Peto", "mặc định"), ("6 Luna", "của OpenAI"), ("Haiku 5.5", "của Anthropic")]
    for clicked, expected in (("6 Luna", 1), ("esc thôi", None)):
        answer = {}
        thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.choose("Đổi model", rows_shown)),
                                  daemon=True)
        thread.start()
        assert settle(lambda: screen.ui.engine.panel is not None)
        time.sleep(0.35)
        click(screen, clicked)
        thread.join(timeout=3)
        assert answer["value"] == expected


def test_a_click_right_after_a_panel_opens_is_ignored(run):  # noqa: F811
    screen = run(100, 26)
    answer = {}
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.choose(
        "Đổi model", [("Peto", ""), ("6 Luna", "")])), daemon=True)
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    click(screen, "6 Luna")
    assert screen.ui.engine.panel is not None, "khung vừa hiện: cú bấm lỡ tay không chọn gì"
    time.sleep(0.35)
    click(screen, "6 Luna")
    thread.join(timeout=3)
    assert answer["value"] == 1


def test_question_options_and_the_btw_box_buttons(run):  # noqa: F811
    screen = run(110, 30)
    question = {"question": "Lưu ở đâu?", "header": "Lưu trữ", "multiple": True,
                "options": [{"label": "SQLite", "description": ""}, {"label": "JSON", "description": ""}]}
    answer = {}
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.questions([question])), daemon=True)
    thread.start()
    assert settle(lambda: screen.ui.engine.panel is not None)
    time.sleep(0.35)
    click(screen, "JSON")
    assert "[x] JSON" in rows(screen), "câu nhiều đáp án: bấm là đánh dấu"
    click(screen, " xong")
    thread.join(timeout=3)
    assert answer["value"] == [["JSON"]]

    screen.ui.ask_aside("Peto đang làm gì?", lambda: ("Đang đọc app.py.", False))
    assert settle(lambda: screen.ui.engine.panel is not None)
    time.sleep(0.35)
    click(screen, "c chép")
    assert screen.copied == ["Đang đọc app.py."]
    click(screen, "esc đóng")
    assert settle(lambda: screen.ui.engine.panel is None)


def test_clicking_your_message_opens_its_menu_or_copies_while_busy(run):  # noqa: F811
    screen = run(100, 26)
    ui, engine = screen.ui, screen.ui.engine
    item = user_message("Sửa lời chào trong app.py")
    ui.replay([item])
    ui.commit_user(Sent(_state("/export")))
    ui.link_user_entry(None)
    click(screen, "/export")
    assert engine.submitted.empty(), "khung lệnh gạch chéo không bấm được"
    engine.busy = True
    click(screen, "Sửa lời chào trong app.py")
    assert screen.copied == ["Sửa lời chào trong app.py"] and "Đã chép tin" in rows(screen)
    assert engine.submitted.empty()
    engine.busy = False
    click(screen, "Sửa lời chào trong app.py")
    assert engine.submitted.get(timeout=1) == ("/timeline", []) and ui.take_clicked() is item
    assert ui.take_clicked() is None


def test_the_timeline_command_opens_the_clicked_message_directly(project):
    from peto_agent.client import Client
    from peto_agent.loop import Session
    from peto_agent.workspace import Workspace

    first, second = user_message("Việc một"), user_message("Việc hai")

    class Clicked(FakeUI):
        def take_clicked(self):
            item, self.item = getattr(self, "item", None), None
            return item

    work = Session(Client("http://127.0.0.1:9", "t"), Workspace(project), FakeUI())
    work.items = [first, second]
    ui = Clicked(answers=["1"])
    ui.item = second
    cli._timeline(ui, work)
    assert "Các tin của bạn" not in ui.text and "Tin 2" in ui.text and "Nhảy tới" not in ui.text
    assert "Việc hai" in ui.text.split("Chữ của tin đó")[1], "Chép (không có clipboard thì in ra)"


def test_slash_menu_items_follow_the_mouse_and_run_or_fill(run):  # noqa: F811
    screen = run(100, 30)
    engine = screen.ui.engine
    type_text(screen.console, "/")
    assert settle(lambda: "/btw" in rows(screen))
    x, y = find(screen, "/timeline")
    mouse(screen, "move", x, y)
    assert engine.state.items()[engine.state.selected].text == "/timeline", "rê qua là chọn"
    click(screen, "/btw")
    assert engine.state.text == "/btw " and engine.submitted.empty(), "lệnh cần gõ thêm thì chỉ điền vào ô"
    engine.state.clear()
    type_text(screen.console, "/")
    assert settle(lambda: "/new" in rows(screen))
    click(screen, "/new ")
    assert engine.submitted.get(timeout=1) == ("/new", [])


def _state(text: str):
    from peto_agent.line_editor import EditorState

    state = EditorState()
    state.insert(text)
    state.finished = True
    return state


def test_the_explore_block_opens_to_show_the_subagent_s_work(run):  # noqa: F811
    """Agent con explore (CLI 0.27.0): một dòng tóm tắt; bấm để thấy từng việc nó làm và kết luận nó trả về."""
    screen = run(110, 40)
    screen.ui.tool_finished(ToolDone(
        "p1", "explore", {"task": "Tìm nơi in lời chào.", "depth": "quick"},
        {"summary": "Lời chào in ở app.py:2.", "steps": 3, "files_read": ["app.py"]},
        {"actions": ["Tìm \"print\"", "Đọc app.py"], "depth": "quick"}))
    assert "Khám phá Tìm nơi in lời chào. · 3 bước · đọc 1 tệp" in rows(screen)
    assert "Lời chào in ở app.py:2." not in rows(screen)
    click(screen, "Khám phá")
    text = rows(screen)
    assert 'Tìm "print"' in text and "Đọc app.py" in text and "Lời chào in ở app.py:2." in text
    click(screen, "Khám phá")
    assert "Lời chào in ở app.py:2." not in rows(screen)
