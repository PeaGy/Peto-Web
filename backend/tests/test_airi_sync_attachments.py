"""Ảnh trong tin Companion bản AIRI (``features/companion/airi_sync.py``, phần "Ảnh"): đăng ký, đẩy byte qua địa chỉ
có chữ ký, finalize, gửi tin kèm ``mediaIds``, máy khác nhận ``attachments`` và tải ảnh về; dọn ảnh khi xóa."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import storage as db
from conftest import TEST_OWNER
from core import config
from core.config import owner_key
from features.accounts import deletion
from features.companion import airi_sync
from main import app
from storage import airi_chats
from test_airi_sync import PREFIX, bearer, call, open_socket, read

OTHER = owner_key("github", "airi-attach-other")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture(autouse=True)
def airi_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AIRI_DIR", tmp_path)


@pytest.fixture
def api():
    async def clear():
        await db.init_db()
        async with db.connection.connect() as conn:
            for table in ("companion_chat_messages", "companion_chats", "companion_attachments"):
                await conn.execute(f"DELETE FROM {table}")
            await conn.commit()
    asyncio.run(clear())
    # Files of an earlier test with the same image id would let a finalize pass before its upload.
    shutil.rmtree(config.UPLOAD_DIR / "companion", ignore_errors=True)
    with TestClient(app) as test_client:
        yield test_client


def register(api, attachment_id="img-1", data=PNG, mime="image/png", owner=TEST_OWNER, sha256=None):
    body = {"id": attachment_id, "mimeType": mime, "sha256": sha256 or hashlib.sha256(data).hexdigest(),
            "size": len(data)}
    return api.post(PREFIX + "/api/v1/attachments", json=body, headers=bearer(owner))


def upload(api, attachment_id="img-1", data=PNG, owner=TEST_OWNER):
    """Đăng ký, đẩy byte và finalize như trang AIRI (``libs/chat-sync/attachments.ts``)."""
    created = register(api, attachment_id, data, owner=owner)
    assert created.status_code == 201, created.text
    target = created.json()["upload"]
    if target:
        assert target["headers"] == {}
        assert api.put(target["url"], content=data).status_code == 200
    finalized = api.post(f"{PREFIX}/api/v1/attachments/{attachment_id}/finalize", headers=bearer(owner))
    assert finalized.status_code == 200, finalized.text
    return finalized.json()


def create_chat(api, chat_id="chat-1", owner=TEST_OWNER):
    response = api.post(PREFIX + "/api/v1/chats", json={"id": chat_id, "type": "bot"}, headers=bearer(owner))
    assert response.status_code == 201


def stored_path(attachment_id: str, owner: str = TEST_OWNER) -> Path:
    return Path(asyncio.run(airi_chats.get_attachment(owner, attachment_id))["path"])


def test_image_goes_up_and_the_other_device_gets_it(api):
    create_chat(api)
    created = register(api)
    assert created.status_code == 201
    body = created.json()
    assert body["attachment"] == {"id": "img-1", "mimeType": "image/png", "size": len(PNG)}
    assert body["upload"]["url"].startswith("http://testserver" + PREFIX + "/api/v1/attachments/img-1/content?sig=")
    # The signed link carries the opaque sync user id only, never the owner key.
    assert TEST_OWNER not in body["upload"]["url"]
    assert upload(api) == {"id": "img-1", "mimeType": "image/png", "size": len(PNG)}
    # Registering again after it is done asks for no second upload, like AIRI.
    assert register(api).json()["upload"] is None

    phone_cm, phone = open_socket(api)
    laptop_cm, laptop = open_socket(api)
    try:
        message = {"id": "m1", "role": "user", "content": "xem nè", "mediaIds": ["img-1"]}
        sent = call(phone, "chat:send-messages", {"chatId": "chat-1", "messages": [message]}, "s1")
        assert sent["body"]["content"] == {"seq": 1}
        pushed = read(laptop)["body"]["messages"][0]
        assert pushed["attachments"] == [{"id": "img-1", "mimeType": "image/png", "size": len(PNG)}]
        pulled = call(laptop, "chat:pull-messages", {"chatId": "chat-1", "afterSeq": 0}, "p1")["body"]["content"]
        assert pulled["messages"][0]["attachments"] == pushed["attachments"]
        # The same message sent again is unchanged and keeps its seq.
        again = call(phone, "chat:send-messages", {"chatId": "chat-1", "messages": [message]}, "s2")
        assert again["body"]["content"] == {"seq": 1}
    finally:
        phone_cm.__exit__(None, None, None)
        laptop_cm.__exit__(None, None, None)

    download = api.get(PREFIX + "/api/v1/attachments/img-1/download", headers=bearer())
    assert download.status_code == 200
    info = download.json()
    assert info["sha256"] == hashlib.sha256(PNG).hexdigest()
    content = api.get(info["url"])
    assert content.status_code == 200 and content.content == PNG
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"


def test_uploads_must_match_what_was_registered(api):
    register(api)
    url = register(api).json()["upload"]["url"]
    assert api.put(url, content=PNG + b"x").status_code == 400
    assert api.put(url, content=PNG[:-1] + b"x").status_code == 400
    # Right size and checksum, but not a PNG.
    text = b"not an image at all"
    fake = register(api, "img-2", text)
    assert api.put(fake.json()["upload"]["url"], content=text).status_code == 400
    assert api.post(PREFIX + "/api/v1/attachments/img-1/finalize", headers=bearer()).status_code == 409
    assert api.put(url, content=PNG).status_code == 200
    assert api.post(PREFIX + "/api/v1/attachments/img-1/finalize", headers=bearer()).status_code == 200
    # Once done, a new upload gets 412, which the AIRI page reads as "already there".
    assert api.put(url, content=PNG).status_code == 412


@pytest.mark.parametrize(("body", "status"), [
    ({"id": "bad id", "mimeType": "image/png", "sha256": "a" * 64, "size": 10}, 400),
    ({"id": "a", "mimeType": "image/svg+xml", "sha256": "a" * 64, "size": 10}, 400),
    ({"id": "a", "mimeType": "image/png", "sha256": "xyz", "size": 10}, 400),
    ({"id": "a", "mimeType": "image/png", "sha256": "a" * 64, "size": 3 * 1024 * 1024 + 1}, 400),
    ({"id": "a", "mimeType": "image/png", "sha256": "a" * 64, "size": True}, 400),
])
def test_bad_registrations(api, body, status):
    assert api.post(PREFIX + "/api/v1/attachments", json=body, headers=bearer()).status_code == status


def test_same_id_with_other_bytes_is_a_conflict(api):
    register(api)
    assert register(api, data=PNG + b"\x01").status_code == 409


def test_links_and_images_are_private(api):
    url = register(api).json()["upload"]["url"]
    content_url = url.split("?")[0]
    assert api.put(content_url, content=PNG).status_code == 403
    assert api.put(url + "x", content=PNG).status_code == 403
    # An upload link of one image is not one of another.
    register(api, "img-9")
    assert api.put(url.replace("/img-1/", "/img-9/"), content=PNG).status_code == 403
    assert api.put(url, content=PNG).status_code == 200
    api.post(PREFIX + "/api/v1/attachments/img-1/finalize", headers=bearer())
    # An upload link does not download.
    assert api.get(url).status_code == 403
    # Another account sees nothing of this image.
    assert api.get(PREFIX + "/api/v1/attachments/img-1/download", headers=bearer(OTHER)).status_code == 404
    assert api.post(PREFIX + "/api/v1/attachments/img-1/finalize", headers=bearer(OTHER)).status_code == 404
    assert api.get(PREFIX + "/api/v1/attachments/img-1/download").status_code == 401


def test_links_expire(api, monkeypatch):
    upload(api)
    url = api.get(PREFIX + "/api/v1/attachments/img-1/download", headers=bearer()).json()["url"]
    monkeypatch.setattr(airi_sync, "LINK_MAX_AGE", -1)
    assert api.get(url).status_code == 403


def test_messages_can_carry_only_own_finished_images(api):
    create_chat(api)
    register(api, "pending")
    upload(api, "theirs", owner=OTHER)
    upload(api, "mine")
    socket_cm, socket = open_socket(api)
    try:
        for media_ids, fragment in ((["pending"], "tải lên xong"), (["theirs"], "tải lên xong"),
                                    (["mine", "mine"], "tối đa"), (["a", "b", "c", "d", "e"], "tối đa"),
                                    (["bad id"], "Mã ảnh")):
            message = {"id": "m1", "role": "user", "content": "x", "mediaIds": media_ids}
            reply = call(socket, "chat:send-messages", {"chatId": "chat-1", "messages": [message]}, "s")
            assert fragment in reply["body"]["content"]["error"]["message"], media_ids
        message = {"id": "m1", "role": "user", "content": "x", "mediaIds": ["mine"]}
        assert call(socket, "chat:send-messages", {"chatId": "chat-1", "messages": [message]}, "ok")["body"][
            "content"] == {"seq": 1}
    finally:
        socket_cm.__exit__(None, None, None)


def test_deleting_a_chat_drops_images_no_other_chat_uses(api):
    create_chat(api, "chat-1")
    create_chat(api, "chat-2")
    upload(api, "only-here")
    upload(api, "shared")
    only_here, shared = stored_path("only-here"), stored_path("shared")
    assert only_here.is_file() and shared.is_file()
    socket_cm, socket = open_socket(api)
    try:
        call(socket, "chat:send-messages", {"chatId": "chat-1", "messages": [
            {"id": "m1", "role": "user", "content": "a", "mediaIds": ["only-here", "shared"]}]}, "s1")
        call(socket, "chat:send-messages", {"chatId": "chat-2", "messages": [
            {"id": "m2", "role": "user", "content": "b", "mediaIds": ["shared"]}]}, "s2")
    finally:
        socket_cm.__exit__(None, None, None)
    assert api.delete(PREFIX + "/api/v1/chats/chat-1", headers=bearer()).status_code == 200
    assert not only_here.exists() and shared.is_file()
    assert asyncio.run(airi_chats.get_attachment(TEST_OWNER, "only-here")) is None
    assert api.get(PREFIX + "/api/v1/attachments/shared/download", headers=bearer()).status_code == 200


def test_unfinished_uploads_are_cleaned_after_a_day(api):
    register(api, "old")
    old_url = register(api, "old").json()["upload"]["url"]
    api.put(old_url, content=PNG)
    old_path = stored_path("old")
    assert old_path.is_file()

    async def age():
        async with db.connection.connect() as conn:
            await conn.execute("UPDATE companion_attachments SET created_at=? WHERE id='old'",
                               (time.time() - airi_chats.PENDING_MAX_AGE - 1,))
            await conn.commit()
    asyncio.run(age())
    register(api, "new")
    assert asyncio.run(airi_chats.get_attachment(TEST_OWNER, "old")) is None
    assert not old_path.exists()


def test_deleting_the_account_removes_its_images(api):
    owner = owner_key("github", "airi-attach-leaving")
    upload(api, "bye", owner=owner)
    path = stored_path("bye", owner)
    assert path.is_file()
    asyncio.run(deletion.delete_account(owner))
    assert not path.exists() and not path.parent.exists()
    assert asyncio.run(airi_chats.get_attachment(owner, "bye")) is None
