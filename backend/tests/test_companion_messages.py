"""Trả lời (Reply) và Xóa một tin trong mạch Companion, như menu tin nhắn của AIRI (chủ web chọn đưa về 26/10/2026)."""
from pathlib import Path

import storage as db
from ai.mock import MockProvider
from features.companion import quotes
from features.companion.memory import MEMORY_MARKER, SUMMARY_MARKER
from storage import connection
from tests.conftest import TEST_OWNER, read_events, sign_in

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


async def turn(client, message: str, conversation: str | None = None, **extra) -> list[dict]:
    body = {"message": message, "mode": "companion", **extra}
    if conversation:
        body["conversation_id"] = conversation
    async with client.stream("POST", "/api/chat", json=body) as response:
        return await read_events(response)


def spy_inputs(monkeypatch) -> list[list]:
    """Tin gửi model ở mỗi lượt Companion (bỏ qua lượt trí nhớ và tóm tắt chạy nền)."""
    seen: list[list] = []
    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, **kwargs):
        if MEMORY_MARKER not in system_prompt and SUMMARY_MARKER not in system_prompt:
            seen.append(list(messages))
        async for chunk in original(self, system_prompt=system_prompt, messages=messages, **kwargs):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    return seen


async def test_done_carries_the_saved_reply_id(client):
    events = await turn(client, "chào Peto")
    done = events[-1]
    assert done["type"] == "done"
    stored = await db.get_messages(TEST_OWNER, events[0]["conversation_id"])
    assert done["message_id"] == stored[-1]["id"] and stored[-1]["role"] == "assistant"


async def test_a_reply_quotes_the_message_for_the_model_but_stores_the_plain_text(client, monkeypatch):
    first = await turn(client, "Chọn một số từ 1 tới 9 rồi nhớ nha __bimat__:số 7")
    conversation = first[0]["conversation_id"]
    reply_id = first[-1]["message_id"]
    seen = spy_inputs(monkeypatch)

    events = await turn(client, "ý bạn là sao?", conversation, quote_id=reply_id)
    assert events[-1]["type"] == "done"
    assert events[0]["message"]["quote_id"] == reply_id
    last_user = [item for item in seen[-1] if item.role == "user"][-1]
    # Câu trích là chữ người dùng thấy: không có ghi chú riêng của Peto.
    assert last_user.content == "[Replying to: Mình chọn xong rồi. Đoán đi!]\ný bạn là sao?"

    stored = await db.get_messages(TEST_OWNER, conversation)
    question = next(row for row in stored if row["content"] == "ý bạn là sao?")
    assert question["quote_id"] == reply_id
    history = (await client.get(f"/api/companion?conversation_id={conversation}")).json()["messages"]
    assert next(item for item in history if item["content"] == "ý bạn là sao?")["quote_id"] == reply_id


async def test_a_quote_from_another_thread_is_dropped_and_the_turn_still_goes(client):
    other = await turn(client, "mạch một")
    mine = await turn(client, "mạch hai", None, card_id="peto")
    events = await turn(client, "trả lời", mine[0]["conversation_id"], quote_id=other[-1]["message_id"])
    assert events[-1]["type"] == "done"
    assert "quote_id" not in events[0]["message"]


async def test_quote_is_companion_only(client):
    response = await client.post("/api/chat", json={"message": "hi", "quote_id": 1})
    assert response.status_code == 400


def test_long_quotes_are_cut_like_airi():
    target = {"role": "user", "content": "chữ " * 400}
    line = quotes.prefix(target, 9)
    assert line.startswith("[Replying to: chữ chữ") and line.endswith("…]\n")
    assert len(line) <= len("[Replying to: ]\n") + quotes.QUOTE_LIMIT
    assert quotes.prefix({"role": "user", "content": ""}, 9) == "[Replying to message: 9]\n"
    assert quotes.prefix(None, 9) == ""


async def test_delete_removes_one_message_and_its_images(client):
    events = await turn(client, "xem ảnh này", attachments=[{"name": "a.png", "mime": "image/png", "data": PNG}])
    conversation = events[0]["conversation_id"]
    user_id = events[0]["message"]["id"]
    async with connection.connect() as conn:
        file_path = (await (await conn.execute("SELECT path FROM attachments WHERE message_id=?", (user_id,))).fetchone())[0]
    assert Path(file_path).exists()
    before = [row["id"] for row in await db.get_messages(TEST_OWNER, conversation)]

    response = await client.delete(f"/api/companion/messages/{user_id}")
    assert response.status_code == 200 and response.json()["conversation_id"] == conversation
    remaining = [row["id"] for row in await db.get_messages(TEST_OWNER, conversation)]
    assert remaining == [item for item in before if item != user_id]
    assert not Path(file_path).exists()
    assert (await client.delete(f"/api/companion/messages/{user_id}")).status_code == 404


async def test_delete_is_owner_scoped_and_companion_only(client):
    events = await turn(client, "của mình")
    message_id = events[0]["message"]["id"]
    async with client.stream("POST", "/api/chat", json={"message": "tab Trò chuyện"}) as response:
        chat = await read_events(response)
    assert (await client.delete(f"/api/companion/messages/{chat[0]['message']['id']}")).status_code == 404

    await sign_in(client)
    assert (await client.delete(f"/api/companion/messages/{message_id}")).status_code == 404


async def test_delete_waits_for_a_running_turn(client):
    events = await turn(client, "chào")
    conversation = events[0]["conversation_id"]
    async with connection.connect() as conn:
        await conn.execute("INSERT INTO chat_turns(owner,request_id,state,conversation_id,created_at) VALUES(?,?,?,?,0)",
                           (TEST_OWNER, "running-turn-0000001", "running", conversation))
        await conn.commit()
    response = await client.delete(f"/api/companion/messages/{events[0]['message']['id']}")
    assert response.status_code == 409


async def test_delete_inside_the_summary_forgets_the_summary(client):
    first = await turn(client, "bí mật cũ")
    conversation = first[0]["conversation_id"]
    await turn(client, "tin sau", conversation)
    async with connection.connect() as conn:
        await conn.execute("INSERT INTO companion_summaries(conversation_id,owner,text,upto,updated_at) VALUES(?,?,?,?,0)",
                           (conversation, TEST_OWNER, "Người dùng kể bí mật cũ.", first[-1]["message_id"]))
        await conn.commit()
    await client.delete(f"/api/companion/messages/{first[0]['message']['id']}")
    async with connection.connect() as conn:
        text, upto = await (await conn.execute("SELECT text, upto FROM companion_summaries WHERE conversation_id=?",
                                               (conversation,))).fetchone()
        latest = (await (await conn.execute("SELECT MAX(id) FROM messages WHERE conversation_id=?", (conversation,))).fetchone())[0]
    assert text == "" and upto == latest


async def test_delete_after_the_summary_keeps_it(client):
    first = await turn(client, "tin đầu")
    conversation = first[0]["conversation_id"]
    later = await turn(client, "tin sau", conversation)
    async with connection.connect() as conn:
        await conn.execute("INSERT INTO companion_summaries(conversation_id,owner,text,upto,updated_at) VALUES(?,?,?,?,0)",
                           (conversation, TEST_OWNER, "Tóm tắt.", first[-1]["message_id"]))
        await conn.commit()
    await client.delete(f"/api/companion/messages/{later[-1]['message_id']}")
    async with connection.connect() as conn:
        text, = await (await conn.execute("SELECT text FROM companion_summaries WHERE conversation_id=?", (conversation,))).fetchone()
    assert text == "Tóm tắt."
