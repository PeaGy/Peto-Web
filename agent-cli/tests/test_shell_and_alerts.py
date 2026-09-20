"""Chọn shell cho lệnh, và hai tín hiệu cho người dùng đang làm việc khác: chuông và tiêu đề cửa sổ."""

from __future__ import annotations

import io
import json
import os
import shutil

import pytest
from conftest import FakeUI

from peto_agent import runner
from peto_agent.command_outcome import classify
from peto_agent.tools import Tools
from peto_agent.ui import UI
from peto_agent.workspace import Workspace

powershell_only = pytest.mark.skipif(os.name != "nt" or shutil.which("powershell") is None,
                                     reason="cần powershell.exe trên Windows")


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


@powershell_only
def test_powershell_runs_cmdlets_that_cmd_cannot(project):
    tools = Tools(Workspace(project), FakeUI(["y", "y"]))
    (project / "a.txt").write_text("x\n", encoding="utf-8")

    result = tools.call("run_command", args(command="Get-ChildItem -Name", timeout_seconds=30, shell="powershell"))
    assert result["exit_code"] == 0 and "a.txt" in result["output"]
    assert "PS> Get-ChildItem -Name" in tools.ui.text
    # Quyền ghi nhớ trong phiên gắn với shell, để lệnh giống nhau ở hai shell không dùng chung quyền.
    assert tools.command_grants == set()

    cmd = tools.call("run_command", args(command="Get-ChildItem -Name", timeout_seconds=30, shell=None))
    assert cmd["classification"] == "environment_error", "cmd không biết cmdlet nên phải nhận ra là lỗi môi trường"


def test_unknown_shell_is_refused(project):
    tools = Tools(Workspace(project), FakeUI(["y"]))
    assert "shell chỉ nhận" in tools.call("run_command", args(command="echo hi", timeout_seconds=None, shell="bash"))["error"]


def test_powershell_missing_command_reads_as_an_environment_error():
    output = "khong-co-lenh-nay : The term 'khong-co-lenh-nay' is not recognized as the name of a cmdlet, function…"
    assert classify("khong-co-lenh-nay", {"exit_code": 1, "output": output}) == "environment_error"


@powershell_only
def test_powershell_process_tree_is_killed_on_timeout(project):
    result = runner.run("Start-Sleep -Seconds 30", project, 2, shell="powershell")
    assert "quá 2 giây" in result["error"]


def test_permission_question_rings_the_bell_and_restores_the_title():
    ui = UI(out=io.StringIO(), reader=lambda prompt: "y", colors=True)
    ui.title("Peto · đang làm · duan")
    assert ui.ask_permission() == "y"
    text = ui.out.getvalue()
    assert "\033]0;Peto · cần bạn duyệt\033\\" in text
    assert text.endswith("\033]0;Peto · đang làm · duan\033\\"), "hỏi xong thì tiêu đề về trạng thái cũ"
    assert text.count("\a") == 1, "chuông kêu đúng một tiếng, tiêu đề không được kêu thêm"


def test_bell_can_be_turned_off_but_the_title_still_works(monkeypatch):
    monkeypatch.setenv("PETO_AGENT_NO_BELL", "1")
    ui = UI(out=io.StringIO(), reader=lambda prompt: "n", colors=True)
    ui.ask_permission()
    assert "\a" not in ui.out.getvalue()
    assert "\033]0;Peto · cần bạn duyệt" in ui.out.getvalue()


def test_nothing_is_written_when_the_output_is_not_a_terminal():
    ui = FakeUI(answers=["y"])
    ui.title("Peto · đang làm")
    ui.bell()
    ui.ask_permission()
    assert "\a" not in ui.text and "\033]0;" not in ui.text
