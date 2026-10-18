"""Hồi quy summary chỉ 57 ký tự, thất lạc kết quả lệnh và giả thuyết bị biến thành sự thật."""
import copy
import json

import pytest
from conftest import FakeUI, handoff
from test_agent_workflow import Client, call, message

from peto_agent import continuation, history, recall
from peto_agent.loop import Session, user_message
from peto_agent.workspace import Workspace


def transcript():
    return [user_message("Thêm bài, giữ nhạc cũ; chỉ báo xong sau kiểm đọc độc lập."),
            call(1, "write_file", path="add_tracks.py", content="work in progress"),
            {"type": "function_call_output", "call_id": "1", "output": json.dumps({"ok": True, "path": "add_tracks.py"})},
            call(2, "update_plan", steps=[{"title": "Kiểm radio", "status": "running"}]),
            {"type": "function_call_output", "call_id": "2", "output": '{"ok":true}'},
            call(3, "run_command", command="python add_tracks.py", cwd=".", shell="cmd"),
            {"type": "function_call_output", "call_id": "3", "output": json.dumps({
                "exit_code": 1, "output": "DOOMER: size mismatch; headroom is an unproven hypothesis", "classification": "execution_error"})},
            *[message("Đã khảo sát. " * 100) for _ in range(40)]]


def test_short_summary_is_rejected_then_one_valid_retry_preserves_evidence(project):
    client = Client([[message("Mình chạy đối chiếu header rồi tiếp tục từ kết quả đã có.")],
                     [message(handoff("Build lỗi; chưa đạt."))]])
    work = Session(client, Workspace(project), FakeUI())
    work.items = transcript()
    work._running = True
    assert work.compact() and work.metrics.calls["compact"] == 2
    assert [body["effort"] for body in client.bodies] == ["low", "medium"]
    assert all(body["input"][-1]["content"].startswith("[Peto Agent] Stop working") for body in client.bodies)
    state = continuation.capture(work.items)
    assert state["files"] == ["add_tracks.py"] and state["plan"][0]["status"] == "running"
    assert state["recent"][-1]["result"]["exit_code"] == 1
    assert "unproven hypothesis" in state["recent"][-1]["result"]["output"]
    saved = history.load(project, client.server)
    resumed = Session(Client(), Workspace(project), FakeUI())
    resumed.resume(saved.items, session_id=saved.id)
    assert continuation.capture(resumed.items) == state


def test_two_bad_summaries_leave_history_and_permissions_untouched(project):
    client = Client([[message("Mình làm tiếp.")]] * 2)
    work = Session(client, Workspace(project), FakeUI())
    work.items = transcript()
    original = copy.deepcopy(work.items)
    work.tools.approve_all = False
    assert not work.compact() and work.items == original
    assert len(client.bodies) == 2 and not work.tools.approve_all
    assert work.session_id is None


def test_save_failure_does_not_commit_compacted_context_or_clear_read_state(project, monkeypatch):
    work = Session(Client([[message(handoff())]]), Workspace(project), FakeUI())
    work.items = transcript()
    original = copy.deepcopy(work.items)
    work.ws.read_digests[project / "a.py"] = "known"
    monkeypatch.setattr(work, "save", lambda **kwargs: False)
    assert not work.compact() and work.items == original
    assert work.ws.read_digests[project / "a.py"] == "known"
    assert len(list(recall.folder(project, work.session_id).glob("*.json"))) == 1


@pytest.mark.parametrize("summary", ["", "Đã xong.", "\n".join("## " + head for head in continuation.HEADINGS),
                                     "preamble\n" + handoff(), handoff() + "x" * 8000])
def test_handoff_contract_rejects_empty_missing_sections_and_unbounded_output(summary):
    assert continuation.validate(summary)


def test_checkpoint_is_bounded_and_never_carries_execution_grants():
    items = transcript()
    items.insert(0, user_message(continuation.checkpoint_message({
        "version": 1, "files": ["prior.py"], "plan": [], "recent": [],
        "approve_all": True, "command_grants": ["anything"]})))
    state = continuation.capture(items)
    assert "approve_all" not in state and "command_grants" not in state
    assert state["files"] == ["prior.py", "add_tracks.py"]
    assert len(continuation.checkpoint_message(state)) < 10500


def test_seeded_checkpoint_is_filtered_and_bounded_too():
    seed = {"version": 1, "files": ["x" * 2000] * 3,
            "plan": [{"title": "z" * 2000, "status": "running", "grant": True}],
            "recent": [{"tool": "read_file", "approve_all": True,
                        "arguments": {"path": "p", "command_grants": ["anything"]},
                        "result": {"error": "q" * 2000, "grant": True}}]}
    state = continuation.capture([user_message(continuation.checkpoint_message(seed))])
    assert len(json.dumps(state)) < 3000 and state["recent"][0]["tool"] == "read_file"
    assert "grant" not in json.dumps(state) and state["plan"][0]["status"] == "running"


def test_retained_tail_does_not_duplicate_evidence_over_repeated_compactions():
    rows = transcript()
    state = continuation.capture(rows)
    for _ in range(10):
        state = continuation.capture([user_message(continuation.checkpoint_message(state)), *rows[5:9]])
    assert len(state["recent"]) == 1 and state["recent"][0]["result"]["exit_code"] == 1
