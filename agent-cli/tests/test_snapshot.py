"""Ảnh chụp dự án bằng kho git ẩn (CLI 0.26.0, theo snapshot.ts và revert.ts của opencode).

Nhật ký thật của chủ web có 10/68 lệnh đổi tệp mà /undo không thấy (dotnet ef migrations add, copy, del…). Giờ Peto chụp
trước và sau mỗi lệnh, thay đổi đó vào bản hoàn tác, và khôi phục được tệp về lúc trước một tin cũ.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest
from conftest import FakeUI

from peto_agent import __main__ as main
from peto_agent import history, snapshot
from peto_agent.checkpoint import Checkpoint
from peto_agent.loop import Session
from peto_agent.tools import FEATURES, Tools
from peto_agent.workspace import Workspace

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="máy test không có git")


@pytest.fixture(autouse=True)
def snapshots_on(monkeypatch):
    monkeypatch.delenv("PETO_AGENT_NO_SNAPSHOTS", raising=False)


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def script(code: str) -> str:
    """Một lệnh Python chạy được trong cmd, để thử lệnh tự đổi tệp mà không phụ thuộc copy, del của Windows."""
    return f'"{sys.executable}" -c "{code}"'


def test_capture_skips_ignored_heavy_secret_and_large_files(project):
    (project / ".gitignore").write_text("logs/\n", encoding="utf-8")
    for name, data in {"a.txt": b"a", "logs/x.log": b"x", "node_modules/m.js": b"m", ".env": b"KEY=1",
                       "big.bin": b"0" * (snapshot.MAX_FILE_BYTES + 1), "src/b.py": b"b = 1"}.items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_bytes(data)
    shots = snapshot.Snapshots(project)
    tree = shots.capture()
    found = shots.contents(tree, ["a.txt", "src/b.py", "logs/x.log", "node_modules/m.js", ".env", "big.bin"])
    assert found["a.txt"] == b"a" and found["src/b.py"] == b"b = 1"
    assert [name for name, data in found.items() if data is None] == ["logs/x.log", "node_modules/m.js", ".env",
                                                                      "big.bin"]
    assert not (project / ".git").exists(), "kho ẩn nằm ngoài dự án"
    (project / "a.txt").write_bytes(b"a2")
    (project / "src" / "b.py").unlink()
    later = shots.capture()
    assert shots.changed(tree, later) == ["a.txt", "src/b.py"]
    assert shots.changed(later, shots.capture()) == []


def test_the_project_git_repository_is_never_touched(project):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "a.txt").write_text("a", encoding="utf-8")
    before = sorted(path.name for path in (project / ".git").iterdir())
    shots = snapshot.Snapshots(project)
    shots.capture()
    assert sorted(path.name for path in (project / ".git").iterdir()) == before
    status = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True).stdout
    assert status.strip() == "?? a.txt", "kho của dự án không có gì được thêm vào index"


def make(project, answers=("y",)) -> Tools:
    tools = Tools(Workspace(project), FakeUI(list(answers)))
    tools.features = [*FEATURES, "explore_v2", "edit_v2"]
    return tools


CHANGE = ("import pathlib; pathlib.Path('a.txt').write_text('sau'); pathlib.Path('new.bin').write_bytes(bytes(range(256)));"
          " pathlib.Path('gone.txt').unlink()")


def test_a_command_s_changes_reach_the_result_the_summary_and_undo(project):
    (project / "a.txt").write_text("trước", encoding="utf-8")
    (project / "gone.txt").write_text("mất", encoding="utf-8")
    tools = make(project)
    result = tools.call("run_command", args(command=script(CHANGE), timeout_seconds=None))
    assert result["exit_code"] == 0 and sorted(result["files_changed"]) == ["a.txt", "gone.txt", "new.bin"]
    assert "đổi 3 tệp" in tools.ui.text
    files = tools.checkpoint.files
    assert files["new.bin"].before is None and files["new.bin"].source == "command"
    assert files["gone.txt"].after is None and files["a.txt"].before == "trước".encode()
    restored = Checkpoint.restore(tools.ws)
    assert restored.commands_covered and set(restored.files) == {"a.txt", "gone.txt", "new.bin"}, "nhị phân vẫn lưu được"
    assert sorted(restored.undo()) == ["a.txt", "gone.txt", "new.bin"]
    assert (project / "a.txt").read_text(encoding="utf-8") == "trước"
    assert (project / "gone.txt").read_text(encoding="utf-8") == "mất" and not (project / "new.bin").exists()


def test_peto_s_own_edit_then_a_command_on_the_same_file_undoes_to_the_start(project):
    (project / "a.txt").write_text("một", encoding="utf-8")
    tools = make(project, ["y", "y"])
    tools.read_file("a.txt")
    tools.call("edit_file", args(path="a.txt", old_text="một", new_text="hai", replace_all=None))
    tools.call("run_command", args(command=script("import pathlib; pathlib.Path('a.txt').write_text('ba')"),
                                   timeout_seconds=None))
    change = tools.checkpoint.files["a.txt"]
    assert change.before == "một".encode() and change.after == b"ba" and change.source == "peto"
    tools.checkpoint.undo()
    assert (project / "a.txt").read_text(encoding="utf-8") == "một"


def test_undo_refuses_when_the_user_changed_a_file_afterwards(project):
    (project / "a.txt").write_text("trước", encoding="utf-8")
    (project / "gone.txt").write_text("mất", encoding="utf-8")
    tools = make(project)
    tools.call("run_command", args(command=script(CHANGE), timeout_seconds=None))
    (project / "a.txt").write_text("bạn sửa", encoding="utf-8")
    with pytest.raises(Exception, match="không còn như lúc Peto để lại"):
        Checkpoint.restore(tools.ws).undo()
    assert (project / "a.txt").read_text(encoding="utf-8") == "bạn sửa"


def test_without_git_nothing_changes_and_the_user_is_told_once(project, monkeypatch):
    monkeypatch.setattr(snapshot.shutil, "which", lambda name: None)
    tools = make(project, ["y", "y"])
    for _ in range(2):
        result = tools.call("run_command", args(command=script("print(1)"), timeout_seconds=None))
        assert "files_changed" not in result
    assert tools.ui.text.count("Máy chưa có git") == 1


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


class Client:
    server = "https://example.test"

    def stream(self, path, body, **kwargs):
        yield {"type": "done", "output": [message("Xong.")], "usage": {}}


def session(project, answers=()) -> Session:
    work = Session(Client(), Workspace(project), FakeUI(list(answers)))
    work.auto_title = False
    return work


def test_restoring_to_before_a_message_and_undoing_the_restore(project, monkeypatch):
    (project / "a.txt").write_text("1", encoding="utf-8")
    work = session(project, ["y"])
    work.run_task("tin đầu")
    work.tools.wait_snapshot()
    (project / "a.txt").write_text("2", encoding="utf-8")
    (project / "b.txt").write_text("mới", encoding="utf-8")
    work.run_task("tin sau")
    work.tools.wait_snapshot()
    first = next(index for index, item in enumerate(work.items) if item.get("role") == "user")
    point = work.restore_point(first)
    assert point and len(work.snapshot_marks) == 2
    monkeypatch.setattr(work.ui, "choose", lambda title, rows: 0)
    work.restore_files(point, "tin đầu")
    assert (project / "a.txt").read_text(encoding="utf-8") == "1" and not (project / "b.txt").exists()
    assert "Đã khôi phục 2 tệp" in work.ui.text
    assert "vừa khôi phục 2 tệp" in history.raw_text(work.items[-1]), "Peto được báo để đọc lại"
    work.undo()
    assert (project / "a.txt").read_text(encoding="utf-8") == "2"
    assert (project / "b.txt").read_text(encoding="utf-8") == "mới"


def test_marks_survive_saving_resume_and_fork(project):
    (project / "a.txt").write_text("1", encoding="utf-8")
    work = session(project)
    work.run_task("làm tiếp")
    work.run_task("làm tiếp")
    work.tools.wait_snapshot()
    positions = [index for index, item in enumerate(work.items) if item.get("role") == "user"]
    keys = [history.fingerprint(work.items, index) for index in positions]
    assert keys[0] != keys[1], "hai tin giống hệt vẫn khác dấu"
    saved = history.load(project, Client.server, work.session_id)
    assert set(saved.snapshots) == set(keys)
    other = session(project)
    other.resume(saved.items, session_id=saved.id, snapshots=saved.snapshots)
    assert other.restore_point(positions[1]) == work.snapshot_marks[keys[1]]


def test_the_message_menu_offers_restoring_files(project, monkeypatch):
    (project / "a.txt").write_text("1", encoding="utf-8")
    work = session(project)
    work.run_task("tin đầu")
    work.tools.wait_snapshot()
    offered = []

    def choose(title, rows):
        offered.append([label for label, _ in rows])
        return 0 if len(offered) == 1 else None
    monkeypatch.setattr(work.ui, "choose", choose)
    main._timeline(work.ui, work)
    assert "Khôi phục tệp về lúc trước tin này" in offered[-1]
