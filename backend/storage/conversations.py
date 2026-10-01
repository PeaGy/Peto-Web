"""Truy vấn hội thoại và tin nhắn theo chủ sở hữu."""

from __future__ import annotations
import json
import time
import uuid
import unicodedata
import aiosqlite
from storage import connection as db_connection
from shared.web_search import normalize_sources
from storage.attachments import _attach_files, list_attachment_paths

async def create_conversation(owner: str, title: str = "", mode: str = "chat", persona: str = "assistant") -> str:
    conversation_id = uuid.uuid4().hex
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            "INSERT INTO conversations (id, owner, title, created_at, updated_at, mode, persona, title_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'temporary')",
            (conversation_id, owner, title[:120], now, now, mode, persona),
        )
        await db.commit()
    return conversation_id


async def owns_conversation(owner: str, conversation_id: str) -> bool:
    """Kiểm tra quyền sở hữu. Gọi trước mọi thao tác trên một hội thoại."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND owner = ?",
            (conversation_id, owner),
        )
        return await cursor.fetchone() is not None


async def conversation_settings(owner: str, conversation_id: str) -> dict | None:
    """Tab ("chat" hay "companion") và persona ("assistant" hay "roleplay") của một hội thoại; None nếu không phải
    của owner."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT mode, persona FROM conversations WHERE id = ? AND owner = ?",
            (conversation_id, owner),
        )
        row = await cursor.fetchone()
        return {"mode": row[0], "persona": row[1]} if row else None


async def latest_conversation(owner: str, mode: str) -> str | None:
    """Hội thoại mới nhất của một tab; Companion chỉ dùng đúng một mạch này."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT id FROM conversations WHERE owner = ? AND mode = ? "
            "ORDER BY updated_at DESC, id DESC LIMIT 1",
            (owner, mode),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def list_conversations(owner: str, limit: int = 50, offset: int = 0, query: str = '') -> list[dict]:
    """Hội thoại của tab Trò chuyện; mạch Companion không hiện ở thanh bên."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        def fold(value):
            return ''.join(c for c in unicodedata.normalize('NFD', value.casefold().replace('đ', 'd')) if unicodedata.category(c) != 'Mn')
        await db.create_function('search_fold', 1, fold, deterministic=True)
        cursor = await db.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at, c.persona, c.title_state, c.title_attempts, c.pinned,
                   (SELECT COUNT(*) FROM messages m
                     WHERE m.conversation_id = c.id) AS message_count
              FROM conversations c
             WHERE c.owner = ? AND c.mode = 'chat'
               AND (? = '' OR instr(search_fold(c.title), search_fold(?)) > 0 OR EXISTS (
                 SELECT 1 FROM messages s WHERE s.conversation_id=c.id AND instr(search_fold(s.content), search_fold(?)) > 0))
             ORDER BY c.pinned DESC, c.updated_at DESC, c.id DESC
             LIMIT ? OFFSET ?
            """,
            (owner, query, query, query, limit, offset),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_messages(
    owner: str, conversation_id: str, limit: int | None = None
) -> list[dict]:
    """Trả về tin nhắn theo thứ tự cũ -> mới, chỉ khi đúng chủ sở hữu."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        if limit is None:
            cursor = await db.execute(
                """
                SELECT m.id, m.role, m.content, m.created_at, m.status, m.sources, m.artifacts
                  FROM messages m
                  JOIN conversations c ON c.id = m.conversation_id
                 WHERE m.conversation_id = ? AND c.owner = ?
                 ORDER BY m.id
                """,
                (conversation_id, owner),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        else:
            # Lấy N tin gần nhất rồi đảo lại, tránh đọc toàn bộ hội thoại dài.
            cursor = await db.execute(
                """
                SELECT m.id, m.role, m.content, m.created_at, m.status, m.sources, m.artifacts
                  FROM messages m
                  JOIN conversations c ON c.id = m.conversation_id
                 WHERE m.conversation_id = ? AND c.owner = ?
                 ORDER BY m.id DESC
                 LIMIT ?
                """,
                (conversation_id, owner, limit),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            rows.reverse()
        for row in rows:
            try:
                row["sources"] = normalize_sources(json.loads(row["sources"]))
            except (ValueError, TypeError):
                row["sources"] = []
            try: row['artifacts'] = json.loads(row['artifacts'])
            except (ValueError, TypeError): row['artifacts'] = []
            # Verify that every artifact still belongs to this account and chat.
            existing, generated = [], []
            for artifact in row['artifacts'] if isinstance(row['artifacts'], list) else []:
                if not isinstance(artifact, dict): continue
                document = await (await db.execute('''SELECT v.title, v.content FROM chat_document_versions v
                    JOIN chat_documents d ON d.id=v.document_id
                    WHERE d.owner=? AND d.conversation_id=? AND d.id=? AND v.version=?''',
                    (owner, conversation_id, artifact.get('id'), artifact.get('version')))).fetchone()
                if document:
                    existing.append(artifact)
                    generated.append({'id': artifact['id'], 'filename': artifact['filename'], 'content': document['content']})
            row['artifacts'], row['generated_documents'] = existing, generated
        return await _attach_files(db, rows)


async def add_message(
    conversation_id: str, role: str, content: str, status: str = "complete", sources: list[dict] | None = None, artifacts: list[dict] | None = None
) -> int:
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at, status, sources, artifacts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, now, status, json.dumps(normalize_sources(sources), ensure_ascii=False), json.dumps(artifacts or [], ensure_ascii=False)),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await db.commit()
        return int(cursor.lastrowid or 0)


async def set_title_if_empty(conversation_id: str, title: str) -> None:
    """Đặt tiêu đề từ tin nhắn đầu tiên, chỉ khi chưa có tiêu đề."""
    cleaned = " ".join(title.split())[:60]
    if not cleaned:
        return
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title = ''",
            (cleaned, conversation_id),
        )
        await db.commit()


async def set_title(owner: str, conversation_id: str, title: str) -> None:
    """Đặt tên riêng và khóa lại để tác vụ nền không ghi đè."""
    cleaned = " ".join(title.split())[:60]
    if not cleaned:
        return
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE conversations SET title = ?, title_state = 'locked' WHERE id = ? AND owner = ?",
            (cleaned, conversation_id, owner),
        )
        await db.commit()


async def delete_conversation(owner: str, conversation_id: str) -> bool:
    paths = await list_attachment_paths(conversation_id)
    async with db_connection.connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ? AND owner = ?",
            (conversation_id, owner),
        )
        deleted = cursor.rowcount > 0
        if deleted:
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
            await db.execute(
                "DELETE FROM attachments WHERE conversation_id = ?",
                (conversation_id,),
            )
            await db.execute("DELETE FROM companion_summaries WHERE conversation_id = ?", (conversation_id,))
        await db.commit()
    if deleted:
        from shared.attachments import delete_files

        delete_files(paths)
    return deleted
