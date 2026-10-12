"""Công cụ báo sự kiện có cấu trúc (events.py) thay vì tự in chữ: giao diện mới chỉ cần đọc các sự kiện này."""

from __future__ import annotations

import io
import json
import re

from conftest import FakeUI

from peto_agent.events import Permission, RequestEnd
from peto_agent.loop import Session
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


class RecordingUI(FakeUI):
    """Ghi lại các sự kiện theo thứ tự, vẫn vẽ như bản dòng nối tiếp."""

    def __init__(self, answers=()):
        super().__init__(answers)
        self.events: list[tuple] = []

    def tool_started(self, call):
        self.events.append(("started", call))
        super().tool_started(call)

    def tool_progress(self, call_id, seconds, output):
        self.events.append(("progress", call_id))
        super().tool_progress(call_id, seconds, output)

    def tool_finished(self, done):
        self.events.append(("finished", done))
        super().tool_finished(done)

    def preview(self, kind, body):
        self.events.append(("preview", kind, body))
        super().preview(kind, body)

    def ask(self, permission: Permission) -> str:
        self.events.append(("ask", permission))
        return super().ask(permission)

    def request_finished(self, end: RequestEnd) -> None:
        self.events.append(("end", end))
        super().request_finished(end)

    def kinds(self) -> list[str]:
        return [event[0] for event in self.events]


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def test_a_read_is_one_started_and_one_finished_event_carrying_what_peto_got(project):
    (project / "app.py").write_text("a\nb\nc\n")
    ui = RecordingUI()
    tools = Tools(Workspace(project), ui)
    tools.call_id = "call_1"

    result = tools.call("read_file", args(path="app.py", start_line=2, end_line=None))

    assert ui.kinds() == ["started", "finished"]
    started, finished = ui.events[0][1], ui.events[1][1]
    assert (started.call_id, started.name, started.args["path"]) == ("call_1", "read_file", "app.py")
    assert finished.result is result and finished.meta == {}
    assert "Đọc app.py (dòng 2–3)" in ui.text
    assert tools.call_id == "", "mã lời gọi chỉ dùng cho đúng một lần gọi"


def test_an_edit_shows_its_diff_before_asking_and_a_refusal_is_marked_for_display(project):
    (project / "app.py").write_text("x = 1\n")
    ui = RecordingUI(["n"])
    tools = Tools(Workspace(project), ui)
    tools.call("read_file", args(path="app.py"))
    ui.events.clear()

    result = tools.call("edit_file", args(path="app.py", old_text="x = 1", new_text="x = 2"))

    assert ui.kinds() == ["started", "preview", "ask", "finished"]
    kind, body = ui.events[1][1], ui.events[1][2]
    assert kind == "file" and body["before"] == "x = 1\n" and body["after"] == "x = 2\n"
    assert ui.events[2][1].kind == "file"
    done = ui.events[3][1]
    assert done.meta == {"refused": True, "path": "app.py"} and done.result is result
    assert "Không sửa app.py" in ui.text
    assert (project / "app.py").read_text() == "x = 1\n"


def test_an_approved_edit_still_previews_its_diff_without_asking_again(project):
    (project / "app.py").write_text("x = 1\n")
    ui = RecordingUI()
    tools = Tools(Workspace(project), ui)
    tools.approve_all = True
    tools.read_file("app.py")
    ui.events.clear()

    tools.call("edit_file", args(path="app.py", old_text="x = 1", new_text="x = 2"))

    assert ui.kinds() == ["started", "preview", "finished"]
    assert "Đã sửa app.py (+1 −1)" in ui.text


def test_a_tool_error_is_reported_once_and_still_reaches_peto(project):
    ui = RecordingUI()
    tools = Tools(Workspace(project), ui)

    result = tools.call("read_file", args(path="khong-co.py"))

    done = ui.events[-1][1]
    assert done.meta["raised"] == "workspace" and done.meta["message"] == result["error"]
    assert ui.text.count(result["error"]) == 1


def test_a_direct_call_without_the_loop_also_reports(project):
    """/init gọi thẳng list_files; giao diện vẫn thấy lần gọi đó như mọi công cụ khác."""
    (project / "src").mkdir()
    ui = RecordingUI()
    Tools(Workspace(project), ui).list_files(".")
    assert ui.kinds() == ["started", "finished"]
    assert ui.events[0][1].args == {"path": "."}
    assert "Xem thư mục ." in ui.text


def test_page_and_command_permissions_carry_what_is_being_asked(project):
    ui = RecordingUI(["n"])
    tools = Tools(Workspace(project), ui)

    tools.call("run_command", args(command="echo hi", timeout_seconds=None, shell=None, cwd=None))

    preview = next(event for event in ui.events if event[0] == "preview")
    assert preview[1] == "command" and preview[2]["command"] == "echo hi"
    permission = next(event[1] for event in ui.events if event[0] == "ask")
    assert permission.kind == "command" and permission.allow_session and permission.allow_always
    assert permission.body["command"] == "echo hi"
    assert "Không chạy lệnh" in ui.text


def test_the_request_summary_is_an_event_with_the_numbers_the_line_shows(project):
    ui = RecordingUI()
    session = Session(client=None, workspace=Workspace(project), ui=ui)
    session.tools.changes = {"a.py": [2, 1]}
    session.tools.commands = [{"command": "pytest", "classification": "check_failed"}]
    session.context_tokens = 18_200

    session._summary(75, "done")

    end = ui.events[-1][1]
    assert (end.outcome, end.seconds, end.changes, end.context_tokens) == ("done", 75, {"a.py": [2, 1]}, 18_200)
    assert "✓ Xong trong 1 phút 15 giây · sửa 1 tệp · chạy 1 lệnh (1 lỗi) · hội thoại 18k token" in ui.text


def test_thinking_keeps_the_waiting_clock_ticking(project, monkeypatch):
    """Tóm tắt suy nghĩ đến liên tục thì client không còn lúc rảnh để gọi on_idle; trước đây "Peto đang nghĩ · Ns"
    đứng yên suốt lúc model nghĩ."""
    from peto_agent import loop
    from peto_agent.ui import UI

    clock = iter(range(0, 1000, 3))
    monkeypatch.setattr(loop.time, "monotonic", lambda: float(next(clock)))

    class Client:
        server = "http://127.0.0.1"

        def stream(self, path, body, on_idle=None):
            yield {"type": "meta", "steps_used": 1, "steps_limit": 200}
            for text in ("Đọc yêu cầu", "Tìm hàm", "So với README"):
                yield {"type": "thinking", "text": text}
            yield {"type": "done", "output": [], "usage": {}}

    thoughts = []
    ui = UI(out=io.StringIO(), colors=True, width=80)
    writer = ui.reply()
    original = writer.think
    writer.think = lambda text: (thoughts.append(text), original(text))
    monkeypatch.setattr(ui, "reply", lambda: writer)
    session = Session(Client(), Workspace(project), ui)

    assert session._step() == []
    assert thoughts == ["Đọc yêu cầu", "Tìm hàm", "So với README"]
    shown = [int(part) for part in re.findall(r"Peto đang nghĩ · (\d+)s", ui.out.getvalue())]
    assert len(set(shown)) >= 3, f"đồng hồ phải chạy theo từng tóm tắt suy nghĩ: {shown}"
