"""Kiểm thử luồng chat bằng nhà cung cấp giả."""

from __future__ import annotations

import pytest

from conftest import read_events


async def _send(client, message: str, conversation_id: str | None = None):
    payload: dict = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    async with client.stream("POST", "/api/chat", json=payload) as response:
        assert response.status_code == 200
        return await read_events(response)


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "provider": "mock"}


async def test_chat_streams_and_persists(client):
    events = await _send(client, "chào")

    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "done"
    conversation_id = events[0]["conversation_id"]

    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert len(deltas) > 1, "phải stream nhiều mảnh, không phải một cục"
    reply = "".join(deltas).strip()
    assert reply

    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    messages = stored.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "chào"
    assert messages[1]["content"] == reply


async def test_history_is_reused_in_same_conversation(client):
    first = await _send(client, "chào")
    conversation_id = first[0]["conversation_id"]

    await _send(client, "cậu khỏe không", conversation_id)

    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    assert len(stored.json()["messages"]) == 4


async def test_conversation_list_has_title_from_first_message(client):
    await _send(client, "tiêu đề lấy từ đây")
    response = await client.get("/api/conversations")
    titles = [c["title"] for c in response.json()["conversations"]]
    assert "tiêu đề lấy từ đây" in titles


async def test_unknown_conversation_is_rejected(client):
    response = await client.post(
        "/api/chat", json={"message": "hi", "conversation_id": "khong-ton-tai"}
    )
    assert response.status_code == 404

    response = await client.get("/api/conversations/khong-ton-tai/messages")
    assert response.status_code == 404


async def test_provider_error_becomes_error_event(client):
    events = await _send(client, "__error__ thử lỗi")
    assert events[-1]["type"] == "error"
    assert "lỗi" in events[-1]["message"].casefold()
    assert not any(e["type"] == "done" for e in events)


async def test_empty_and_oversized_messages_rejected(client):
    assert (await client.post("/api/chat", json={"message": "   "})).status_code == 400
    assert (
        await client.post("/api/chat", json={"message": "a" * 5000})
    ).status_code == 400


async def test_delete_conversation(client):
    events = await _send(client, "xóa tôi đi")
    conversation_id = events[0]["conversation_id"]

    assert (
        await client.delete(f"/api/conversations/{conversation_id}")
    ).status_code == 200
    assert (
        await client.delete(f"/api/conversations/{conversation_id}")
    ).status_code == 404
    assert (
        await client.get(f"/api/conversations/{conversation_id}/messages")
    ).status_code == 404


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chào cậu", "low"),
        ("giải phương trình bậc hai giúp tao", "medium"),
        ("chứng minh giúp tao bất đẳng thức này", "high"),
        ("lỗi code python này là gì", "medium"),
    ],
)
def test_effort_routing(text, expected):
    from ai.routing import choose_effort

    assert choose_effort(text) == expected
