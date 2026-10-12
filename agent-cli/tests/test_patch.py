"""apply_patch cho model GPT (CLI 0.21.0, theo opencode): đọc bản patch, khớp chặt, nhiều tệp một lần duyệt, sai một
chỗ là không ghi gì, và /undo hoàn tác cả bản."""

from __future__ import annotations

import codecs
import json

import pytest
from conftest import FakeUI

from peto_agent import patch
from peto_agent.checkpoint import Checkpoint
from peto_agent.tools import FEATURES, PLAN_REFUSAL, Tools
from peto_agent.workspace import Workspace


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def make(project, answers=()) -> Tools:
    tools = Tools(Workspace(project), FakeUI(answers))
    tools.features = [*FEATURES, "explore_v2", "edit_v2", "patch"]
    return tools


def read(tools, path):
    assert "error" not in tools.call("read_file", args(path=path, start_line=None, end_line=None))


# ---- Đọc và áp

def test_parse_understands_add_delete_update_move_and_heredoc():
    ops = patch.parse("cat <<'EOF'\n*** Begin Patch\n*** Add File: moi.py\n+a = 1\n+b = 2\n*** Delete File: cu.txt\n"
                      "*** Update File: app.py\n*** Move to: main.py\n@@ def greet():\n-    print('Hi')\n"
                      "+    print('Hello')\n*** End Patch\nEOF")
    assert [(op.kind, op.path) for op in ops] == [("add", "moi.py"), ("delete", "cu.txt"), ("update", "app.py")]
    assert ops[0].contents == "a = 1\nb = 2\n" and ops[2].move_to == "main.py"
    chunk = ops[2].chunks[0]
    assert chunk.context == "def greet():" and chunk.old == ["    print('Hi')"] and chunk.new == ["    print('Hello')"]


@pytest.mark.parametrize("text,message", [
    ("*** Update File: a.py\n", "Dòng đầu"),
    ("*** Begin Patch\n*** Add File: a.py\n+x\n", "Dòng cuối"),
    ("*** Begin Patch\n*** Rename File: a.py\n*** End Patch", "không phải đầu mục"),
    ("*** Begin Patch\n*** Add File: a.py\nx\n*** End Patch", "chỉ gồm các dòng bắt đầu bằng"),
    ("*** Begin Patch\n*** Update File: a.py\n*** End Patch", "không có thay đổi"),
    ("*** Begin Patch\n*** Update File: a.py\n@@\n?sai\n*** End Patch", "mỗi dòng phải bắt đầu"),
])
def test_bad_patches_say_which_line_is_wrong(text, message):
    with pytest.raises(patch.PatchError, match=message):
        patch.parse(text)


def test_apply_matches_strictly_and_only_once():
    text = "def a():\n    return 1\n\ndef b():\n    return 1\n"
    chunks = patch.parse("*** Begin Patch\n*** Update File: x.py\n@@ def b():\n-    return 1\n+    return 2\n"
                         "*** End Patch")[0].chunks
    assert patch.apply(text, chunks, "x.py") == "def a():\n    return 1\n\ndef b():\n    return 2\n"
    loose = patch.parse("*** Begin Patch\n*** Update File: x.py\n@@\n-return 1  \n+return 3\n*** End Patch")[0].chunks
    with pytest.raises(patch.PatchError, match="khớp 2 chỗ"):
        patch.apply(text, loose, "x.py")
    other = patch.parse("*** Begin Patch\n*** Update File: x.py\n@@\n-    retrun 1\n+x\n*** End Patch")[0].chunks
    with pytest.raises(patch.PatchError, match="Không thấy đoạn"):
        patch.apply(text, other, "x.py")
    indented = patch.parse("*** Begin Patch\n*** Update File: x.py\n@@ def a():\n-return 1\n+    return 9\n"
                           "*** End Patch")[0].chunks
    assert patch.apply(text, indented, "x.py").startswith("def a():\n    return 9\n"), "bỏ khoảng trắng đầu dòng vẫn khớp"


