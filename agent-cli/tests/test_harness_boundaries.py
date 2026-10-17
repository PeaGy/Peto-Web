"""Hợp đồng đầu vào, lưu trước thực thi và khôi phục lời gọi bị ngắt."""

import importlib.util
import inspect
import json
import os
from pathlib import Path

import pytest
from conftest import FakeUI

from peto_agent import atomic_file, history
from peto_agent.client import Client
from peto_agent.loop import Session
from peto_agent.session_protocol import INTERRUPTED_RESULT, interrupted_items
from peto_agent.tools import FEATURES, NEW_FEATURES, Tools
from peto_agent.tool_input import argument_error
from peto_agent.workspace import Workspace


@pytest.mark.parametrize("name,values,field", [
    ("read_file", {"path": "a.txt", "start_line": "1"}, "start_line"),
    ("read_file", {"path": "a.txt", "start_line": True}, "start_line"),
    ("run_command", {"command": "echo test", "timeout_seconds": "20"}, "timeout_seconds"),
    ("start_command", {"command": ["echo", "test"]}, "command"),
    ("list_files", {"path": ".", "depth": []}, "depth"),
    ("write_file", {"path": "a.txt", "content": None}, "content"),
    ("apply_patch", {"patch_text": 0}, "patch_text"),
    ("browser_open", {"url": False}, "url"),
    ("ask_user", {"questions": "sai"}, "questions"),
])
def test_wrong_json_types_never_reach_permission_or_execution(project, monkeypatch, name, values, field):
    tools = Tools(Workspace(project), FakeUI())

    def unexpected(*args):
        pytest.fail("Không được chạy hoặc hỏi quyền với đầu vào sai kiểu")

    monkeypatch.setattr(tools.ui, "tool_started", unexpected)
    monkeypatch.setattr(tools.ui, "ask", unexpected)
    result = tools.call(name, json.dumps(values))
    assert result["classification"] == "invalid_arguments" and field in result["error"]
    assert not list(project.iterdir())


def test_nullable_fields_and_unknown_null_keep_wire_compatibility(project):
    (project / "a.txt").write_text("dòng một\n", encoding="utf-8")
    tools = Tools(Workspace(project), FakeUI())
    result = tools.call("read_file", json.dumps({"path": "a.txt", "start_line": None, "end_line": None,
                                                "future_optional": None}))
    assert "dòng một" in result["content"]


def test_patch_obeys_the_same_repair_budget_as_other_writes(project):
    tools = Tools(Workspace(project), FakeUI(["y"]))
    tools.failed_commands = 3
    result = tools.call("apply_patch", json.dumps({"patch_text": "*** Begin Patch\n*** Add File: a.txt\n+x\n*** End Patch"}))
    assert "3 lần kiểm tra" in result["error"] and not (project / "a.txt").exists()


def _work(project, monkeypatch):
    ui = FakeUI(["y", "y"])
    outcomes = []
    ui.request_finished = lambda end: outcomes.append(end.outcome)
    work = Session(Client("https://peto.example", "peto_token_thu"), Workspace(project), ui)
    work.auto_title = False
    calls = [{"type": "function_call", "call_id": f"call_{n}", "name": "write_file",
              "arguments": json.dumps({"path": f"a{n}.txt", "content": "đã ghi"})} for n in (1, 2)]
    monkeypatch.setattr(work, "_step", lambda: calls)
    return work, ui, outcomes


@pytest.mark.parametrize("fail_at", [1, 3])
def test_session_storage_failure_stops_before_the_next_side_effect(project, monkeypatch, fail_at):
    work, ui, outcomes = _work(project, monkeypatch)
    original = history.os.replace
    attempts = []

    def replace(source, target):
        if "sessions" in Path(target).parts:
            attempts.append(str(target))
            if len(attempts) >= fail_at:
                raise OSError("Hết dung lượng giả lập")
        return original(source, target)

    monkeypatch.setattr(history.os, "replace", replace)
    work.run_task("Tạo hai tệp")
    assert outcomes == ["error"] and "Không lưu được" in ui.text
    assert interrupted_items(work.items)[1] == 0, "Yêu cầu tiếp theo trong cùng cửa sổ cũng cần hội thoại hợp lệ"
    assert (project / "a1.txt").exists() is (fail_at == 3)
    assert not (project / "a2.txt").exists()
    if fail_at == 3:
        saved = history.load(project, work.client.server)
        assert saved.interrupted
        assert any(json.loads(x["output"]) == INTERRUPTED_RESULT for x in saved.items
                   if x.get("type") == "function_call_output")


def test_final_reply_save_failure_is_not_reported_as_done(project, monkeypatch):
    work, ui, outcomes = _work(project, monkeypatch)
    monkeypatch.setattr(work, "_step", lambda: [{"type": "message", "role": "assistant", "content": "Trả lời"}])
    original = history.save
    saves = []

    def save(*args, **kwargs):
        saves.append(None)
        return original(*args, **kwargs) if len(saves) == 1 else False

    monkeypatch.setattr(history, "save", save)
    work.run_task("Hỏi một câu")
    assert outcomes == ["error"] and "Không lưu được hội thoại" in ui.text


