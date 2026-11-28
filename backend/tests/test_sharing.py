"""Link chia sẻ cuộc trò chuyện (28/11/2026): bản chụp công khai, chỉ đọc, không cần đăng nhập, thu hồi được."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import storage as db
from core.config import UPLOAD_DIR
from features.chat import sharing
from tests.conftest import TEST_OWNER, _make_client, read_events, sign_in


async def _chat(client, text: str = "Chào Peto") -> str:
    events = await read_events(await client.post("/api/chat", json={"message": text}))
    assert events[-1]["type"] == "done"
    return next(event["conversation_id"] for event in events if event["type"] == "meta")


async def test_create_read_update_and_revoke(client, anon_client):
    conversation = await _chat(client, "Câu hỏi bí mật số một")
    assert (await client.get(f"/api/conversations/{conversation}/share")).json() == {"share": None}

    created = (await client.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]
    share_id = created["id"]
    assert len(share_id) >= 16 and created["include_images"] is False and created["message_count"] == 2

    # Người xem không đăng nhập đọc được bản chụp: chỉ vai, chữ, thời điểm; không có mã hội thoại hay chủ link.
    public = await anon_client.get(f"/api/shared/{share_id}")
    assert public.status_code == 200
    assert public.headers["cache-control"] == "no-store" and "noindex" in public.headers["x-robots-tag"]
    body = public.json()
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "Câu hỏi bí mật số một"
    assert TEST_OWNER not in public.text and conversation not in public.text

    # Tin gửi sau không lọt vào link; "Cập nhật link" chụp lại mà giữ nguyên mã.
    await client.post("/api/chat", json={"message": "Tin gửi sau", "conversation_id": conversation})
    assert "Tin gửi sau" not in (await anon_client.get(f"/api/shared/{share_id}")).text
    updated = (await client.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]
    assert updated["id"] == share_id and updated["message_count"] == 4
    assert "Tin gửi sau" in (await anon_client.get(f"/api/shared/{share_id}")).text

    listed = (await client.get("/api/shares")).json()["shares"]
    assert listed[0]["id"] == share_id and listed[0]["message_count"] == 4

    assert (await client.delete(f"/api/shares/{share_id}")).json() == {"deleted": True}
    gone = await anon_client.get(f"/api/shared/{share_id}")
    assert gone.status_code == 404 and "thu hồi" in gone.json()["detail"]


async def test_other_accounts_cannot_share_or_revoke(client):
    conversation = await _chat(client)
    share_id = (await client.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]["id"]
    async with _make_client() as other:
        await db.init_db()
        await sign_in(other)
        assert (await other.post(f"/api/conversations/{conversation}/share", json={})).status_code == 404
        assert (await other.get(f"/api/conversations/{conversation}/share")).status_code == 404
        assert (await other.delete(f"/api/shares/{share_id}")).status_code == 404
        assert (await other.get("/api/shares")).json() == {"shares": []}
    assert (await client.get(f"/api/shared/{share_id}")).status_code == 200


async def test_deleting_the_conversation_removes_its_link(client, anon_client):
    conversation = await _chat(client)
    share_id = (await client.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]["id"]
    assert (await client.delete(f"/api/conversations/{conversation}")).status_code == 200
    assert (await anon_client.get(f"/api/shared/{share_id}")).status_code == 404
    assert share_id not in [item["id"] for item in (await client.get("/api/shares")).json()["shares"]]


async def test_deleting_the_account_removes_its_links(anon_client):
    async with _make_client() as other:
        await sign_in(other)
        conversation = await _chat(other)
        share_id = (await other.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]["id"]
        assert (await other.post("/api/account/delete", json={"confirm": "XÓA"})).status_code == 200
    assert (await anon_client.get(f"/api/shared/{share_id}")).status_code == 404


async def test_bad_ids_and_anonymous_management(anon_client):
    assert (await anon_client.get("/api/shared/short")).status_code == 404
    assert (await anon_client.get("/api/shared/" + "x" * 22)).status_code == 404
    assert (await anon_client.get("/api/shares")).status_code == 401
    assert (await anon_client.post(f"/api/conversations/{uuid.uuid4().hex}/share", json={})).status_code == 401


async def test_images_only_when_included(client, anon_client):
    conversation = await _chat(client)
    rows = await db.get_messages(TEST_OWNER, conversation)
    user_message = next(row for row in rows if row["role"] == "user")
    folder = UPLOAD_DIR / conversation
    folder.mkdir(parents=True, exist_ok=True)
    image_path, file_path = folder / "anh.png", folder / "bao-cao.pdf"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nanh")
    file_path.write_bytes(b"%PDF-1.4")
    for attachment_id, name, mime, kind, path in (("img1", "anh.png", "image/png", "image", image_path),
                                                  ("pdf1", "bao-cao.pdf", "application/pdf", "file", file_path)):
        await db.add_attachment(attachment_id=attachment_id, owner=TEST_OWNER, conversation_id=conversation,
                                message_id=user_message["id"], filename=name, mime=mime, kind=kind, size=8, path=str(path))

    share_id = (await client.post(f"/api/conversations/{conversation}/share", json={})).json()["share"]["id"]
    files = (await anon_client.get(f"/api/shared/{share_id}")).json()["messages"][0]["attachments"]
    assert files == [{"name": "anh.png", "kind": "image"}, {"name": "bao-cao.pdf", "kind": "file"}]
    assert (await anon_client.get(f"/api/shared/{share_id}/images/img1")).status_code == 404

    await client.post(f"/api/conversations/{conversation}/share", json={"include_images": True})
    files = (await anon_client.get(f"/api/shared/{share_id}")).json()["messages"][0]["attachments"]
    assert files[0] == {"name": "anh.png", "kind": "image", "id": "img1"} and "id" not in files[1]
    image = await anon_client.get(f"/api/shared/{share_id}/images/img1")
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert image.headers["x-content-type-options"] == "nosniff"
    # Tệp không phải ảnh, hay mã ảnh không có trong bản chụp, không mở được.
    assert (await anon_client.get(f"/api/shared/{share_id}/images/pdf1")).status_code == 404
    assert (await anon_client.get(f"/api/shared/{share_id}/images/khac")).status_code == 404


def test_snapshot_keeps_only_public_fields():
    rows = [
        {"role": "system", "content": "bí mật"},
        {"role": "user", "content": "Hỏi", "created_at": 1, "work": {"steps": []}, "quoted_source": {"text": "x"}},
        {"role": "assistant", "content": "  ", "created_at": 2},
        {"role": "assistant", "content": "Đáp [web:1]", "created_at": 3, "work": {"steps": [1]},
         "sources": [{"url": "https://example.com", "title": "Nguồn"}],
         "artifacts": [{"title": "Báo cáo", "filename": "bao-cao.docx", "id": "d1", "version": 2}]},
    ]
    result = sharing.snapshot(rows, include_images=False)
    assert [item["role"] for item in result] == ["user", "assistant"]
    assert set(result[0]) == {"role", "content", "created_at"}
    assert result[1]["documents"] == [{"title": "Báo cáo", "filename": "bao-cao.docx"}]
    assert result[1]["sources"][0]["url"] == "https://example.com"
    assert "work" not in result[1]


@pytest.mark.parametrize("path, public", [("s/" + "a" * 22, True), ("s/abc", False), ("s/" + "a" * 22 + "/x", False)])
def test_share_page_path(path, public):
    from core.static_files import _SHARE_PATH
    assert bool(_SHARE_PATH.fullmatch(path)) is public
