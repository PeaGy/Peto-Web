"""Mốc xóa của tài khoản đã xóa, để thu hồi phiên cũ (G5, 20/11/2026).

Cookie phiên và mã đồng bộ Companion chỉ là khóa owner có chữ ký và thời điểm ký; không có kho phiên để xóa. Sau khi
một tài khoản bị xóa, mọi phiên ký TRƯỚC mốc xóa bị từ chối, còn đăng nhập lại sau đó (tài khoản mới tinh, cùng khóa
owner) vẫn dùng được. Chỉ lưu SHA-256 của khóa owner chứ không lưu chính nó, và bỏ mốc khi mọi phiên cũ chắc chắn đã
hết hạn.
"""
from __future__ import annotations

import hashlib

from storage import connection


async def init_tables(db) -> None:
    await db.execute("""CREATE TABLE IF NOT EXISTS deleted_accounts (
        owner_hash TEXT PRIMARY KEY, deleted_at REAL NOT NULL)""")


def owner_hash(owner: str) -> str:
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()


async def mark_deleted(db, owner: str, at: float, *, forget_before: float) -> None:
    """Ghi mốc xóa trong giao dịch đang mở của ``db``; dọn luôn các mốc đã cũ hơn mọi phiên còn hạn."""
    await db.execute("DELETE FROM deleted_accounts WHERE deleted_at < ?", (forget_before,))
    await db.execute("INSERT OR REPLACE INTO deleted_accounts(owner_hash, deleted_at) VALUES(?, ?)",
                     (owner_hash(owner), at))


async def deleted_at(owner: str) -> float | None:
    async with connection.connect() as db:
        row = await (await db.execute("SELECT deleted_at FROM deleted_accounts WHERE owner_hash=?",
                                      (owner_hash(owner),))).fetchone()
    return row[0] if row else None
