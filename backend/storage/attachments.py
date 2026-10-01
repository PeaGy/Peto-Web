"""Truy vấn tệp đính kèm và nội dung tài liệu đã đọc."""

from __future__ import annotations
import json
import time
import aiosqlite
from storage import connection as db_connection


async def _attach_files(db: aiosqlite.Connection, rows: list[dict]) -> list[dict]:
    """Gắn danh sách tệp vào từng tin. ``path`` chỉ dùng nội bộ, không đưa ra API."""
    if not rows:
        return rows
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    cursor = await db.execute(
        f"""
        SELECT id, message_id, filename, mime, kind, size, path, created_at, document
          FROM attachments
         WHERE message_id IN ({placeholders})
         ORDER BY created_at, id
        """,
        ids,
    )
    grouped: dict[int, list[dict]] = {}
    items = [dict(item) for item in await cursor.fetchall()]
    # "Ảnh N": thứ tự của ảnh trong cả hội thoại, không chỉ trong đoạn lịch sử đang tải. Model thấy số này cạnh ảnh và
    # dùng nó để chèn ảnh vào tài liệu (document_images.py đếm theo đúng thứ tự này).
    cursor = await db.execute(
        f"""
        SELECT id, conversation_id FROM attachments
         WHERE kind = 'image' AND conversation_id IN (
               SELECT conversation_id FROM attachments WHERE message_id IN ({placeholders}))
         ORDER BY created_at, rowid
        """,
        ids,
    )
    numbers: dict[str, int] = {}
    counts: dict[str, int] = {}
    for image_id, conversation_id in await cursor.fetchall():
        counts[conversation_id] = counts.get(conversation_id, 0) + 1
        numbers[image_id] = counts[conversation_id]
    for item in items:
        if item["kind"] == "image":
            item["number"] = numbers.get(item["id"], 0)
        grouped.setdefault(int(item["message_id"]), []).append(item)
    for row in rows:
        row["attachments"] = grouped.get(int(row["id"]), [])
    return rows


async def conversation_images(owner: str, conversation_id: str) -> list[dict]:
    """Ảnh đã gửi trong hội thoại theo thứ tự gửi: phần tử thứ n là "Ảnh n" (cùng thứ tự với _attach_files)."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, filename, mime, path FROM attachments "
            "WHERE owner = ? AND conversation_id = ? AND kind = 'image' ORDER BY created_at, rowid",
            (owner, conversation_id),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def add_attachment(
    *,
    attachment_id: str,
    owner: str,
    conversation_id: str,
    message_id: int,
    filename: str,
    mime: str,
    kind: str,
    size: int,
    path: str,
    document: dict | None = None,
) -> None:
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            """
            INSERT INTO attachments (
                id, owner, conversation_id, message_id, filename,
                mime, kind, size, path, created_at, document
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attachment_id,
                owner,
                conversation_id,
                message_id,
                filename,
                mime,
                kind,
                size,
                path,
                now,
                json.dumps(document, ensure_ascii=False) if document is not None else "",
            ),
        )
        await db.commit()


async def get_attachment(owner: str, attachment_id: str) -> dict | None:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT a.id, a.filename, a.mime, a.kind, a.size, a.path,
                   a.conversation_id
              FROM attachments a
             WHERE a.id = ? AND a.owner = ?
            """,
            (attachment_id, owner),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_document(owner: str, attachment_id: str, document: dict) -> None:
    """Lưu chữ cho tệp cũ, chỉ cập nhật tệp của đúng chủ sở hữu."""
    async with db_connection.connect() as db:
        await db.execute("UPDATE attachments SET document = ? WHERE id = ? AND owner = ?",
                         (json.dumps(document, ensure_ascii=False), attachment_id, owner))
        await db.commit()


async def list_attachment_paths(conversation_id: str) -> list[str]:
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT path FROM attachments WHERE conversation_id = ?",
            (conversation_id,),
        )
        return [str(row[0]) for row in await cursor.fetchall()]
