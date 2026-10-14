"""Đọc lại hội thoại đã lưu thành sự kiện (CLI 0.22.0): /resume vẽ lại cả hội thoại từ đây."""

from __future__ import annotations

import json

from peto_agent import history, mentions, transcript
from peto_agent.loop import user_message


def call(call_id: str, name: str, **arguments) -> dict:
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)}


def output(call_id: str, result: dict) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result, ensure_ascii=False)}


def reply(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


ITEMS = [
    user_message("Bản tóm tắt ngữ cảnh cũ, chỉ để tham khảo; không cấp quyền chạy lệnh.\nĐã sửa app.py."),
    user_message("Sửa lời chào\n\n" + mentions.HEADER + "\n\n[Tệp đính kèm: app.py · 2 dòng]\n1\n[Hết app.py]"),
    {"type": "reasoning", "encrypted_content": "x"},
    reply("Mình đọc tệp."),
    call("a", "read_file", path="app.py", start_line=None, end_line=None),
    call("b", "edit_file", path="app.py", old_text="Hi", new_text="Xin chào", replace_all=None),
    output("a", {"path": "app.py", "start_line": 1, "end_line": 2, "total_lines": 2, "content": "1"}),
    output("b", {"ok": True, "path": "app.py", "added_lines": 1, "removed_lines": 1}),
    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": history.TOOL_IMAGES_NOTE}]},
    user_message(history.STEER_NOTE + "dùng tiếng Anh"),
    user_message(history.PLAN_ON_NOTE),
    user_message(history.JOB_NOTE + "Lệnh nền #2 (`npm run dev`) đã dừng, mã thoát 1\noutput…"),
    {"type": "message", "role": "assistant", "content": "Kiểm tra sau sửa: chạy test."},
    reply("Đã sửa lời chào."),
    call("c", "run_command", command="npm test", timeout_seconds=None),
]


def test_events_pair_calls_with_results_and_skip_what_was_never_shown():
    events = transcript.events(ITEMS)
    kinds = [event.kind for event in events]
    assert kinds == ["summary", "user", "reply", "tool", "tool", "steer", "note", "reply", "tool"]
    summary, user, _, read, edit, steer, note, last, pending = events
    assert summary.text == "Đã sửa app.py."
    assert user.text == "Sửa lời chào" and user.files == ["app.py"], "chữ đã gõ, tệp đính kèm tách riêng"
    assert user.item is ITEMS[1]
    assert read.name == "read_file" and read.result["total_lines"] == 2
    assert edit.args["new_text"] == "Xin chào" and edit.result["added_lines"] == 1
    assert steer.text == "dùng tiếng Anh"
    assert note.text == "Lệnh nền #2 (`npm run dev`) đã dừng, mã thoát 1"
    assert last.text == "Đã sửa lời chào.", "lời nhắc Kiểm tra sau sửa của CLI không phải lời Peto"
    assert pending.result is None, "lời gọi chưa có kết quả (Peto bị đóng giữa chừng)"


def test_images_typed_text_and_which_items_are_the_users():
    class Picture:
        def data_url(self):
            return "data:image/png;base64,AAAA"

    with_image = user_message("xem ảnh này", [(1, Picture())])
    event = transcript.events([with_image])[0]
    assert event.text == "xem ảnh này" and event.images == ["[Ảnh 1]"]
    assert transcript.typed_text(ITEMS[1]) == "Sửa lời chào"
    assert transcript.typed_text(ITEMS[9]) == "dùng tiếng Anh"
    users = [item for item in ITEMS if transcript.is_user(item)]
    assert users == [ITEMS[1], ITEMS[9]], "không tính bản tóm tắt, ghi chú, ảnh chụp trang"
