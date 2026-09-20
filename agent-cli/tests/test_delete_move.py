"""Xóa và đổi tên tệp: hỏi người dùng, đi qua bản nhớ hoàn tác, và /undo lấy lại được."""

from __future__ import annotations

import codecs
import json

import pytest
from conftest import FakeUI

from peto_agent.checkpoint import Checkpoint
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace, WorkspaceError


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def test_delete_asks_first_and_can_be_undone(project):
    original = codecs.BOM_UTF8 + b"mot\r\nhai\r\n"
    (project / "cu.py").write_bytes(original)
    tools = Tools(Workspace(project), FakeUI(["y"]))

    result = tools.call("delete_file", args(path="cu.py"))
    assert result == {"ok": True, "path": "cu.py", "deleted": True, "removed_lines": 2}
    assert not (project / "cu.py").exists()
    # Nội dung sắp mất phải hiện ra trước khi hỏi.
    assert "Muốn xóa cu.py" in tools.ui.text and "mot" in tools.ui.text

    restored = Checkpoint.restore(Workspace(project))
    assert restored.files["cu.py"].after is None
    assert restored.undo() == ["cu.py"]
    assert (project / "cu.py").read_bytes() == original, "giữ nguyên BOM và CRLF như lúc xóa"


def test_delete_refused_keeps_the_file(project):
    (project / "cu.py").write_text("x\n")
    tools = Tools(Workspace(project), FakeUI(["n"]))
    assert "không đồng ý xóa cu.py" in tools.call("delete_file", args(path="cu.py"))["error"]
    assert (project / "cu.py").exists()
    assert not Checkpoint.restore(Workspace(project)).files


def test_delete_rejects_folders_secrets_and_files_undo_cannot_hold(project):
    (project / "thumuc").mkdir()
    (project / ".env").write_text("TOKEN=1")
    (project / "anh.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    tools = Tools(Workspace(project), FakeUI(["y", "y", "y", "y"]))
    assert "thư mục" in tools.call("delete_file", args(path="thumuc"))["error"]
    assert "bí mật" in tools.call("delete_file", args(path=".env"))["error"]
    assert "nhị phân" in tools.call("delete_file", args(path="anh.png"))["error"]
    assert "Không tìm thấy" in tools.call("delete_file", args(path="chua-co.py"))["error"]
    assert (project / "anh.png").exists() and (project / ".env").exists()


def test_move_keeps_content_and_undo_puts_it_back(project):
    (project / "src").mkdir()
    (project / "src" / "cu.py").write_bytes(b"noi dung\n")
    tools = Tools(Workspace(project), FakeUI(["y"]))

    result = tools.call("move_file", args(path="src/cu.py", new_path="src/moi/moi.py"))
    assert result == {"ok": True, "path": "src/moi/moi.py", "moved_from": "src/cu.py"}
    assert (project / "src" / "moi" / "moi.py").read_bytes() == b"noi dung\n"
    assert not (project / "src" / "cu.py").exists()

    restored = Checkpoint.restore(Workspace(project))
    assert sorted(restored.files) == ["src/cu.py", "src/moi/moi.py"]
    assert sorted(restored.undo()) == ["src/cu.py", "src/moi/moi.py"]
    assert (project / "src" / "cu.py").read_bytes() == b"noi dung\n"
    assert not (project / "src" / "moi" / "moi.py").exists()


def test_move_refuses_when_something_is_already_there(project):
    (project / "a.py").write_text("a\n")
    (project / "b.py").write_text("b\n")
    tools = Tools(Workspace(project), FakeUI(["y", "y"]))
    assert "đã có sẵn" in tools.call("move_file", args(path="a.py", new_path="b.py"))["error"]
    assert "trùng đường dẫn cũ" in tools.call("move_file", args(path="a.py", new_path="./a.py"))["error"]
    assert "ngoài thư mục dự án" in tools.call("move_file", args(path="a.py", new_path="../a.py"))["error"]
    assert (project / "a.py").read_text() == "a\n" and (project / "b.py").read_text() == "b\n"


def test_creating_then_deleting_in_one_task_leaves_nothing_to_restore(project):
    tools = Tools(Workspace(project), FakeUI(["a"]))
    tools.call("write_file", args(path="tam.py", content="tam\n"))
    tools.call("delete_file", args(path="tam.py"))
    restored = Checkpoint.restore(Workspace(project))
    assert restored.files["tam.py"].before is None and restored.files["tam.py"].after is None
    assert restored.undo() == ["tam.py"]
    assert not (project / "tam.py").exists(), "hoàn tác không dựng lại tệp vốn chưa từng có"


def test_a_shell_deletion_between_two_tool_calls_blocks_undo(project):
    """Bản hoàn tác chỉ nói về những gì công cụ sửa tệp làm; người dùng đổi tay thì dừng, không đè lên."""
    (project / "a.py").write_text("goc\n")
    tools = Tools(Workspace(project), FakeUI(["y"]))
    tools.call("delete_file", args(path="a.py"))
    (project / "a.py").write_text("nguoi dung tu tao lai\n")
    with pytest.raises(WorkspaceError, match="không hoàn tác"):
        Checkpoint.restore(Workspace(project)).undo()
    assert (project / "a.py").read_text() == "nguoi dung tu tao lai\n"
