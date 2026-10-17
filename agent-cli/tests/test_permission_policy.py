"""Mặc định tự làm, quyền hỏi/chặn bền qua phiên và không bị quyền cũ vượt qua."""

import json
from types import SimpleNamespace

import pytest
from conftest import FakeUI

from peto_agent import approvals
from peto_agent.client import Client
from peto_agent.loop import Session
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


def invoke(tools, name, **values):
    return tools.call(name, json.dumps(values))


@pytest.fixture
def runs(monkeypatch):
    calls = []
    def run(command, directory, timeout, **kwargs):
        calls.append(command)
        return {"exit_code": 0, "output": "ok", "seconds": 0}
    monkeypatch.setattr("peto_agent.runner.run", run)
    return calls


def test_default_runs_distinct_commands_across_tasks_without_prompting(project, runs):
    tools = Tools(Workspace(project), FakeUI())
    for index in range(6):
        if index == 3:
            tools.reset_task()
        assert tools.run_command(f"echo thu-{index}")["exit_code"] == 0
    assert len(runs) == 6 and not tools.approve_all and not tools.command_grants


def test_default_file_operations_keep_read_and_undo_contracts(project):
    tools = Tools(Workspace(project), FakeUI())
    assert tools.write_file("a.txt", "cu\n")["ok"]
    assert tools.edit_file("a.txt", "cu", "moi")["ok"]
    assert tools.move_file("a.txt", "b.txt")["ok"]
    assert (project / "b.txt").read_text() == "moi\n"
    assert tools.delete_file("b.txt")["ok"]
    assert not (project / "b.txt").exists()
    (project / "unread.txt").write_text("cu\n")
    result = invoke(tools, "edit_file", path="unread.txt", old_text="cu", new_text="moi")
    assert "chưa được đọc" in result["error"] and (project / "unread.txt").read_text() == "cu\n"


def test_default_background_command_does_not_wait_for_permission(project, monkeypatch):
    tools = Tools(Workspace(project), FakeUI())
    calls = []
    def start(command, cwd, shell, **kwargs):
        calls.append(command)
        return SimpleNamespace(id="1")
    monkeypatch.setattr(tools.jobs, "start", start)
    assert tools.start_command("echo nen")["ok"] and calls == ["echo nen"]


def test_ask_is_saved_per_project_and_legacy_grants_preserve_the_policy(project, tmp_path, runs):
    assert approvals.set_policy(project, "ask", "shell")
    tools = Tools(Workspace(project), FakeUI(["l"]))
    assert tools.run_command("echo da-nho")["exit_code"] == 0
    later = Tools(Workspace(project), FakeUI())
    assert later.run_command("echo da-nho")["exit_code"] == 0
    assert "không đồng ý" in later.run_command("echo khac")["error"]
    assert approvals.policy(project, "shell") == "ask"
    assert approvals.policy(project, "edit") == "allow"
    other = tmp_path / "other"
    other.mkdir()
    assert Tools(Workspace(other), FakeUI()).run_command("echo khac")["exit_code"] == 0
    assert runs == ["echo da-nho", "echo da-nho", "echo khac"]


def test_deny_beats_all_old_command_grants_and_approve_all(project, runs, monkeypatch):
    assert approvals.add(project, ".", "echo blocked", "cmd")
    assert approvals.set_policy(project, "deny", "shell")
    tools = Tools(Workspace(project), FakeUI(["y"]))
    tools.approve_all = True
    tools.command_grants.add((str(project), "echo blocked", 120, "cmd"))
    monkeypatch.setattr(tools.jobs, "start", lambda *a, **kw: pytest.fail("Không được tạo tiến trình"))
    for result in (invoke(tools, "run_command", command="echo blocked"),
                   invoke(tools, "start_command", command="echo blocked")):
        assert "/permissions shell deny" in result["error"]
    assert runs == [] and tools.ui.answers == ["y"]


def test_edit_deny_blocks_patch_and_moves_without_partial_changes(project):
    assert approvals.set_policy(project, "deny", "edit")
    (project / "a.txt").write_text("cu\n")
    tools = Tools(Workspace(project), FakeUI(["y"]))
    tools.approve_all = True
    tools.read_file("a.txt")
    patch = "*** Begin Patch\n*** Update File: a.txt\n@@\n-cu\n+moi\n*** Add File: b.txt\n+them\n*** End Patch"
    for result in (invoke(tools, "edit_file", path="a.txt", old_text="cu", new_text="moi"),
                   invoke(tools, "write_file", path="b.txt", content="them"),
                   invoke(tools, "delete_file", path="a.txt"),
                   invoke(tools, "move_file", path="a.txt", new_path="b.txt"),
                   invoke(tools, "apply_patch", patch_text=patch)):
        assert "/permissions edit deny" in result["error"]
    assert (project / "a.txt").read_text() == "cu\n" and not (project / "b.txt").exists()
    assert tools.ui.answers == ["y"]


