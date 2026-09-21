"""Bỏ qua mục .gitignore khi liệt kê và tìm, và nhật ký ghi lại lời Peto."""

from __future__ import annotations

import copy
import json

from conftest import FakeUI

from peto_agent import mentions
from peto_agent.loop import MAX_LOGGED_REPLY, Session
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace, gitignored, parse_gitignore


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def make_project(project):
    (project / ".gitignore").write_text("# tệp sinh ra\ncoverage/\n*.log\n!keep.log\n/target\n", encoding="utf-8")
    for folder in ("src", "coverage", "target", "sub/target"):
        (project / folder).mkdir(parents=True, exist_ok=True)
    (project / "src" / "app.py").write_text("tim_toi = 1\n", encoding="utf-8")
    (project / "coverage" / "report.txt").write_text("tim_toi\n", encoding="utf-8")
    (project / "target" / "out.txt").write_text("tim_toi\n", encoding="utf-8")
    (project / "sub" / "target" / "giu.txt").write_text("tim_toi\n", encoding="utf-8")
    (project / "app.log").write_text("tim_toi\n", encoding="utf-8")
    (project / "keep.log").write_text("tim_toi\n", encoding="utf-8")


def test_rules_follow_git_order_anchoring_and_directory_marks():
    rules = parse_gitignore("coverage/\n*.log\n!keep.log\n/target\n\n# chú thích\n")
    assert gitignored(rules, "coverage", True) and not gitignored(rules, "coverage", False), "coverage/ chỉ là thư mục"
    assert gitignored(rules, "a/b/app.log", False)
    assert not gitignored(rules, "keep.log", False), "dòng ! sau thắng dòng trước"
    assert gitignored(rules, "target", True) and not gitignored(rules, "sub/target", True), "/target chỉ ở gốc"


def test_listing_and_search_skip_ignored_entries(project):
    make_project(project)
    tools = Tools(Workspace(project), FakeUI())

    entries = tools.call("list_files", args(path=".", depth=3))["entries"]
    assert "src/app.py" in entries and "keep.log" in entries and "sub/target/giu.txt" in entries
    assert not {"coverage/", "target/", "app.log"} & set(entries)

    found = tools.call("search_files", args(pattern="tim_toi", path=None, glob=None))["matches"]
    assert sorted(line.split(":")[0] for line in found) == ["keep.log", "src/app.py", "sub/target/giu.txt"]


def test_ignored_files_can_still_be_read_and_attached_by_path(project):
    make_project(project)
    workspace = Workspace(project)
    tools = Tools(workspace, FakeUI())
    assert tools.call("read_file", args(path="app.log", start_line=None, end_line=None))["content"] == "tim_toi"
    assert mentions.attach(workspace, tools, "xem @coverage/report.txt").paths == ["coverage/report.txt"]
    # Nhưng bảng gợi ý @ không mời chọn chúng, cho đỡ rối.
    labels = [item.label for item in mentions.suggest("@", mentions.Files(workspace))]
    assert "app.log" not in labels and "coverage/report.txt" not in labels


def test_editing_gitignore_takes_effect_without_restarting(project):
    make_project(project)
    workspace = Workspace(project)
    tools = Tools(workspace, FakeUI())
    assert "app.log" not in tools.call("list_files", args(path=".", depth=1))["entries"]
    (project / ".gitignore").write_text("coverage/\n", encoding="utf-8")
    import os
    stamp = os.path.getmtime(project / ".gitignore") + 5
    os.utime(project / ".gitignore", (stamp, stamp))
    assert "app.log" in tools.call("list_files", args(path=".", depth=1))["entries"]


class Client:
    server = "https://example.test"

    def __init__(self, turns):
        self.turns = list(turns)

    def stream(self, path, body, **kwargs):
        yield from copy.deepcopy(self.turns.pop(0))


def test_the_log_keeps_what_peto_said(project):
    """Nhật ký đọc được như bản chép lại: tệp hội thoại cho /resume chỉ giữ lần gần nhất nên không đủ để xem lại."""
    long_reply = "đầu " + "x" * (MAX_LOGGED_REPLY + 500) + " cuối"
    message = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": long_reply}]}
    work = Session(Client([[{"type": "done", "output": [message]}]]), Workspace(project), FakeUI())
    entries = []
    work.log = type("Log", (), {"write": lambda self, kind, **data: entries.append((kind, data))})()

    work.run_task("giải thích giúp")
    replies = [data["text"] for kind, data in entries if kind == "reply"]
    assert len(replies) == 1
    assert replies[0].startswith("đầu ") and replies[0].endswith(" cuối"), "giữ cả phần đầu lẫn phần cuối"
    assert len(replies[0]) < MAX_LOGGED_REPLY + 100
    assert [kind for kind, _ in entries] == ["task", "reply", "summary"]
