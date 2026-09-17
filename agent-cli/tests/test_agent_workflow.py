"""Safety and continuity of the extended agent workflow, without model/network calls."""
import codecs
import copy
import json

import pytest
from conftest import FakeUI

from peto_agent import history
from peto_agent.client import ApiError
from peto_agent.context import compact_prefix
from peto_agent.loop import Session, user_message
from peto_agent.project_guide import guides
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace, WorkspaceError


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(number, name, **args):
    return {"type": "function_call", "call_id": str(number), "name": name, "arguments": json.dumps(args)}


class Client:
    server = "https://example.test"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.bodies = []

    def stream(self, path, body, **kwargs):
        self.bodies.append(copy.deepcopy(body))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        yield {"type": "done", "output": reply, "purpose": body.get("context", {}).get("purpose")}


def test_undo_exact_bytes_multiple_edits_and_created_file(project):
    original = codecs.BOM_UTF8 + b"one\r\ntwo\r\n"
    target = project / "a.txt"
    target.write_bytes(original)
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.read_file("a.txt")
    tools.edit_file("a.txt", "one", "first")
    tools.edit_file("a.txt", "two", "second")
    tools.write_file("new.txt", "new")
    assert tools.checkpoint.files["a.txt"].before == original
    assert tools.checkpoint.undo() == ["a.txt", "new.txt"]
    assert target.read_bytes() == original
    assert not (project / "new.txt").exists()
    assert not tools.checkpoint.files


@pytest.mark.parametrize("external", [b"mine", None])
def test_undo_preflights_all_files_before_any_restore(project, external):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "first")
    tools.write_file("b", "second")
    if external is None:
        (project / "b").unlink()
    else:
        (project / "b").write_bytes(external)
    with pytest.raises(WorkspaceError, match="không hoàn tác"):
        tools.checkpoint.undo()
    assert (project / "a").read_text() == "first"
    assert len(tools.checkpoint.files) == 2


def test_intervening_external_edit_not_absorbed_by_checkpoint(project):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "first")
    (project / "a").write_text("mine")
    tools.read_file("a")
    with pytest.raises(WorkspaceError, match="ngoài công cụ"):
        tools.edit_file("a", "mine", "bad")
    assert (project / "a").read_text() == "mine"


def test_undo_decline_then_restore_updates_context(project):
    client = Client()
    ui = FakeUI(["y", "n", "y"])
    work = Session(client, Workspace(project), ui)
    work.tools.write_file("a", "first")
    work.undo()
    assert (project / "a").exists()
    work.undo()
    assert not (project / "a").exists()
    assert "/undo" in work.items[-1]["content"]
    assert history.load(project, client.server).items == work.items


def test_guidance_scope_refresh_and_missing_new_file(project):
    (project / "AGENTS.md").write_text("root rule")
    (project / "src").mkdir()
    nested = project / "src" / "AGENTS.md"
    nested.write_text("nested rule")
    (project / "src" / "a").write_text("old")
    (project / "other").mkdir()
    (project / "other" / "AGENTS.md").write_text("unrelated")
    tools = Tools(Workspace(project), FakeUI(["a"]))
    read = tools.read_file("src/a")
    assert [g["scope"] for g in read["project_guidance"]] == [".", "src"]
    nested.write_text("updated rule")
    failed = tools.call("edit_file", json.dumps({"path": "src/a", "old_text": "old", "new_text": "new"}))
    assert failed["project_guidance"][-1]["text"] == "updated rule"
    assert (project / "src" / "a").read_text() == "old"
    assert tools.edit_file("src/a", "old", "new")["ok"]
    assert tools.write_file("src/new", "new")["ok"]
    assert [g["scope"] for g in guides(tools.ws)] == ["."]


def test_guidance_large_is_not_silently_truncated(project):
    (project / "AGENTS.md").write_text("x" * 32001)
    with pytest.raises(WorkspaceError, match="32.000"):
        guides(Workspace(project))


def test_guidance_changed_during_permission_blocks_write(project):
    guide = project / "AGENTS.md"
    guide.write_text("old rule")
    target = project / "a"
    target.write_text("old")
    ui = FakeUI()
    tools = Tools(Workspace(project), ui)
    tools.read_file("a")
    def permit(**kwargs):
        guide.write_text("new rule")
        return "y"
    ui.ask_permission = permit
    with pytest.raises(WorkspaceError, match="Hướng dẫn"):
        tools.edit_file("a", "old", "new")
    assert target.read_text() == "old"


def test_session_permission_exact_command_timeout_and_revocation(project, monkeypatch):
    executed = []
    def run(command, root, timeout, **kwargs):
        executed.append((command, root, timeout))
        return {"exit_code": 0, "output": "ok", "seconds": 0}
    monkeypatch.setattr("peto_agent.runner.run", run)
    ui = FakeUI(["s", "n", "n", "n"])
    work = Session(Client(), Workspace(project), ui)
    tools = work.tools
    tools.run_command("npm test")
    tools.reset_task()
    tools.run_command("npm test")
    assert "error" in tools.run_command("npm test && echo other")
    assert "error" in tools.run_command("npm test", 121)
    work.permissions(clear=True)
    assert "error" in tools.run_command("npm test")
    assert len(executed) == 2
    tools.command_grants.add((str(project), "x", 120))
    work.reset()
    assert not tools.command_grants


def test_three_failed_commands_stop_execution_and_further_edits(project, monkeypatch):
    executed = []
    def run(*args, **kwargs):
        executed.append(args)
        return {"exit_code": 1, "output": "failed", "seconds": 0}
    monkeypatch.setattr("peto_agent.runner.run", run)
    tools = Tools(Workspace(project), FakeUI(["a"]))
    for _ in range(3):
        tools.run_command("npm test")
    assert "3 lần kiểm tra" in tools.run_command("npm test")["error"]
    assert "error" in tools.call("write_file", '{"path":"a","content":"x"}')
    assert len(executed) == 3 and not (project / "a").exists()


