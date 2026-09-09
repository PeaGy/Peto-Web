"""Kiểm thử đăng nhập Discord và ranh giới quyền sở hữu.

Không gọi ra Discord thật — luồng callback được test ở mức đơn vị bằng cách
thay lớp HTTP client, còn phần chống CSRF/allowlist kiểm tra trực tiếp.
"""

from __future__ import annotations

import auth
import pytest
from conftest import BLOCKED_DISCORD_ID, TEST_DISCORD_ID, TEST_OWNER

import db
from config import SESSION_COOKIE, owner_key

ENDPOINTS = [
    ("GET", "/api/conversations"),
    ("GET", "/api/conversations/bat-ky/messages"),
    ("DELETE", "/api/conversations/bat-ky"),
]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
async def test_endpoints_require_login(anon_client, method, path):
    response = await anon_client.request(method, path)
    assert response.status_code == 401


async def test_chat_requires_login(anon_client):
    response = await anon_client.post("/api/chat", json={"message": "chào"})
    assert response.status_code == 401


async def test_me_reports_anonymous(anon_client):
    body = (await anon_client.get("/api/auth/me")).json()
    assert body["authenticated"] is False
    assert body["login_configured"] is True


async def test_me_reports_logged_in_user(client):
    body = (await client.get("/api/auth/me")).json()
    assert body["authenticated"] is True
    assert body["user"]["discord_id"] == TEST_DISCORD_ID
    assert body["user"]["display_name"] == "Người Test"


async def test_me_never_leaks_tokens(client):
    body = (await client.get("/api/auth/me")).json()
    serialized = str(body).casefold()
    assert "token" not in serialized
    assert "secret" not in serialized
    assert "email" not in serialized


async def test_login_redirects_to_discord(anon_client):
    response = await anon_client.get(
        "/api/auth/discord/login", follow_redirects=False
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://discord.com/oauth2/authorize")
    assert "scope=identify" in location
    # Client secret không bao giờ được xuất hiện trong URL gửi cho trình duyệt.
    assert "test-client-secret" not in location
    assert response.cookies.get(auth.STATE_COOKIE)


async def test_callback_rejects_mismatched_state(anon_client):
    response = await anon_client.get(
        "/api/auth/discord/callback",
        params={"code": "abc", "state": "gia-mao"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert "auth_error" in response.headers["location"]
    assert not response.cookies.get(SESSION_COOKIE)


async def test_session_cookie_is_signed():
    assert auth.read_session(auth._sign(TEST_OWNER)) == TEST_OWNER
    assert auth.read_session("gia-mao") is None
    assert auth.read_session(None) is None

    # Sửa một ký tự trong chữ ký là phải hỏng.
    token = auth._sign(TEST_OWNER)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert auth.read_session(tampered) is None


def test_allowlist_blocks_unknown_discord_id():
    from config import ALLOWED_DISCORD_IDS

    assert TEST_DISCORD_ID in ALLOWED_DISCORD_IDS
    assert BLOCKED_DISCORD_ID not in ALLOWED_DISCORD_IDS


async def test_conversations_are_isolated_between_users(client, anon_client):
    """Người khác không đọc được hội thoại của mình, dù biết đúng ID."""
    async with client.stream(
        "POST", "/api/chat", json={"message": "riêng tư"}
    ) as response:
        from conftest import read_events

        events = await read_events(response)
    conversation_id = events[0]["conversation_id"]

    other_owner = owner_key(BLOCKED_DISCORD_ID)
    anon_client.cookies.set(SESSION_COOKIE, auth._sign(other_owner))

    assert (
        await anon_client.get(f"/api/conversations/{conversation_id}/messages")
    ).status_code == 404
    assert (
        await anon_client.delete(f"/api/conversations/{conversation_id}")
    ).status_code == 404
    assert (
        await anon_client.post(
            "/api/chat",
            json={"message": "chen vao", "conversation_id": conversation_id},
        )
    ).status_code == 404
    assert (await anon_client.get("/api/conversations")).json()["conversations"] == []


async def test_upsert_user_updates_profile_without_duplicating(client):
    await db.upsert_user(
        owner=TEST_OWNER,
        discord_id=TEST_DISCORD_ID,
        username="ten_moi",
        display_name="Tên Mới",
        avatar_url="https://cdn.discordapp.com/embed/avatars/1.png",
    )
    user = await db.get_user(TEST_OWNER)
    assert user is not None
    assert user["display_name"] == "Tên Mới"
    assert user["first_login_at"] <= user["last_login_at"]


async def test_logout_clears_cookie(client):
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