# ---- Công cụ

def test_one_patch_changes_several_files_after_one_approval_and_undo_restores_all(project):
    (project / "app.py").write_bytes(codecs.BOM_UTF8 + b"def greet():\r\n    print('Hi')\r\n")
    (project / "cu.txt").write_text("bỏ đi\n", encoding="utf-8")
    (project / "doi.py").write_text("x = 1\n", encoding="utf-8")
    tools = make(project, ["y"])
    for path in ("app.py", "doi.py"):
        read(tools, path)
    text = ("*** Begin Patch\n*** Add File: moi.py\n+print('mới')\n*** Delete File: cu.txt\n"
            "*** Update File: app.py\n@@ def greet():\n-    print('Hi')\n+    print('Hello')\n"
            "*** Update File: doi.py\n*** Move to: ten_moi.py\n@@\n-x = 1\n+x = 2\n*** End Patch")
    result = tools.call("apply_patch", args(patch_text=text))
    assert result["ok"] and [item["path"] for item in result["files"]] == ["moi.py", "cu.txt", "app.py", "ten_moi.py"]
    assert result["files"][3]["moved_from"] == "doi.py"
    assert (result["files"][3]["added_lines"], result["files"][3]["removed_lines"]) == (1, 1), "đếm phần nội dung đổi"
    assert (project / "moi.py").read_text(encoding="utf-8") == "print('mới')\n"
    assert not (project / "cu.txt").exists() and not (project / "doi.py").exists()
    assert (project / "app.py").read_bytes() == codecs.BOM_UTF8 + b"def greet():\r\n    print('Hello')\r\n", "giữ BOM, CRLF"
    assert (project / "ten_moi.py").read_text(encoding="utf-8") == "x = 2\n"
    assert tools.ui.text.count("Muốn ") == 4 and len(tools.ui.answers) == 0, "một lần hỏi cho cả bản patch"

    restored = Checkpoint.restore(Workspace(project))
    assert sorted(restored.undo()) == ["app.py", "cu.txt", "doi.py", "moi.py", "ten_moi.py"]
    assert (project / "app.py").read_bytes() == codecs.BOM_UTF8 + b"def greet():\r\n    print('Hi')\r\n"
    assert (project / "cu.txt").exists() and (project / "doi.py").exists() and not (project / "moi.py").exists()


def test_one_wrong_hunk_writes_nothing(project):
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 1\n", encoding="utf-8")
    tools = make(project, ["y"])
    read(tools, "a.py")
    read(tools, "b.py")
    text = ("*** Begin Patch\n*** Update File: a.py\n@@\n-a = 1\n+a = 2\n*** Update File: b.py\n@@\n-b = 9\n+b = 2\n"
            "*** End Patch")
    assert "Không thấy đoạn cần sửa trong b.py" in tools.call("apply_patch", args(patch_text=text))["error"]
    assert (project / "a.py").read_text(encoding="utf-8") == "a = 1\n", "tệp đầu cũng không bị ghi"
    assert tools.ui.answers == ["y"], "sai thì không hỏi gì"


def test_the_same_rules_as_edit_file_apply(project):
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "co.py").write_text("x\n", encoding="utf-8")
    tools = make(project, ["n"])
    update = "*** Begin Patch\n*** Update File: a.py\n@@\n-a = 1\n+a = 2\n*** End Patch"
    assert "Đọc a.py bằng read_file trước khi sửa" in tools.call("apply_patch", args(patch_text=update))["error"]
    add = "*** Begin Patch\n*** Add File: co.py\n+y\n*** End Patch"
    assert "đã có sẵn" in tools.call("apply_patch", args(patch_text=add))["error"]
    read(tools, "a.py")
    assert "không đồng ý" in tools.call("apply_patch", args(patch_text=update))["error"]
    assert (project / "a.py").read_text(encoding="utf-8") == "a = 1\n"
    tools.ui.mode = "plan"
    assert tools.call("apply_patch", args(patch_text=update)) == {"error": PLAN_REFUSAL}
