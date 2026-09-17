"""Bước gọi xAI của Peto Agent: lý do lỗi xAI trả về vào log máy chủ, người dùng chỉ thấy câu báo tiếng Việt."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from ai import agent
from ai.base import ProviderError

openai = pytest.importorskip("openai")
httpx2 = pytest.importorskip("httpx2")

SECRET_TEXT = "nội dung riêng trong dự án"


class FakeAuth:
    async def get_access_token(self) -> str:
        return "xai-token-thu"


class FakeStream:
    def __init__(self, events):
        self.events = events

    async def _events(self):
        for event in self.events:
            yield event

    def __aiter__(self):
        return self._events()

    async def close(self) -> None:
        pass


def use_fake_client(monkeypatch, create) -> None:
    client = SimpleNamespace(api_key="", responses=SimpleNamespace(create=create))
    monkeypatch.setattr(agent, "_client", client)
    monkeypatch.setattr(agent, "_auth", FakeAuth())


async def run_step() -> None:
    async for _ in agent._xai_step("chỉ dẫn", [{"role": "user", "content": SECRET_TEXT}], [], "high"):
        pass


async def test_rejected_step_logs_the_reason_from_xai(monkeypatch, caplog):
    request = httpx2.Request("POST", "https://api.x.ai/v1/responses")
    response = httpx2.Response(400, request=request, json={
        "code": "Client specified an invalid argument",
        "error": "This model's maximum prompt length is 131072 but the request contains 150000 tokens.",
    })

    async def create(**kwargs):
        raise openai.BadRequestError(f"Error code: 400 - {response.text}", response=response, body=response.json())

    use_fake_client(monkeypatch, create)
    caplog.set_level(logging.WARNING, logger="peto_web.agent")
    with pytest.raises(ProviderError) as raised:
        await run_step()
    assert "Gõ /moi" in str(raised.value)
    assert "HTTP 400" in caplog.text and "maximum prompt length is 131072" in caplog.text
    assert SECRET_TEXT not in caplog.text and "xai-token-thu" not in caplog.text


async def test_failed_stream_logs_the_reason_from_xai(monkeypatch, caplog):
    failed = SimpleNamespace(type="response.failed",
                             response=SimpleNamespace(error=SimpleNamespace(code="server_error", message="Model crashed")))

    async def create(**kwargs):
        return FakeStream([failed])

    use_fake_client(monkeypatch, create)
    caplog.set_level(logging.WARNING, logger="peto_web.agent")
    with pytest.raises(ProviderError) as raised:
        await run_step()
    assert str(raised.value) == "Mô hình gặp lỗi ở bước này. Thử lại nhé."
    assert "server_error Model crashed" in caplog.text
