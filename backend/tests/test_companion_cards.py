"""Thẻ nhân vật Companion theo AIRI: thẻ Peto mặc định công khai và sửa được, thẻ tự viết làm persona, mỗi mạch giữ
thẻ lúc tạo, câu chào đầu, quy tắc cố định, trí nhớ chung chỉ cho thẻ mặc định, cô lập theo tài khoản."""
import pytest

import storage as db
from ai.mock import MockProvider
from features.chat import titles
from features.companion import cards as companion_cards
from features.companion import memory as companion_memory
from features.companion.memory import MEMORY_MARKER, SUMMARY_MARKER
from prompts import COMPANION_CARD_RULE, COMPANION_SYSTEM_PROMPT
from prompts.companion import COMPANION_PERSONA_PROMPT
from tests.conftest import read_events, sign_in


@pytest.fixture
async def owner(client):
    """Tài khoản mới cho mỗi test: chưa có thẻ, chưa có mạch Companion."""
    companion_memory._pending_until.clear()
    return await sign_in(client)


@pytest.fixture
def prompts(monkeypatch):
    seen: list[str] = []
    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, **kwargs):
        if not any(marker in system_prompt for marker in (MEMORY_MARKER, SUMMARY_MARKER, titles.TITLE_MARKER)):
            seen.append(system_prompt)
        async for chunk in original(self, system_prompt=system_prompt, messages=messages, **kwargs):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    return seen


async def send(client, message: str, **extra) -> list[dict]:
    async with client.stream("POST", "/api/chat", json={"message": message, "mode": "companion", **extra}) as response:
        assert response.status_code == 200, await response.aread()
        events = await read_events(response)
    assert events[-1]["type"] == "done", events
    return events


async def create(client, **fields) -> dict:
    response = await client.post("/api/companion/cards", json={"name": "Mika", **fields})
    assert response.status_code == 201, response.text
    return response.json()


async def test_every_account_starts_with_the_public_default_peto_card(client, owner):
    body = (await client.get("/api/companion/cards")).json()
    assert body["active_card"] == "peto"
    [card] = body["cards"]
    assert (card["id"], card["name"], card["is_default"], card["modified"]) == ("peto", "Peto", True, False)
    # Prompt Companion gốc công khai nguyên văn, có cả phần thẻ cảm xúc để người dùng học cách viết thẻ.
    assert card["system_prompt"] == COMPANION_SYSTEM_PROMPT
    assert "<|EMOTE_HAPPY|>" in card["system_prompt"]
    assert card["display_model"] == "hiyori"


async def test_default_card_turn_keeps_the_original_prompt_and_adds_the_fixed_rule(client, owner, prompts):
    await send(client, "hi")
    [prompt] = prompts
    assert prompt.startswith(COMPANION_PERSONA_PROMPT)
    # Quy tắc cố định sau mọi phần của thẻ và của máy chủ; chỉ khối giờ của từng lượt đứng sau nó.
    assert prompt.index("## Current user") < prompt.index(COMPANION_CARD_RULE)
    assert prompt.split(COMPANION_CARD_RULE)[1].strip().startswith("## Server-verified current time")


async def test_custom_card_becomes_the_persona_with_macros_and_post_history_last(client, owner, prompts):
    card = await create(client, nickname="Mi", system_prompt="You are {{char}}, talking with {{USER}}.",
                        description="A sleepy fox spirit.", personality="Lazy, kind.", scenario="A tea shop at night.",
                        post_history="Stay as {{char}}.")
    assert (await client.put("/api/companion/cards/active", json={"card_id": card["id"]})).status_code == 200
    await send(client, "hello")
    [prompt] = prompts
    assert prompt.startswith("You are Mi, talking with Người Mới.\n\nA sleepy fox spirit.\n\nLazy, kind.\n\nA tea shop at night.")
    assert COMPANION_PERSONA_PROMPT not in prompt
    # Hướng dẫn sau lịch sử rồi quy tắc cố định, sau mọi phần máy chủ tự thêm (chỉ khối giờ đứng sau).
    assert "Stay as Mi.\n\n" + COMPANION_CARD_RULE in prompt
    assert prompt.index("## Current user") < prompt.index("Stay as Mi.")


