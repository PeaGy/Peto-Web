"""Chế độ nhập vai: bật lúc bắt đầu hội thoại, chỉ cho tài khoản Discord/Google đã xác nhận 18+, dùng persona cũ của
bot và gửi nhiều tin cũ hơn chat thường."""

from __future__ import annotations

import main
import titles
from conftest import read_events

ASSISTANT_MARKER = "## Trung thực và an toàn"
ROLEPLAY_MARKER = "## Cảm giác hiện diện"


async def send(client, message: str, *, persona: str | None = None, conversation_id: str | None = None,
               mode: str | None = None):
    payload: dict = {"message": message}
    if persona is not None:
        payload["persona"] = persona
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if mode is not None:
        payload["mode"] = mode
    return await client.post("/api/chat", json=payload)


def spy_on_provider(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    from ai.mock import MockProvider

    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, effort="low", timezone=None, web_search="auto"):
        if titles.TITLE_MARKER not in system_prompt:
            calls.append({"system_prompt": system_prompt, "messages": len(messages)})
        async for chunk in original(
            self, system_prompt=system_prompt, messages=messages, effort=effort, timezone=timezone, web_search=web_search
        ):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    return calls


async def test_roleplay_needs_a_real_account_and_an_adult_confirmation(client, anon_client):
    before = await send(client, "chào", persona="roleplay")
    assert before.status_code == 403 and "xác nhận đủ 18 tuổi" in before.json()["detail"]
    assert (await client.get("/api/auth/me")).json()["user"]["roleplay_confirmed"] is False

    assert (await client.post("/api/profile/roleplay-consent")).json() == {"roleplay_confirmed": True}
    assert (await client.get("/api/auth/me")).json()["user"]["roleplay_confirmed"] is True
    assert (await send(client, "chào", persona="roleplay")).status_code == 200

    assert (await send(client, "chào", persona="roleplay", mode="companion")).status_code == 400
    assert (await send(client, "chào", persona="phan-dien")).status_code == 400

    await anon_client.post("/api/auth/guest")
    guest_consent = await anon_client.post("/api/profile/roleplay-consent")
    assert guest_consent.status_code == 403 and "Discord hoặc Google" in guest_consent.json()["detail"]
    guest_chat = await send(anon_client, "chào", persona="roleplay")
    assert guest_chat.status_code == 403 and "Discord hoặc Google" in guest_chat.json()["detail"]


async def test_roleplay_conversation_keeps_its_persona_and_a_longer_history(client, monkeypatch):
    calls = spy_on_provider(monkeypatch)
    monkeypatch.setattr(main, "MAX_HISTORY_MESSAGES", 2)
    monkeypatch.setattr(main, "ROLEPLAY_MAX_HISTORY", 4)
    await client.post("/api/profile/roleplay-consent")

    events = await read_events(await send(client, "*ngồi xuống cạnh Peto* hôm nay mệt ghê", persona="roleplay"))
    roleplay_id = events[0]["conversation_id"]
    assert ROLEPLAY_MARKER in calls[-1]["system_prompt"] and ASSISTANT_MARKER not in calls[-1]["system_prompt"]

    # Lượt sau gửi nhầm persona khác vẫn theo chế độ đã chọn lúc bắt đầu.
    for text in ("kể tiếp đi", "rồi sao nữa"):
        await read_events(await send(client, text, persona="assistant", conversation_id=roleplay_id))
    assert ROLEPLAY_MARKER in calls[-1]["system_prompt"]
    assert calls[-1]["messages"] == 4, "nhập vai gửi tới ROLEPLAY_MAX_HISTORY tin"

    events = await read_events(await send(client, "giải thích asyncio"))
    assistant_id = events[0]["conversation_id"]
    for text in ("ví dụ đi", "thêm một ví dụ"):
        await read_events(await send(client, text, conversation_id=assistant_id))
    assert ASSISTANT_MARKER in calls[-1]["system_prompt"] and ROLEPLAY_MARKER not in calls[-1]["system_prompt"]
    assert calls[-1]["messages"] == 2, "trợ lý vẫn gửi MAX_HISTORY_MESSAGES tin"

    listed = {item["id"]: item["persona"] for item in (await client.get("/api/conversations")).json()["conversations"]}
    assert listed[roleplay_id] == "roleplay" and listed[assistant_id] == "assistant"
