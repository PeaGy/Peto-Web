"""Kiểm thử phần đọc trí nhớ từ bot Discord.

Không gọi ra mạng thật: mọi lượt gọi Memory Gateway đều được thay bằng giả.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import TEST_DISCORD_ID, TEST_OWNER, read_events

import main
from config import discord_id_from_owner
from discord_memory import DiscordMemory
from persona import build_memory_context


@pytest.fixture
def patch_httpx(monkeypatch):
    def apply(handler):
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr("discord_memory.httpx.AsyncClient", factory)

    return apply


# --- Đọc trí nhớ ---------------------------------------------------------


async def test_fetch_returns_summary(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Peto-Token"] == "token-test"
        assert request.url.path == f"/internal/memory/{TEST_DISCORD_ID}"
        return httpx.Response(
            200,
            json={
                "available": True,
                "summary": "Thích Limbus.",
                "explicit": ["Đang ôn thi."],
            },
        )

    patch_httpx(handler)
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test")
    snapshot = await memory.fetch(TEST_DISCORD_ID)

    assert snapshot.summary == "Thích Limbus."
    assert snapshot.explicit == ("Đang ôn thi.",)


async def test_anonymous_user_yields_nothing(patch_httpx):
    patch_httpx(
        lambda request: httpx.Response(
            200, json={"available": False, "reason": "anonymous", "summary": "", "explicit": []}
        )
    )
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test")
    assert (await memory.fetch(TEST_DISCORD_ID)).is_empty


@pytest.mark.parametrize("status", [401, 429, 500, 503])
async def test_error_statuses_fail_open(patch_httpx, status):
    patch_httpx(lambda request: httpx.Response(status, json={"error": "x"}))
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test")
    assert (await memory.fetch(TEST_DISCORD_ID)).is_empty


async def test_gateway_down_fails_open(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bot không chạy")

    patch_httpx(handler)
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test")
    assert (await memory.fetch(TEST_DISCORD_ID)).is_empty


async def test_disabled_when_not_configured():
    memory = DiscordMemory(base_url="", token="")
    assert not memory.enabled
    assert (await memory.fetch(TEST_DISCORD_ID)).is_empty


async def test_non_numeric_id_is_never_requested(patch_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("không được gọi gateway với ID không hợp lệ")

    patch_httpx(handler)
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test")
    assert (await memory.fetch("../etc/passwd")).is_empty


async def test_permission_is_rechecked_each_turn(patch_httpx):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"available": True, "summary": "A", "explicit": []})

    patch_httpx(handler)
    memory = DiscordMemory(base_url="http://gateway.test", token="token-test", ttl=300)
    await memory.fetch(TEST_DISCORD_ID)
    await memory.fetch(TEST_DISCORD_ID)
    assert len(calls) == 2

    memory.forget(TEST_DISCORD_ID)
    await memory.fetch(TEST_DISCORD_ID)
    assert len(calls) == 3


# --- Ghép vào prompt -----------------------------------------------------


def test_owner_key_roundtrip():
    assert discord_id_from_owner(TEST_OWNER) == TEST_DISCORD_ID
    assert discord_id_from_owner("local") == ""
    assert discord_id_from_owner("discord:khong-phai-so") == ""


def test_khach_va_google_khong_cham_toi_tri_nho_cua_ai():
    """Chỉ owner Discord mới có ID để hỏi cổng trí nhớ.

    Đây là thứ giữ cho việc mở đăng ký không làm lộ trí nhớ dài hạn của thành
    viên: không có Discord ID thì main.py không gọi cổng, chấm hết.
    """
    assert discord_id_from_owner("guest:" + "a" * 32) == ""
    assert discord_id_from_owner("google:111111111111111111") == ""


def test_memory_context_without_memory_says_so():
    context = build_memory_context(display_name="Người Test")
    assert "chưa có ký ức" in context.casefold()
    assert "Người Test" in context


def test_memory_context_includes_rules():
    context = build_memory_context(
        display_name="Người Test", summary="Thích Limbus.", explicit=("Đang ôn thi.",)
    )
    assert "Thích Limbus." in context
    assert "Đang ôn thi." in context
    # Luật bám theo MEMORY_PRIVACY_PROMPT của bot.
    assert "tin lời hiện tại" in context
    assert "trí nhớ của người khác" in context


async def test_chat_still_works_when_gateway_is_down(client, patch_httpx, monkeypatch):
    """Bot tắt thì Peto vẫn phải trả lời — không được chặn cuộc trò chuyện."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bot không chạy")

    patch_httpx(handler)
    monkeypatch.setattr(
        main.discord_memory, "base_url", "http://gateway.test", raising=False
    )
    monkeypatch.setattr(main.discord_memory, "token", "token-test", raising=False)
    main.discord_memory.forget(TEST_DISCORD_ID)

    async with client.stream("POST", "/api/chat", json={"message": "chào"}) as response:
        events = await read_events(response)

    assert events[-1]["type"] == "done"
    assert any(e["type"] == "delta" for e in events)


