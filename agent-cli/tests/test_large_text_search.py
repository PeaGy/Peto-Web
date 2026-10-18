"""Tái hiện metadata lớn và mẫu ngoặc trong bài GTA, không cần game/converter."""
import json

import pytest
from conftest import FakeUI

from peto_agent.file_glob import glob_regex
from peto_agent.tools import Tools
from peto_agent.workspace import MAX_FILE_BYTES, MAX_TEXT_LINE_CHARS, Workspace


def call(tools, name, **values):
    return tools.call(name, json.dumps(values))


def test_find_and_search_share_brace_globs_in_subfolders(project):
    root = project / "src"
    (root / "nested").mkdir(parents=True)
    for name in ("a.py", "b.json", "nested/c.md", "nested/d.txt"):
        (root / name).write_text("needle\n", encoding="utf-8")
    tools = Tools(Workspace(project), FakeUI())
    tools.features = ["explore_v2"]
    pattern = "**/*.{py,{json,md}}"
    files = call(tools, "find_files", path="src", pattern=pattern)
    matches = call(tools, "search_files", path="src", glob=pattern, pattern="needle")
    assert set(files["files"]) == {item["path"] for item in matches["files"]} == {
        "src/a.py", "src/b.json", "src/nested/c.md"}
    assert glob_regex("file{,.test}.py").fullmatch("file.py")
    assert glob_regex("file{,.test}.py").fullmatch("file.test.py")


@pytest.mark.parametrize("pattern", ["**/*.{py,json", "*.{1..3}", "x}", "{a,b}" * 8])
def test_unsupported_or_explosive_globs_report_errors_in_both_tools(project, pattern):
    tools = Tools(Workspace(project), FakeUI())
    assert "error" in call(tools, "find_files", pattern=pattern)
    assert "error" in call(tools, "search_files", pattern="needle", glob=pattern)


def test_large_utf8_bom_crlf_metadata_can_be_read_and_searched_beyond_one_mb(project):
    path = project / "âm thanh.json"
    count = 24000
    line = '  "unchanged": "' + "x" * 70 + '",\r\n'
    path.write_bytes(b"\xef\xbb\xbf" + (line * count + '  "NEEDLE_DOOMER": 5042176\r\n').encode("utf-8"))
    assert path.stat().st_size > MAX_FILE_BYTES
    tools = Tools(Workspace(project), FakeUI())
    tools.features = ["read_more", "explore_v2"]
    view = call(tools, "read_file", path=path.name, start_line=count, end_line=count + 1)
    assert view["total_lines"] == count + 1 and "NEEDLE_DOOMER" in view["content"]
    assert "\r" not in view["content"] and view["editing_supported"] is False
    assert path not in tools.ws.read_digests
    found = call(tools, "search_files", path=".", pattern="NEEDLE_DOOMER", glob="*.{json,py}")
    assert found["total"] == 1 and found["files"][0]["matches"][0]["line"] == count + 1
    edit = call(tools, "edit_file", path=path.name, old_text="NEEDLE_DOOMER", new_text="changed")
    assert "1 MB" in edit["error"] and b"NEEDLE_DOOMER" in path.read_bytes()


def test_large_read_stays_bounded_and_has_honest_line_truncation(project):
    path = project / "long.json"
    path.write_text("a" * (MAX_TEXT_LINE_CHARS + 7) + "needle-at-end\nlast\n")
    tools = Tools(Workspace(project), FakeUI())
    tools.features = ["read_more"]
    view = call(tools, "read_file", path=path.name, start_line=1, end_line=1)
    assert len(view["content"]) <= 32000 and view["truncated_lines"] == [1]
    assert view["total_lines"] == 2 and view["next_start_line"] == 2
    results = call(tools, "search_files", path=path.name, pattern="needle-at-end")
    assert results["matches"] == [] and results["incomplete"]
    assert results["skipped"]["long_line"] == 1


def test_skipped_binary_invalid_encoding_and_over_limit_files_are_visible(project, monkeypatch):
    (project / "binary.dat").write_bytes(b"\0data")
    (project / "ansi.txt").write_bytes(b"\xff\xfe")
    (project / "ok.txt").write_text("needle")
    (project / "huge.txt").write_text("x" * 201)
    monkeypatch.setattr("peto_agent.workspace.MAX_TEXT_SCAN_BYTES", 200)
    tools = Tools(Workspace(project), FakeUI())
    results = call(tools, "search_files", pattern="needle")
    assert len(results["matches"]) == 1
    assert results["skipped"] == {"not_utf8": 1, "binary": 1, "too_large": 1}
    assert len(results["skipped_files"]) == 3 and results["incomplete"]


def test_streaming_read_does_not_bypass_secret_or_project_boundaries(project, tmp_path):
    (project / ".env").write_text("secret" * 200000)
    outside = tmp_path / "outside.txt"
    outside.write_text("x" * 1000001)
    tools = Tools(Workspace(project), FakeUI())
    assert "bí mật" in call(tools, "read_file", path=".env")["error"]
    assert "ngoài thư mục" in call(tools, "read_file", path=str(outside))["error"]
