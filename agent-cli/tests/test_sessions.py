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


def test_delete_and_rename_keep_to_this_folder_and_keep_the_save_time(project, tmp_path):
    history.save(project, SERVER, said("Việc một"), session_id="20261014-090000-aaaaaa")
    history.save(project, SERVER, said("Việc hai"), session_id="20261014-091000-bbbbbb")
    before = history.load(project, SERVER, "20261014-090000-aaaaaa").saved_at
    time.sleep(0.01)
    history.rename(project, SERVER, "20261014-090000-aaaaaa", "Tên mới")
    assert history.load(project, SERVER, "20261014-090000-aaaaaa").saved_at == before, \
        "đổi tên không đẩy hội thoại lên đầu danh sách"
    other = tmp_path / "khac"
    other.mkdir()
    assert not history.delete(other, SERVER, "20261014-090000-aaaaaa"), "thư mục khác không xóa được"
    assert not history.delete(project, "https://khac.example", "20261014-090000-aaaaaa"), "máy chủ khác cũng không"
    assert history.delete(project, SERVER, "20261014-090000-aaaaaa")
    assert not history.delete(project, SERVER, "20261014-090000-aaaaaa"), "xóa rồi thì không còn gì để xóa"
    assert [saved.id for saved in history.list_sessions(project, SERVER)] == ["20261014-091000-bbbbbb"]
    assert history.valid_id(history.new_id()) and history.valid_id("20261014-091000-bbbbbb")
    for bad in ("", "..\\..\\x", "../x","20261014-091000-bbbbbb.json", "20261014-091000-BBBBBB", "a"):
        assert not history.valid_id(bad), bad


def test_fork_starts_a_new_conversation_from_before_the_chosen_message(project):
    work = Session(Client(SERVER, "t"), Workspace(project), FakeUI())
    work.items = said("Việc một") + said("Việc hai") + said("Việc ba")
    work.title = "Ba việc"
    work.save()
    first = work.session_id
    ui = FakeUI(answers=["2"])
    work.ui = ui
    cli._timeline(ui, work, fork=True)
    assert "1. Việc một" in ui.text and "3. Việc ba" in ui.text
    assert work.items == said("Việc một") and work.session_id not in {None, first}
    assert work.title == "Ba việc (nhánh)" and 'Đã tách thành hội thoại mới "Ba việc (nhánh)"' in ui.text
    assert "Việc hai" in ui.text.split("Chữ của tin đó")[1], "chữ của tin được chọn để gửi lại"
    saved = {saved.id: saved for saved in history.list_sessions(project, SERVER)}
    assert saved[first].items == said("Việc một") + said("Việc hai") + said("Việc ba"), "hội thoại cũ giữ nguyên"
    assert saved[work.session_id].title == "Ba việc (nhánh)"


def test_timeline_copies_a_message_or_forks_from_it(project):
    work = Session(Client(SERVER, "t"), Workspace(project), FakeUI())
    ui = FakeUI()
    work.ui = ui
    cli._timeline(ui, work)
    assert "chưa có tin nào của bạn" in ui.text
    work.items = said("Việc một") + said("Việc hai")
    ui = FakeUI(answers=["1", "1"])
    work.ui = ui
    cli._timeline(ui, work)
    assert "Nhảy tới" not in ui.text, "bản in chữ không cuộn được nên không có Nhảy tới"
    assert "Chữ của tin đó" in ui.text and "Việc một" in ui.text.split("Chữ của tin đó")[1], \
        "không chép được vào clipboard thì in ra"
    assert work.items == said("Việc một") + said("Việc hai")
    ui = FakeUI(answers=["2", "2"])
    work.ui = ui
    cli._timeline(ui, work)
    assert work.items == said("Việc một"), "Tách hội thoại từ đây"
