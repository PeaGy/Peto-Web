"""CLI 0.25.0: output đầy đủ của lệnh dài (read_output) và AGENTS.md chung của người dùng (/guide)."""

from __future__ import annotations

import json
import os
import sys
import time

from conftest import FakeUI

from peto_agent import config, external_editor, outputs, runner, user_guide
from peto_agent import __main__ as main
from peto_agent.loop import Session
from peto_agent.tools import FEATURES, Tools
from peto_agent.workspace import Workspace

PRINT_LINES = f'"{sys.executable}" -c "import sys; [print(f\'dong {{n}}\') for n in range(1, 4001)]"'


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


# ---- Output đầy đủ

def test_a_long_output_is_saved_whole_and_short_ones_leave_nothing(project):
    result = runner.run(PRINT_LINES, project, 60, spool=True)
    assert "bỏ bớt" in result["output"], "kết quả gửi Peto vẫn chỉ giữ đầu và cuối"
    assert result["output_lines"] == 4000 and result["output_id"].startswith("out_")
    found = outputs.read(result["output_id"], pattern=r"^dong 2000$")
    assert found["matches"] == [{"line": 2000, "text": "dong 2000"}] and found["total_matches"] == 1
    page = outputs.read(result["output_id"], start_line=1999, end_line=2001)
    assert page["content"].split("\n") == ["  1999\tdong 1999", "  2000\tdong 2000", "  2001\tdong 2001"]
    short = runner.run(f'"{sys.executable}" -c "print(1)"', project, 60, spool=True)
    assert "output_id" not in short
    assert [path.name for path in config.outputs_dir().glob("*.log")] == [f"{result['output_id']}.log"]


def test_read_output_is_a_tool_that_needs_no_permission(project):
    tools = Tools(Workspace(project), FakeUI(["y"]))
    tools.features = [*FEATURES, "output_files"]
    run = tools.call("run_command", args(command=PRINT_LINES, timeout_seconds=None, shell=None, cwd=None))
    assert run["output_id"]
    found = tools.call("read_output", args(output_id=run["output_id"], pattern="dong 3999", start_line=None,
                                           end_line=None))
    assert found["matches"][0]["line"] == 3999
    assert "không hợp lệ" in tools.call("read_output", args(output_id="../../config", pattern=None, start_line=None,
                                                            end_line=None))["error"]
    missing = tools.call("read_output", args(output_id="out_000000000000", pattern=None, start_line=None,
                                             end_line=None))
    assert "Không còn output" in missing["error"]
    plain = Tools(Workspace(project), FakeUI(["y"]))
    assert "output_id" not in plain.call("run_command", args(command=PRINT_LINES, timeout_seconds=None)), \
        "máy chủ chưa có output_files thì không lưu"


def test_old_outputs_are_pruned_after_seven_days(project):
    old = runner.run(PRINT_LINES, project, 60, spool=True)["output_id"]
    path = config.outputs_dir() / f"{old}.log"
    stale = time.time() - 8 * 24 * 3600
    os.utime(path, (stale, stale))
    fresh = runner.run(PRINT_LINES, project, 60, spool=True)["output_id"]
    outputs.prune()
    assert not path.exists() and (config.outputs_dir() / f"{fresh}.log").exists()


