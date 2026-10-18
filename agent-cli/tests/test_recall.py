"""Hồi quy từ phiên radio: mất yêu cầu gốc, mất bằng chứng và nhầm tóm tắt là lời người dùng."""

import copy
import json

import pytest
from conftest import FakeUI, handoff
from test_agent_workflow import Client, message

from peto_agent import history, recall
from peto_agent.loop import Session, user_message
from peto_agent.workspace import Workspace, WorkspaceError


def old_steps():
    return [message("Đã xem mẫu và thử bộ đọc. " * 20) for _ in range(30)]


def test_repeated_compaction_retains_goal_correction_and_failure_verbatim(project):
    goal = "Đưa 20 bài vào các đài, giữ bản sao lưu và phải nghe được trong game."
    correction = "Thay cả các đài nói chuyện, không dùng đài nhạc người dùng thay thế."
    failure = "Tôi vừa vào game, vẫn không có bài nào phát."
    work = Session(Client([[message(handoff("Đã sửa tệp; chưa xác nhận trong game."))]] * 2), Workspace(project), FakeUI())
    work.items = [user_message(goal), *old_steps(), user_message(correction), user_message(failure),
                  *old_steps(), user_message("làm tiếp")]
    assert work.compact()
    work.items += old_steps() + [user_message("làm tiếp")]
    assert work.compact()
    texts = [history.raw_text(item) for item in work.items if item.get("role") == "user" and not history.is_note(item)]
    assert goal in texts and correction in texts and failure in texts
    assert not any(text.startswith(history.SUMMARY_NOTE) for text in texts)
    assert history.is_note(work.items[0])
    assert len(list(recall.folder(project, work.session_id).glob("*.json"))) == 2


def test_complete_old_reply_and_tool_result_can_be_recovered_after_resume(project):
    reply = "đầu\n" + "một đoạn không có trong nhật ký rút gọn\n" * 600 + "CUỐI"
    result = json.dumps({"output": "đầu\n" + "chi tiết\n" * 6000 + "KẾT THÚC", "exit_code": 1}, ensure_ascii=False)
    work = Session(Client([[message(handoff("Chưa đạt kết quả; cần kiểm tra bộ đọc độc lập."))]]), Workspace(project), FakeUI())
    work.tools.features.append("recall")
    work.items = [user_message("Tạo tệp mà ứng dụng đọc được."), message(reply),
                  {"type": "function_call", "call_id": "reader", "name": "run_command", "arguments": "{}"},
                  {"type": "function_call_output", "call_id": "reader", "output": result},
                  *old_steps()]
    assert work.compact()
    saved = history.load(project, work.client.server)
    resumed = Session(Client(), Workspace(project), FakeUI())
    resumed.tools.features.append("recall")
    resumed.resume(saved.items, session_id=saved.id)
    found = resumed.tools.read_history("nhật ký rút gọn")
    assert json.loads(found["entries"][0]["content"])["content"] == reply
    found = resumed.tools.read_history("KẾT THÚC")
    entry = found["entries"][0]
    chunks = [entry["content"]]
    while entry["truncated"]:
        entry = resumed.tools.read_history(None, entry["entry"], entry["next_character"])["entries"][0]
        chunks.append(entry["content"])
    assert json.loads("".join(chunks))["output"] == result


def test_archive_failure_preserves_original_context(project, monkeypatch):
    work = Session(Client([[message(handoff())]]), Workspace(project), FakeUI())
    work.items = [user_message("Yêu cầu không được mất."), *old_steps()]
    original = copy.deepcopy(work.items)
    def fail(*args, **kwargs):
        raise OSError("Ổ đĩa đầy.")
    monkeypatch.setattr(recall, "preserve", fail)
    assert not work.compact()
    assert work.items == original
    assert "giữ nguyên hội thoại" in work.ui.text


def test_archive_is_scoped_and_does_not_persist_private_reasoning_or_image_bytes(project):
    items = [user_message("yêu cầu"), {"type": "reasoning", "encrypted_content": "không lưu"},
             {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "ảnh mẫu"},
                 {"type": "input_image", "image_url": "data:image/png;base64,KHONGLUUANH"}]}]
    recall.preserve(project, "https://one.test", "session", items)
    raw = next(recall.folder(project, "session").glob("*.json")).read_text(encoding="utf-8")
    assert "encrypted_content" not in raw and "KHONGLUUANH" not in raw
    with pytest.raises(WorkspaceError, match="không thuộc"):
        recall.read(project, "https://two.test", "session")
    with pytest.raises(WorkspaceError, match="không hợp lệ"):
        recall.read(project, "https://one.test", "../session")


def test_deleting_a_conversation_removes_only_its_archive(project):
    server = "https://example.test"
    for sid in ("first", "second"):
        history.save(project, server, [user_message(sid)], session_id=sid)
        recall.preserve(project, server, sid, [user_message(sid)])
    assert history.delete(project, server, "first")
    assert not recall.folder(project, "first").exists()
    assert recall.read(project, server, "second")["entries"]


def test_check_observations_preserve_failure_without_claiming_success(project, monkeypatch):
    work = Session(Client(), Workspace(project), FakeUI(["a"]))
    work.tools.features.append("recall")
    monkeypatch.setattr("peto_agent.runner.run", lambda *a, **kw: {"exit_code": 1, "output": "Một test lỗi.", "seconds": 0})
    work.tools.run_command("python -m unittest")
    context = work._step_context()["check_observations"]
    assert context["observations"][-1]["classification"] == "check_failed"
    assert context["recent_commands"][-1]["exit_code"] == 1
    work.tools.reset_task()
    assert work._step_context()["check_observations"] == {
        "current_revision": 0, "observations": [], "recent_commands": []}


def test_check_from_before_an_edit_is_not_presented_as_current_evidence(project):
    work = Session(Client(), Workspace(project), FakeUI(["a"]))
    work.tools.features.append("recall")
    work.tools._checked({"classification": "passed", "exit_code": 0})
    work.tools.write_file("changed.py", "print('đã đổi')\n")
    facts = work._step_context()["check_observations"]
    assert facts["observations"][-1]["revision"] < facts["current_revision"]


def test_non_code_changes_receive_behavioral_verification_reminder(project):
    work = Session(Client(), Workspace(project), FakeUI())
    work.tools.changes["radio.bin"] = [1, 0]
    work.tools.revision = 1
    assert work._remind_to_check()
    text = history.raw_text(work.items[-1])
    assert "bộ đọc độc lập" in text and "chưa chứng minh ứng dụng dùng được" in text
    assert "đưa bước thử cụ thể" in text
