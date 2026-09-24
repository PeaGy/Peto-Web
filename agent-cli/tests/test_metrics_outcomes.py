import copy
import json

import pytest
from conftest import FakeUI

from peto_agent.client import ApiError
from peto_agent.command_outcome import classify, command_kind, local_probe
from peto_agent.loop import Session, user_message
from peto_agent.metrics import Metrics
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


@pytest.mark.parametrize("command,code,output,expected", [
    ('rg "missing" .', 1, "", "no_match"),
    ('grep needle file', 1, "", "no_match"),
    ('rg needle .', 2, "bad pattern", "unknown_failure"),
    ('rg needle . && npm test', 1, "", "unknown_failure"),
    ('npm test', 1, "assertion failed", "check_failed"),
    ('python -m pytest', 1, "1 failed", "check_failed"),
    ('pytest', 5, "no tests ran", "no_tests"),
    ('pytest', 4, "invalid args", "execution_error"),
    ('npm test', 1, "npm error Missing script: test", "environment_error"),
    ('python -m pytest', 1, "No module named pytest", "environment_error"),
    ('custom-check', 1, "failed", "unknown_failure"),
    ('npm test', 0, "ok", "passed"),
    ('echo ok', 0, "ok", "success"),
    ('pytest --version', 0, "pytest 9", "success"),
])
def test_classification(command, code, output, expected):
    assert classify(command, {"exit_code": code, "output": output}) == expected
    assert classify(command, {"exit_code": code, "output": output, "error": "timeout"}) == "execution_error"


@pytest.mark.parametrize("command,probe", [
    ("curl -s http://localhost:5080/api/monhoc/99", True),
    ('curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/ && curl.exe http://localhost:8000/x', True),
    ("Invoke-WebRequest -Uri http://localhost:5080/api -UseBasicParsing", True),
    ("$r = Invoke-RestMethod -Method Post -Uri http://[::1]:5080/api/monhoc", True),
    ("curl -s https://example.com/", False),
    ("python -m http.server 8765", False),
    ("npm test", False),
    ("echo http://localhost:5080", False),
])
def test_local_probe_means_calling_a_server_on_this_machine(command, probe):
    assert local_probe(command) is probe


def test_search_and_environment_errors_do_not_spend_repair_budget(project, monkeypatch):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    response = {"exit_code": 1, "output": "", "seconds": 0}
    monkeypatch.setattr("peto_agent.runner.run", lambda *args, **kwargs: dict(response))
    for _ in range(5):
        assert tools.run_command('rg "missing" .')["classification"] == "no_match"
    response["output"] = "No module named pytest"
    for _ in range(3):
        tools.run_command("python -m pytest")
    assert "error" in tools.run_command("python -m pytest")
    assert tools.failed_commands == 0 and tools.checked_revision == -1
    assert tools.call("write_file", json.dumps({"path": "a", "content": "fixed"}))["ok"]
    response["output"] = "1 failed"
    for _ in range(3):
        tools.run_command("npm test")
    assert tools.failed_commands == 3
    assert "error" in tools.run_command("npm run lint")
    response.update(exit_code=0, output="info")
    assert tools.run_command("python --version")["classification"] == "success"


def test_metrics_exclude_nested_permission_and_command_time(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("peto_agent.metrics.time.monotonic", lambda: now[0])
    metrics = Metrics()
    with metrics.measure("tools"):
        now[0] = 1
        with metrics.measure("permission"):
            now[0] = 6
        with metrics.measure("commands"):
            now[0] = 9
        now[0] = 10
    assert metrics.seconds["tools"] == 2
    assert metrics.seconds["permission"] == 5
    assert metrics.seconds["commands"] == 3
    with pytest.raises(KeyboardInterrupt):
        with metrics.measure("model"):
            now[0] = 12
            raise KeyboardInterrupt()
    assert metrics.seconds["model"] == 2 and not metrics._stack


def test_usage_validation_and_missing_reports():
    metrics = Metrics()
    for usage in (None, {}, {"input_tokens": True, "output_tokens": 2},
                  {"input_tokens": -1, "output_tokens": 1}):
        metrics.record_usage("model", usage)
    assert metrics.usage["model"]["reported"] == 0
    metrics.record_usage("model", {"input_tokens": 0, "output_tokens": 0})
    metrics.record_usage("compact", {"input_tokens": 100, "output_tokens": 10})
    assert metrics.usage["model"]["reported"] == 1
    assert metrics.usage["compact"]["input_tokens"] == 100


class Client:
    server = "https://example.test"

    def __init__(self, events):
        self.events = list(events)

    def stream(self, *args, **kwargs):
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        yield event


def done(usage=None, **extra):
    return {"type": "done", "output": [{"type": "message", "role": "assistant", "content": "summary"}],
            "usage": usage, **extra}


def test_task_retry_metrics_accumulate_and_new_task_resets(project):
    client = Client([ApiError(0, "lost"), done({"input_tokens": 100, "output_tokens": 20}), done()])
    work = Session(client, Workspace(project), FakeUI())
    work.run_task("task")
    assert work.metrics.calls["model"] == 1
    work.retry_task()
    assert work.metrics.calls["model"] == 2
    assert work.metrics.usage["model"] == {"input_tokens": 100, "output_tokens": 20, "reported": 1}
    # Cuối yêu cầu không in chi tiết nữa; /usage mới in, đúng như số đo đã cộng dồn.
    assert "thiếu số liệu" not in work.ui.text
    work.show_metrics()
    assert "thiếu số liệu 1 lượt" in work.ui.text
    work.run_task("next")
    assert work.metrics.calls["model"] == 1
    assert work.metrics.usage["model"]["reported"] == 0
    work.resume([user_message("old")], retryable=True)
    assert work.metrics.calls["model"] == 0


def test_automatic_compaction_metrics_are_separate_from_work(project):
    client = Client([done({"input_tokens": 500, "output_tokens": 30}, purpose="compact"),
                     done({"input_tokens": 100, "output_tokens": 10})])
    work = Session(client, Workspace(project), FakeUI())
    work.items = [user_message("history " * 30) for _ in range(180)]
    work.run_task("continue")
    assert work.metrics.calls == {"model": 1, "compact": 1}
    assert work.metrics.usage["compact"]["input_tokens"] == 500
    snapshot = copy.deepcopy(work.metrics.snapshot())
    # A manual compaction must not silently add to the previous task's totals.
    work.items = [user_message("history " * 30) for _ in range(40)]
    client.events.append(done({"input_tokens": 300, "output_tokens": 20}, purpose="compact"))
    assert work.compact()
    assert work.metrics.snapshot() == snapshot
