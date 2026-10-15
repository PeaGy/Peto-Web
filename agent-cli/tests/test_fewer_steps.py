"""CLI 0.25.0 (theo lõi opencode, chủ web chọn ngày 2026-10-15): những chỗ bớt được bước.

Nhật ký thật của chủ web: 88/269 lần read_file bị cắt ở 160 dòng, 11 lần sửa bị từ chối vì chưa đọc (mỗi lần mất một
bước), 2 lần rớt mạng phải tự gõ /retry, và một yêu cầu dài tới 39 bước, sát mức 40.
"""

from __future__ import annotations

import copy
import json

import pytest
from conftest import FakeUI

from peto_agent import loop
from peto_agent.client import ApiError
from peto_agent.loop import Session
from peto_agent.tools import FEATURES, NEW_FEATURES, READ_MORE_CHARS, Tools
from peto_agent.workspace import Workspace


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def make(project, answers=(), *, more=True) -> Tools:
    tools = Tools(Workspace(project), FakeUI(answers))
    tools.features = [*FEATURES, "explore_v2", "edit_v2", *(["read_more"] if more else [])]
    return tools


# ---- Đọc tới 1000 dòng mỗi lần

def test_read_more_reads_a_medium_file_whole_in_one_call(project):
    (project / "app.py").write_text("".join(f"x{n} = {n}\n" for n in range(1, 401)), encoding="utf-8")
    result = make(project).read_file("app.py")
    assert result["end_line"] == 400 and "truncated" not in result
    old = make(project, more=False).read_file("app.py")
    assert old["end_line"] == 160 and old["next_start_line"] == 161, "CLI với máy chủ cũ giữ cách cũ"


def test_read_more_stops_at_a_line_boundary_by_characters_and_lines(project):
    (project / "wide.txt").write_text("".join("y" * 99 + "\n" for _ in range(600)), encoding="utf-8")
    result = make(project).read_file("wide.txt")
    content = result["content"]
    assert len(content) <= READ_MORE_CHARS and result["truncated"] is True
    assert content.split("\n")[-1].endswith("y" * 99), "không cắt giữa dòng"
    assert result["next_start_line"] == result["end_line"] + 1
    (project / "long.txt").write_text("".join(f"{n}\n" for n in range(1, 1501)), encoding="utf-8")
    assert make(project).read_file("long.txt")["end_line"] == 1000
    assert make(project).read_file("long.txt", 1001)["end_line"] == 1500


def test_a_minified_line_is_cut_and_the_result_is_not_cut_again_in_the_middle(project):
    (project / "min.js").write_text("a" * 50_000 + "\nb\n", encoding="utf-8")
    tools = make(project)
    raw = tools.call("read_file", args(path="min.js", start_line=None, end_line=None))
    assert "dài 50000 ký tự, đã cắt" in raw["content"]
    capped = loop.cap_result(raw, loop.READ_BOUNDED_KEYS)
    assert capped["content"] == raw["content"], "nội dung đọc đã tự giới hạn, cap_text không cắt phần giữa nữa"
    assert "bỏ bớt" in loop.cap_result({"output": "z" * 30_000})["output"], "kết quả khác vẫn bị cắt như cũ"


def test_new_features_are_offered_to_the_server():
    assert {"read_more", "output_files", "wrapup", "user_guide"} <= set(NEW_FEATURES)


# ---- Sửa tệp chưa đọc: từ chối kèm nội dung

def test_editing_an_unread_file_returns_its_content_and_the_next_edit_succeeds(project):
    (project / "app.py").write_text("def greet(name):\n    print('Hi ' + name)\n", encoding="utf-8")
    tools = make(project, ["y"])
    edit = args(path="app.py", old_text="print('Hi ' + name)", new_text="print(f'Xin chào {name}')",
                replace_all=None)
    refused = tools.call("edit_file", edit)
    assert "chưa được đọc" in refused["error"] and "current" in refused
    assert "     2\t    print('Hi ' + name)" in refused["current"]["content"], "có số dòng như read_file"
    assert (project / "app.py").read_text(encoding="utf-8").count("Hi ") == 1, "chưa sửa gì"
    assert "Chưa đọc app.py · đã gửi nội dung cho Peto" in tools.ui.text
    again = tools.call("edit_file", args(path="app.py", old_text="def greet(name):", new_text="def greet(who):",
                                         replace_all=None))
    assert "error" in again and "current" not in again, "lần sửa sau trong cùng bước viết khi chưa thấy tệp"
    tools.start_step()
    assert tools.call("edit_file", edit)["ok"] is True, "bước sau sửa được ngay, không cần đọc thêm"


