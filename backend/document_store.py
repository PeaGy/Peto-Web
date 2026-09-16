"""Versioned chat documents. Every query checks the authenticated owner."""
from __future__ import annotations

import time
import uuid
import aiosqlite
from fastapi import HTTPException
from config import DB_PATH

MAX_DOCUMENTS = 100
MAX_VERSIONS = 20


async def init_tables(connection):
    await connection.executescript("""
        CREATE TABLE IF NOT EXISTS chat_documents (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, conversation_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_documents_owner ON chat_documents(owner, conversation_id);
        CREATE TABLE IF NOT EXISTS chat_document_versions (
            document_id TEXT NOT NULL, version INTEGER NOT NULL,
            title TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL,
            PRIMARY KEY(document_id, version),
            FOREIGN KEY(document_id) REFERENCES chat_documents(id) ON DELETE CASCADE
        );
    """)


async def list_documents(owner, conversation_id):
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        owns = await (await connection.execute(
            "SELECT id FROM conversations WHERE id=? AND owner=? AND mode='chat'", (conversation_id, owner)
        )).fetchone()
        if not owns:
            raise HTTPException(404, "Không tìm thấy hội thoại")
        rows = await (await connection.execute("""
            SELECT d.id, d.conversation_id, v.version, v.title, v.created_at
            FROM chat_documents d JOIN chat_document_versions v ON v.document_id=d.id
            WHERE d.owner=? AND d.conversation_id=? AND v.version=(
                SELECT MAX(version) FROM chat_document_versions WHERE document_id=d.id
            ) ORDER BY v.created_at DESC
        """, (owner, conversation_id))).fetchall()
        return [dict(row) for row in rows]


async def get_document(owner, document_id, version=None):
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        row = await (await connection.execute("""
            SELECT d.id, d.conversation_id, v.version, v.title, v.content, v.created_at
            FROM chat_documents d JOIN chat_document_versions v ON v.document_id=d.id
            WHERE d.id=? AND d.owner=? AND v.version=COALESCE(?, (
                SELECT MAX(version) FROM chat_document_versions WHERE document_id=d.id
            ))
        """, (document_id, owner, version))).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy tài liệu hoặc phiên bản này")
        versions = await (await connection.execute(
            "SELECT version, title, created_at FROM chat_document_versions WHERE document_id=? ORDER BY version DESC",
            (document_id,),
        )).fetchall()
        return {**dict(row), "versions": [dict(item) for item in versions]}


async def save_document(owner, conversation_id, title, content, document_id=None, base_version=None):
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("BEGIN IMMEDIATE")
        if document_id:
            row = await (await connection.execute("""
                SELECT MAX(v.version) FROM chat_documents d JOIN chat_document_versions v ON v.document_id=d.id
                WHERE d.id=? AND d.owner=?
            """, (document_id, owner))).fetchone()
            if not row or row[0] is None:
                raise HTTPException(404, "Không tìm thấy tài liệu")
            if row[0] != base_version:
                raise HTTPException(409, "Tài liệu đã có phiên bản mới ở cửa sổ khác. Đóng rồi mở lại để lấy bản mới nhất; bản đang sửa vẫn được giữ ở đây.")
            if row[0] >= MAX_VERSIONS:
                raise HTTPException(400, "Tài liệu đã đủ 20 phiên bản. Hãy tạo tài liệu mới từ nội dung cần dùng.")
            version = row[0] + 1
        else:
            owns = await (await connection.execute(
                "SELECT id FROM conversations WHERE id=? AND owner=? AND mode='chat'", (conversation_id, owner)
            )).fetchone()
            if not owns:
                raise HTTPException(404, "Không tìm thấy hội thoại")
            count = await (await connection.execute(
                "SELECT COUNT(*) FROM chat_documents WHERE owner=?", (owner,)
            )).fetchone()
            if count[0] >= MAX_DOCUMENTS:
                raise HTTPException(400, "Bạn đã lưu 100 tài liệu. Xóa tài liệu không còn cần trước khi tạo thêm.")
            document_id, version = uuid.uuid4().hex, 1
            await connection.execute("INSERT INTO chat_documents VALUES (?, ?, ?, ?)",
                                     (document_id, owner, conversation_id, time.time()))
        await connection.execute("INSERT INTO chat_document_versions VALUES (?, ?, ?, ?, ?)",
                                 (document_id, version, title, content, time.time()))
        await connection.commit()
    return await get_document(owner, document_id, version)


async def delete_document(owner, document_id):
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        cursor = await connection.execute("DELETE FROM chat_documents WHERE id=? AND owner=?", (document_id, owner))
        await connection.commit()
        if not cursor.rowcount:
            raise HTTPException(404, "Không tìm thấy tài liệu")
