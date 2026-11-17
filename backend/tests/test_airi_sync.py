"""Đồng bộ hội thoại Companion bản AIRI (``features/companion/airi_sync.py``): mã đồng bộ, REST ``/api/v1/chats`` và
WebSocket ``/ws/v2/chat`` theo khung eventa của AIRI, tách riêng từng tài khoản."""

from __future__ import annotations

import asyncio
import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import storage as db
from conftest import TEST_DISCORD_ID, TEST_OWNER
from core import config
from core.config import SESSION_COOKIE, owner_key
from features.accounts import auth
from features.companion import airi_sync
from main import app
from storage import airi_chats

PREFIX = "/api/companion/airi-cloud"
OTHER = owner_key("github", "airi-sync-other")


@pytest.fixture(autouse=True)
def airi_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AIRI_DIR", tmp_path)


@pytest.fixture(autouse=True)
def empty_sync_tables():
    """Database thử dùng chung cả lượt chạy: mỗi test bắt đầu với bảng đồng bộ trống."""
    async def clear():
        await db.init_db()
        async with db.connection.connect() as conn:
            await conn.execute("DELETE FROM airi_chat_messages")
            await conn.execute("DELETE FROM airi_chats")
            await conn.commit()
    asyncio.run(clear())


def bearer(owner: str = TEST_OWNER) -> dict:
    return {"Authorization": f"Bearer {airi_sync.issue_token(owner)}"}


def request_frame(name: str, content: object, invoke_id: str = "inv1") -> str:
    """Khung yêu cầu như eventa 1.0.2 của trình duyệt gửi (ghi lại từ thư viện thật)."""
    eventa = {"id": f"{name}-send", "type": "event", "invokeType": 0,
              "body": {"invokeId": invoke_id, "content": content}, "_flowDirection": "outbound"}
    return json.dumps({"deliveryId": "d" + invoke_id, "hopsRemaining": 31, "eventa": eventa, "id": "d" + invoke_id,
                       "type": f"{name}-send", "payload": eventa, "timestamp": 1})


def read(ws) -> dict:
    return json.loads(ws.receive_text())["eventa"]


def call(ws, name: str, content: object, invoke_id: str) -> dict:
    ws.send_text(request_frame(name, content, invoke_id))
    event = read(ws)
    assert event["body"]["invokeId"] == invoke_id
    return event


def open_socket(test_client: TestClient, owner: str = TEST_OWNER):
    ws = test_client.websocket_connect(PREFIX + "/ws/v2/chat")
    socket = ws.__enter__()
    event = call(socket, "chat:authenticate", {"token": airi_sync.issue_token(owner)}, "auth")
    assert event["id"] == "chat:authenticate-receive-auth" and event["invokeType"] == 4
    assert event["body"]["content"] == {"userId": airi_sync.sync_user_id(owner)}
    return ws, socket


@pytest.fixture
def ws_client():
    asyncio.run(db.init_db())
    with TestClient(app) as test_client:
        yield test_client


# --- Mã đồng bộ -----------------------------------------------------------------------------------------------------

async def test_session_gives_an_opaque_user_and_a_token(client):
    response = await client.get("/api/companion/sync/session")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["userId"] == airi_sync.sync_user_id(TEST_OWNER)
    assert TEST_DISCORD_ID not in body["userId"] and TEST_OWNER not in json.dumps(body)
    assert airi_sync.token_owner(body["token"]) == TEST_OWNER


async def test_session_needs_sign_in_and_the_airi_page(anon_client, client, monkeypatch):
    assert (await anon_client.get("/api/companion/sync/session")).status_code == 401
    monkeypatch.setattr(config, "AIRI_DIR", None)
    assert (await client.get("/api/companion/sync/session")).status_code == 404
    assert (await client.get(PREFIX + "/api/v1/chats", headers=bearer())).status_code == 404


