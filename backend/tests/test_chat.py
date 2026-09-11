"""Kiểm thử luồng chat bằng nhà cung cấp giả."""

from __future__ import annotations

import pytest

from conftest import read_events


async def _send(
    client,
    message: str,
    conversation_id: str | None = None,
    *,
    effort: str | None = None,
    attachments: list[dict] | None = None,
):
    payload: dict = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if effort is not None:
        payload["effort"] = effort
    if attachments:
        payload["attachments"] = attachments
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
    thinking = "".join(e["text"] for e in events if e["type"] == "thinking")
    assert "Đọc tin nhắn" in thinking
    assert thinking not in reply

    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    messages = stored.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "chào"
    assert messages[1]["content"] == reply
    assert thinking not in messages[1]["content"]


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
    from config import MAX_INPUT_CHARS
    assert (await client.post("/api/chat", json={"message": "   "})).status_code == 400
    assert (
        await client.post("/api/chat", json={"message": "a" * (MAX_INPUT_CHARS + 1)})
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


async def test_effort_can_be_overridden(client, monkeypatch):
    seen: list[str] = []
    from ai.mock import MockProvider

    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, effort="low", timezone=None, web_search="auto"):
        seen.append(effort)
        async for chunk in original(
            self, system_prompt=system_prompt, messages=messages, effort=effort, timezone=timezone, web_search=web_search
        ):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    events = await _send(client, "chào cậu", effort="high")
    assert events[0]["effort"] == "high"
    assert seen == ["high"]


async def test_invalid_effort_is_rejected(client):
    response = await client.post(
        "/api/chat", json={"message": "hi", "effort": "ultra"}
    )
    assert response.status_code == 400


async def test_auto_effort_still_uses_routing(client):
    events = await _send(
        client, "chứng minh giúp tao bất đẳng thức này", effort="auto"
    )
    assert events[0]["effort"] == "high"


PNG_1x1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def test_image_reaches_the_provider(client, monkeypatch):
    seen: list = []
    from ai.mock import MockProvider

    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, effort="low", timezone=None, web_search="auto"):
        seen.append(messages)
        async for chunk in original(
            self, system_prompt=system_prompt, messages=messages, effort=effort, timezone=timezone, web_search=web_search
        ):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    await _send(
        client,
        "xem ảnh này",
        attachments=[
            {"name": "cham.png", "mime": "image/png", "data": PNG_1x1_B64},
        ],
    )
    assert seen
    last = seen[0][-1]
    assert last.attachments
    assert last.attachments[0].kind == "image"
    assert last.attachments[0].data_url.startswith("data:image/png;base64,")


async def test_image_attachment_is_persisted_and_served(client):
    events = await _send(
        client,
        "ảnh này là gì",
        attachments=[
            {"name": "cham.png", "mime": "image/png", "data": PNG_1x1_B64},
        ],
    )
    conversation_id = events[0]["conversation_id"]
    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    messages = stored.json()["messages"]
    assert messages[0]["content"] == "ảnh này là gì"
    assert len(messages[0]["attachments"]) == 1
    att = messages[0]["attachments"][0]
    assert att["kind"] == "image"
    assert att["name"] == "cham.png"
    assert att["url"].startswith("/api/attachments/")

    fetched = await client.get(att["url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/png")
    assert fetched.content.startswith(b"\x89PNG")

    reply = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "cham.png" in reply


async def test_text_file_attachment_is_accepted(client):
    import base64

    payload = base64.b64encode("ghi chú của cậu".encode()).decode()
    events = await _send(
        client,
        "đọc giúp",
        attachments=[{"name": "note.txt", "mime": "text/plain", "data": payload}],
    )
    assert events[-1]["type"] == "done"
    conversation_id = next(event["conversation_id"] for event in events if event["type"] == "meta")
    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    att = stored.json()["messages"][0]["attachments"][0]
    assert att["kind"] == "file"
    assert att["name"] == "note.txt"


async def test_image_only_message_is_allowed(client):
    events = await _send(
        client,
        "   ",
        attachments=[
            {"name": "cham.png", "mime": "image/png", "data": PNG_1x1_B64},
        ],
    )
    assert events[-1]["type"] == "done"
    listed = await client.get("/api/conversations")
    assert listed.json()["conversations"][0]["title"].startswith("Ảnh:")


async def test_bad_attachment_is_rejected(client):
    import base64

    fake = base64.b64encode(b"not-an-image").decode()
    response = await client.post(
        "/api/chat",
        json={
            "message": "xem ảnh",
            "attachments": [{"name": "x.png", "mime": "image/png", "data": fake}],
        },
    )
    assert response.status_code == 400


async def test_attachment_is_not_visible_to_another_user(client, monkeypatch):
    events = await _send(
        client,
        "bí mật",
        attachments=[
            {"name": "cham.png", "mime": "image/png", "data": PNG_1x1_B64},
        ],
    )
    conversation_id = events[0]["conversation_id"]
    stored = await client.get(f"/api/conversations/{conversation_id}/messages")
    url = stored.json()["messages"][0]["attachments"][0]["url"]

    import auth
    from config import SESSION_COOKIE, owner_key

    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("discord", "222222222222222222")))
    assert (await client.get(url)).status_code == 404


async def test_delete_conversation_removes_files(client):
    from pathlib import Path

    from config import UPLOAD_DIR

    events = await _send(
        client,
        "xóa kèm ảnh",
        attachments=[
            {"name": "cham.png", "mime": "image/png", "data": PNG_1x1_B64},
        ],
    )
    conversation_id = events[0]["conversation_id"]
    folder = Path(UPLOAD_DIR) / conversation_id
    assert folder.exists()
    await client.delete(f"/api/conversations/{conversation_id}")
    assert not folder.exists()


def test_xai_payload_includes_image():
    from ai.base import ChatAttachment, ChatMessage
    from ai.xai import build_input_payload

    messages = [
        ChatMessage(
            role="user",
            content="đây là gì",
            attachments=(
                ChatAttachment(
                    kind="image",
                    name="a.png",
                    mime="image/png",
                    data_url="data:image/png;base64,xxx",
                ),
            ),
        )
    ]
    payload = build_input_payload(messages)
    types = [part["type"] for part in payload[0]["content"]]
    assert "input_image" in types
    assert payload[0]["content"][0]["image_url"].startswith("data:image/png")


async def test_health_accepts_head(client):
    """Giám sát uptime thường dùng HEAD chứ không phải GET."""
    assert (await client.head("/api/health")).status_code == 200