def test_a_background_job_keeps_its_log_only_when_a_read_was_cut(project):
    tools = Tools(Workspace(project), FakeUI(["y", "y"]))
    tools.features = [*FEATURES, "output_files"]
    job = tools.call("start_command", args(command=PRINT_LINES, shell=None))
    first = tools.jobs.jobs[job["id"]]
    first.process.wait(timeout=30)
    deadline = time.monotonic() + 10
    while first.spool._file is not None and time.monotonic() < deadline:  # luồng đọc gom xong thì đóng tệp
        time.sleep(0.02)
    # Đọc một lần sau khi lệnh xong: cả 4000 dòng (khoảng 40.000 ký tự) vượt mức cắt nên lần đọc này bị cắt.
    read = tools.call("read_command_output", args(job_id=job["id"], wait_seconds=0))
    assert read["output_id"] == first.spool.id and "bỏ bớt" in read["output"]
    assert outputs.read(read["output_id"], pattern="^dong 2000$")["total_matches"] == 1
    quiet = tools.call("start_command", args(command=f'"{sys.executable}" -c "print(1)"', shell=None))
    second = tools.jobs.jobs[quiet["id"]]
    second.process.wait(timeout=30)
    assert "output_id" not in tools.call("read_command_output", args(job_id=quiet["id"], wait_seconds=0))
    tools.jobs.stop_all()
    assert not second.spool.path.exists(), "output ngắn: hết phiên thì xóa"
    assert first.spool.path.exists(), "Peto đã được báo output_id nên giữ tệp (7 ngày)"


# ---- AGENTS.md chung

def test_the_user_guide_is_sent_with_each_step_when_the_server_supports_it(project):
    user_guide.write("Luôn dùng pnpm.\n")
    work = Session(object(), Workspace(project), FakeUI())
    work.tools.features = [*FEATURES, "user_guide"]
    assert work._step_context()["user_guidance"] == "Luôn dùng pnpm."
    work.tools.features = list(FEATURES)
    assert "user_guidance" not in work._step_context(), "máy chủ cũ không nhận"
    assert user_guide.path() == config.home() / "AGENTS.md", "nằm trong hồ sơ người dùng, không trong dự án"
    (project / "AGENTS.md").write_text("Hướng dẫn của dự án.\n", encoding="utf-8")
    work.tools.features = [*FEATURES, "user_guide"]
    assert work._step_context()["user_guidance"] == "Luôn dùng pnpm.", "AGENTS.md của dự án không thành hướng dẫn chung"


def test_a_guide_that_is_too_long_is_not_sent_and_the_user_is_told_once(project):
    user_guide.path().parent.mkdir(parents=True, exist_ok=True)
    user_guide.path().write_text("x" * (user_guide.MAX_CHARS + 1), encoding="utf-8")
    work = Session(object(), Workspace(project), FakeUI())
    work.tools.features = [*FEATURES, "user_guide"]
    assert "user_guidance" not in work._step_context()
    work._step_context()
    assert work.ui.text.count("dài quá") == 1


def editor_writing(monkeypatch, text):
    def fake(initial, *, cmd):
        fake.initial = initial
        return text
    monkeypatch.setattr(external_editor, "edit", fake)
    return fake


def test_guide_edits_the_shared_file_or_the_project_agents_md(project, monkeypatch):
    work = Session(object(), Workspace(project), FakeUI())
    work.tools.features = [*FEATURES, "user_guide"]
    monkeypatch.setattr(work.ui, "choose", lambda title, rows: 0)
    fake = editor_writing(monkeypatch, "# Chung\nDùng pnpm.\n")
    main._guide(work.ui, work)
    assert fake.initial == user_guide.TEMPLATE
    assert user_guide.path().read_text(encoding="utf-8") == "# Chung\nDùng pnpm.\n"
    assert "Đã lưu hướng dẫn chung" in work.ui.text

    (project / "AGENTS.md").write_bytes(b"# D\xe1\xbb\xb1 \xc3\xa1n\r\n")
    work.ws.read_digests[project / "AGENTS.md"] = "cũ"
    monkeypatch.setattr(work.ui, "choose", lambda title, rows: 1)
    editor_writing(monkeypatch, "# Dự án\nChạy pytest.\n")
    main._guide(work.ui, work)
    assert (project / "AGENTS.md").read_bytes() == "# Dự án\r\nChạy pytest.\r\n".encode(), "giữ CRLF của tệp cũ"
    assert project / "AGENTS.md" not in work.ws.read_digests, "Peto phải đọc lại trước khi tự sửa"
    assert not work.tools.checkpoint.files, "không vào bản hoàn tác"

    editor_writing(monkeypatch, None)
    main._guide(work.ui, work)
    assert "tệp để nguyên" in work.ui.text
