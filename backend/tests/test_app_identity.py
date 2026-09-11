"""Kiểm thử phần lấy tên và avatar từ Discord application.

Không gọi ra Discord thật.
"""

from __future__ import annotations

import httpx
import pytest

import app_identity
from app_identity import get_app_identity


@pytest.fixture(autouse=True)
def clear_cache():
    app_identity.reset_cache()
    yield
    app_identity.reset_cache()


@pytest.fixture
def patch_discord(monkeypatch):
    def apply(handler):
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr("app_identity.httpx.AsyncClient", factory)

    return apply


async def test_builds_avatar_url_from_icon_hash(patch_discord):
    patch_discord(
        lambda request: httpx.Response(
            200, json={"id": "123", "name": "Pearto", "icon": "abc123"}
        )
    )
    info = await get_app_identity()
    assert info["avatar_url"].startswith("https://cdn.discordapp.com/app-icons/")
    assert "abc123.png" in info["avatar_url"]


async def test_application_without_icon_has_no_avatar(patch_discord):
    patch_discord(
        lambda request: httpx.Response(200, json={"id": "123", "name": "X", "icon": None})
    )
    assert (await get_app_identity())["avatar_url"] is None


async def test_discord_down_falls_back_quietly(patch_discord):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Discord không phản hồi")

    patch_discord(handler)
    info = await get_app_identity()
    assert info["name"] == "Peto"
    assert info["avatar_url"] is None


@pytest.mark.parametrize("status", [401, 404, 429, 500])
async def test_error_statuses_fall_back(patch_discord, status):
    patch_discord(lambda request: httpx.Response(status, json={}))
    assert (await get_app_identity())["avatar_url"] is None


@pytest.mark.parametrize(
    "body",
    [{"text": "<html>không phải JSON</html>"}, {"json": ["không", "phải", "object"]}],
)
async def test_malformed_payload_falls_back(patch_discord, body):
    """Trang chủ chờ hàm này, nên dữ liệu hỏng mà raise là cả web sập theo."""
    patch_discord(lambda request: httpx.Response(200, **body))
    assert await get_app_identity() == {"name": "Peto", "avatar_url": None}


async def test_result_is_cached(patch_discord):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"id": "123", "name": "X", "icon": "abc"})

    patch_discord(handler)
    await get_app_identity()
    await get_app_identity()
    assert len(calls) == 1


async def test_overrides_skip_the_network(monkeypatch, patch_discord):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("đã ép giá trị thì không được gọi Discord")

    patch_discord(handler)
    monkeypatch.setattr(app_identity, "NAME_OVERRIDE", "Peto Riêng")
    monkeypatch.setattr(app_identity, "AVATAR_OVERRIDE", "https://example/x.png")

    info = await get_app_identity()
    assert info == {"name": "Peto Riêng", "avatar_url": "https://example/x.png"}


async def test_endpoint_is_public(anon_client):
    """Màn hình đăng nhập cũng cần avatar, nên không được yêu cầu đăng nhập."""
    response = await anon_client.get("/api/app-info")
    assert response.status_code == 200
    assert set(response.json()) == {"name", "avatar_url"}


async def test_endpoint_never_leaks_credentials(anon_client):
    body = str((await anon_client.get("/api/app-info")).json()).casefold()
    assert "secret" not in body
    assert "token" not in body
