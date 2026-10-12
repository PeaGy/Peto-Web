"""Nhiều hội thoại có tên mỗi dự án (CLI 0.20.0, theo opencode): /new giữ hội thoại cũ, /resume mở danh sách."""

from __future__ import annotations

import json
import os
import time

from conftest import FakeUI

from peto_agent import __main__ as cli
from peto_agent import history
from peto_agent.client import Client
from peto_agent.loop import Session
from peto_agent.workspace import Workspace

SERVER = "https://peto.example"


def said(text: str) -> list[dict]:
    return [{"type": "message", "role": "user", "content": text},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Xong: {text}"}]}]


def test_each_conversation_has_its_own_file_and_title_newest_first(project):
    history.save(project, SERVER, said("Sửa lỗi checksum trong tệp lưu"), session_id="a")
    time.sleep(0.01)
    history.save(project, SERVER, said("Thêm lệnh done " + "rất dài " * 20), session_id="b")
    sessions = history.list_sessions(project, SERVER)
    assert [saved.id for saved in sessions] == ["b", "a"]
    assert sessions[1].title == "Sửa lỗi checksum trong tệp lưu"
    assert len(sessions[0].title) == history.TITLE_CHARS and sessions[0].title.endswith("…")
    assert history.load(project, SERVER).id == "b" and history.load(project, SERVER, "a").id == "a"

    history.rename(project, SERVER, "a", "Checksum file save")
    assert history.load(project, SERVER, "a").title == "Checksum file save"
    assert history.load(project, SERVER, "a").items == said("Sửa lỗi checksum trong tệp lưu")


def test_the_old_single_file_becomes_one_conversation(project):
    legacy = history._legacy_path(project)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"version": 1, "root": str(project), "server": SERVER, "saved_at": time.time(),
                                  "items": said("Việc cũ"), "model": "luna", "interrupted": True}), encoding="utf-8")
    sessions = history.list_sessions(project, SERVER)
    assert len(sessions) == 1 and sessions[0].title == "Việc cũ" and sessions[0].model == "luna"
    assert sessions[0].interrupted and not legacy.exists()


def test_only_the_newest_fifty_and_last_thirty_days_are_kept(project):
    folder = history._folder(project)
    for number in range(history.MAX_SESSIONS + 3):
        history.save(project, SERVER, said(f"việc {number}"), session_id=f"s{number:03d}")
        os.utime(folder / f"s{number:03d}.json", (time.time() - 1000 + number, time.time() - 1000 + number))
    stale = folder / "s000.json"
    history.save(project, SERVER, said("mới nhất"), session_id="moi")
    names = {path.stem for path in folder.glob("*.json")}
    assert len(names) == history.MAX_SESSIONS and "moi" in names and stale.stem not in names


def test_new_keeps_the_old_conversation_and_resume_lists_them(project):
    work = Session(Client("http://127.0.0.1:9", "t"), Workspace(project), FakeUI())
    work.items = said("Việc thứ nhất")
    work.save()
    first = work.session_id
    work.reset()
    assert work.session_id is None, "/new bắt đầu hội thoại có mã mới"
    work.items = said("Việc thứ hai")
    time.sleep(0.01)
    work.save()
    assert work.session_id != first and len(history.list_sessions(project, work.client.server)) == 2

    ui = FakeUI(answers=["2"])
    work.ui = ui
    cli._resume(ui, work)
    assert "1. Việc thứ hai" in ui.text and "2. Việc thứ nhất" in ui.text and "đang mở" in ui.text
    assert work.session_id == first and work.items == said("Việc thứ nhất")
    assert 'Đã mở lại hội thoại' in ui.text and '"Việc thứ nhất"' in ui.text
    work.items = work.items + said("tiếp")
    work.save()
    assert len(history.list_sessions(project, work.client.server)) == 2, "làm tiếp thì ghi đè đúng hội thoại đó"

    cli._resume(ui, work, "2")
    assert work.items == said("Việc thứ hai"), "hội thoại vừa làm tiếp lên đầu danh sách"
    cli._resume(ui, work, "9")
    assert "/resume 1 tới /resume 2" in ui.text