def test_plan_commands_still_ask_even_under_default_allow(project, runs):
    tools = Tools(Workspace(project), FakeUI())
    tools.ui.mode = "plan"
    assert "không đồng ý" in tools.run_command("echo plan")["error"] and not runs


def test_supervised_tools_keep_policy_review_across_requests(project, runs):
    tools = Tools(Workspace(project), FakeUI())
    tools.require_approval = True
    assert "không đồng ý" in tools.run_command("echo supervised")["error"]
    tools.reset_task()
    assert "không đồng ý" in tools.write_file("a.txt", "no")["error"]
    assert not runs and not (project / "a.txt").exists()


def test_clear_can_remove_invalid_project_policy(project, agent_home):
    agent_home.mkdir(parents=True)
    (agent_home / "permissions.json").write_text(json.dumps({
        "version": 1, "projects": {}, "policies": {approvals._key(project): None}}))
    assert approvals.policy(project, "shell") == "ask"
    approvals.clear(project)
    assert approvals.policy(project, "shell") == "allow"


def test_cli_policy_commands_persist_and_clear_explains_default(project, tmp_path, agent_home):
    other = tmp_path / "other"
    other.mkdir()
    assert approvals.set_policy(other, "deny")
    work = Session(Client("http://127.0.0.1:9", "peto_test"), Workspace(project), FakeUI())
    work.permissions(value="ask")
    assert all(approvals.policy(project, action) == "ask" for action in approvals.POLICY_ACTIONS)
    work.permissions(value="shell allow")
    work.permissions(value="edit deny")
    assert approvals.policy(project, "shell") == "allow" and approvals.policy(project, "edit") == "deny"
    work.permissions()
    assert "Chạy lệnh: tự thực hiện (allow)" in work.ui.text and "Thay đổi tệp: chặn (deny)" in work.ui.text
    work.permissions(value="shell * allow")
    assert approvals.policy(project, "edit") == "deny", "Cú pháp sai không đổi quyền"
    work.permissions(value="clear")
    assert approvals.policy(project, "edit") == "allow" and approvals.policy(other, "edit") == "deny"
    assert "Đã về mặc định: tự chạy lệnh" in work.ui.text
    assert (agent_home / "permissions.json").exists() and not (project / "permissions.json").exists()


@pytest.mark.parametrize("data", ["{broken", '{"version":1,"projects":{},"policies":[]}',
                                  '{"version":9,"projects":{}}'])
def test_unreadable_policy_never_silently_auto_allows_or_overwrites(project, agent_home, data, runs):
    agent_home.mkdir(parents=True)
    path = agent_home / "permissions.json"
    path.write_text(data)
    assert approvals.policy(project, "shell") == "ask"
    assert not approvals.set_policy(project, "allow")
    assert not approvals.add(project, ".", "echo no", "cmd")
    assert "không đồng ý" in Tools(Workspace(project), FakeUI()).run_command("echo no")["error"]
    assert path.read_text() == data and runs == []


def test_repo_cannot_override_user_policy(project, runs):
    assert approvals.set_policy(project, "deny")
    shipped = {"version": 1, "projects": {}, "policies": {str(project): {"shell": "allow", "edit": "allow"}}}
    (project / "permissions.json").write_text(json.dumps(shipped))
    assert "/permissions shell deny" in invoke(Tools(Workspace(project), FakeUI()), "run_command", command="echo blocked")["error"]
    assert runs == []


def test_failed_policy_save_keeps_existing_deny_and_reports_failure(project, monkeypatch):
    assert approvals.set_policy(project, "deny")
    monkeypatch.setattr(approvals, "_write_document", lambda data: False)
    work = Session(Client("http://127.0.0.1:9", "peto_test"), Workspace(project), FakeUI())
    work.permissions(value="allow")
    work.permissions(value="clear")
    assert approvals.policy(project, "shell") == "deny"
    assert "Không lưu được" in work.ui.text and "Đã xóa" not in work.ui.text
