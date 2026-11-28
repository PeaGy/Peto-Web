"""Link chia sẻ cuộc trò chuyện (28/11/2026).

Chủ web chốt theo đề xuất: ai có link đều xem được, không cần đăng nhập; mặc định không kèm ảnh người dùng gửi, khi tạo
link có ô để kèm. Link là bản chụp tin nhắn của nhánh đang xem (``storage.shared_chats``): chỉ vai, chữ, nguồn, tên tệp
và tên tài liệu Peto tạo. Không bao giờ có trí nhớ, hồ sơ, hướng dẫn riêng, nhật ký "Đang làm" hay tên người chia sẻ.
Trang công khai ``/s/{id}`` (``core.static_files``) đọc ``GET /api/shared/{id}``, có ``noindex``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

import storage as db
from features.accounts.auth import current_owner
from shared.web_search import normalize_sources
from storage import connection as db_connection
from storage import shared_chats

router = APIRouter(tags=["sharing"])

MAX_LINKS = 100
MAX_SNAPSHOT_BYTES = 2_000_000
SHARE_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
PUBLIC_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}


class ShareRequest(BaseModel):
    include_images: bool = False


async def _chat_title(owner: str, conversation_id: str) -> str | None:
    """Tiêu đề của hội thoại Chat (không phải Companion) thuộc owner; None nếu không có."""
    async with db_connection.connect() as conn:
        row = await (await conn.execute("SELECT title, mode FROM conversations WHERE id=? AND owner=?",
                                        (conversation_id, owner))).fetchone()
    if not row or row[1] != "chat":
        return None
    return row[0] or "Cuộc trò chuyện với Peto"


def snapshot(rows: list[dict], include_images: bool) -> list[dict]:
    """Bản chụp công khai của các tin: chỉ những gì người xem cần để đọc lại cuộc trò chuyện."""
    result = []
    for row in rows:
        if row.get("role") not in ("user", "assistant"):
            continue
        content = (row.get("content") or "").strip()
        files = []
        for item in row.get("attachments") or []:
            image = item.get("kind") == "image"
            entry = {"name": item.get("filename") or "tệp", "kind": "image" if image else "file"}
            if image and include_images:
                entry["id"] = item["id"]
            files.append(entry)
        documents = [{"title": item.get("title") or "", "filename": item.get("filename") or ""}
                     for item in row.get("artifacts") or [] if isinstance(item, dict)] if row["role"] == "assistant" else []
        if not content and not files and not documents:
            continue
        message = {"role": row["role"], "content": content, "created_at": row.get("created_at")}
        if files:
            message["attachments"] = files
        if documents:
            message["documents"] = documents
        if row["role"] == "assistant":
            sources = normalize_sources(row.get("sources"))
            if sources:
                message["sources"] = sources
        result.append(message)
    return result


def _public_link(share: dict) -> dict:
    return {"id": share["id"], "conversation_id": share["conversation_id"], "title": share["title"],
            "include_images": share["include_images"], "created_at": share["created_at"],
            "updated_at": share["updated_at"],
            "message_count": share.get("message_count", len(share.get("snapshot") or []))}


@router.get("/api/conversations/{conversation_id}/share")
async def current_share(conversation_id: str, owner: str = Depends(current_owner)) -> dict:
    if await _chat_title(owner, conversation_id) is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    share = await shared_chats.for_conversation(owner, conversation_id)
    return {"share": _public_link(share) if share else None}


@router.post("/api/conversations/{conversation_id}/share")
async def create_share(conversation_id: str, body: ShareRequest, owner: str = Depends(current_owner)) -> dict:
    title = await _chat_title(owner, conversation_id)
    if title is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    existing = await shared_chats.for_conversation(owner, conversation_id)
    if existing is None and await shared_chats.count_for_owner(owner) >= MAX_LINKS:
        raise HTTPException(429, f"Bạn đã có {MAX_LINKS} link chia sẻ. Xóa bớt ở Cài đặt → Link chia sẻ rồi thử lại nhé.")
    messages = snapshot(await db.get_messages(owner, conversation_id), body.include_images)
    if not messages:
        raise HTTPException(400, "Cuộc trò chuyện chưa có tin nhắn để chia sẻ.")
    if len(json.dumps(messages, ensure_ascii=False).encode()) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(413, "Cuộc trò chuyện quá dài để chia sẻ bằng link.")
    share = await shared_chats.save(owner, conversation_id, title, messages, body.include_images)
    return {"share": _public_link(share)}


@router.get("/api/shares")
async def list_shares(owner: str = Depends(current_owner)) -> dict:
    return {"shares": [_public_link(item) for item in await shared_chats.list_for_owner(owner)]}


@router.delete("/api/shares/{share_id}")
async def delete_share(share_id: str, owner: str = Depends(current_owner)) -> dict:
    if not SHARE_ID.fullmatch(share_id) or not await shared_chats.delete(owner, share_id):
        raise HTTPException(404, "Không tìm thấy link chia sẻ")
    return {"deleted": True}


async def _public_share(share_id: str) -> dict:
    share = await shared_chats.get(share_id) if SHARE_ID.fullmatch(share_id) else None
    if share is None:
        raise HTTPException(404, "Link chia sẻ không còn hoặc đã bị thu hồi.", headers=PUBLIC_HEADERS)
    return share


@router.get("/api/shared/{share_id}")
async def read_shared(share_id: str, response: Response) -> dict:
    """Trang công khai, không cần đăng nhập: không trả mã hội thoại hay chủ link."""
    share = await _public_share(share_id)
    response.headers.update(PUBLIC_HEADERS)
    return {"title": share["title"], "updated_at": share["updated_at"], "include_images": share["include_images"],
            "messages": share["snapshot"]}


@router.get("/api/shared/{share_id}/images/{attachment_id}")
async def shared_image(share_id: str, attachment_id: str):
    """Ảnh người dùng gửi, chỉ khi link được tạo với "Kèm ảnh" và ảnh có trong bản chụp."""
    share = await _public_share(share_id)
    allowed = share["include_images"] and any(
        item.get("id") == attachment_id for message in share["snapshot"] for item in message.get("attachments") or [])
    record = await db.get_attachment(share["owner"], attachment_id) if allowed else None
    # Ảnh phải nằm trong bản chụp và thuộc chủ link; hội thoại tách nhánh có thể dùng ảnh của hội thoại gốc.
    if not record or record["kind"] != "image":
        raise HTTPException(404, "Không tìm thấy ảnh", headers=PUBLIC_HEADERS)
    path = Path(record["path"])
    if not path.is_file():
        raise HTTPException(404, "Không tìm thấy ảnh", headers=PUBLIC_HEADERS)
    return FileResponse(path, media_type=record["mime"], content_disposition_type="inline",
                        headers={**PUBLIC_HEADERS, "X-Content-Type-Options": "nosniff"})
