"""/btw: hỏi bên lề về hội thoại, kể cả lúc Peto đang làm; câu trả lời trong hộp nổi (CLI 0.23.0, theo opencode)."""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from conftest import FakeUI
from test_footer import settle, type_text
from test_loop_client import message, peto  # noqa: F401 - fixture máy chủ giả
from test_screen import rich_glyphs, run  # noqa: F401 - fixture màn hình giả

from peto_agent import __main__ as cli
from peto_agent import history
from peto_agent.client import ApiError, Client
from peto_agent.line_editor import Key
from peto_agent.loop import PENDING_RESULT, Session, user_message
from peto_agent.workspace import Workspace

ANSWER = "**Đang sửa** `app.py`: đổi lời chào sang tiếng Việt."


def call(call_id: str, name: str, **arguments) -> dict:
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)}


def test_a_side_question_sends_a_snapshot_and_leaves_the_conversation_alone(project, peto):  # noqa: F811
    def reply(path, body):
        return 200, [{"type": "meta", "steps_used": 12, "steps_limit": 200},
                     {"type": "done", "output": [message(ANSWER)], "purpose": "btw",
                      "usage": {"input_tokens": 900, "output_tokens": 20}}]

    peto.reply = reply
    work = Session(Client(peto.url, "peto_token_thu"), Workspace(project), FakeUI(), model="luna")
    work.supported_efforts = ["low", "medium", "high"]
    work.effort = "high"
    work.items = [user_message("Sửa lời chào trong app.py"), call("a", "read_file", path="app.py"),
                  {"type": "function_call_output", "call_id": "a", "output": "{}"},
                  call("b", "edit_file", path="app.py", old_text="Hi", new_text="Xin chào")]
    before = json.dumps(work.items)
    assert work.side_question("Peto đang sửa tệp nào?") == ANSWER
    body = peto.requests[-1]["body"]
    assert body["context"]["purpose"] == "btw" and body["model"] == "luna" and body["effort"] == "low"
    assert body["input"][-1] == user_message("Peto đang sửa tệp nào?")
    pending = [item for item in body["input"] if item.get("call_id") == "b" and item["type"] == "function_call_output"]
    assert pending and json.loads(pending[0]["output"]) == PENDING_RESULT, "lời gọi đang chạy vẫn có kết quả hợp lệ"
    assert json.dumps(work.items) == before, "không thêm gì vào hội thoại"
    assert not history.list_sessions(project, peto.url), "không lưu gì"
    assert work.steps_used == 12

    peto.reply = lambda path, body: (200, [{"type": "error", "message": "Hôm nay đã dùng hết bước."}])
    with pytest.raises(ApiError, match="hết bước"):
        work.side_question("còn gì?")
    peto.reply = lambda path, body: (200, [{"type": "done", "output": [message("Chào bạn")],
                                            "usage": {}}])
    with pytest.raises(ApiError, match="chưa hỗ trợ /btw"):
        work.side_question("máy chủ cũ?")


class FakeWork:
    def __init__(self, answer=ANSWER, features=("btw",), release: threading.Event | None = None):
        self.tools = SimpleNamespace(features=list(features))
        self.answer, self.release, self.asked = answer, release, []

    def side_question(self, question: str) -> str:
        self.asked.append(question)
        if self.release is not None:
            self.release.wait(3)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_text_interface_prints_the_answer_or_why_it_cannot_ask():
    ui = FakeUI()
    cli._btw(ui, FakeWork(), "Peto đang làm gì?")
    assert "/btw · Peto đang làm gì?" in ui.text and "**Đang sửa** `app.py`" in ui.text
    assert "không thêm vào hội thoại" in ui.text
    cli._btw(ui, FakeWork(), "")
    assert cli.BTW_HINT in ui.text
    cli._btw(ui, FakeWork(features=()), "hỏi")
    assert "Máy chủ chưa hỗ trợ /btw" in ui.text
    failed = FakeUI()
    cli._btw(failed, FakeWork(answer=ApiError(429, "Hôm nay đã dùng hết bước.")), "hỏi")
    assert "Hôm nay đã dùng hết bước." in failed.text


def test_btw_while_busy_shows_a_waiting_line_then_a_box_that_copies_and_closes(run):  # noqa: F811
    screen = run(100, 30)
    release = threading.Event()
    work = FakeWork(release=release)
    screen.ui.engine.side = lambda text: cli._aside(screen.ui, work, text)
    screen.ui.engine.busy = True
    type_text(screen.console, "/btw Peto đang sửa tệp nào?")
    screen.press(Key("enter"))
    assert settle(lambda: work.asked == ["Peto đang sửa tệp nào?"])
    assert settle(lambda: any("/btw Peto đang sửa tệp nào?" in row for row in screen.rows()))
    engine = screen.ui.engine
    assert not engine.steers and not engine.queued and engine.state.text == "", "không thành tin nhắn thêm"
    release.set()
    assert settle(lambda: engine.panel is not None)
    time.sleep(0.35)
    text = "\n".join(screen.rows())
    assert "Đang sửa app.py: đổi lời chào sang tiếng Việt." in text, "câu trả lời vẽ Markdown"
    assert "esc đóng · không thêm vào hội thoại" in text and "Peto đang sửa tệp nào?" in text
    screen.press(Key("char", "c"))
    assert screen.copied == [ANSWER] and any("Đã chép câu trả lời" in row for row in screen.rows())
    screen.press(Key("interrupt"))
    assert settle(lambda: engine.panel is None)
    assert screen.interrupts == [], "Ctrl+C trong hộp chỉ đóng hộp, không dừng việc đang làm"
    assert not any("/btw Peto" in row for row in screen.rows()), "hết dòng chờ"


def test_a_bare_btw_keeps_the_prompt_and_the_box_waits_for_an_open_question(run):  # noqa: F811
    screen = run(100, 30)
    engine = screen.ui.engine
    engine.side = lambda text: cli._aside(screen.ui, FakeWork(), text)
    type_text(screen.console, "/btw")
    screen.press(Key("enter"))
    assert engine.state.text == "/btw " and engine.state.notice == cli.BTW_HINT
    engine.state.clear()

    answer = {}
    chooser = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.choose(
        "Mở lại hội thoại", [("Sửa lỗi checksum", "hôm nay")])), daemon=True)
    chooser.start()
    assert settle(lambda: engine.panel is not None)
    screen.ui.ask_aside("Còn bao nhiêu bước?", lambda: ("Còn 190 bước.", False))
    time.sleep(0.4)
    assert not any("Còn 190 bước." in row for row in screen.rows()), "chờ khung đang mở đóng đã"
    screen.press(Key("escape"))
    chooser.join(timeout=3)
    assert answer["value"] is None
    assert settle(lambda: any("Còn 190 bước." in row for row in screen.rows()))
    time.sleep(0.35)
    screen.press(Key("escape"))
    assert settle(lambda: engine.panel is None)


def test_a_long_answer_scrolls_inside_the_box(run):  # noqa: F811
    screen = run(90, 24)
    engine = screen.ui.engine
    long = "\n".join(f"- dòng {number:02d}" for number in range(40))
    screen.ui.ask_aside("Liệt kê", lambda: (long, False))
    assert settle(lambda: engine.panel is not None)
    time.sleep(0.35)
    rows = "\n".join(screen.rows())
    assert "dòng 00" in rows and "dòng 39" not in rows and "cuộn · dòng 1–" in rows
    screen.press(Key("end"))
    rows = "\n".join(screen.rows())
    assert "dòng 39" in rows and "dòng 00" not in rows
    screen.press(Key("escape"))
    assert settle(lambda: engine.panel is None)
