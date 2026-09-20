"""Danh sách việc của yêu cầu dài, và lệnh chạy nền."""

from __future__ import annotations

import json
import sys
import time

import pytest
from conftest import FakeUI

from peto_agent import background
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def tools_for(project, answers=()):
    return Tools(Workspace(project), FakeUI(answers))


def steps(*items):
    return [{"title": title, "status": status} for title, status in items]


def test_plan_shows_where_peto_is(project):
    tools = tools_for(project)
    result = tools.call("update_plan", args(steps=steps(("Đọc code", "done"), ("Sửa lỗi", "running"),
                                                        ("Chạy test", "pending"))))
    assert result == {"ok": True, "steps": 3, "left": 2}
    assert "☑ Đọc code" in tools.ui.text and "▶ Sửa lỗi" in tools.ui.text and "☐ Chạy test" in tools.ui.text


def test_plan_rejects_junk_and_overlong_lists(project):
    tools = tools_for(project)
    assert "tối đa 10 mục" in tools.call("update_plan", args(steps=steps(*[(f"v{i}", "pending") for i in range(11)])))["error"]
    assert "pending, running hoặc done" in tools.call("update_plan", args(steps=[{"title": "x", "status": "xong"}]))["error"]
    assert "ít nhất một việc" in tools.call("update_plan", args(steps=[]))["error"]
    assert tools.plan == [], "dữ liệu sai thì không thay danh sách đang có"


def test_plan_is_forgotten_when_a_new_request_starts(project):
    tools = tools_for(project)
    tools.call("update_plan", args(steps=steps(("Việc", "pending"))))
    tools.reset_task()
    assert tools.plan == []


SCRIPT = ("import sys, time\n"
          "print('da chay', flush=True)\n"
          "time.sleep(30)\n")


def start_script(tools, project, name="nen.py"):
    (project / name).write_text(SCRIPT, encoding="utf-8")
    return tools.call("start_command", args(command=f'"{sys.executable}" {name}', shell=None))


def test_background_command_keeps_running_and_can_be_read_then_stopped(project):
    tools = tools_for(project, ["y"])
    started = start_script(tools, project)
    assert started["ok"] is True and started["id"] == "1"

    read = tools.call("read_command_output", args(job_id="1", wait_seconds=10))
    assert "da chay" in read["output"] and read["running"] is True and read["exit_code"] is None
    assert tools.call("read_command_output", args(job_id="1", wait_seconds=0))["output"] == "", "không đọc lại phần cũ"

    stopped = tools.call("stop_command", args(job_id="1"))
    assert stopped["running"] is False
    assert not tools.jobs.running()
    assert "Đã dừng lệnh nền #1" in tools.ui.text


def test_reading_waits_for_output_instead_of_returning_empty(project):
    tools = tools_for(project, ["y"])
    (project / "cho.py").write_text("import time\ntime.sleep(0.6)\nprint('xong', flush=True)\n", encoding="utf-8")
    tools.call("start_command", args(command=f'"{sys.executable}" cho.py', shell=None))
    try:
        started = time.monotonic()
        read = tools.call("read_command_output", args(job_id="1", wait_seconds=10))
        assert "xong" in read["output"]
        assert time.monotonic() - started < 9, "chờ tới lúc có output rồi trả ngay, không đợi hết wait_seconds"
    finally:
        tools.jobs.stop_all()


def test_unknown_job_and_too_many_jobs_are_refused(project):
    tools = tools_for(project, ["a"])
    assert "Không có lệnh nền #9" in tools.call("read_command_output", args(job_id="9", wait_seconds=0))["error"]
    try:
        for index in range(background.MAX_JOBS):
            assert start_script(tools, project, f"nen{index}.py")["ok"] is True
        assert "Đang có 3 lệnh nền" in start_script(tools, project, "nua.py")["error"]
    finally:
        tools.jobs.stop_all()


def test_refusing_a_background_command_starts_nothing(project):
    tools = tools_for(project, ["n"])
    assert "không đồng ý" in start_script(tools, project)["error"]
    assert not tools.jobs.jobs


def test_closing_the_session_stops_every_background_command(project):
    tools = tools_for(project, ["a"])
    try:
        start_script(tools, project, "mot.py")
        start_script(tools, project, "hai.py")
        assert len(tools.jobs.running()) == 2
        stopped = tools.jobs.stop_all()
        assert len(stopped) == 2 and not tools.jobs.running()
    finally:
        tools.jobs.stop_all()


@pytest.mark.parametrize("wait", [None, 0, 99])
def test_wait_seconds_is_clamped(project, wait):
    tools = tools_for(project, ["y"])
    (project / "nhanh.py").write_text("print('ok', flush=True)\n", encoding="utf-8")
    tools.call("start_command", args(command=f'"{sys.executable}" nhanh.py', shell=None))
    started = time.monotonic()
    tools.call("read_command_output", args(job_id="1", wait_seconds=wait))
    assert time.monotonic() - started < background.MAX_WAIT_SECONDS
