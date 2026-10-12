"""Hành vi công cụ theo OpenCode (CLI 0.18.0): đọc có số dòng, tìm gộp theo tệp, find_files, sửa khớp gần đúng có kiểm
soát (chủ web duyệt ngày 2026-10-12), replace_all và chặn gọi lặp."""

from __future__ import annotations

import json
import os
import time

import pytest
from conftest import FakeUI

from peto_agent import edit_match, mentions
from peto_agent.tools import FEATURES, Tools, glob_regex
from peto_agent.workspace import Workspace


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def make(project, answers=(), *, v2=True) -> Tools:
    tools = Tools(Workspace(project), FakeUI(answers))
    if v2:
        tools.features = [*FEATURES, "explore_v2", "edit_v2"]
    return tools


# ---- Khớp gần đúng

def test_exact_text_wins_and_nothing_fuzzy_ever_matches_different_words():
    text = "def f():\n    return 1\n"
    assert edit_match.find(text, "return 1").strategy == "exact"
    assert edit_match.find(text, "return 2").matches == []
    assert edit_match.find(text, "    retrun 1").matches == [], "lệch chữ thì không khớp"


def test_line_numbers_copied_from_read_file_are_dropped():
    text = "a = 1\nb = 2\n"
    found = edit_match.find(text, "     1\ta = 1\n     2\tb = 2")
    assert found.strategy == "numbers" and found.old == "a = 1\nb = 2"


def test_trimmed_lines_match_and_new_text_follows_the_file_indentation():
    text = "class A:\n        def f(self):\n            return 1\n"
    found = edit_match.find(text, "def f(self):\n    return 1")
    assert found.strategy == "trimmed" and len(found.matches) == 1
    match = found.matches[0]
    replaced = text[:match.start] + edit_match.reindent("def f(self):\n    return 2", match) + text[match.end:]
    assert replaced == "class A:\n        def f(self):\n            return 2\n"


def test_whitespace_inside_a_line_is_normalised_as_a_last_resort():
    text = "x  =   compute( a,b )\n"
    found = edit_match.find(text, "x = compute( a,b )")
    assert found.strategy == "spaces" and len(found.matches) == 1


# ---- Sửa tệp (edit_v2)

def test_an_approximate_edit_is_flagged_for_the_user_and_peto(project):
    (project / "app.py").write_text("def f():\n        return 1\n")
    tools = make(project, ["y"])
    tools.read_file("app.py")
    result = tools.call("edit_file", args(path="app.py", old_text="def f():\n    return 1",
                                          new_text="def f():\n    return 2", replace_all=None))
    assert result["match"] == "bỏ qua khoảng trắng đầu và cuối dòng" and result["replacements"] == 1
    assert (project / "app.py").read_text() == "def f():\n        return 2\n"
    assert "khớp gần đúng: bỏ qua khoảng trắng đầu và cuối dòng" in tools.ui.text


def test_ambiguous_old_text_names_the_lines_and_offers_replace_all(project):
    (project / "app.py").write_text("x = 1\ny = 2\nx = 1\n")
    tools = make(project, ["y"])
    tools.read_file("app.py")
    error = tools.call("edit_file", args(path="app.py", old_text="x = 1", new_text="x = 3", replace_all=None))["error"]
    assert "khớp 2 chỗ" in error and "dòng 1, 3" in error and "replace_all" in error
    result = tools.call("edit_file", args(path="app.py", old_text="x = 1", new_text="x = 3", replace_all=True))
    assert result["replacements"] == 2 and (project / "app.py").read_text() == "x = 3\ny = 2\nx = 3\n"


def test_without_edit_v2_the_old_exact_rules_stay(project):
    (project / "app.py").write_text("def f():\n        return 1\n")
    tools = make(project, ["y"], v2=False)
    tools.read_file("app.py")
    result = tools.call("edit_file", args(path="app.py", old_text="def f():\n    return 1", new_text="x"))
    assert "Không thấy old_text" in result["error"]


def test_the_edit_still_requires_a_fresh_read_and_keeps_crlf(project):
    (project / "app.py").write_bytes(b"a = 1\r\n    b = 2\r\n")
    tools = make(project, ["y"])
    assert "read_file trước" in tools.call("edit_file", args(path="app.py", old_text="b = 2", new_text="b = 3"))["error"]
    tools.read_file("app.py")
    tools.call("edit_file", args(path="app.py", old_text="b = 2  ", new_text="b = 3", replace_all=None))
    assert (project / "app.py").read_bytes() == b"a = 1\r\n    b = 3\r\n"