def test_verification_followup_is_bounded_and_honors_refusal(project):
    client = Client([
        [call(1, "write_file", path="a", content="new")],
        [message("done")],
        [call(2, "run_command", command="npm test")],
        [message("check refused; not verified")],
    ])
    ui = FakeUI(["y", "n"])
    work = Session(client, Workspace(project), ui)
    work.run_task("create a")
    assert len(client.bodies) == 4
    assert "Kiểm tra sau sửa" in client.bodies[2]["input"][-1]["content"]
    assert not work.tools.commands
    assert "không đồng ý" in client.bodies[3]["input"][-1]["output"]


def test_retry_keeps_checkpoint_and_counters_without_replaying_tools(project):
    client = Client([
        [call(1, "write_file", path="a", content="new")], ApiError(0, "lost"),
        [message("done")], [message("No check applies to this text file")],
    ])
    work = Session(client, Workspace(project), FakeUI(["y"]))
    work.run_task("create")
    assert work.can_retry
    checkpoint = work.tools.checkpoint
    work.retry_task()
    assert work.tools.checkpoint is checkpoint
    assert work.tools.revision == 1
    assert len(checkpoint.files) == 1
    assert sum(i.get("type") == "function_call_output" for i in work.items) == 1
    assert checkpoint.undo() == ["a"]


def long_history():
    return [user_message("original goal and constraints " * 30)] + [message("step result " * 40) for _ in range(40)]


def test_compaction_preserves_tool_pairs():
    items = [user_message("goal"), message("plan"), call(1, "read_file", path="a"),
             call(2, "read_file", path="b"),
             {"type": "function_call_output", "call_id": "1", "output": "a"},
             {"type": "function_call_output", "call_id": "2", "output": "b"}, message("done")]
    prefix, tail = compact_prefix(items, keep=2)
    assert not prefix, "must not split a parallel call batch"
    prefix, tail = compact_prefix(items, keep=1)
    assert len(prefix) == 6 and tail == items[6:]


def test_compaction_success_persists_tail_and_clears_stale_reads(project):
    client = Client([[message("Goal: original. Decisions: retained. Tests: passed. Pending: next step.")]])
    work = Session(client, Workspace(project), FakeUI())
    work.items = long_history()
    tail = copy.deepcopy(work.items[-24:])
    work.ws.read_digests[project / "a"] = "stale"
    work.can_retry = True
    assert work.compact()
    assert work.items[-24:] == tail
    assert "original goal" in work.items[1]["content"]
    assert not work.ws.read_digests and work.can_retry
    assert history.load(project, client.server).items == work.items
    assert client.bodies[0]["context"] == {"purpose": "compact"}


@pytest.mark.parametrize("reply", [ApiError(0, "lost"), KeyboardInterrupt(), [],
                                  [call(1, "run_command", command="bad")], [message("x" * 24001)],
                                  [{"type": "message", "role": "assistant", "content": None}]])
def test_failed_compaction_leaves_original_untouched(project, reply):
    work = Session(Client([reply]), Workspace(project), FakeUI())
    work.items = long_history()
    original = copy.deepcopy(work.items)
    assert not work.compact()
    assert work.items == original


def test_undo_disk_failure_keeps_original_and_checkpoint(project, monkeypatch):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    (project / "a").write_text("original")
    tools.read_file("a")
    tools.edit_file("a", "original", "updated")
    def fail(*args):
        raise OSError("disk denied")
    monkeypatch.setattr("peto_agent.checkpoint.os.replace", fail)
    with pytest.raises(OSError, match="disk denied"):
        tools.checkpoint.undo()
    assert (project / "a").read_text() == "updated"
    assert "a" in tools.checkpoint.files
    assert not list(project.glob(".peto-undo-*"))


def test_undo_rejects_redirected_paths(project, monkeypatch):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "updated")
    (project / "b").write_text("updated")
    monkeypatch.setattr(tools.ws, "resolve", lambda *args, **kwargs: project / "b")
    with pytest.raises(WorkspaceError, match="không hoàn tác"):
        tools.checkpoint.undo()
    assert (project / "a").exists() and (project / "b").exists()


def test_auto_compaction_cancel_stops_before_work_step(project):
    client = Client([KeyboardInterrupt()])
    work = Session(client, Workspace(project), FakeUI())
    work.items = [message("old " * 50) for _ in range(180)]
    work.run_task("continue")
    assert len(client.bodies) == 1
    assert client.bodies[0]["context"]["purpose"] == "compact"
    assert "Đã dừng yêu cầu" in work.ui.text


def test_old_server_cannot_replace_history_with_normal_answer(project):
    class OldClient(Client):
        def stream(self, *args, **kwargs):
            yield {"type": "done", "output": [message("normal answer") ]}
    work = Session(OldClient(), Workspace(project), FakeUI())
    work.items = long_history()
    original = copy.deepcopy(work.items)
    assert not work.compact()
    assert work.items == original
    assert "Cập nhật VPS" in work.ui.text


def test_long_guidance_is_not_truncated_in_tool_results(project):
    from peto_agent.loop import cap_result
    (project / "AGENTS.md").write_text("x" * 31000)
    tools = Tools(Workspace(project), FakeUI())
    result = tools.call("write_file", '{"path":"new","content":"x"}')
    assert len(cap_result(result)["project_guidance"][0]["text"]) == 31000
    assert not (project / "new").exists()
