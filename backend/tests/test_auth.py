"""Kiểm thử ba lối đăng nhập và ranh giới quyền sở hữu.

Không gọi ra Discord hay Google thật — luồng callback được test ở mức đơn vị
bằng cách thay lớp HTTP client, còn phần chống CSRF kiểm tra trực tiếp.
"""

from __future__ import annotations

import auth
import pytest
from conftest import OTHER_DISCORD_ID, TEST_DISCORD_ID, TEST_OWNER

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
    assert body["user"]["provider"] == "discord"
    assert body["user"]["display_name"] == "Người Test"
    # Trả mã băm ổn định thay vì khóa owner: khóa của khách là uuid ngẫu nhiên
    # nên không có lý do gì để nó xuống tới trình duyệt.
    assert body["user"]["id"] == auth.account_id(TEST_OWNER)
    assert TEST_DISCORD_ID not in str(body)
    assert TEST_OWNER not in str(body)


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


async def test_login_redirects_to_google(anon_client):
    response = await anon_client.get(
        "/api/auth/google/login", follow_redirects=False
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    # Không xin "email": màn hình đăng nhập chỉ hứa đọc tên và ảnh đại diện.
    assert "scope=openid+profile" in location
    assert "email" not in location
    assert "test-google-client-secret" not in location
    assert response.cookies.get(auth.GOOGLE_STATE_COOKIE)


async def test_google_login_bao_loi_khi_chua_cau_hinh(anon_client, monkeypatch):
    """Thiếu credential thì nút Google phải im lặng tắt, không làm hỏng thứ khác."""
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "")
    assert (await anon_client.get("/api/auth/google/login")).status_code == 503
    assert auth.available_providers() == {
        "discord": True, "google": False, "guest": True,
    }


async def test_google_callback_tu_choi_state_lech(anon_client):
    response = await anon_client.get(
        "/api/auth/google/callback",
        params={"code": "abc", "state": "gia-mao"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert "auth_error" in response.headers["location"]


async def test_khach_vao_thang_va_co_du_lieu_rieng(anon_client):
    """Khách là owner thật: có hội thoại riêng, không thấy của người khác."""
    assert (await anon_client.get("/api/auth/me")).json()["authenticated"] is False

    assert (await anon_client.post("/api/auth/guest")).json() == {"ok": True}
    body = (await anon_client.get("/api/auth/me")).json()
    assert body["authenticated"] is True
    assert body["user"]["provider"] == "guest"
    assert body["user"]["display_name"] == "Khách"

    # Hội thoại của người khác vẫn vô hình với khách.
    nguoi_khac = await db.create_conversation(TEST_OWNER)
    assert (
        await anon_client.get(f"/api/conversations/{nguoi_khac}/messages")
    ).status_code == 404
    assert (await anon_client.get("/api/conversations")).json()["conversations"] == []


async def test_moi_lan_vao_khach_la_mot_tai_khoan_moi(anon_client):
    """Khách không chứng minh được mình là khách cũ, nên không gộp phiên."""
    await anon_client.post("/api/auth/guest")
    mot = (await anon_client.get("/api/auth/me")).json()["user"]["id"]
    await anon_client.post("/api/auth/guest")
    hai = (await anon_client.get("/api/auth/me")).json()["user"]["id"]
    assert mot != hai


async def test_me_liet_ke_cac_cach_dang_nhap(anon_client):
    body = (await anon_client.get("/api/auth/me")).json()
    assert body["providers"] == {"discord": True, "google": True, "guest": True}
    assert body["login_configured"] is True


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

    # Sửa phần payload là chữ ký phải hỏng.
    #
    # Cố ý KHÔNG sửa ký tự cuối của chữ ký: chữ ký là base64url, ký tự cuối
    # mang bit thừa nên hai ký tự khác nhau có thể giải mã ra cùng chuỗi byte
    # và chữ ký vẫn hợp lệ — sửa ở đó làm test lúc xanh lúc đỏ.
    token = auth._sign(TEST_OWNER)
    middle = len(token) // 2
    flipped = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1:]
    assert flipped != token
    assert auth.read_session(flipped) is None

    # Cắt cụt cũng phải hỏng.
    assert auth.read_session(token[:middle]) is None


def test_dang_ky_mo_khong_con_allowlist():
    """Allowlist đã bị gỡ có chủ đích — đừng dựng lại nếu không được yêu cầu.

    Trước đây chỉ Discord ID nằm trong ``PETO_ALLOWED_DISCORD_IDS`` mới vào
    được. Giờ mọi khóa owner hợp lệ đều là một phiên dùng được, và biến môi
    trường đó không còn ý nghĩa gì.
    """
    import config

    assert not hasattr(config, "ALLOWED_DISCORD_IDS")
    for owner in (
        owner_key("discord", OTHER_DISCORD_ID),
        owner_key("google", "sub-la-hoac"),
        owner_key("guest", "a" * 32),
    ):
        assert auth.session_owner(auth._sign(owner)) == owner


def test_khoa_owner_la_bi_tu_choi():
    """Cookie ký đúng nhưng khóa sai định dạng vẫn không dùng được."""
    for owner in ("", "local", "khong-co-dau-hai-cham", "facebook:1", "discord:"):
        assert auth.session_owner(auth._sign(owner)) is None


async def test_conversations_are_isolated_between_users(client, anon_client, monkeypatch):
    """Người khác không đọc được hội thoại của mình, dù biết đúng ID."""
    async with client.stream(
        "POST", "/api/chat", json={"message": "riêng tư"}
    ) as response:
        from conftest import read_events

        events = await read_events(response)
    conversation_id = events[0]["conversation_id"]

    other_owner = owner_key("discord", OTHER_DISCORD_ID)
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
        provider="discord",
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


def test_redirect_target_is_relative_by_default():
    """Không cấu hình gì thì phải quay về ĐÚNG domain người dùng vừa đến.

    Trước đây mặc định là http://localhost:5173, nên deploy lên VPS mà quên đặt
    PETO_FRONTEND_URL là đăng nhập xong bị ném về localhost.
    """
    assert auth._frontend_url() == "/"
    assert auth._frontend_url(auth_error="hong").startswith("/?auth_error=")


def test_failed_login_redirects_relatively():
    response = auth._fail("thu nghiem")
    location = response.headers["location"]
    assert location.startswith("/?auth_error=")
    assert "localhost" not in location


def test_absolute_frontend_url_is_respected(monkeypatch):
    """Vẫn cho phép ép domain khác khi frontend tách riêng."""
    monkeypatch.setattr(auth, "FRONTEND_URL", "https://peto.example/app")
    assert auth._frontend_url() == "https://peto.example/app"
    assert auth._frontend_url(auth_error="x") == (
        "https://peto.example/app?auth_error=x"
    )

    monkeypatch.setattr(auth, "FRONTEND_URL", "https://peto.example/?a=1")
    assert auth._frontend_url(auth_error="x") == "https://peto.example/?a=1&auth_error=x"
