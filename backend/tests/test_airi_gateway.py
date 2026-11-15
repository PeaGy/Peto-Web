"""Cổng Chat Completions cho bộ não AIRI (``/api/companion/v1``): cookie phiên, luật cố định, không lưu gì."""

from __future__ import annotations

import json

import pytest

import storage as db
from ai.mock import MockProvider
from core.rate_limit import AdmissionDenied, admission
from conftest import TEST_OWNER
from prompts import COMPANION_CARD_RULE

URL = "/api/companion/v1/chat/completions"
MESSAGES = [
    {"role": "system", "content": "You are a cheerful test character."},
    {"role": "user", "content": "chào bạn"},
]


async def _chunks(response) -> list:
    items = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            payload = line[6:]
            items.append(payload if payload == "[DONE]" else json.loads(payload))
    return items


@pytest.fixture
def spy(monkeypatch):
    """Ghi lại system prompt và lịch sử provider nhận được (vá lớp, không vá instance dùng chung)."""
    seen: dict = {}
    original = MockProvider.stream

    def stream(self, **kwargs):
        seen.update(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(MockProvider, "stream", stream)
    return seen


async def test_models_requires_session(anon_client):
    response = await anon_client.get("/api/companion/v1/models")
    assert response.status_code == 401


async def test_models_lists_peto(client):
    response = await client.get("/api/companion/v1/models")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == ["peto"]


async def test_completions_require_session(anon_client):
    response = await anon_client.post(URL, json={"model": "peto", "messages": MESSAGES, "stream": True})
    assert response.status_code == 401


async def test_stream_returns_openai_chunks_and_appends_card_rule(client, spy):
    async with client.stream("POST", URL, json={"model": "anything", "messages": MESSAGES, "stream": True,
                                                "tools": [{"type": "function", "function": {"name": "x"}}]}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        items = await _chunks(response)
    assert items[-1] == "[DONE]"
    chunks = items[:-1]
    assert all(item["object"] == "chat.completion.chunk" for item in chunks)
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    text = "".join(item["choices"][0]["delta"].get("content", "") for item in chunks)
    assert text.strip()
    # System prompt của AIRI đi trước, luật dưới 18 tuổi luôn nối sau cùng.
    assert spy["system_prompt"].startswith("You are a cheerful test character.")
    assert spy["system_prompt"].endswith(COMPANION_CARD_RULE)
    assert [(m.role, m.content) for m in spy["messages"]] == [("user", "chào bạn")]
    assert spy["tools_enabled"] is False and spy["web_search"] == "off"


async def test_card_rule_added_without_system_message(client, spy):
    response = await client.post(URL, json={"messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]})
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"].strip()
    assert spy["system_prompt"] == COMPANION_CARD_RULE
    assert spy["messages"][0].content == "hi"


async def test_stores_nothing(client):
    before = await db.list_conversations(TEST_OWNER)
    response = await client.post(URL, json={"messages": MESSAGES, "stream": False})
    assert response.status_code == 200
    assert await db.list_conversations(TEST_OWNER) == before


async def test_provider_error_becomes_error_chunk(client):
    messages = [{"role": "user", "content": "__error__"}]
    async with client.stream("POST", URL, json={"messages": messages, "stream": True}) as response:
        items = await _chunks(response)
    assert "[DONE]" not in items
    assert items[-1]["error"]["code"] == 502
    assert "giả lập" in items[-1]["error"]["message"]


async def test_admission_is_used(client, monkeypatch):
    class Denied:
        async def __aenter__(self):
            raise AdmissionDenied("queue_full")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(admission, "slot", lambda owner: Denied())
    response = await client.post(URL, json={"messages": MESSAGES})
    assert response.status_code == 429
    assert response.json()["error"]["message"] == AdmissionDenied("queue_full").message


@pytest.mark.parametrize("messages, fragment", [
    ([], "Thiếu"),
    ([{"role": "assistant", "content": "x"}], "người dùng"),
    ([{"role": "wizard", "content": "x"}], "Vai trò"),
])
async def test_bad_messages_are_400(client, messages, fragment):
    response = await client.post(URL, json={"messages": messages})
    assert response.status_code == 400
    assert fragment in response.json()["error"]["message"]
