"""Chọn model: Peto (xAI) và dòng GPT-6 của OpenAI.

6 Luna cho tài khoản Discord/Google trên web và trong Peto Agent; 5.6 Terra và 6 Sol chỉ cho chủ web trong Agent;
bước Agent tính theo giá. Không test nào gọi OpenAI thật: provider giả, hoặc client giả.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import agent_api
import ai
import config
import db
import titles
from ai.base import ChatMessage, ProviderError
from ai.mock import MockProvider
from conftest import TEST_OWNER, read_events
from test_agent_api import bearer, connect, events_of, login_as

openai = pytest.importorskip("openai")
httpx2 = pytest.importorskip("httpx2")


def spy_models(monkeypatch) -> list[str]:
    """Model của từng lượt trả lời (bỏ lượt đặt tên hội thoại)."""
    seen: list[str] = []
    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, effort="low", timezone=None, web_search="auto"):
        if titles.TITLE_MARKER not in system_prompt:
            seen.append(self.model)
        async for chunk in original(self, system_prompt=system_prompt, messages=messages, effort=effort,
                                    timezone=timezone, web_search=web_search):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    return seen


def keys(models: list[dict]) -> list[str]:
    return [model["key"] for model in models]


async def test_web_offers_luna_to_discord_and_google_accounts_only(client, anon_client, monkeypatch):
    me = (await client.get("/api/auth/me")).json()["user"]
    assert me["models"] == [
        {"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1},
        {"key": "luna", "label": "6 Luna", "description": "Nhanh, của OpenAI", "step_cost": 1},
    ]
    seen = spy_models(monkeypatch)
    events = await read_events(await client.post("/api/chat", json={"message": "chào", "model": "luna"}))
    assert events[-1]["type"] == "done"
    events = await read_events(await client.post("/api/chat", json={
        "message": "tiếp nhé", "conversation_id": events[0]["conversation_id"]}))
    assert events[-1]["type"] == "done"
    assert seen == ["luna", "peto"], "mỗi tin theo model chọn lúc gửi, đổi giữa chừng được"

    await anon_client.post("/api/auth/guest")
    assert keys((await anon_client.get("/api/auth/me")).json()["user"]["models"]) == ["peto"]
    guest = await anon_client.post("/api/chat", json={"message": "chào", "model": "luna"})
    assert guest.status_code == 403 and "Discord hoặc Google" in guest.json()["detail"]

    for model in ("sol", "terra", "gpt-6-luna", ""):
        assert (await client.post("/api/chat", json={"message": "chào", "model": model})).status_code == 400
    assert (await client.post("/api/chat", json={"message": "chào", "model": "luna", "mode": "companion"})).status_code == 400


async def test_roleplay_conversations_stay_on_peto(client):
    conversation_id = await db.create_conversation(TEST_OWNER, persona="roleplay")
    response = await client.post("/api/chat", json={"message": "chào", "conversation_id": conversation_id,
                                                    "model": "luna"})
    assert response.status_code == 400 and response.json()["detail"] == "Chế độ nhập vai chỉ dùng Peto."


async def test_openai_models_disappear_without_a_key(client, monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert keys((await client.get("/api/auth/me")).json()["user"]["models"]) == ["peto"]
    response = await client.post("/api/chat", json={"message": "chào", "model": "luna"})
    assert response.status_code == 503 and "chưa bật 6 Luna" in response.json()["detail"]


async def test_agent_models_and_step_costs(anon_client, client, monkeypatch):
    owner = await login_as(client, "discord")
    token = await connect(anon_client, client)
    me = (await anon_client.get("/api/agent/me", headers=bearer(token))).json()
    assert keys(me["models"]) == ["peto", "luna"]
    task = {"type": "message", "role": "user", "content": "chào"}

    async def step(model: str, effort: str = "medium"):
        return await anon_client.post("/api/agent/step", headers=bearer(token),
                                      json={"input": [task], "model": model, "effort": effort})

    refused = await step("sol")
    assert refused.status_code == 403 and refused.json()["detail"] == "6 Sol chỉ dành cho chủ web."
    assert (await step("gpt")).status_code == 400
    assert (await client.get("/api/agent/devices")).json()["steps_used"] == 0, "model bị từ chối không tốn bước"

    monkeypatch.setattr(config, "OWNER_ACCOUNTS", frozenset({owner}))
    me = (await anon_client.get("/api/agent/me", headers=bearer(token))).json()
    assert [(model["key"], model["step_cost"]) for model in me["models"]] == [
        ("peto", 1), ("luna", 1), ("terra", 2), ("sol", 4)]
    for model, effort, expected in (("luna", "medium", 1), ("terra", "medium", 3), ("sol", "high", 11)):
        response = await step(model, effort)
        assert response.status_code == 200 and events_of(response)[-1]["type"] == "done"
        assert (await client.get("/api/agent/devices")).json()["steps_used"] == expected

    monkeypatch.setattr(agent_api, "AGENT_DAILY_STEPS", 14)
    short = await step("sol")
    assert short.status_code == 429
    assert "6 Sol" in short.json()["detail"] and "chỉ còn 3 bước" in short.json()["detail"]
    assert "/model peto" in short.json()["detail"]


def test_owner_accounts_accept_bare_discord_ids():
    assert config.parse_owner_accounts(" 123 , google:456,, discord:789") == frozenset(
        {"discord:123", "google:456", "discord:789"})


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __aiter__(self):
        async def run():
            for event in self.events:
                yield event
        return run()

    async def close(self) -> None:
        pass


def completed(text: str):
    output = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]
    return [SimpleNamespace(type="response.output_text.delta", delta=text),
            SimpleNamespace(type="response.completed",
                            response=SimpleNamespace(status="completed", output=output, usage=None))]


async def test_luna_calls_openai_with_its_model_and_key(monkeypatch):
    from ai import gpt

    monkeypatch.setattr(ai, "AI_PROVIDER", "xai")
    monkeypatch.setattr(ai, "_instances", {})
    provider = ai.get_provider("luna")
    assert isinstance(provider, gpt.GPTProvider) and provider.model == "gpt-6-luna"
    assert ai.get_provider("luna") is provider

    with pytest.raises(ProviderError, match="chưa có khóa OpenAI"):
        async for _ in provider.stream(system_prompt="chỉ dẫn", messages=[], web_search="off"):
            pass

    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        return FakeStream(completed("Chào bạn"))

    monkeypatch.setattr(gpt, "OPENAI_API_KEY", "khoa-thu")
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    parts = [chunk async for chunk in provider.stream(
        system_prompt="chỉ dẫn", messages=[ChatMessage("user", "chào")], effort="medium", web_search="off")]
    assert parts == ["Chào bạn"]
    assert calls[0]["model"] == "gpt-6-luna" and calls[0]["max_output_tokens"] == config.OPENAI_MAX_OUTPUT_TOKENS
    assert calls[0]["reasoning"] == {"effort": "medium"} and calls[0]["store"] is False

    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx2.Response(429, request=request, json={"error": {"message": "quota"}})

    async def exhausted(**kwargs):
        raise openai.RateLimitError("quota", response=response, body=None)

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=exhausted))
    with pytest.raises(ProviderError, match="^6 Luna đang bị OpenAI giới hạn lượt hoặc đã hết hạn mức. Chọn Peto"):
        async for _ in provider.stream(system_prompt="chỉ dẫn", messages=[ChatMessage("user", "chào")],
                                       web_search="off"):
            pass


async def test_agent_steps_on_terra_go_to_openai(monkeypatch):
    from ai import agent

    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        return FakeStream(completed("Xong"))

    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(agent, "OPENAI_API_KEY", "khoa-thu")
    monkeypatch.setattr(agent, "_openai_client", SimpleNamespace(responses=SimpleNamespace(create=create)))
    events = [event async for event in agent.agent_step(
        instructions="chỉ dẫn", input_items=[{"role": "user", "content": "chào"}], tools=[], effort="high",
        model="terra")]
    assert events[-1].kind == "done" and calls[0]["model"] == "gpt-5.6-terra"

    monkeypatch.setattr(agent, "OPENAI_API_KEY", "")
    with pytest.raises(ProviderError, match="/model peto"):
        async for _ in agent.agent_step(instructions="", input_items=[], tools=[], model="luna"):
            pass
