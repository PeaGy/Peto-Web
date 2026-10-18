"""Chế độ nhập vai đã bỏ ngày 2026-10-18 (chủ web: đã có Companion). Không mở được hội thoại nhập vai mới; hội thoại cũ
chỉ còn để xem: không nhắn tiếp, không tách phiên bản, không đổi model, vì lịch sử có thể có nội dung 18+ và không được
gửi tới model nào. Xem, đổi tên, lưu trữ và xóa vẫn được."""

from __future__ import annotations

import storage as db
from conftest import TEST_OWNER, read_events
from features.chat import conversations as conversation_actions
from features.chat import service as chat_service


async def test_new_roleplay_chats_are_refused_with_a_clear_message(client):
    for mode in ("chat", "companion"):
        response = await client.post("/api/chat", json={"message": "chào", "persona": "roleplay", "mode": mode})
        assert response.status_code == 400 and response.json()["detail"] == chat_service.ROLEPLAY_REMOVED
    assert (await client.post("/api/profile/roleplay-consent")).status_code in {404, 405}
    assert "roleplay_confirmed" not in (await client.get("/api/auth/me")).json()["user"]
    # Trang cũ mặc định vẫn gửi persona "assistant": chat bình thường.
    events = await read_events(await client.post("/api/chat", json={"message": "chào", "persona": "assistant"}))
    assert events[-1]["type"] == "done"


async def test_old_roleplay_chats_stay_readable_but_never_continue(client):
    old = await db.create_conversation(TEST_OWNER, persona="roleplay")
    question = await db.add_message(old, "user", "*ngồi xuống cạnh Peto* kể chuyện đi")
    await db.add_message(old, "assistant", "Ngày xửa ngày xưa…")

    listed = {item["id"]: item["persona"] for item in (await client.get("/api/conversations")).json()["conversations"]}
    assert listed[old] == "roleplay", "danh sách vẫn đánh dấu để trang hiện nhãn và khóa ô nhắn"
    history = (await client.get(f"/api/conversations/{old}/messages")).json()
    assert history["persona"] == "roleplay" and [row["content"] for row in history["messages"]] == [
        "*ngồi xuống cạnh Peto* kể chuyện đi", "Ngày xửa ngày xưa…"]

    for body in ({"message": "kể tiếp đi", "conversation_id": old},
                 {"message": "kể lại", "conversation_id": old, "branch_message_id": question}):
        response = await client.post("/api/chat", json=body)
        assert response.status_code == 409 and response.json()["detail"] == conversation_actions.LEGACY_ROLEPLAY
    assert (await client.patch(f"/api/conversations/{old}", json={"model": "peto", "effort": "low"})).status_code == 409
    assert len((await db.get_messages(TEST_OWNER, old))) == 2, "không có tin nào được thêm"

    assert (await client.patch(f"/api/conversations/{old}", json={"title": "Truyện cũ"})).status_code == 200
    assert (await client.patch(f"/api/conversations/{old}", json={"archived": True})).status_code == 200
    assert (await client.delete(f"/api/conversations/{old}")).status_code == 200
    assert await db.conversation_settings(TEST_OWNER, old) is None


async def test_chat_prompts_carry_no_roleplay_persona(client, monkeypatch):
    seen: list[str] = []

    class Spy:
        async def stream(self, **kwargs):
            seen.append(kwargs["system_prompt"])
            yield "Chào bạn."

    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": Spy())
    await read_events(await client.post("/api/chat", json={"message": "*ngồi xuống cạnh Peto* hôm nay mệt ghê"}))
    prompt = next(text for text in seen if "## Identity and communication" in text)
    assert "never sexual roleplay" in prompt
    for leftover in ("Cảm giác hiện diện", "20 tuổi", "18+", "*Peto nghiêng đầu"):
        assert leftover not in prompt
