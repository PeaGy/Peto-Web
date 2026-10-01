"""API lịch sử hội thoại, tệp đính kèm và đăng ký luồng chat."""

from __future__ import annotations
from pathlib import Path
from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
import storage as db
from features.accounts.auth import current_owner
from features.chat import conversations as conversation_actions
from features.chat.history import _public_message
from features.chat.schemas import ConversationUpdate
from fastapi import APIRouter
from features.chat import service
router = APIRouter()
router.add_api_route("/api/chat", service.chat, methods=["POST"])

@router.get("/api/conversations")
async def list_conversations(
    owner: str = Depends(current_owner),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default='', max_length=200),
) -> dict:
    rows = await db.list_conversations(owner, limit=limit + 1, offset=offset, query=q.strip())
    return {"conversations": rows[:limit], "has_more": len(rows) > limit}


@router.patch('/api/conversations/{conversation_id}')
async def update_conversation(conversation_id: str, body: ConversationUpdate, owner: str = Depends(current_owner)):
    await conversation_actions.update(owner, conversation_id, body.title, body.pinned)
    return {'updated': True}


@router.get('/api/conversations/{conversation_id}/versions')
async def conversation_versions(conversation_id: str, owner: str = Depends(current_owner)):
    return {'versions': await conversation_actions.versions(owner, conversation_id)}


@router.get("/api/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str, owner: str = Depends(current_owner)
) -> dict:
    settings = await db.conversation_settings(owner, conversation_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    rows = await db.get_messages(owner, conversation_id)
    companion = settings["mode"] == "companion"
    return {"messages": [_public_message(row, companion) for row in rows]}


@router.get("/api/attachments/{attachment_id}")
async def get_attachment(attachment_id: str, owner: str = Depends(current_owner)):
    record = await db.get_attachment(owner, attachment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")
    path = Path(record["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")
    inline = record["kind"] == "image"
    return FileResponse(
        path,
        media_type=record["mime"],
        filename=record["filename"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, owner: str = Depends(current_owner)
) -> dict:
    if not await db.delete_conversation(owner, conversation_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return {"deleted": True}
