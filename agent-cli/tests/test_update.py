"""/update (CLI 0.22.0, theo /update của opencode): cài bản mới bằng install.ps1 của máy chủ rồi mở lại đúng hội thoại."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeUI
from test_loop_client import peto  # noqa: F401 - fixture máy chủ giả

from peto_agent import __main__ as cli
from peto_agent import __version__, config, history, updater


def newer() -> str:
    major, minor, _ = (int(part) for part in __version__.split("."))
    return f"{major}.{minor + 1}.0"


def test_only_an_install_ps1_copy_updates_itself(tmp_path, monkeypatch):
    monkeypatch.setenv("PETO_AGENT_INSTALL_DIR", str(tmp_path / "PetoAgent"))
    (tmp_path / "PetoAgent" / "venv").mkdir(parents=True)
    assert updater.installed(str(tmp_path / "PetoAgent" / "venv"))
    assert not updater.installed(str(tmp_path / "ma-nguon" / ".venv")), "chạy từ mã nguồn thì không tự cài đè"
    assert updater.launcher() == tmp_path / "PetoAgent" / "bin" / "peto.exe"
    assert updater.restart_argv("20261014-090000-aaaaaa") == [str(updater.launcher()), "--resume",
                                                              "20261014-090000-aaaaaa"]
    assert updater.restart_argv(None) == [str(updater.launcher())]
    monkeypatch.delenv("PETO_AGENT_INSTALL_DIR")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert updater.install_root() == tmp_path / "Local" / "PetoAgent"


def test_the_install_command_is_quoted_for_powershell(monkeypatch):
    prefix = "$env:PETO_AGENT_UPDATING = '1'; "
    assert updater.install_script("https://peto.example/") == prefix + "& { irm 'https://peto.example/install.ps1' | iex }"
    assert updater.install_script("https://o'x.example") == prefix + "& { irm 'https://o''x.example/install.ps1' | iex }"
    calls = []
    monkeypatch.setattr(updater.runner, "run", lambda command, cwd, timeout, **flags: calls.append(
        (command, cwd, timeout, flags["shell"])) or {"exit_code": 0, "seconds": 1.0, "output": ""})
    assert updater.install("https://peto.example")["exit_code"] == 0
    assert calls == [(prefix + "& { irm 'https://peto.example/install.ps1' | iex }", Path.home(),
                      updater.INSTALL_TIMEOUT, "powershell")]


@pytest.fixture
def account(project, peto, monkeypatch):  # noqa: F811
    me = {"account": "Bình", "device_name": "MAY-THU", "steps_used": 1, "steps_limit": 200, "tokens_used": 0,
          "default_effort": "medium", "cli_version": newer()}
    peto.reply = lambda path, body: (200, me)
    config.save({"server": peto.url, "token": "peto_token_thu"})
    monkeypatch.chdir(project)
    restarted = []
    monkeypatch.setattr(cli.subprocess, "call", lambda argv: restarted.append(argv) or 0)
    monkeypatch.setattr(updater, "installed", lambda prefix=None: True)
    return me, restarted


def test_update_installs_then_reopens_the_same_conversation(project, peto, account, monkeypatch):  # noqa: F811
    me, restarted = account
    session_id = "20261014-090000-aaaaaa"
    history.save(project, peto.url, [{"type": "message", "role": "user", "content": "Sửa README"}],
                 session_id=session_id, title="Sửa README")
    installs = []

    def install(server, on_progress=None):
        installs.append(server)
        on_progress(2.0, "Đang cài peto…\n")
        return {"exit_code": 0, "seconds": 12.0, "output": "Đã cài peto " + newer()}

    monkeypatch.setattr(updater, "install", install)
    ui = FakeUI(answers=["/update", "1", "1"])
    assert cli.session(ui, resume=session_id) == 0
    assert 'Đã mở lại hội thoại' in ui.text and '"Sửa README"' in ui.text, "--resume mở thẳng hội thoại"
    assert f"Gõ /update để cập nhật" in ui.text
    assert installs == [peto.url]
    assert f"Đã cài peto {newer()}" in ui.text
    assert restarted == [[str(updater.launcher()), "--resume", session_id]]

    restarted.clear()
    later = FakeUI(answers=["/update", "1", "2", "/exit"])
    assert cli.session(later) == 0
    assert restarted == [] and "Để sau" in later.text

    me["cli_version"] = __version__
    current = FakeUI(answers=["/update", "/exit"])
    assert cli.session(current) == 0
    assert f"Đang dùng bản mới nhất ({__version__})" in current.text


def test_update_refuses_source_checkouts_and_reports_failed_installs(project, peto, account,  # noqa: F811
                                                                    monkeypatch):
    _, restarted = account
    monkeypatch.setattr(updater, "install", lambda server, on_progress=None: {"exit_code": 1, "seconds": 3.0,
                                                                               "output": "Lỗi tải gói"})
    failed = FakeUI(answers=["/update", "1", "/exit"])
    assert cli.session(failed) == 0
    assert "Cập nhật chưa xong; peto đang dùng vẫn chạy bình thường." in failed.text and restarted == []

    monkeypatch.setattr(updater, "installed", lambda prefix=None: False)
    source = FakeUI(answers=["/update", "/exit"])
    assert cli.session(source) == 0
    assert "không chạy từ bản cài bằng install.ps1" in source.text and f"irm {peto.url}/install.ps1 | iex" in source.text
    assert "Thoát peto rồi chạy lệnh cài để cập nhật" in source.text, "lời nhắc đầu phiên như cũ"

    bad = FakeUI(answers=["/exit"])
    assert cli.session(bad, resume="..\\x") == 0
    assert "Đã mở lại hội thoại" not in bad.text, "mã sai dạng không thành đường dẫn"
