"""Những gì tới trong lúc Peto làm (CLI 0.20.0, theo opencode): tin nhắn thêm, đổi chế độ Lập kế hoạch, lệnh nền tự
dừng. Tất cả được chèn vào hội thoại trước bước kế tiếp."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from conftest import FakeUI
from test_loop_client import Handler, call, message

from peto_agent import history
from peto_agent.client import Client
from peto_agent.loop import Session
from peto_agent.tools import PLAN_REFUSAL
from peto_agent.workspace import Workspace


class InboxUI(FakeUI):
    """Giao diện giả có tin nhắn thêm: mỗi lần vòng làm việc hỏi thì trả tin kế tiếp trong danh sách."""

    def __init__(self, answers=(), steers=()):
        super().__init__(answers)
        self.steers = list(steers)
        self.asked = 0

    def take_steers(self):
        self.asked += 1
        return [self.steers.pop(0)] if self.steers else []


@pytest.fixture
def server():
    peto = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    peto.requests = []
    peto.script = []
    peto.reply = lambda path, body: script_reply(peto, body)
    threading.Thread(target=peto.serve_forever, daemon=True).start()
    peto.url = f"http://127.0.0.1:{peto.server_address[1]}"
    yield peto
    peto.shutdown()
    peto.server_close()


def script_reply(peto, body):
    steps = [request for request in peto.requests if request["path"] == "/api/agent/step"]
    text, calls = peto.script[min(len(steps) - 1, len(peto.script) - 1)]
    return 200, [{"type": "meta", "steps_used": len(steps), "steps_limit": 200}, {"type": "delta", "text": text},
                 {"type": "done", "output": [message(text), *calls], "usage": {"input_tokens": 10, "output_tokens": 5}}]


def inputs(peto):
    return [request["body"]["input"] for request in peto.requests if request["path"] == "/api/agent/step"]


def user_texts(items):
    return [history.raw_text(item) for item in items if item.get("role") == "user"]


def session(project, peto, ui):
    (project / "README.md").write_text("# Dự án\n", encoding="utf-8")
    return Session(Client(peto.url, "peto_token_thu"), Workspace(project), ui)


def test_a_message_typed_while_peto_works_goes_into_the_next_step(project, server):
    server.script = [("", [call(0, "read_file", path="README.md", start_line=None, end_line=None)]),
                     ("Đã đọc, viết bằng tiếng Anh nhé.", [])]
    ui = InboxUI(steers=[("trả lời bằng tiếng Anh", [])])
    work = session(project, server, ui)
    work.run_task("Đọc README")
    second = inputs(server)[1]
    kinds = [item.get("type") for item in second]
    steer = second[-1]
    assert kinds[-2] == "function_call_output" and steer["role"] == "user", "chèn sau kết quả công cụ"
    assert history.raw_text(steer) == history.STEER_NOTE + "trả lời bằng tiếng Anh"
    assert history.recap(work.items)[0] == ("Bạn", "trả lời bằng tiếng Anh"), "tóm tắt bỏ phần đầu của CLI"


def test_a_message_that_arrives_as_peto_finishes_keeps_the_request_going(project, server):
    server.script = [("Xong rồi.", []), ("Đã đổi theo ý bạn.", [])]
    ui = InboxUI(steers=[("à mà đổi tên hàm luôn", [])])
    work = session(project, server, ui)
    work.run_task("Xem giúp")
    assert len(inputs(server)) == 2, "model định dừng mà còn tin nhắn thêm thì chạy thêm một bước"
    assert user_texts(inputs(server)[1])[-1].endswith("à mà đổi tên hàm luôn")
    assert "Peto › Đã đổi theo ý bạn." in ui.text


def test_plan_mode_blocks_file_changes_and_tells_peto_when_it_starts_and_ends(project, server):
    server.script = [("", [call(0, "edit_file", path="README.md", old_text="# Dự án", new_text="# Mới",
                                replace_all=None)]),
                     ("Kế hoạch: đổi tiêu đề README.", [])]
    ui = InboxUI()
    ui.mode = "plan"
    work = session(project, server, ui)
    work.run_task("Đổi tiêu đề README")
    assert (project / "README.md").read_text(encoding="utf-8") == "# Dự án\n", "không sửa gì ở chế độ Lập kế hoạch"
    first, second = inputs(server)
    assert user_texts(first)[-2:] == [history.PLAN_ON_NOTE, "Đổi tiêu đề README"], "nhắc chế độ trước tin của người dùng"
    output = next(item for item in second if item.get("type") == "function_call_output")
    assert json.loads(output["output"]) == {"error": PLAN_REFUSAL}
    assert "Đang lập kế hoạch nên chưa sửa README.md" in ui.text

    ui.mode = "build"
    server.requests.clear()
    server.script = [("Ok.", [])]
    work.run_task("Làm đi")
    assert user_texts(inputs(server)[0])[-2:] == [history.PLAN_OFF_NOTE, "Làm đi"]
    assert history.is_note(next(item for item in work.items if history.raw_text(item) == history.PLAN_ON_NOTE))
    assert ("Bạn", "Làm đi") == history.recap(work.items)[0], "tin nhắc chế độ không phải lời người dùng"

    resumed = session(project, server, InboxUI())
    resumed.resume(work.items[:3])
    assert resumed._announced_mode == "plan", "mở lại hội thoại thì nhớ chế độ đã báo gần nhất"


def test_a_background_job_that_stops_by_itself_is_reported_once(project, server):
    work = session(project, server, InboxUI())
    job = work.tools.jobs.start(f'"{sys.executable}" -c "print(\'may chu loi cong\'); raise SystemExit(3)"', project)
    deadline = time.monotonic() + 10
    while job.running() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert work._inbox() is False, "tin báo lệnh nền không bắt Peto chạy thêm bước"
    note = history.raw_text(work.items[-1])
    assert note.startswith(history.JOB_NOTE) and "mã thoát 3" in note and "may chu loi cong" in note
    assert "Lệnh nền #1 đã dừng · mã thoát 3" in work.ui.text
    count = len(work.items)
    work._inbox()
    assert len(work.items) == count, "mỗi lệnh chỉ báo một lần"

    stopped = work.tools.jobs.start(f'"{sys.executable}" -c "import time; time.sleep(30)"', project)
    work.tools.jobs.stop(stopped.id)
    seen = work.tools.jobs.start(f'"{sys.executable}" -c "print(1)"', project)
    while seen.running():
        time.sleep(0.05)
    work.tools.jobs.read(seen.id, 0)
    work._inbox()
    assert len(work.items) == count, "lệnh Peto tự dừng, hay Peto đã thấy nó dừng, thì không báo"


PLAN = [{"title": "Đọc README", "status": "done"}, {"title": "Trả lời", "status": "done"}]


def test_a_final_answer_sent_with_an_all_done_plan_ends_the_request(project, server):
    server.script = [("", [call(0, "update_plan", steps=[{**PLAN[0], "status": "running"}, {**PLAN[1], "status": "pending"}]),
                           call(1, "read_file", path="README.md", start_line=None, end_line=None)]),
                     ("README chỉ có tiêu đề.", [call(2, "update_plan", steps=PLAN)]),
                     ("không được tới đây", [])]
    work = session(project, server, InboxUI())
    work.run_task("README có gì?")
    assert len(inputs(server)) == 2, "đánh dấu xong hết kèm câu trả lời thì không tốn thêm bước"
    assert work.items[-1]["type"] == "function_call_output", "lời gọi update_plan vẫn có kết quả cho lượt sau"
    assert "Peto › README chỉ có tiêu đề." in work.ui.text


def test_a_lead_in_with_an_unfinished_plan_or_an_unchecked_edit_keeps_going(project, server):
    running = [{**PLAN[0], "status": "running"}, {**PLAN[1], "status": "pending"}]
    server.script = [("Mình xem README.", [call(0, "update_plan", steps=running)]),
                     ("Xong.", [])]
    work = session(project, server, InboxUI())
    work.run_task("README có gì?")
    assert len(inputs(server)) == 2, "kế hoạch còn việc dở thì câu chữ chỉ là lời mở đầu"

    server.requests.clear()
    server.script = [("", [call(0, "read_file", path="README.md", start_line=None, end_line=None)]),
                     ("", [call(1, "edit_file", path="README.md", old_text="# Dự án", new_text="# Mới",
                                replace_all=None)]),
                     ("Đã đổi tiêu đề.", [call(2, "update_plan", steps=PLAN)]),
                     ("Không có test; đã đọc lại tệp.", [])]
    edit = session(project, server, InboxUI(["y"]))
    edit.run_task("Đổi tiêu đề")
    assert len(inputs(server)) == 4, "sửa mà chưa kiểm tra thì vẫn nhắc kiểm tra như khi Peto tự dừng"
    assert "Kiểm tra sau sửa" in json.dumps(inputs(server)[3], ensure_ascii=False)
