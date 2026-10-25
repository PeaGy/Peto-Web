"""Thẻ nhân vật Companion (Cài đặt Companion → Thẻ nhân vật, và nút Profile ở đầu khung chat), theo trang AIRI Card.

Mọi thao tác chỉ đụng thẻ của tài khoản đang đăng nhập. Thẻ mặc định ``peto`` không xóa được, chỉ khôi phục bản gốc.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import storage as db
from features.accounts.auth import current_owner
from features.chat.prompt_context import _build_system_prompt
from features.companion import cards as companion_cards
from storage import cards as card_store
from storage.cards import DEFAULT_CARD

router = APIRouter(prefix="/api/companion/cards", tags=["companion-cards"])


class CardFields(BaseModel):
    """Trường gửi lên; chỉ trường có mặt mới được đổi. Kiểu và độ dài kiểm trong ``companion_cards.clean``."""
    name: Any = None
    nickname: Any = None
    version: Any = None
    description: Any = None
    notes: Any = None
    personality: Any = None
    scenario: Any = None
    system_prompt: Any = None
    post_history: Any = None
    display_model: Any = None
    greetings: Any = None
    modules: Any = None


class ActiveCard(BaseModel):
    card_id: str = Field(min_length=1, max_length=32)


def _sent(body: CardFields) -> dict:
    return body.model_dump(exclude_unset=True)


async def _owned(owner: str, card_id: str) -> dict:
    card = await card_store.get_card(owner, companion_cards.check_id(card_id))
    if card is None:
        raise HTTPException(404, "Không tìm thấy thẻ nhân vật")
    return card


@router.get("")
async def list_cards(owner: str = Depends(current_owner)) -> dict:
    active, cards = await card_store.list_cards(owner)
    return {"active_card": active, "limit": companion_cards.MAX_CARDS,
            "cards": [companion_cards.public(card) for card in cards]}


@router.post("", status_code=201)
async def create_card(body: CardFields, owner: str = Depends(current_owner)) -> dict:
    """Tạo thẻ mới, hoặc nhân bản thẻ đang dùng ("Lưu thành Profile mới": trang gửi đủ trường của thẻ cũ)."""
    fields = companion_cards.clean(_sent(body), None)
    if not fields.get("name"):
        raise HTTPException(400, "Thẻ cần có tên.")
    card = {**companion_cards.EMPTY, **fields}
    companion_cards.check_size(card)
    _, cards = await card_store.list_cards(owner)
    companion_cards.check_name(card["name"], cards, None)
    card_id = await card_store.create_card(owner, card, companion_cards.MAX_CARDS)
    if card_id is None:
        raise HTTPException(409, f"Mỗi tài khoản có tối đa {companion_cards.MAX_CARDS} thẻ tự tạo.")
    return companion_cards.public(await card_store.get_card(owner, card_id))


@router.put("/active")
async def set_active(body: ActiveCard, owner: str = Depends(current_owner)) -> dict:
    """Đổi thẻ đang dùng (Profile). Trang mở tiếp mạch đang mở của thẻ đó qua GET /api/companion."""
    await _owned(owner, body.card_id)
    await card_store.set_active_card(owner, body.card_id)
    return {"active_card": body.card_id}


@router.get("/{card_id}")
async def get_card(card_id: str, owner: str = Depends(current_owner)) -> dict:
    return companion_cards.public(await _owned(owner, card_id))


@router.patch("/{card_id}")
async def update_card(card_id: str, body: CardFields, owner: str = Depends(current_owner)) -> dict:
    current = await _owned(owner, card_id)
    fields = companion_cards.clean(_sent(body), card_id)
    merged = companion_cards.effective({**current, **fields})
    companion_cards.check_size(merged)
    if "name" in fields:
        _, cards = await card_store.list_cards(owner)
        companion_cards.check_name(merged["name"], cards, card_id)
    await card_store.update_card(owner, card_id, fields)
    return companion_cards.public(await _owned(owner, card_id))


@router.post("/{card_id}/reset")
async def reset_card(card_id: str, owner: str = Depends(current_owner)) -> dict:
    """Thẻ Peto mặc định về đúng bản gốc của máy chủ (và theo các lần cập nhật bản gốc về sau)."""
    if card_id != DEFAULT_CARD:
        raise HTTPException(400, "Chỉ thẻ Peto mặc định mới khôi phục được bản gốc.")
    await _owned(owner, card_id)
    _, cards = await card_store.list_cards(owner)
    companion_cards.check_name(companion_cards.BUILTIN["name"], cards, card_id)
    await card_store.update_card(owner, card_id, {name: None for name in card_store.FIELDS})
    return companion_cards.public(await _owned(owner, card_id))


@router.delete("/{card_id}")
async def delete_card(card_id: str, owner: str = Depends(current_owner)) -> dict:
    """Xóa thẻ tự tạo cùng mọi mạch trò chuyện của nó (kèm ảnh đã gửi). Thẻ mặc định không xóa được."""
    if card_id == DEFAULT_CARD:
        raise HTTPException(400, "Thẻ Peto mặc định không xóa được. Bạn có thể khôi phục bản gốc của nó.")
    await _owned(owner, card_id)
    conversations = await card_store.card_conversations(owner, card_id)
    for conversation_id in conversations:
        await db.delete_conversation(owner, conversation_id)
    await card_store.delete_card(owner, card_id)
    active, _ = await card_store.list_cards(owner)
    return {"deleted": True, "conversations_deleted": len(conversations), "active_card": active}


@router.get("/{card_id}/prompt")
async def card_prompt(card_id: str, owner: str = Depends(current_owner)) -> dict:
    """Toàn bộ system prompt máy chủ sẽ gửi cho lượt kế tiếp của thẻ, kể cả phần máy chủ tự thêm (giờ, trí nhớ, hồ
    sơ…): chủ web muốn công khai hết. Phần công cụ Player và tra web gắn thêm tùy lượt thì không có ở đây."""
    card = companion_cards.effective(await _owned(owner, card_id))
    remembers = companion_cards.remembers(card_id)
    conversation_id = await card_store.active_conversation(owner, card_id) if remembers else None
    prompt = await _build_system_prompt(owner, "companion", conversation_id=conversation_id, memory=remembers, card=card)
    return {"prompt": prompt, "memory": remembers}
