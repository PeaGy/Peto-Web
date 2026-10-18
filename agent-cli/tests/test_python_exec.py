"""Mã Python nhiều dòng qua argv thật; giữ quyền, timeout, output và giao diện của lệnh."""
import json
import subprocess
import sys

from conftest import FakeUI

from peto_agent import approvals
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


def invoke(tools, **args):
    return tools.call("run_python", json.dumps(args))


def python_tools(project, ui=None):
    tools = Tools(Workspace(project), ui or FakeUI())
    tools.features = (*tools.features, "python_exec", "output_files")
    return tools


def test_real_multiline_unicode_quotes_and_shell_characters_stay_in_python(project):
    tools = python_tools(project)
    code = 'from pathlib import Path\ntext = "Nhạc mới & echo BAD > injected.txt"\nPath("ok.txt").write_text(text, encoding="utf-8")\nprint(text)'
    result = invoke(tools, code=code)
    assert result["exit_code"] == 0 and "Nhạc mới" in result["output"]
    assert (project / "ok.txt").read_text(encoding="utf-8") == "Nhạc mới & echo BAD > injected.txt"
    assert not (project / "injected.txt").exists()
    assert tools.checkpoint.shell_used


def test_exception_and_nonroot_cwd_are_reported(project):
    tools = python_tools(project)
    (project / "sub").mkdir()
    result = invoke(tools, code='print("before")\nraise ValueError("line two")', cwd="sub")
    assert result["exit_code"] != 0 and result["cwd"] == "sub"
    assert "line 2" in result["output"] and "ValueError" in result["output"]


def test_ask_and_deny_apply_without_losing_argv(project, monkeypatch):
    ui = FakeUI(["n"])
    tools = python_tools(project, ui)
    assert approvals.set_policy(project, "ask", "shell")
    assert invoke(tools, code='print("must not run")')["error"]
    assert "Không chạy Python" in ui.text
    assert approvals.set_policy(project, "deny", "shell")
    tools.approve_all = True
    assert "deny" in invoke(tools, code="print(1)")["error"]


def test_feature_validation_and_unknown_interpreter(project):
    tools = Tools(Workspace(project), FakeUI())
    assert "chưa bật" in invoke(tools, code="print(1)")["error"]
    tools.features = (*tools.features, "python_exec")
    for code in ("", "x" * 12001, "\x00"):
        assert "error" in invoke(tools, code=code)
    assert "kiểu JSON" in invoke(tools, code=42)["error"]
    assert "error" in invoke(tools, code="print(1)", python="python\nBAD")
    assert "trình thông dịch" in invoke(tools, code="print(1)", python="missing-peto-python-exe")["error"]


def test_direct_python_keeps_timeout(project):
    result = invoke(python_tools(project), code="import time\nprint('started', flush=True)\ntime.sleep(30)", timeout_seconds=1)
    assert result["exit_code"] != 0 and result["error"] and "started" in result["output"]


def test_terminal_results_refusal_and_replay_do_not_crash(project):
    from test_tui import make_ui, plain
    ui = make_ui(["n"], colors=False)
    tools = python_tools(project, ui)
    result = invoke(tools, code='print("terminal python")')
    assert result["exit_code"] == 0 and "terminal python" in plain(ui.out.getvalue())
    ui.replay([{"type": "function_call", "call_id": "replay", "name": "run_python", "arguments": '{"code":"print(1)"}'},
               {"type": "function_call_output", "call_id": "replay", "output": json.dumps(result)}])
    assert approvals.set_policy(project, "ask", "shell")
    assert invoke(tools, code="print(2)")["error"]


def test_eval_policy_checks_actual_argv_and_python_source(project):
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "evals"))
    from policy import Policy, PolicyUI
    ui = PolicyUI(Policy(project))
    tools = python_tools(project, ui)
    tools.require_approval = True
    assert invoke(tools, code='print("ok")\nprint("two")')["exit_code"] == 0
    assert invoke(tools, code='import os\nprint(os.environ)')["error"]
    assert [row["answer"] for row in ui.requests] == ["y", "n"]
    argv = [sys.executable, "-c", "print(1)"]
    policy = ui.policy.commands
    assert not policy.decide(subprocess.list2cmdline(argv), project, "python").allowed
    assert not policy.decide("different display", project, "python", argv=argv).allowed
    argv[0] = str(project / "fake-python.exe")
    assert not policy.decide(subprocess.list2cmdline(argv), project, "python", argv=argv).allowed