async def test_rest_needs_the_sync_token_not_the_cookie(client):
    assert (await client.get(PREFIX + "/api/v1/chats")).status_code == 401
    cookie = client.cookies.get(SESSION_COOKIE)
    for token in (cookie, "junk", auth._sign(TEST_OWNER)):
        response = await client.get(PREFIX + "/api/v1/chats", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
    assert (await client.get(PREFIX + "/api/v1/chats", headers=bearer())).status_code == 200


# --- REST hội thoại -------------------------------------------------------------------------------------------------

async def test_chat_lifecycle_in_the_shape_airi_reads(client):
    body = {"id": "sess-1", "type": "bot", "title": "Chào", "members": [{"type": "character", "characterId": "default"}]}
    created = await client.post(PREFIX + "/api/v1/chats", json=body, headers=bearer())
    assert created.status_code == 201
    chat = created.json()
    assert chat["id"] == "sess-1" and chat["type"] == "bot" and chat["title"] == "Chào"
    assert chat["createdAt"].endswith("Z") and "T" in chat["createdAt"]

    listed = (await client.get(PREFIX + "/api/v1/chats", headers=bearer())).json()["chats"]
    assert [item["id"] for item in listed] == ["sess-1"]
    members = {(m["memberType"], m["characterId"]) for m in listed[0]["members"]}
    assert members == {("user", None), ("character", "default")}

    duplicate = await client.post(PREFIX + "/api/v1/chats", json=body, headers=bearer())
    assert duplicate.status_code == 409

    renamed = await client.patch(PREFIX + "/api/v1/chats/sess-1", json={"title": "Mới"}, headers=bearer())
    assert renamed.status_code == 200 and renamed.json()["title"] == "Mới"

    deleted = await client.delete(PREFIX + "/api/v1/chats/sess-1", headers=bearer())
    assert deleted.status_code == 200 and deleted.json()["deletedAt"]
    assert (await client.get(PREFIX + "/api/v1/chats", headers=bearer())).json()["chats"] == []
    assert (await client.get(PREFIX + "/api/v1/chats/sess-1", headers=bearer())).status_code == 404
    # Mã đã xóa không tạo lại được, như AIRI.
    assert (await client.post(PREFIX + "/api/v1/chats", json=body, headers=bearer())).status_code == 409


async def test_chats_are_private_to_each_account(client):
    await client.post(PREFIX + "/api/v1/chats", json={"id": "same"}, headers=bearer())
    assert (await client.get(PREFIX + "/api/v1/chats", headers=bearer(OTHER))).json()["chats"] == []
    assert (await client.get(PREFIX + "/api/v1/chats/same", headers=bearer(OTHER))).status_code == 404
    assert (await client.delete(PREFIX + "/api/v1/chats/same", headers=bearer(OTHER))).status_code == 404
    # Cùng mã ở tài khoản khác là một hội thoại khác.
    assert (await client.post(PREFIX + "/api/v1/chats", json={"id": "same"}, headers=bearer(OTHER))).status_code == 201
    assert len((await client.get(PREFIX + "/api/v1/chats", headers=bearer())).json()["chats"]) == 1


async def test_server_picks_an_id_when_none_is_given(client):
    created = await client.post(PREFIX + "/api/v1/chats", json={}, headers=bearer())
    assert created.status_code == 201 and created.json()["id"] and created.json()["type"] == "group"


@pytest.mark.parametrize("body", [
    {"type": "secret"}, {"title": "x" * 501}, {"id": "x" * 65}, {"id": ""},
    {"members": [{"type": "robot"}]}, {"members": "all"}, {"members": [{"type": "character"}]},
])
async def test_bad_chats_are_400(client, body):
    assert (await client.post(PREFIX + "/api/v1/chats", json=body, headers=bearer())).status_code == 400


async def test_chat_count_cap(client, monkeypatch):
    monkeypatch.setattr(airi_chats, "MAX_CHATS", 1)
    assert (await client.post(PREFIX + "/api/v1/chats", json={"id": "a"}, headers=bearer())).status_code == 201
    response = await client.post(PREFIX + "/api/v1/chats", json={"id": "b"}, headers=bearer())
    assert response.status_code == 413 and "Xóa bớt" in response.json()["message"]


# --- WebSocket --------------------------------------------------------------------------------------------------------

def _create(owner: str, chat_id: str) -> None:
    asyncio.run(airi_chats.create_chat(owner, airi_sync.sync_user_id(owner), chat_id, "bot", None, []))


def test_socket_closes_without_a_valid_first_authenticate_frame(ws_client):
    for first in (request_frame("chat:pull-messages", {"chatId": "x", "afterSeq": 0}),
                  request_frame("chat:authenticate", {"token": "junk"}),
                  request_frame("chat:authenticate", {"token": auth._sign(TEST_OWNER)})):
        with ws_client.websocket_connect(PREFIX + "/ws/v2/chat") as ws:
            ws.send_text(first)
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_text()
            assert closed.value.code == airi_sync.CLOSE_UNAUTHORIZED


def test_a_few_non_call_frames_before_authenticate_are_skipped(ws_client):
    # eventa sends its own "connected" event first when its context exists before the socket opens.
    connected = json.dumps({"deliveryId": "x", "hopsRemaining": 31, "eventa": {
        "id": "SDlCADrpdKGxxlGs", "type": "event", "body": {"url": "ws://example.com"}, "_flowDirection": "outbound"}})
    with ws_client.websocket_connect(PREFIX + "/ws/v2/chat") as ws:
        ws.send_text(connected)
        ws.send_text("not json")
        event = call(ws, "chat:authenticate", {"token": airi_sync.issue_token(TEST_OWNER)}, "auth")
        assert event["invokeType"] == 4

    with ws_client.websocket_connect(PREFIX + "/ws/v2/chat") as ws:
        for _ in range(airi_sync.MAX_PRE_AUTH_FRAMES):
            ws.send_text(connected)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
        assert closed.value.code == airi_sync.CLOSE_UNAUTHORIZED


def test_socket_is_refused_when_the_airi_page_is_off(ws_client, monkeypatch):
    monkeypatch.setattr(config, "AIRI_DIR", None)
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(PREFIX + "/ws/v2/chat") as ws:
            ws.receive_text()


def test_send_pull_and_fanout_to_the_other_devices_of_the_account(ws_client):
    _create(TEST_OWNER, "chat-1")
    _create(OTHER, "chat-1")
    phone_cm, phone = open_socket(ws_client)
    laptop_cm, laptop = open_socket(ws_client)
    stranger_cm, stranger = open_socket(ws_client, OTHER)
    try:
        messages = [{"id": "m1", "role": "user", "content": "chào"}, {"id": "m2", "role": "assistant", "content": "hi"}]
        sent = call(phone, "chat:send-messages", {"chatId": "chat-1", "messages": messages}, "s1")
        assert sent["id"] == "chat:send-messages-receive-s1" and sent["body"]["content"] == {"seq": 2}

        pushed = read(laptop)
        assert pushed["id"] == "chat:new-messages" and "invokeType" not in pushed
        body = pushed["body"]
        assert body["chatId"] == "chat-1" and body["fromSeq"] == 1 and body["toSeq"] == 2
        assert [(m["id"], m["role"], m["content"], m["seq"]) for m in body["messages"]] == [
            ("m1", "user", "chào", 1), ("m2", "assistant", "hi", 2)]
        assert body["messages"][0]["senderId"] == airi_sync.sync_user_id(TEST_OWNER)

        # Sửa tin đã có: cùng mã, seq mới, máy kia nhận bản sửa.
        call(phone, "chat:send-messages", {"chatId": "chat-1", "messages": [
            {"id": "m2", "role": "assistant", "content": "hi again"}]}, "s2")
        assert read(laptop)["body"]["messages"][0]["content"] == "hi again"

        pulled = call(laptop, "chat:pull-messages", {"chatId": "chat-1", "afterSeq": 1}, "p1")["body"]["content"]
        assert pulled["seq"] == 3 and [(m["id"], m["seq"]) for m in pulled["messages"]] == [("m2", 3)]
        limited = call(laptop, "chat:pull-messages", {"chatId": "chat-1", "afterSeq": 0, "limit": 1}, "p2")
        assert len(limited["body"]["content"]["messages"]) == 1

        # Tài khoản khác cùng mã hội thoại không thấy gì và không nhận tin.
        theirs = call(stranger, "chat:pull-messages", {"chatId": "chat-1", "afterSeq": 0}, "p3")
        assert theirs["body"]["content"] == {"messages": [], "seq": 0}
    finally:
        for manager in (phone_cm, laptop_cm, stranger_cm):
            manager.__exit__(None, None, None)


@pytest.mark.parametrize(("content", "fragment"), [
    ({"chatId": "chat-2", "messages": [{"id": "t", "role": "tool", "content": "x"}]}, "người dùng"),
    ({"chatId": "missing", "messages": [{"id": "a", "role": "user", "content": "x"}]}, "Không tìm thấy"),
    ({"chatId": "chat-2", "messages": "x"}, "không hợp lệ"),
    ({"chatId": "chat-2", "messages": [{"id": "a", "role": "user", "content": 5}]}, "không hợp lệ"),
])
def test_bad_sends_are_error_replies_and_the_socket_stays(ws_client, content, fragment):
    _create(TEST_OWNER, "chat-2")
    manager, ws = open_socket(ws_client)
    try:
        event = call(ws, "chat:send-messages", content, "bad")
        assert event["id"] == "chat:send-messages-receive-error-bad" and event["invokeType"] == 5
        assert fragment in event["body"]["content"]["error"]["message"]
        assert call(ws, "chat:pull-messages", {"chatId": "chat-2", "afterSeq": 0}, "ok")["invokeType"] == 4
    finally:
        manager.__exit__(None, None, None)


def test_message_of_another_chat_is_refused_and_delete_drops_messages(ws_client):
    _create(TEST_OWNER, "a")
    _create(TEST_OWNER, "b")
    manager, ws = open_socket(ws_client)
    try:
        call(ws, "chat:send-messages", {"chatId": "a", "messages": [{"id": "m", "role": "user", "content": "x"}]}, "1")
        moved = call(ws, "chat:send-messages", {"chatId": "b", "messages": [{"id": "m", "role": "user", "content": "y"}]}, "2")
        assert moved["invokeType"] == 5
        asyncio.run(airi_chats.delete_chat(TEST_OWNER, "u", "a"))
        gone = call(ws, "chat:pull-messages", {"chatId": "a", "afterSeq": 0}, "3")
        assert gone["invokeType"] == 5
    finally:
        manager.__exit__(None, None, None)

    async def remaining():
        async with db.connection.connect() as conn:
            return (await (await conn.execute(
                "SELECT COUNT(*) FROM airi_chat_messages WHERE owner=? AND chat_id='a'", (TEST_OWNER,))).fetchone())[0]
    assert asyncio.run(remaining()) == 0


def test_message_cap(ws_client, monkeypatch):
    monkeypatch.setattr(airi_chats, "MAX_MESSAGES", 1)
    _create(TEST_OWNER, "c")
    manager, ws = open_socket(ws_client)
    try:
        ok = call(ws, "chat:send-messages", {"chatId": "c", "messages": [{"id": "1", "role": "user", "content": "x"}]}, "1")
        assert ok["invokeType"] == 4
        full = call(ws, "chat:send-messages", {"chatId": "c", "messages": [{"id": "2", "role": "user", "content": "y"}]}, "2")
        assert full["invokeType"] == 5 and "đầy" in full["body"]["content"]["error"]["message"]
        # Sửa tin đã có vẫn được khi đã đầy.
        edit = call(ws, "chat:send-messages", {"chatId": "c", "messages": [{"id": "1", "role": "user", "content": "z"}]}, "3")
        assert edit["invokeType"] == 4
    finally:
        manager.__exit__(None, None, None)


def test_logs_never_carry_message_text(ws_client, caplog):
    _create(TEST_OWNER, "log")
    manager, ws = open_socket(ws_client)
    try:
        with caplog.at_level("INFO"):
            call(ws, "chat:send-messages", {"chatId": "log", "messages": [
                {"id": "1", "role": "user", "content": "bí mật riêng"}]}, "1")
    finally:
        manager.__exit__(None, None, None)
    assert "bí mật riêng" not in caplog.text