async def test_a_conversation_keeps_its_card_after_switching_cards(client, owner, prompts):
    card = await create(client, system_prompt="I am Mika.")
    await client.put("/api/companion/cards/active", json={"card_id": card["id"]})
    events = await send(client, "first")
    conversation_id = events[0]["conversation_id"]
    await client.put("/api/companion/cards/active", json={"card_id": "peto"})
    await send(client, "second", conversation_id=conversation_id)
    assert prompts[1].startswith("I am Mika.")
    # Mạch mới (không gửi conversation_id) theo thẻ đang dùng.
    await send(client, "third")
    assert prompts[2].startswith(COMPANION_PERSONA_PROMPT)


async def test_new_conversation_opens_with_the_card_greeting_and_becomes_active(client, owner):
    card = await create(client, greetings=["Hi {{user}}, I'm {{char}}!", "Alt greeting"])
    response = await client.post("/api/companion/conversations", json={"card_id": card["id"]})
    assert response.status_code == 200
    thread = response.json()
    assert thread["card_id"] == card["id"]
    [greeting] = thread["messages"]
    assert (greeting["role"], greeting["content"]) == ("assistant", "Hi Người Mới, I'm Mika!")
    current = (await client.get("/api/companion")).json()
    assert (current["conversation_id"], current["card_id"]) == (thread["conversation_id"], card["id"])
    listed = (await client.get("/api/companion/conversations")).json()
    [item] = listed["conversations"]
    assert (item["card_name"], item["active"], listed["active_card"]) == ("Mika", True, card["id"])


async def test_opening_an_old_conversation_switches_to_its_card(client, owner):
    card = await create(client)
    peto_thread = (await client.post("/api/companion/conversations", json={})).json()
    mika_thread = (await client.post("/api/companion/conversations", json={"card_id": card["id"]})).json()
    assert (await client.get("/api/companion/cards")).json()["active_card"] == card["id"]
    response = await client.put("/api/companion/active", json={"conversation_id": peto_thread["conversation_id"]})
    assert response.json() == {"conversation_id": peto_thread["conversation_id"], "card_id": "peto"}
    current = (await client.get("/api/companion")).json()
    assert (current["conversation_id"], current["card_id"]) == (peto_thread["conversation_id"], "peto")
    # Mỗi thẻ nhớ mạch đang mở của mình.
    await client.put("/api/companion/cards/active", json={"card_id": card["id"]})
    assert (await client.get("/api/companion")).json()["conversation_id"] == mika_thread["conversation_id"]
    asked = (await client.get("/api/companion", params={"conversation_id": peto_thread["conversation_id"]})).json()
    assert asked["card_id"] == "peto"


async def test_default_card_edits_and_restore(client, owner, prompts):
    edited = (await client.patch("/api/companion/cards/peto", json={"system_prompt": "Custom Peto."})).json()
    assert (edited["system_prompt"], edited["modified"]) == ("Custom Peto.", True)
    await send(client, "hi")
    assert prompts[0].startswith("Custom Peto.")
    # Gửi lại đúng bản gốc thì thẻ lại theo bản gốc của máy chủ.
    same = (await client.patch("/api/companion/cards/peto", json={"system_prompt": COMPANION_SYSTEM_PROMPT})).json()
    assert same["modified"] is False
    await client.patch("/api/companion/cards/peto", json={"name": "Peto ơi"})
    restored = (await client.post("/api/companion/cards/peto/reset")).json()
    assert (restored["name"], restored["modified"]) == ("Peto", False)


async def test_card_validation(client, owner, monkeypatch):
    assert (await client.post("/api/companion/cards", json={"name": "  "})).status_code == 400
    assert (await client.post("/api/companion/cards", json={"name": "Peto"})).status_code == 409
    assert (await client.post("/api/companion/cards", json={"name": "A", "personality": 5})).status_code == 400
    long = "x" * (companion_cards.LIMITS["personality"] + 1)
    response = await client.post("/api/companion/cards", json={"name": "A", "personality": long})
    assert response.status_code == 400 and "Tính cách" in response.json()["detail"]
    response = await client.post("/api/companion/cards", json={"name": "A", "modules": {"brain": {"provider": "openai", "key": "x"}}})
    assert response.status_code == 400
    card = await create(client, modules={"voice": {"source": "official", "voice": "stepfun:x"}, "brain": None})
    assert card["modules"] == {"voice": {"source": "official", "voice": "stepfun:x"}}
    assert (await client.patch(f"/api/companion/cards/{card['id']}", json={"name": "Peto"})).status_code == 409
    assert (await client.delete("/api/companion/cards/peto")).status_code == 400
    assert (await client.post(f"/api/companion/cards/{card['id']}/reset")).status_code == 400
    assert (await client.get("/api/companion/cards/NOT-AN-ID")).status_code == 404
    monkeypatch.setattr(companion_cards, "MAX_CARDS", 1)
    assert (await client.post("/api/companion/cards", json={"name": "B"})).status_code == 409
    async with client.stream("POST", "/api/chat", json={"message": "x", "card_id": card["id"]}) as response:
        assert response.status_code == 400


