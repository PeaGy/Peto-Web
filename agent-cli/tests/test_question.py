"""Câu hỏi có lựa chọn (ask_user) và tên hội thoại do model đặt (CLI 0.21.0, theo opencode)."""

from __future__ import annotations

import json
import threading
import time

import pytest
from conftest import FakeUI
from test_inbox import inputs, server  # noqa: F401 - fixture máy chủ giả có kịch bản
from test_screen import Run

from peto_agent import history
from peto_agent.client import Client
from peto_agent.line_editor import Key
from peto_agent.loop import Session
from peto_agent.tools import FEATURES, Tools
from peto_agent.workspace import Workspace

QUESTION = {"question": "Lưu dữ liệu ở đâu?", "header": "Lưu trữ", "multiple": None,
            "options": [{"label": "SQLite (nên chọn)", "description": "Một tệp, không cần máy chủ"},
                        {"label": "JSON", "description": "Đơn giản nhất"},
                        {"label": "PostgreSQL", "description": "Cần cài đặt"}]}


def ask(tools, questions):
    return tools.call("ask_user", json.dumps({"questions": questions}, ensure_ascii=False))


def make(project, answers=()):
    tools = Tools(Workspace(project), FakeUI(answers))
    tools.features = [*FEATURES, "question"]
    return tools


def test_typed_answers_pick_options_by_number_or_take_free_text(project):
    tools = make(project, ["2", "1,3", "dùng Redis cho nhanh", ""])
    assert ask(tools, [QUESTION])["answers"] == [{"question": "Lưu dữ liệu ở đâu?", "answer": ["JSON"]}]
    multiple = {**QUESTION, "multiple": True}
    assert ask(tools, [multiple])["answers"][0]["answer"] == ["SQLite (nên chọn)", "PostgreSQL"]
    assert ask(tools, [QUESTION])["answers"][0]["answer"] == ["dùng Redis cho nhanh"]
    assert ask(tools, [QUESTION])["dismissed"] is True, "Enter trống là bỏ qua"
    assert "? Lưu trữ: Lưu dữ liệu ở đâu?" in tools.ui.text and "1. SQLite (nên chọn)" in tools.ui.text


def test_bad_questions_are_sent_back_to_peto(project):
    tools = make(project)
    assert "1 tới 3 câu hỏi" in ask(tools, [])["error"]
    assert "2 tới 4 lựa chọn" in ask(tools, [{**QUESTION, "options": QUESTION["options"][:1]}])["error"]
    tools.ui.mode = "plan"
    tools.ui.answers = ["1"]
    assert ask(tools, [QUESTION])["answers"][0]["answer"] == ["SQLite (nên chọn)"], "hỏi được cả khi lập kế hoạch"


def test_the_eval_policy_takes_the_recommended_option(project):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
    from policy import Policy, PolicyUI

    ui = PolicyUI(Policy(project))
    assert ui.questions([QUESTION, {**QUESTION, "options": QUESTION["options"][1:]}]) == [["SQLite (nên chọn)"],
                                                                                          ["JSON"]]
    assert ui.requests[0]["kind"] == "question" and ui.requests[0]["answer"] == "SQLite (nên chọn)"


@pytest.fixture
def screen():
    run = Run(90, 26)
    yield run
    run.stop()


def answer_in_panel(screen, questions, *keys):
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("value", screen.ui.questions(questions)))
    thread.start()
    from test_footer import settle

    assert settle(lambda: screen.ui.engine.panel is not None)
    time.sleep(0.35)
    screen.press(*keys)
    thread.join(timeout=3)
    return result.get("value", "chưa trả lời")


def test_the_panel_answers_by_number_arrows_space_or_typing(screen):
    assert answer_in_panel(screen, [QUESTION], Key("char", "2")) == [["JSON"]]
    assert answer_in_panel(screen, [QUESTION], Key("down"), Key("down"), Key("enter")) == [["PostgreSQL"]]
    multiple = {**QUESTION, "multiple": True}
    assert answer_in_panel(screen, [multiple], Key("char", " "), Key("down"), Key("down"), Key("char", " "),
                           Key("enter")) == [["SQLite (nên chọn)", "PostgreSQL"]]
    typed = [Key("up"), Key("enter"), *[Key("char", char) for char in "dùng Redis"], Key("backspace"), Key("enter")]
    assert answer_in_panel(screen, [QUESTION], *typed) == [["dùng Redi"]], "dòng cuối mở ô tự trả lời"
    mixed = [Key("char", " "), Key("up"), Key("enter"), *[Key("char", char) for char in "Redis"], Key("enter")]
    assert answer_in_panel(screen, [multiple], *mixed) == [["SQLite (nên chọn)", "Redis"]], "giữ cả mục đã đánh dấu"
    assert answer_in_panel(screen, [QUESTION], Key("escape")) is None, "Esc là bỏ qua"