def test_a_file_changed_since_reading_is_sent_again(project):
    target = project / "app.py"
    target.write_text("a = 1\n", encoding="utf-8")
    tools = make(project, ["y"])
    tools.read_file("app.py")
    target.write_text("a = 2\n", encoding="utf-8")
    refused = tools.call("edit_file", args(path="app.py", old_text="a = 1", new_text="a = 3", replace_all=None))
    assert "đã thay đổi kể từ lần đọc" in refused["error"] and "a = 2" in refused["current"]["content"]
    assert "app.py vừa đổi" in tools.ui.text


def test_the_window_centres_on_the_text_being_edited(project):
    lines = [f"line {n}" for n in range(1, 1601)]
    (project / "big.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refused = make(project).call("edit_file", args(path="big.txt", old_text="line 1500", new_text="x",
                                                   replace_all=None))
    current = refused["current"]
    assert current["start_line"] == 1460 and "line 1500" in current["content"]


def test_overwriting_an_unread_file_returns_its_content(project):
    (project / "notes.md").write_text("cũ\n", encoding="utf-8")
    refused = make(project).call("write_file", args(path="notes.md", content="mới\n"))
    assert "chưa ghi đè" in refused["error"] and "edit_file" in refused["error"]
    assert "cũ" in refused["current"]["content"]
    assert (project / "notes.md").read_text(encoding="utf-8") == "cũ\n"


def test_a_patch_with_unread_files_returns_two_contents_and_writes_nothing(project):
    for name in ("a.py", "b.py", "c.py"):
        (project / name).write_text(f"{name} = 1\n", encoding="utf-8")
    tools = make(project, ["y"])
    tools.features.append("patch")
    patch = "*** Begin Patch\n" + "".join(
        f"*** Update File: {name}\n@@\n-{name} = 1\n+{name} = 2\n" for name in ("a.py", "b.py", "c.py")
    ) + "*** Add File: d.py\n+d = 1\n*** End Patch"
    refused = tools.call("apply_patch", args(patch_text=patch))
    assert "a.py, b.py, c.py" in refused["error"] and "chưa ghi tệp nào" in refused["error"]
    assert [item["path"] for item in refused["current"]] == ["a.py", "b.py"]
    assert not (project / "d.py").exists()
    tools.start_step()
    tools.read_file("c.py")
    assert tools.call("apply_patch", args(patch_text=patch))["ok"] is True
    assert (project / "a.py").read_text(encoding="utf-8") == "a.py = 2\n"


# ---- Tự thử lại khi rớt mạng

def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


class Client:
    """Máy chủ giả: mỗi phần tử là danh sách sự kiện SSE, hoặc một exception ném ra trước sự kiện đầu tiên."""

    server = "https://example.test"

    def __init__(self, replies):
        self.replies = list(replies)
        self.bodies = []

    def stream(self, path, body, **kwargs):
        self.bodies.append(copy.deepcopy(body))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        for event in reply:
            if isinstance(event, BaseException):
                raise event
            yield event


def done(text="Xong.", purpose=None):
    # Như máy chủ thật: chữ tới bằng delta, rồi done mang cả câu trả lời.
    return [{"type": "meta", "steps_used": 1, "steps_limit": 200}, {"type": "delta", "text": text + "\n"},
            {"type": "done", "output": [message(text)], "usage": {}, **({"purpose": purpose} if purpose else {})}]


@pytest.fixture
def quick_retries(monkeypatch):
    waits = []
    monkeypatch.setattr(loop, "RETRY_WAITS", (0.01, 0.01, 0.01))
    real = loop.Session._log

    def log(self, kind, **fields):
        if kind == "retry_auto":
            waits.append(fields)
        return real(self, kind, **fields)
    monkeypatch.setattr(loop.Session, "_log", log)
    return waits


