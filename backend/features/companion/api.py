"""Lấy hội thoại gần nhất của Companion."""

from __future__ import annotations
from fastapi import Depends
import storage as db
from features.accounts.auth import current_owner
from core.config import MAX_HISTORY_MESSAGES
from fastapi import APIRouter
from features.chat.history import _public_message
router = APIRouter()

@router.get("/api/companion")
async def get_companion(owner: str = Depends(current_owner)) -> dict:
    """Mạch trò chuyện của tab Companion: cuộc mới nhất cùng các tin gần đây."""
    conversation_id = await db.latest_conversation(owner, "companion")
    if not conversation_id:
        return {"conversation_id": None, "messages": []}
    rows = await db.get_messages(owner, conversation_id, limit=MAX_HISTORY_MESSAGES)
    return {"conversation_id": conversation_id, "messages": [_public_message(row, True) for row in rows]}