def test_prompt_is_saved_before_the_first_model_step(project, monkeypatch):
    work, ui, outcomes = _work(project, monkeypatch)
    seen = []

    def model_step():
        saved = history.load(project, work.client.server)
        seen.append(saved)
        assert saved.interrupted and saved.items[-1]["content"] == "Yêu cầu phải còn khi đóng cửa sổ"
        return [{"type": "message", "role": "assistant", "content": "Đã đọc yêu cầu"}]

    monkeypatch.setattr(work, "_step", model_step)
    work.run_task("Yêu cầu phải còn khi đóng cửa sổ")
    assert len(seen) == 1 and outcomes == ["done"]


def test_old_crashed_session_is_reconciled_in_memory_without_replay_or_rewrite(project):
    items = [{"type": "message", "role": "user", "content": "Giữ nguyên logic"},
             {"type": "function_call", "call_id": "old", "name": "write_file", "arguments": "{}"}]
    assert history.save(project, "https://peto.example", items, session_id="cu", retryable=True)
    path = history._folder(project) / "cu.json"
    original = path.read_bytes()
    saved = history.load(project, "https://peto.example")
    assert saved.interrupted and not saved.retryable
    assert saved.items[:-1] == items
    assert json.loads(saved.items[-1]["output"]) == INTERRUPTED_RESULT
    assert path.read_bytes() == original and not list(project.iterdir())


def test_reused_call_id_does_not_hide_a_new_unanswered_call():
    first = {"type": "function_call", "call_id": "same", "name": "read_file"}
    answered = {"type": "function_call_output", "call_id": "same", "output": '{"ok":true}'}
    second = {"type": "function_call", "call_id": "same", "name": "write_file"}
    items = [first, answered, second]
    recovered, count = interrupted_items(items)
    assert count == 1 and len(recovered) == 4 and len(items) == 3
    assert json.loads(recovered[-1]["output"]) == INTERRUPTED_RESULT
    again, count = interrupted_items(recovered)
    assert count == 0 and again == recovered


def test_failed_legacy_migration_preserves_the_original_session(project, monkeypatch):
    path = history._legacy_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": history.LEGACY_VERSION, "root": str(project), "server": "https://peto.example",
            "saved_at": 1, "items": [{"type": "message", "role": "user", "content": "Nội dung gốc"}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(history.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("Hết dung lượng")))
    history._migrate(project, data["server"])
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Lỗi chia sẻ tệp trên Windows")
def test_transient_windows_replace_failure_retries_only_the_save(project, monkeypatch):
    path = project / "session.json"
    path.write_text("cũ", encoding="utf-8")
    original = atomic_file.os.replace
    attempts = []

    def replace(source, target):
        attempts.append(str(source))
        if len(attempts) <= 2:
            error = PermissionError("Tệp tạm thời bận")
            error.winerror = 32
            raise error
        return original(source, target)

    monkeypatch.setattr(atomic_file.os, "replace", replace)
    atomic_file.write_text(path, "mới")
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert path.read_text(encoding="utf-8") == "mới" and not list(project.glob("*.tmp"))


def test_permanent_save_error_keeps_the_original_and_cleans_its_temp_file(project, monkeypatch):
    path = project / "session.json"
    path.write_text("cũ", encoding="utf-8")
    attempts = []

    def replace(*args):
        attempts.append(None)
        raise OSError("Hết dung lượng")

    monkeypatch.setattr(atomic_file.os, "replace", replace)
    with pytest.raises(OSError):
        atomic_file.write_text(path, "mới")
    assert len(attempts) == 1 and path.read_text(encoding="utf-8") == "cũ"
    assert not list(project.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Lỗi chia sẻ tệp trên Windows")
def test_windows_replace_retries_are_bounded(project, monkeypatch):
    attempts = []

    def replace(*args):
        attempts.append(None)
        error = PermissionError("Quyền ghi vẫn bị từ chối")
        error.winerror = 5
        raise error

    monkeypatch.setattr(atomic_file.os, "replace", replace)
    with pytest.raises(PermissionError):
        atomic_file.write_text(project / "session.json", "mới")
    assert len(attempts) == len(atomic_file.REPLACE_DELAYS) + 1
    assert not list(project.iterdir())


@pytest.mark.parametrize("patch_model", [False, True])
@pytest.mark.parametrize("features", [frozenset(), frozenset(FEATURES), frozenset((*FEATURES, *NEW_FEATURES))])
def test_backend_advertises_only_tools_and_parameters_this_cli_can_execute(project, patch_model, features):
    path = Path(__file__).resolve().parents[2] / "backend/features/agent/tools.py"
    spec = importlib.util.spec_from_file_location("peto_backend_tool_contract", path)
    backend_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend_tools)
    tools = Tools(Workspace(project), FakeUI())
    for schema in backend_tools.tool_schemas(features, patch_model=patch_model):
        name = schema["name"]
        assert name in tools._handlers, name
        signature = inspect.signature(tools._handlers[name])
        properties = schema["parameters"]["properties"]
        assert set(properties) <= set(signature.parameters), name
        required = {key for key, value in signature.parameters.items()
                    if value.default is inspect.Parameter.empty}
        assert required <= set(properties), name
        examples = {"string": "x", "integer": 1, "boolean": True, "array": [], "object": {}, "null": None}
        for parameter, shape in properties.items():
            kinds = shape["type"] if isinstance(shape["type"], list) else [shape["type"]]
            for kind in kinds:
                assert argument_error(tools._handlers[name], {parameter: examples[kind]}) is None, (name, parameter, kind)
