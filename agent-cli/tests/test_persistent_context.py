import codecs
import copy
import json
import os
import time
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FakeUI

from peto_agent import checkpoint_store
from peto_agent.checkpoint import Checkpoint
from peto_agent.context import efficient_input
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace, WorkspaceError


def test_checkpoint_survives_new_instance_and_undo_is_not_repeated(project):
    original = codecs.BOM_UTF8 + b"old\r\n"
    (project / "a").write_bytes(original)
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.read_file("a")
    tools.edit_file("a", "old", "new")
    tools.write_file("b", "created")
    restored = Checkpoint.restore(Workspace(project))
    assert restored.files["a"].before == original
    assert restored.undo() == ["a", "b"]
    assert (project / "a").read_bytes() == original
    assert not (project / "b").exists()
    assert not Checkpoint.restore(Workspace(project)).files


def test_restored_checkpoint_does_not_overwrite_user_edits(project):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "peto")
    (project / "a").write_text("user")
    with pytest.raises(WorkspaceError, match="không hoàn tác"):
        Checkpoint.restore(Workspace(project)).undo()
    assert (project / "a").read_text() == "user"


def test_failed_checkpoint_save_blocks_file_change(project, monkeypatch):
    (project / "a").write_text("old")
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.read_file("a")
    def fail(*args):
        raise OSError("full disk")
    monkeypatch.setattr(checkpoint_store, "save", fail)
    result = tools.call("edit_file", '{"path":"a","old_text":"old","new_text":"new"}')
    assert "error" in result
    assert (project / "a").read_text() == "old"
    assert not tools.checkpoint.files


def test_checkpoint_limit_blocks_next_write_without_losing_previous(project, monkeypatch):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "first")
    monkeypatch.setattr(checkpoint_store, "MAX_BYTES", 400)
    with pytest.raises(WorkspaceError, match="16 MB"):
        tools.write_file("b", "x" * 500)
    assert not (project / "b").exists()
    assert set(Checkpoint.restore(Workspace(project)).files) == {"a"}


@pytest.mark.parametrize("files", [{"../outside": {"before": None, "after": "eA=="}},
                                  {".env": {"before": None, "after": "eA=="}},
                                  {"a": {"before": None, "after": "!invalid"}},
                                  [], {"a": {"before": None, "after": "//4="}}])
def test_malformed_checkpoint_cannot_restore_files(project, files):
    checkpoint_store.save(project, files, False)
    with pytest.raises(WorkspaceError):
        Checkpoint.restore(Workspace(project))
    assert list(project.iterdir()) == []


def test_expiry_and_global_budget(project, tmp_path, monkeypatch):
    checkpoint_store.save(project, {}, False)
    old = checkpoint_store.path_for(project)
    os.utime(old, (time.time() - checkpoint_store.MAX_AGE - 10,) * 2)
    assert checkpoint_store.load(project) is None
    assert not old.exists()
    other = tmp_path / "other"
    other.mkdir()
    checkpoint_store.save(project, {}, False)
    os.utime(old, (time.time() - 100,) * 2)
    monkeypatch.setattr(checkpoint_store, "MAX_TOTAL_BYTES", 300)
    checkpoint_store.save(other, {"padding": "x" * 100}, False)
    assert not old.exists()
    assert checkpoint_store.path_for(other).exists()


def pair(identifier, name, value):
    return [{"type": "function_call", "call_id": identifier, "name": name, "arguments": "{}"},
            {"type": "function_call_output", "call_id": identifier, "output": json.dumps(value)}]


def test_repeated_read_keeps_latest_full_content_and_original_history():
    value = {"path": "a", "start_line": 1, "end_line": 10, "content": "original " * 100,
             "project_guidance": []}
    items = pair("first", "read_file", value) + pair("second", "read_file", value)
    original = copy.deepcopy(items)
    output = efficient_input(items)
    assert items == original
    assert json.loads(output[1]["output"])["content_reference"] == "second"
    assert json.loads(output[3]["output"])["content"] == value["content"]
    assert len(json.dumps(output)) < len(json.dumps(items))
    assert [i["call_id"] for i in output] == [i["call_id"] for i in items]
    # Both changed content and different ranges must remain available in full.
    for key, change in (("content", "new"), ("start_line", 2), ("project_guidance", ["changed"])):
        changed = {**value, key: change}
        output = efficient_input(pair("first", "read_file", value) + pair("second", "read_file", changed))
        assert "content" in json.loads(output[1]["output"])


def test_old_command_output_shrinks_but_recent_failure_and_metadata_survive():
    result = {"exit_code": 1, "error": "failure", "output": "start" + "x" * 20000 + "end",
              "classification": "check_failed"}
    items = pair("old", "run_command", result)
    for n in range(6):
        items += pair(str(n), "run_command", result)
    output = efficient_input(items)
    old = json.loads(output[1]["output"])
    latest = json.loads(output[-1]["output"])
    assert len(old["output"]) < 4200 and old["output"].startswith("start") and old["output"].endswith("end")
    assert old["exit_code"] == 1 and old["error"] == "failure" and old["classification"] == "check_failed"
    assert latest == result


def test_read_default_page_and_fresh_disk_check(project):
    (project / "a").write_text("\n".join(str(n) for n in range(500)))
    tools = Tools(Workspace(project), FakeUI(["a"]))
    first = tools.read_file("a")
    assert first["end_line"] == 160 and first["next_start_line"] == 161
    assert tools.read_file("a", 161, 500)["end_line"] == 500
    (project / "a").write_text("changed")
    with pytest.raises(WorkspaceError, match="đã thay đổi"):
        tools.edit_file("a", "0", "x")


def test_tiny_read_reference_does_not_increase_payload():
    items = pair("a", "read_file", {"content": "x", "path": "a"}) + pair("b", "read_file", {"content": "x", "path": "a"})
    assert efficient_input(items) == items


def test_checkpoint_can_be_undone_in_separate_process(project):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.write_file("a", "created")
    code = ("import sys; from peto_agent.checkpoint import Checkpoint; from peto_agent.workspace import Workspace; "
            "print(Checkpoint.restore(Workspace(sys.argv[1])).undo())")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, "-c", code, str(project)], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "'a'" in result.stdout and not (project / "a").exists()
    assert not Checkpoint.restore(Workspace(project)).files
