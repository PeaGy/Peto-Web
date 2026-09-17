"""Phạm vi thư mục, chặn tệp bí mật và các công cụ đọc, tìm, sửa, ghi."""

from __future__ import annotations

import codecs
import json
import os
import subprocess

import pytest
from conftest import FakeUI

from peto_agent.tools import Tools
from peto_agent.workspace import Workspace, WorkspaceError


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def test_paths_outside_the_project_and_secret_files_are_blocked(tmp_path, project):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("print(1)\n")
    (tmp_path / "outside.txt").write_text("bí mật", encoding="utf-8")
    ws = Workspace(project)
    assert ws.relative(ws.resolve("src/app.py")) == "src/app.py"
    for outside in ["../outside.txt", str(tmp_path / "outside.txt"), "src/../../outside.txt"]:
        with pytest.raises(WorkspaceError, match="ngoài thư mục dự án"):
            ws.resolve(outside)
    for secret in [".env", ".env.local", "config/.ENV", "keys/server.pem", "id_rsa", ".git/config"]:
        with pytest.raises(WorkspaceError, match="bí mật"):
            ws.resolve(secret, must_exist=False)


@pytest.mark.skipif(os.name != "nt", reason="junction chỉ có trên Windows")
def test_junction_pointing_outside_cannot_be_used(tmp_path, project):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    link = project / "link"
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
    if made.returncode != 0:
        pytest.skip("không tạo được junction trên máy này")
    ws = Workspace(project)
    with pytest.raises(WorkspaceError, match="ngoài thư mục dự án"):
        ws.resolve("link/secret.txt")
    assert Tools(ws, FakeUI()).call("list_files", args(path=".", depth=None))["entries"] == []


def test_edit_needs_a_fresh_read_and_keeps_crlf(project):
    (project / "app.py").write_bytes(b"line1\r\nline2\r\nline3\r\n")
    tools = Tools(Workspace(project), FakeUI(answers=["y"]))
    assert "read_file" in tools.call("edit_file", args(path="app.py", old_text="line2", new_text="x"))["error"]

    read = tools.call("read_file", args(path="app.py", start_line=2, end_line=3))
    assert read == {"path": "app.py", "start_line": 2, "end_line": 3, "total_lines": 3, "content": "line2\nline3"}
    (project / "app.py").write_bytes(b"line1\r\nchanged\r\nline3\r\n")
    assert "đã thay đổi" in tools.call("edit_file", args(path="app.py", old_text="changed", new_text="x"))["error"]

    tools.call("read_file", args(path="app.py", start_line=None, end_line=None))
    edited = tools.call("edit_file", args(path="app.py", old_text="changed", new_text="đã sửa"))
    assert edited == {"ok": True, "path": "app.py", "added_lines": 1, "removed_lines": 1}
    assert (project / "app.py").read_bytes() == "line1\r\nđã sửa\r\nline3\r\n".encode()
    assert tools.changes == {"app.py": [1, 1]}


def test_edit_needs_a_unique_match_and_keeps_bom(project):
    (project / "notes.txt").write_bytes(codecs.BOM_UTF8 + b"a\nb\na\n")
    tools = Tools(Workspace(project), FakeUI(answers=["y"]))
    tools.call("read_file", args(path="notes.txt", start_line=None, end_line=None))
    assert "2 chỗ" in tools.call("edit_file", args(path="notes.txt", old_text="a", new_text="x"))["error"]
    assert "Không thấy" in tools.call("edit_file", args(path="notes.txt", old_text="zzz", new_text="x"))["error"]
    assert tools.call("edit_file", args(path="notes.txt", old_text="b", new_text="c"))["ok"]
    assert (project / "notes.txt").read_bytes() == codecs.BOM_UTF8 + b"a\nc\na\n"


def test_refusal_keeps_the_file_and_approve_all_lasts_for_one_task(project):
    (project / "a.txt").write_text("one\n")
    (project / "b.txt").write_text("two\n")
    (project / "exists.txt").write_text("x\n")
    ui = FakeUI(answers=["n", "a"])
    tools = Tools(Workspace(project), ui)
    for name in ("a.txt", "b.txt"):
        tools.call("read_file", args(path=name, start_line=None, end_line=None))

    refused = tools.call("edit_file", args(path="a.txt", old_text="one", new_text="1"))
    assert "không đồng ý" in refused["error"] and (project / "a.txt").read_text() == "one\n"
    assert tools.call("edit_file", args(path="a.txt", old_text="one", new_text="1"))["ok"]
    assert tools.call("edit_file", args(path="b.txt", old_text="two", new_text="2"))["ok"]
    assert "Đọc tệp trước" in tools.call("write_file", args(path="exists.txt", content="y\n"))["error"]
    created = tools.call("write_file", args(path="docs/new.md", content="# Mới\n"))
    assert created["created"] and (project / "docs" / "new.md").read_text(encoding="utf-8") == "# Mới\n"
    assert ui.answers == []

    tools.reset_task()
    assert tools.approve_all is False and tools.changes == {}


def test_list_and_search_skip_heavy_folders_and_secrets(project):
    (project / "src").mkdir()
    (project / "src" / "login.js").write_text("function handleLogin() {}\n")
    (project / "node_modules" / "lib").mkdir(parents=True)
    (project / "node_modules" / "lib" / "x.js").write_text("handleLogin\n")
    (project / ".env").write_text("TOKEN=handleLogin\n")
    tools = Tools(Workspace(project), FakeUI())

    assert tools.call("list_files", args(path=".", depth=None))["entries"] == ["src/", "src/login.js"]
    found = tools.call("search_files", args(pattern="handleLogin", path=None, glob="*.js"))
    assert found == {"matches": ["src/login.js:1: function handleLogin() {}"], "truncated": False}
    assert "không hợp lệ" in tools.call("search_files", args(pattern="(", path=None, glob=None))["error"]
    assert "Tham số" in tools.call("read_file", args(file="src/login.js"))["error"]
    assert "không có công cụ" in tools.call("delete_file", "{}")["error"]
    assert "bí mật" in tools.call("read_file", args(path=".env", start_line=None, end_line=None))["error"]
