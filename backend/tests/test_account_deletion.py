"""Xóa tài khoản trong Cài đặt → Tài khoản (G5): xóa ngay mọi dữ liệu của chính tài khoản đó, không đụng tài khoản
khác; phải gõ "XÓA"; tài khoản quản trị bị chặn; cookie cũ ở máy khác không ghi được gì nữa."""
import sqlite3
import time
import uuid

from core import config
from core.config import DB_PATH, SESSION_COOKIE, UPLOAD_DIR
from features.accounts import auth
from features.accounts.deletion import confirmed
from storage import email_login as email_store
import storage as db

from conftest import read_events, sign_in


async def _chat(client, message: str) -> str:
    async with client.stream("POST", "/api/chat", json={"message": message}) as response:
        assert response.status_code == 200
        events = await read_events(response)
    return next(event["conversation_id"] for event in events if event["type"] == "meta")


async def _fill(client, owner: str) -> str:
    """Tạo dữ liệu ở vài khu: hội thoại, dự án, hồ sơ, danh tính gộp, mật khẩu, tệp tải lên."""
    conversation = await _chat(client, "chào Peto")
    assert (await client.post("/api/projects", json={"name": "Dự án thử"})).status_code in (200, 201)
    await db.save_profile(owner=owner, full_name="Người Thử", nickname="Thử", occupation="", instructions="")
    await email_store.link_identity(f"google:{uuid.uuid4().hex}", owner)
    await email_store.set_password(owner, "scrypt$thu-gia", replace=True)
    folder = UPLOAD_DIR / conversation
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tep.txt").write_text("nội dung", encoding="utf-8")
    return conversation


def _rows_of(owner: str) -> dict[str, int]:
    with sqlite3.connect(DB_PATH) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {}
        for name in tables:
            if any(column[1] == "owner" for column in conn.execute(f'PRAGMA table_info("{name}")')):
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}" WHERE owner=?', (owner,)).fetchone()[0]
                if count:
                    counts[name] = count
    return counts


async def test_delete_removes_every_row_and_file_of_that_account_only(client, anon_client):
    owner = await sign_in(client)
    conversation = await _fill(client, owner)
    other = await sign_in(anon_client)
    other_conversation = await _fill(anon_client, other)
    assert {"users", "conversations", "projects", "account_identities", "account_passwords"} <= set(_rows_of(owner))
    before_other = _rows_of(other)
    stale_cookie = client.cookies.get(SESSION_COOKIE)

    response = await client.post("/api/account/delete", json={"confirm": "XÓA"})

    assert response.status_code == 200 and response.json() == {"deleted": True}
    assert _rows_of(owner) == {}
    assert _rows_of(other) == before_other
    assert not (UPLOAD_DIR / conversation).exists()
    assert (UPLOAD_DIR / other_conversation / "tep.txt").exists()
    with sqlite3.connect(DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)).fetchone()[0] == 0
    # Phản hồi xóa cookie; cookie cũ còn hạn ở máy khác cũng không dùng được nữa.
    assert "peto_session" in response.headers.get("set-cookie", "")
    client.cookies.set(SESSION_COOKIE, stale_cookie)
    assert (await client.get("/api/auth/me")).json()["authenticated"] is False
    assert (await client.get("/api/conversations")).status_code == 401
    async with client.stream("POST", "/api/chat", json={"message": "còn ai không"}) as late:
        assert late.status_code == 401
    assert _rows_of(owner) == {}


async def test_wrong_confirmation_deletes_nothing(client):
    owner = await sign_in(client)
    await _fill(client, owner)
    before = _rows_of(owner)
    for word in ("", "xoa", "XÓA TÀI KHOẢN", "delete"):
        response = await client.post("/api/account/delete", json={"confirm": word})
        assert response.status_code == 400
        assert "XÓA" in response.json()["detail"]
    assert _rows_of(owner) == before


def test_confirmation_ignores_case_spaces_and_unicode_form():
    assert confirmed("XÓA") and confirmed(" xóa ") and confirmed("Xóa")
    assert confirmed("XÓA")  # dấu sắc tổ hợp (bàn phím Telex trên một số máy)
    assert not confirmed("XOA") and not confirmed("XÓA!")


async def test_admin_account_is_blocked(client, monkeypatch):
    owner = await sign_in(client)
    monkeypatch.setattr(config, "OWNER_ACCOUNTS", frozenset({owner}))
    assert (await client.get("/api/auth/me")).json()["user"]["is_owner"] is True  # giao diện ẩn nút theo cờ này
    response = await client.post("/api/account/delete", json={"confirm": "XÓA"})
    assert response.status_code == 403 and "quản trị" in response.json()["detail"]
    assert "users" in _rows_of(owner)


async def test_running_reply_blocks_deletion_until_it_ends(client):
    owner = await sign_in(client)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO chat_turns(owner,request_id,state,created_at,updated_at) VALUES(?,?,?,?,?)",
                     (owner, "dang-chay", "running", time.time(), time.time()))
        # Lượt mồ côi từ lâu (máy chủ tắt giữa chừng) không chặn.
        conn.execute("INSERT INTO chat_turns(owner,request_id,state,created_at,updated_at) VALUES(?,?,?,?,?)",
                     (owner, "mo-coi", "running", time.time() - 7200, time.time() - 7200))
    response = await client.post("/api/account/delete", json={"confirm": "XÓA"})
    assert response.status_code == 409
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE chat_turns SET state='done' WHERE owner=? AND request_id='dang-chay'", (owner,))
    assert (await client.post("/api/account/delete", json={"confirm": "XÓA"})).status_code == 200


async def test_signing_in_again_starts_a_fresh_account(client):
    owner = await sign_in(client, "google")
    await _fill(client, owner)
    await email_store.link_identity(owner, owner)
    assert (await client.post("/api/account/delete", json={"confirm": "XÓA"})).status_code == 200
    # Cookie chỉ ghi thời điểm ký theo giây; lần đăng nhập lại thật luôn sau mốc xóa vài giây.
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE deleted_accounts SET deleted_at = deleted_at - 5")
    # Cùng danh tính Google đăng nhập lại: không còn gì gắn với nó, nên là tài khoản trống.
    assert await email_store.identity_owner(owner) is None
    assert await auth._linked_owner(owner, None) == owner
    await db.upsert_user(owner=owner, provider="google", username="lai", display_name="Lại", avatar_url="")
    client.cookies.set(SESSION_COOKIE, auth._sign(owner))
    listing = (await client.get("/api/conversations")).json()
    assert not (listing.get("conversations") if isinstance(listing, dict) else listing)
    assert set(_rows_of(owner)) <= {"users", "account_identities"}



async def test_companion_sync_token_issued_before_deletion_stops_working(client):
    from features.companion import airi_sync
    owner = await sign_in(client)
    token = airi_sync.issue_token(owner)
    assert await airi_sync.live_token_owner(token) == owner
    assert (await client.post("/api/account/delete", json={"confirm": "XÓA"})).status_code == 200
    assert airi_sync.token_owner(token) == owner  # chữ ký vẫn đúng...
    assert await airi_sync.live_token_owner(token) is None  # ...nhưng đã bị thu hồi
