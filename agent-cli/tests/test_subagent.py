"""Agent con chỉ đọc explore (CLI 0.27.0, theo agent "explore" của opencode)."""

from __future__ import annotations

import copy
import json

from conftest import FakeUI

from peto_agent.client import ApiError
from peto_agent.loop import Session
from peto_agent.tools import FEATURES
from peto_agent.workspace import Workspace


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(call_id, name, **args):
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(args)}


def done(*output, purpose=None):
    return [{"type": "meta", "steps_used": 3, "steps_limit": 200},
            {"type": "done", "output": list(output), "usage": {"input_tokens": 100},
             **({"purpose": purpose} if purpose else {})}]


class Client:
    """Máy chủ giả: trả lần lượt; ghi lại thân từng bước. Phần tử là exception thì ném ra."""

    server = "https://example.test"

    def __init__(self, replies):
        self.replies = list(replies)
        self.bodies = []

    def stream(self, path, body, **kwargs):
        self.bodies.append(copy.deepcopy(body))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        yield from reply


def session(project, replies, answers=()):
    work = Session(Client(replies), Workspace(project), FakeUI(list(answers)))
    work.tools.features = [*FEATURES, "explore_v2", "edit_v2", "read_more", "subagent"]
    work.auto_title = False
    return work


def result_of(items, call_id):
    return json.loads(next(item["output"] for item in items
                           if item.get("type") == "function_call_output" and item.get("call_id") == call_id))


def explore_call(task="Tìm nơi in lời chào.", depth="quick"):
    return call("p1", "explore", task=task, depth=depth)


def test_the_subagent_reads_on_its_own_and_only_its_conclusion_returns(project):
    (project / "app.py").write_text("def greet(name):\n    print('Hi ' + name)\n", encoding="utf-8")
    replies = [
        done(explore_call()),
        done(call("c1", "search_files", pattern="print", path=None, glob=None), purpose="explore"),
        done(call("c2", "read_file", path="app.py", start_line=None, end_line=None), purpose="explore"),
        done(message("Lời chào in ở app.py:2."), purpose="explore"),
        done(message("Lời chào nằm ở app.py:2.")),
    ]
    work = session(project, replies)
    work.run_task("Lời chào được in ở đâu?")
    child = [body for body in work.client.bodies if body["context"].get("purpose") == "explore"]
    assert len(child) == 3 and all(body["effort"] == "low" and body["model"] == "peto" for body in child)
    assert child[0]["input"] == [{"type": "message", "role": "user", "content": "Tìm nơi in lời chào."}], \
        "agent con chỉ thấy task, không thấy hội thoại"
    parent = work.client.bodies[-1]["input"]
    result = result_of(parent, "p1")
    assert result == {"summary": "Lời chào in ở app.py:2.", "steps": 3, "files_read": ["app.py"]}
    assert not any("def greet" in json.dumps(item, ensure_ascii=False) for item in parent), "nội dung tệp không vào"
    assert project / "app.py" not in work.ws.read_digests, "agent con đọc không tính là Peto đã đọc"
    assert "Khám phá xong · 3 bước · đọc 1 tệp" in work.ui.text and "· Đọc app.py" in work.ui.text


def test_the_last_allowed_step_is_final_and_tools_outside_the_list_are_refused(project):
    (project / "a.txt").write_text("a", encoding="utf-8")
    replies = [
        done(explore_call()),
        done(call("c1", "edit_file", path="a.txt", old_text="a", new_text="b"), purpose="explore"),
        done(call("c2", "list_files", path=".", depth=None), purpose="explore"),
        done(call("c3", "list_files", path=".", depth=1), purpose="explore"),
        done(message("Chưa tìm ra, mới xem thư mục gốc."), purpose="explore"),
        done(message("Xong.")),
    ]
    work = session(project, replies)
    work.run_task("dò")
    child = [body for body in work.client.bodies if body["context"].get("purpose") == "explore"]
    assert [body["context"].get("final", False) for body in child] == [False, False, False, True], "quick: 4 bước"
    refused = result_of(child[1]["input"], "c1")
    assert "chỉ được tìm và đọc" in refused["error"]
    assert (project / "a.txt").read_text(encoding="utf-8") == "a"


def test_a_failure_in_the_subagent_comes_back_as_an_error_result(project):
    replies = [done(explore_call()), ApiError(400, "Dịch vụ AI không nhận nội dung bước này."), done(message("Ok."))]
    work = session(project, replies)
    work.run_task("dò")
    result = result_of(work.client.bodies[-1]["input"], "p1")
    assert result["error"].startswith("Agent con dừng giữa chừng: Dịch vụ AI không nhận") and result["steps"] == 0


def test_ctrl_c_in_the_subagent_stops_the_request(project):
    replies = [done(explore_call()), KeyboardInterrupt()]
    work = session(project, replies)
    work.run_task("dò")
    assert "Đã dừng yêu cầu" in work.ui.text
    stopped = next(item for item in work.items if item.get("call_id") == "p1" and item["type"] == "function_call_output")
    assert "Ctrl+C" in stopped["output"]


def test_an_old_server_never_offers_explore(project):
    work = session(project, [])
    work.tools.features = list(FEATURES)
    assert work.tools.call("explore", json.dumps({"task": "x", "depth": "quick"}))["error"]
