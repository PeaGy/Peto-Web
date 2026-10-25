"""Mạch trò chuyện Companion: mạch đang mở, danh sách mạch, mạch mới (theo thẻ nhân vật như AIRI)."""

from __future__ import annotations
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
import storage as db
from features.accounts.auth import current_owner
from core.config import MAX_HISTORY_MESSAGES
from fastapi import APIRouter
from features.chat.history import _public_message
from features.companion import cards as companion_cards
from storage import cards as card_store
router = APIRouter()


class NewConversation(BaseModel):
    card_id: str | None = Field(default=None, max_length=32)


class OpenConversation(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)


async def _thread(owner: str, conversation_id: str | None, card_id: str) -> dict:
    """Mạch kèm ``title`` (tin đầu tiên, cắt ngắn) cho tiêu đề khung chat."""
    found = await card_store.companion_conversation(owner, conversation_id) if conversation_id else None
    if not found:
        return {"conversation_id": None, "card_id": card_id, "title": "", "messages": []}
    rows = await db.get_messages(owner, conversation_id, limit=MAX_HISTORY_MESSAGES)
    return {"conversation_id": conversation_id, "card_id": found["card_id"], "title": found["title"],
            "messages": [_public_message(row, True) for row in rows]}


@router.get("/api/companion")
async def get_companion(conversation_id: str | None = None, owner: str = Depends(current_owner)) -> dict:
    """Một mạch Companion cùng các tin gần đây: mạch được hỏi, hoặc mạch đang mở của thẻ đang dùng."""
    if conversation_id:
        found = await card_store.companion_conversation(owner, conversation_id)
        if found is None:
            raise HTTPException(404, "Không tìm thấy hội thoại")
        return await _thread(owner, found["id"], found["card_id"])
    active, _ = await card_store.list_cards(owner)
    return await _thread(owner, await card_store.active_conversation(owner, active), active)


@router.get("/api/companion/conversations")
async def list_conversations(owner: str = Depends(current_owner)) -> dict:
    """Mọi mạch Companion, hoạt động gần nhất trước (AIRI: sessions-drawer). ``preview`` là tiêu đề hoặc tin đầu."""
    active, cards = await card_store.list_cards(owner)
    names = {card["id"]: companion_cards.effective(card)["name"] for card in cards}
    current = await card_store.active_conversation(owner, active)
    items = []
    for row in await card_store.list_companion_conversations(owner):
        preview = " ".join((row["title"] or row["first_user"] or "").split())
        items.append({
            "id": row["id"], "card_id": row["card_id"], "card_name": names.get(row["card_id"], ""),
            "preview": preview[:80] + ("…" if len(preview) > 80 else ""),
            "message_count": row["message_count"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "active": row["id"] == current,
        })
    return {"active_card": active, "conversations": items}


@router.post("/api/companion/conversations")
async def new_conversation(body: NewConversation, owner: str = Depends(current_owner)) -> dict:
    """"Hội thoại mới" cho thẻ được chọn (mặc định thẻ đang dùng); mạch có câu chào đầu nếu thẻ có."""
    card = await companion_cards.resolve(owner, body.card_id)
    conversation_id = await db.create_conversation(owner, mode="companion", card_id=card["id"])
    await companion_cards.open_conversation(owner, card, conversation_id)
    return await _thread(owner, conversation_id, card["id"])


@router.put("/api/companion/active")
async def open_conversation(body: OpenConversation, owner: str = Depends(current_owner)) -> dict:
    """Mở một mạch cũ: thẻ của mạch thành thẻ đang dùng và nhớ mạch này là mạch đang mở của thẻ."""
    found = await card_store.companion_conversation(owner, body.conversation_id)
    if found is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    await card_store.set_active_card(owner, found["card_id"], found["id"])
    return {"conversation_id": found["id"], "card_id": found["card_id"]}