def session(project, replies, features=("wrapup",)):
    work = Session(Client(replies), Workspace(project), FakeUI())
    work.tools.features = [*FEATURES, *features]
    work.auto_title = False
    return work


def test_connection_failures_before_any_event_are_retried(project, quick_retries):
    work = session(project, [ApiError(0, "Không kết nối được máy chủ Peto."), ApiError(503, "bận"), done()])
    work.run_task("chào")
    assert len(work.client.bodies) == 3 and len(quick_retries) == 2
    assert not work.can_retry and "Xong." in work.ui.text
    assert "Không kết nối được" not in work.ui.text, "lần thử lại thành công thì không in lỗi"


def test_a_refunded_transient_error_is_retried(project, quick_retries):
    error = [{"type": "meta", "steps_used": 1}, {"type": "error", "message": "Mô hình gặp lỗi ở bước này. Thử lại nhé.",
                                                 "retryable": True}]
    work = session(project, [error, done()])
    work.run_task("chào")
    assert len(work.client.bodies) == 2 and quick_retries[0]["message"].startswith("Mô hình gặp lỗi")


def test_errors_that_may_have_cost_a_step_still_need_retry(project, quick_retries):
    dropped = [{"type": "meta", "steps_used": 1}, {"type": "delta", "text": "Đang"}, ApiError(0, "Mất kết nối.")]
    work = session(project, [dropped])
    work.run_task("chào")
    assert len(work.client.bodies) == 1 and not quick_retries and work.can_retry, "đã có chữ: giữ /retry"
    lasting = [{"type": "meta", "steps_used": 1}, {"type": "error", "message": "Khóa hết hạn."}]
    work = session(project, [lasting])
    work.run_task("chào")
    assert len(work.client.bodies) == 1 and "Khóa hết hạn." in work.ui.text


def test_retries_give_up_after_three_and_show_the_error(project, quick_retries):
    work = session(project, [ApiError(0, "Không kết nối được máy chủ Peto.")] * 4)
    work.run_task("chào")
    assert len(work.client.bodies) == 4 and len(quick_retries) == 3
    assert "Không kết nối được máy chủ Peto." in work.ui.text and work.can_retry


def test_ctrl_c_while_waiting_stops_the_request(project, monkeypatch):
    monkeypatch.setattr(loop, "RETRY_WAITS", (5, 5, 5))

    def interrupted(seconds):
        raise KeyboardInterrupt
    monkeypatch.setattr(loop.time, "sleep", interrupted)
    work = session(project, [ApiError(0, "Không kết nối được.")])
    work.run_task("chào")
    assert "Đã dừng yêu cầu" in work.ui.text and len(work.client.bodies) == 1


# ---- Hết bước: lượt tóm tắt

def test_the_step_limit_ends_with_a_wrapup_turn(project, monkeypatch):
    monkeypatch.setattr(loop, "MAX_STEPS_PER_TASK", 2)
    call = {"type": "function_call", "call_id": "1", "name": "list_files", "arguments": args(path=".", depth=None)}
    working = [{"type": "meta", "steps_used": 1}, {"type": "done", "output": [call], "usage": {}}]
    work = session(project, [copy.deepcopy(working), copy.deepcopy(working),
                             done("Đã chạm giới hạn bước; còn lại: viết test.", "wrapup")])
    work.run_task("làm việc dài")
    wrapup = work.client.bodies[-1]
    assert wrapup["context"]["purpose"] == "wrapup"
    assert wrapup["input"][-1]["type"] == "function_call_output", "lời gọi cuối đã có kết quả"
    assert "còn lại: viết test" in work.ui.text and 'Gõ "làm tiếp"' in work.ui.text
    assert work.items[-1]["content"][0]["text"].startswith("Đã chạm giới hạn")


def test_an_old_server_gets_no_wrapup_turn(project, monkeypatch):
    monkeypatch.setattr(loop, "MAX_STEPS_PER_TASK", 1)
    call = {"type": "function_call", "call_id": "1", "name": "list_files", "arguments": args(path=".", depth=None)}
    work = session(project, [[{"type": "done", "output": [call], "usage": {}}]], features=())
    work.run_task("làm việc dài")
    assert len(work.client.bodies) == 1 and 'Gõ "làm tiếp"' in work.ui.text
