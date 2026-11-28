"""Link chia sẻ cuộc trò chuyện (28/11/2026, chủ web chọn theo đề xuất trong khảo sát app chat).

Mỗi cuộc trò chuyện của một tài khoản có tối đa một link. Link giữ **bản chụp** tin nhắn lúc tạo hoặc lúc bấm "Cập nhật
link" (cột ``snapshot``, JSON), nên tin gửi sau không lọt ra ngoài. Mã link ngẫu nhiên, khó đoán (``secrets``). Xóa hội
thoại thì xóa link của nó (``storage.conversations.delete_conversation``); xóa tài khoản thì bảng này đi theo vì có cột
``owner`` (``features.accounts.deletion``).
"""
from __future__ import annotations

import json
import secrets
import time

from storage import connection as db_connection


async def init_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS shared_chats (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            title TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            include_images INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner, conversation_id)
        )""")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_shared_chats_owner ON shared_chats(owner, updated_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_shared_chats_conversation ON shared_chats(conversation_id)")


def _row(row) -> dict:
    return {"id": row[0], "owner": row[1], "conversation_id": row[2], "title": row[3], "snapshot": json.loads(row[4]),
            "include_images": bool(row[5]), "created_at": row[6], "updated_at": row[7]}


_COLUMNS = "id, owner, conversation_id, title, snapshot, include_images, created_at, updated_at"


async def save(owner: str, conversation_id: str, title: str, snapshot: list[dict], include_images: bool) -> dict:
    """Tạo link mới, hay chụp lại link sẵn có của hội thoại này (giữ nguyên mã link)."""
    now = time.time()
    body = json.dumps(snapshot, ensure_ascii=False)
    async with db_connection.connect() as db:
        row = await (await db.execute("SELECT id, created_at FROM shared_chats WHERE owner=? AND conversation_id=?",
                                      (owner, conversation_id))).fetchone()
        if row:
            share_id, created = row
            await db.execute("UPDATE shared_chats SET title=?, snapshot=?, include_images=?, updated_at=? WHERE id=?",
                             (title, body, int(include_images), now, share_id))
        else:
            share_id, created = secrets.token_urlsafe(16), now
            await db.execute(f"INSERT INTO shared_chats ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (share_id, owner, conversation_id, title, body, int(include_images), now, now))
        await db.commit()
    return {"id": share_id, "conversation_id": conversation_id, "title": title, "include_images": include_images,
            "created_at": created, "updated_at": now, "message_count": len(snapshot)}


async def get(share_id: str) -> dict | None:
    async with db_connection.connect() as db:
        row = await (await db.execute(f"SELECT {_COLUMNS} FROM shared_chats WHERE id=?", (share_id,))).fetchone()
    return _row(row) if row else None


async def for_conversation(owner: str, conversation_id: str) -> dict | None:
    async with db_connection.connect() as db:
        row = await (await db.execute(f"SELECT {_COLUMNS} FROM shared_chats WHERE owner=? AND conversation_id=?",
                                      (owner, conversation_id))).fetchone()
    return _row(row) if row else None


async def list_for_owner(owner: str) -> list[dict]:
    async with db_connection.connect() as db:
        rows = await (await db.execute(f"SELECT {_COLUMNS} FROM shared_chats WHERE owner=? ORDER BY updated_at DESC",
                                       (owner,))).fetchall()
    return [_row(row) for row in rows]


async def count_for_owner(owner: str) -> int:
    async with db_connection.connect() as db:
        row = await (await db.execute("SELECT COUNT(*) FROM shared_chats WHERE owner=?", (owner,))).fetchone()
    return row[0]


async def delete(owner: str, share_id: str) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute("DELETE FROM shared_chats WHERE id=? AND owner=?", (share_id, owner))
        await db.commit()
    return cursor.rowcount > 0


async def delete_for_conversation(db, conversation_id: str) -> None:
    """Gọi trong giao dịch xóa hội thoại."""
    await db.execute("DELETE FROM shared_chats WHERE conversation_id=?", (conversation_id,))
