"""Cài đặt → Trí nhớ Companion: xem, xóa và bật/tắt những điều Peto tự ghi nhớ (companion_memory.py).

Mọi thao tác chỉ đụng dòng của đúng tài khoản đang đăng nhập; biết id ghi nhớ của người khác cũng chỉ nhận 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from features.companion import memory as companion_memory
import storage as db
from features.accounts.auth import current_owner

router = APIRouter(prefix="/api/companion/memory", tags=["companion-memory"])


class MemorySettings(BaseModel):
    enabled: bool


def _public(item: dict) -> dict:
    return {"id": item["id"], "text": item["text"], "created_at": item["created_at"], "updated_at": item["updated_at"]}


@router.get("")
async def read_memory(owner: str = Depends(current_owner)) -> dict:
    """Danh sách ghi nhớ; ``pending`` là còn đang ghi nhớ lượt vừa xong (trang hỏi lại sau vài giây)."""
    return {
        "available": companion_memory.available(),
        "enabled": await companion_memory.enabled_for(owner),
        "pending": companion_memory.is_pending(owner),
        "limit": companion_memory.MAX_MEMORIES,
        "memories": [_public(item) for item in await db.list_memories(owner)],
    }


@router.put("/settings")
async def update_settings(body: MemorySettings, owner: str = Depends(current_owner)) -> dict:
    if not companion_memory.available():
        raise HTTPException(status_code=503, detail="Chủ web đã tắt trí nhớ Companion trên máy chủ này.")
    await db.set_memory_enabled(owner, body.enabled)
    return {"enabled": body.enabled}


@router.delete("/{memory_id}")
async def forget_one(memory_id: int, owner: str = Depends(current_owner)) -> dict:
    if not await db.delete_memory(owner, memory_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi nhớ này. Có thể nó đã được xóa.")
    return {"ok": True}


@router.delete("")
async def forget_all(owner: str = Depends(current_owner)) -> dict:
    return {"deleted": await db.clear_memories(owner)}
