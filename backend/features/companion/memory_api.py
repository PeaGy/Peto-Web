"""Cài đặt → Trí nhớ: xem, sửa, xóa và bật/tắt những điều Peto tự ghi nhớ từ Chat và Companion (companion_memory.py),
và ô "Bảo Peto…" để người dùng tự bảo Peto nhớ, đổi hay bỏ điều gì. Đường dẫn giữ /api/companion/memory như lúc trí nhớ
chỉ có ở Companion.

Trí nhớ chia mục như trang Memory của Claude (chủ web chọn bản mẫu "Như Claude" ngày 15/10/2026): mỗi mục thuộc nhóm
Bạn, Chủ đề hay Lĩnh vực, có tên, một dòng tóm tắt và các ý. Mọi thao tác chỉ đụng dòng của đúng tài khoản đang đăng
nhập; biết id mục của người khác cũng chỉ nhận 404.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from features.companion import memory as companion_memory
import storage as db
from features.accounts.auth import current_owner

router = APIRouter(prefix="/api/companion/memory", tags=["companion-memory"])


class MemorySettings(BaseModel):
    enabled: bool


class MemoryEdit(BaseModel):
    title: str | None = None
    summary: str | None = None
    details: list[str] | None = None


class MemoryCreate(BaseModel):
    section: str
    title: str
    summary: str = ""
    details: list[str]


class MemoryTell(BaseModel):
    text: str
    entry_id: int | None = None


def _public(item: dict) -> dict:
    return {
        "id": item["id"], "section": item["section"], "title": item["title"], "summary": item["summary"],
        "details": item["details"], "fixed": item.get("slot") in companion_memory.SLOTS,
        "legacy": item.get("slot") == companion_memory.LEGACY,
        "created_at": item["created_at"], "updated_at": item["updated_at"],
    }


async def _state(owner: str, tasks: BackgroundTasks | None = None) -> dict:
    """Trí nhớ cho trang Cài đặt. Còn mục "Ghi nhớ cũ" thì ``sorting`` báo Peto đang xếp chúng vào từng mục (trang hỏi
    lại sau vài giây), và việc xếp chạy nền sau khi trả lời."""
    enabled = await companion_memory.enabled_for(owner)
    memories = await db.list_memories(owner)
    sorting = (enabled and companion_memory.sort_due(owner)
               and any(item.get("slot") == companion_memory.LEGACY for item in memories))
    if sorting and tasks is not None:
        tasks.add_task(companion_memory.sort_legacy, owner)
    return {
        "available": companion_memory.available(),
        "enabled": enabled,
        "pending": companion_memory.is_pending(owner),
        "sorting": sorting,
        "limit": companion_memory.MAX_ENTRIES,
        "memories": [_public(item) for item in memories],
    }


@router.get("")
async def read_memory(tasks: BackgroundTasks, owner: str = Depends(current_owner)) -> dict:
    """Các mục trí nhớ; ``pending`` là còn đang ghi nhớ lượt vừa xong."""
    return await _state(owner, tasks)


@router.put("/settings")
async def update_settings(body: MemorySettings, owner: str = Depends(current_owner)) -> dict:
    if not companion_memory.available():
        raise HTTPException(status_code=503, detail="Chủ web đã tắt trí nhớ trên máy chủ này.")
    await db.set_memory_enabled(owner, body.enabled)
    return {"enabled": body.enabled}


@router.post("/tell")
async def tell(body: MemoryTell, owner: str = Depends(current_owner)) -> dict:
    """Người dùng bảo Peto nhớ, đổi hay bỏ điều gì: một lượt gọi model nhỏ, rồi trả về câu báo và trí nhớ mới."""
    try:
        result = await companion_memory.tell(owner, body.text, body.entry_id)
    except companion_memory.MemoryRequestError as err:
        raise HTTPException(status_code=err.status, detail=err.detail) from err
    return {
        "message": result["message"],
        "changes": [{key: change[key] for key in ("id", "kind", "fresh")} for change in result["changes"]],
        "memories": [_public(item) for item in result["memories"]],
    }


@router.post("")
async def create(body: MemoryCreate, owner: str = Depends(current_owner)) -> dict:
    """Tạo lại một mục người dùng vừa xóa (nút Hoàn tác)."""
    entry = companion_memory.new_entry(body.section, body.title, body.summary, body.details)
    if not entry:
        raise HTTPException(status_code=400, detail="Mục này thiếu tên hay chưa có ý nào.")
    memories = await db.list_memories(owner)
    if entry["slot"] and any(item.get("slot") == entry["slot"] for item in memories):
        raise HTTPException(status_code=409, detail=f"Đã có mục “{entry['title']}”.")
    if len(memories) >= companion_memory.MAX_ENTRIES:
        raise HTTPException(status_code=409, detail=f"Trí nhớ đã đủ {companion_memory.MAX_ENTRIES} mục.")
    created = await db.apply_memory_changes(owner, upserts=[entry], remove=[], limit=companion_memory.MAX_ENTRIES)
    if not created:
        raise HTTPException(status_code=409, detail="Chưa tạo lại được mục này. Thử lại sau nha.")
    return _public(created[0])


@router.patch("/{memory_id}")
async def edit(memory_id: int, body: MemoryEdit, owner: str = Depends(current_owner)) -> dict:
    """Người dùng tự sửa tên (trừ hai mục cố định), dòng tóm tắt hay các ý của một mục."""
    entry = next((item for item in await db.list_memories(owner) if item["id"] == memory_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này. Có thể nó đã được xóa.")
    patch: dict = {"id": memory_id}
    if body.details is not None:
        details = companion_memory.clean_details(body.details, companion_memory.max_details(entry)) or []
        if not details:
            raise HTTPException(status_code=400, detail="Mục cần ít nhất một ý. Muốn bỏ cả mục thì bấm Xóa.")
        if len(body.details) > companion_memory.max_details(entry):
            raise HTTPException(
                status_code=400, detail=f"Mỗi mục tối đa {companion_memory.max_details(entry)} ý.")
        patch["details"] = details
    if body.summary is not None:
        patch["summary"] = companion_memory.clean_memory(body.summary, companion_memory.MAX_ENTRY_SUMMARY_CHARS)
    if body.title is not None and not entry.get("slot"):
        title = companion_memory.clean_memory(body.title, companion_memory.MAX_TITLE_CHARS)
        if not title:
            raise HTTPException(status_code=400, detail="Mục cần có tên.")
        patch["title"] = title
    await db.apply_memory_changes(owner, upserts=[patch], remove=[], limit=companion_memory.MAX_ENTRIES)
    if "details" in patch and set(entry["details"]) - set(patch["details"]):
        # Bỏ một ý thì bản tóm tắt Companion cũng phải quên theo, như khi xóa cả mục.
        await db.forget_summaries(owner)
    updated = next((item for item in await db.list_memories(owner) if item["id"] == memory_id), entry)
    return _public(updated)


@router.delete("/{memory_id}")
async def forget_one(memory_id: int, owner: str = Depends(current_owner)) -> dict:
    if not await db.delete_memory(owner, memory_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này. Có thể nó đã được xóa.")
    return {"ok": True}


@router.delete("")
async def forget_all(owner: str = Depends(current_owner)) -> dict:
    return {"deleted": await db.clear_memories(owner)}