async def test_prompt_only_asks_for_the_logged_in_user(client, patch_httpx, monkeypatch):
    """Web chỉ được hỏi trí nhớ của chính người đang đăng nhập."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"available": True, "summary": "A", "explicit": []})

    patch_httpx(handler)
    monkeypatch.setattr(
        main.discord_memory, "base_url", "http://gateway.test", raising=False
    )
    monkeypatch.setattr(main.discord_memory, "token", "token-test", raising=False)
    main.discord_memory.forget(TEST_DISCORD_ID)

    async with client.stream("POST", "/api/chat", json={"message": "chào"}) as response:
        await read_events(response)

    assert asked == [TEST_DISCORD_ID]


async def test_memory_reaches_the_provider(client, patch_httpx, monkeypatch):
    """Trí nhớ lấy được phải thực sự đi vào system prompt gửi cho AI."""
    seen: list[str] = []

    patch_httpx(
        lambda request: httpx.Response(
            200,
            json={"available": True, "summary": "Rất thích Limbus.", "explicit": []},
        )
    )
    monkeypatch.setattr(
        main.discord_memory, "base_url", "http://gateway.test", raising=False
    )
    monkeypatch.setattr(main.discord_memory, "token", "token-test", raising=False)
    main.discord_memory.forget(TEST_DISCORD_ID)

    provider = main.get_provider()
    original = provider.stream

    def spy(*, system_prompt, messages, effort, timezone=None, web_search="auto"):
        seen.append(system_prompt)
        return original(system_prompt=system_prompt, messages=messages, effort=effort, timezone=timezone, web_search=web_search)

    monkeypatch.setattr(provider, "stream", spy)

    async with client.stream("POST", "/api/chat", json={"message": "chào"}) as response:
        await read_events(response)

    assert seen
    assert "Rất thích Limbus." in seen[0]
    assert "Người Test" in seen[0]


def test_half_configured_gateway_is_disabled():
    """Đặt URL mà quên token thì phải coi như tắt, không gọi bừa."""
    assert not DiscordMemory(base_url="http://gateway.test", token="").enabled
    assert not DiscordMemory(base_url="", token="token-test").enabled
    assert DiscordMemory(base_url="http://gateway.test", token="t").enabled


def test_startup_warns_about_half_configuration():
    """Thiếu một nửa cấu hình phải cảnh báo lúc khởi động, không im lặng.

    Đây đúng là tình huống đã xảy ra khi deploy: `.env` của web có URL nhưng
    thiếu token, nên trí nhớ tắt lặng lẽ và chỉ biểu hiện là 'Peto không nhớ gì'.
    """
    import inspect

    source = inspect.getsource(main.lifespan)
    assert "PETO_MEMORY_GATEWAY_TOKEN" in source
    assert "Trí nhớ từ Discord" in source