# ---- Đọc và tìm (explore_v2)

def test_reads_are_numbered_like_cat_n(project):
    (project / "app.py").write_text("a\nb\nc\n")
    content = make(project).read_file("app.py", start_line=2)["content"]
    assert content == "     2\tb\n     3\tc"
    assert make(project, v2=False).read_file("app.py")["content"] == "a\nb\nc"


def test_search_groups_matches_by_file_newest_first(project):
    (project / "old.py").write_text("todo = 1\n")
    (project / "new.py").write_text("x = 0\ntodo = 2\ntodo = 3\n")
    past = time.time() - 3600
    os.utime(project / "old.py", (past, past))
    result = make(project).search_files("todo")
    assert [item["path"] for item in result["files"]] == ["new.py", "old.py"]
    assert result["files"][0]["matches"] == [{"line": 2, "text": "todo = 2"}, {"line": 3, "text": "todo = 3"}]
    assert result["total"] == 3 and result["truncated"] is False


@pytest.mark.parametrize("pattern,expected", [
    ("**/*.py", ["src/app.py", "src/deep/util.py", "top.py"]),
    ("*.py", ["src/app.py", "src/deep/util.py", "top.py"]),
    ("src/*.py", ["src/app.py"]),
    ("src/**/*.py", ["src/app.py", "src/deep/util.py"]),
    ("*.JSON", ["package.json"]),
    ("src/[ad]*.py", ["src/app.py"]),
])
def test_find_files_matches_globs_and_skips_ignored_folders(project, pattern, expected):
    for rel in ("src/app.py", "src/deep/util.py", "top.py", "package.json", "node_modules/x/lib.py", "build/gen.py"):
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text("x\n")
    (project / ".gitignore").write_text("build/\n")
    result = make(project).find_files(pattern)
    assert sorted(result["files"]) == expected


def test_find_files_lists_newest_first_and_caps(project):
    for number in range(105):
        (project / f"f{number}.txt").write_text("x")
    past = time.time() - 3600
    for number in range(104):
        os.utime(project / f"f{number}.txt", (past, past))
    result = make(project).find_files("*.txt")
    assert result["files"][0] == "f104.txt" and len(result["files"]) == 100
    assert result["total"] == 105 and result["truncated"] is True


def test_glob_translation_keeps_single_star_inside_one_folder():
    assert glob_regex("src/*.py").fullmatch("src/a.py") and not glob_regex("src/*.py").fullmatch("src/x/a.py")
    assert glob_regex("**/test_?.py").fullmatch("test_a.py") and glob_regex("**/test_?.py").fullmatch("a/b/test_c.py")


def test_mentions_are_numbered_the_same_way(project):
    (project / "app.py").write_text("a\nb\n")
    attached = mentions.attach(Workspace(project), make(project), "xem @app.py")
    assert "     1\ta\n     2\tb" in attached.text


# ---- Chặn gọi lặp

def test_the_third_identical_call_without_changes_asks_and_can_be_stopped(project):
    (project / "app.py").write_text("a\n")
    tools = make(project, ["n"])
    call = args(path="app.py", start_line=None, end_line=None)
    assert "content" in tools.call("read_file", call)
    assert "content" in tools.call("read_file", call)
    refused = tools.call("read_file", call)
    assert "dừng vòng lặp" in refused["error"]
    assert "Peto gọi read_file y hệt 3 lần liền" in tools.ui.text and "Đã chặn" in tools.ui.text


def test_allowing_a_repeat_resets_the_count_and_file_changes_reset_it_too(project):
    (project / "app.py").write_text("a\n")
    tools = make(project, ["y"])
    call = args(path="app.py", start_line=None, end_line=None)
    for _ in range(5):
        assert "content" in tools.call("read_file", call), "lần 3 được cho phép, lần 4–5 đếm lại từ đầu"
    assert tools.ui.text.count("y hệt 3 lần liền") == 1
    tools.revision += 1
    assert "content" in tools.call("read_file", call), "tệp vừa đổi thì đọc lại là bình thường"


def test_polling_tools_are_never_counted_as_loops(project):
    tools = make(project)
    for _ in range(4):
        tools.call("update_plan", args(steps=[{"title": "Làm", "status": "running"}]))
    assert "y hệt" not in tools.ui.text