def test_the_panel_shows_the_question_options_and_hint(screen):
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("value", screen.ui.questions([QUESTION])))
    thread.start()
    from test_footer import settle

    assert settle(lambda: screen.ui.engine.panel is not None)
    text = "\n".join(screen.rows())
    assert "? Lưu trữ" in text and "Lưu dữ liệu ở đâu?" in text and "SQLite (nên chọn)" in text
    assert "Một tệp, không cần máy chủ" in text and "Tự trả lời…" in text and "1–3 chọn nhanh" in text
    time.sleep(0.35)
    screen.press(Key("escape"))
    thread.join(timeout=3)


def test_the_first_request_gets_a_title_from_one_cheap_step(project, server):  # noqa: F811
    server.script = [("Đã sửa checksum.", []), ("Sửa lỗi checksum tệp lưu", [])]
    plain = server.reply

    def reply(path, body):
        status, events = plain(path, body)
        if body.get("context", {}).get("purpose") == "title":
            events[-1]["purpose"] = "title"  # như máy chủ thật: lượt đặt tên ghi rõ purpose
        return status, events

    server.reply = reply
    (project / "README.md").write_text("# Dự án\n", encoding="utf-8")
    work = Session(Client(server.url, "peto_token_thu"), Workspace(project), FakeUI(), model="luna")
    work.tools.features = [*FEATURES, "title"]
    work.run_task("sửa giúp mình cái checksum bị sai trong tệp lưu")
    deadline = time.monotonic() + 5
    while work.title is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert work.title == "Sửa lỗi checksum tệp lưu"
    title_request = server.requests[-1]["body"]
    assert title_request["context"] == {"purpose": "title"} and title_request["model"] == "peto"
    assert title_request["effort"] == "low" and "checksum bị sai" in history.raw_text(title_request["input"][0])
    deadline = time.monotonic() + 5
    while history.load(project, work.client.server).title != work.title and time.monotonic() < deadline:
        time.sleep(0.05)
    assert history.load(project, work.client.server).title == "Sửa lỗi checksum tệp lưu"

    count = len(inputs(server))
    server.script = [("Ok.", [])]
    work.run_task("thêm test")
    time.sleep(0.3)
    assert len(inputs(server)) == count + 1, "chỉ đặt tên một lần mỗi hội thoại"


def test_no_title_without_the_server_feature_or_in_evals(project, server):  # noqa: F811
    server.script = [("Xong.", [])]
    work = Session(Client(server.url, "peto_token_thu"), Workspace(project), FakeUI())
    work.run_task("làm gì đó")
    time.sleep(0.3)
    assert len(inputs(server)) == 1 and work.title is None
    work.tools.features = [*FEATURES, "title"]
    work.auto_title = False
    work.run_task("làm tiếp")
    time.sleep(0.3)
    assert len(inputs(server)) == 2


def test_a_title_arriving_after_new_still_names_the_old_conversation(project, server):  # noqa: F811
    server.script = [("Xong.", []), ("Tên tới chậm", [])]
    plain = server.reply

    def reply(path, body):
        status, events = plain(path, body)
        if body.get("context", {}).get("purpose") == "title":
            time.sleep(0.6)
            events[-1]["purpose"] = "title"
        return status, events

    server.reply = reply
    work = Session(Client(server.url, "peto_token_thu"), Workspace(project), FakeUI())
    work.tools.features = [*FEATURES, "title"]
    work.run_task("việc đầu tiên")
    old = work.session_id
    work.reset()
    assert work.session_id is None and work.title is None
    def saved_title():
        saved = history.load(project, work.client.server, old)
        return saved.title if saved else None

    deadline = time.monotonic() + 5
    while saved_title() != "Tên tới chậm" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert saved_title() == "Tên tới chậm"
    assert work.title is None, "hội thoại mới không nhận tên của hội thoại cũ"