async def test_deleting_a_card_deletes_its_conversations_and_falls_back_to_peto(client, owner):
    card = await create(client)
    thread = (await client.post("/api/companion/conversations", json={"card_id": card["id"]})).json()
    response = await client.delete(f"/api/companion/cards/{card['id']}")
    assert response.json() == {"deleted": True, "conversations_deleted": 1, "active_card": "peto"}
    assert (await client.get("/api/companion", params={"conversation_id": thread["conversation_id"]})).status_code == 404
    assert (await client.get(f"/api/companion/cards/{card['id']}")).status_code == 404


async def test_cards_and_conversations_are_private_to_their_account(client, owner):
    card = await create(client)
    thread = (await client.post("/api/companion/conversations", json={"card_id": card["id"]})).json()
    await sign_in(client)
    assert (await client.get(f"/api/companion/cards/{card['id']}")).status_code == 404
    assert (await client.patch(f"/api/companion/cards/{card['id']}", json={"name": "X"})).status_code == 404
    assert (await client.delete(f"/api/companion/cards/{card['id']}")).status_code == 404
    assert (await client.put("/api/companion/cards/active", json={"card_id": card["id"]})).status_code == 404
    assert (await client.put("/api/companion/active", json={"conversation_id": thread["conversation_id"]})).status_code == 404
    assert (await client.post("/api/companion/conversations", json={"card_id": card["id"]})).status_code == 404
    async with client.stream("POST", "/api/chat", json={"message": "x", "mode": "companion", "card_id": card["id"]}) as response:
        assert response.status_code == 404
    assert (await client.get("/api/companion/conversations")).json()["conversations"] == []


async def test_custom_cards_neither_read_nor_write_shared_memory(client, owner, prompts):
    await db.set_memory_enabled(owner, True)
    await send(client, "warm up")
    created = await db.apply_memory_changes(owner, upserts=[companion_memory.new_entry("topic", "Mèo", "", ["Nuôi mèo Mơ"])],
                                            remove=[], limit=companion_memory.MAX_ENTRIES)
    assert created
    card = await create(client, system_prompt="I am Mika.")
    await client.put("/api/companion/cards/active", json={"card_id": card["id"]})
    await send(client, "secret __nho__:Bí mật của thẻ Mika")
    assert "Nuôi mèo Mơ" not in prompts[-1]
    # Lượt kế của thẻ Peto chạy ghi nhớ: tin của thẻ Mika không được đọc.
    await client.put("/api/companion/cards/active", json={"card_id": "peto"})
    await send(client, "back to Peto")
    assert "Nuôi mèo Mơ" in prompts[-1]
    details = [text for item in await db.list_memories(owner) for text in item["details"]]
    assert not any("Mika" in text for text in details)


async def test_prompt_endpoint_shows_the_whole_prompt(client, owner):
    card = await create(client, system_prompt="I am {{char}}.")
    body = (await client.get(f"/api/companion/cards/{card['id']}/prompt")).json()
    assert body["memory"] is False
    assert body["prompt"].startswith("I am Mika.") and COMPANION_CARD_RULE in body["prompt"]
    default = (await client.get("/api/companion/cards/peto/prompt")).json()
    assert default["memory"] is True and default["prompt"].startswith(COMPANION_PERSONA_PROMPT)


async def test_old_companion_threads_belong_to_the_default_card(client, owner):
    """Mạch Companion có từ trước thẻ nhân vật (card_id NULL) thành mạch của thẻ Peto sau khi khởi động."""
    from storage import connection as db_connection

    conversation_id = await db.create_conversation(owner, mode="companion")
    async with db_connection.connect() as conn:
        await conn.execute("UPDATE conversations SET card_id=NULL WHERE id=?", (conversation_id,))
        await conn.commit()
    await db.init_db()
    current = (await client.get("/api/companion")).json()
    assert (current["conversation_id"], current["card_id"]) == (conversation_id, "peto")
