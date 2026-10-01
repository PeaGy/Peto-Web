"""Truy vấn ghi nhớ và tóm tắt hội thoại Companion."""

from __future__ import annotations
import time
import aiosqlite
from storage import connection as db_connection


async def list_memories(owner: str) -> list[dict]:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, text, created_at, updated_at FROM companion_memories WHERE owner = ? ORDER BY id",
            (owner,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def memory_state(owner: str) -> dict | None:
    """Bật/tắt, vị trí đã đọc và mốc tóm tắt; None khi người dùng chưa từng có (mặc định là bật)."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT enabled, cursor, since FROM companion_memory_state WHERE owner = ?", (owner,)
        )
        row = await cursor.fetchone()
    return {"enabled": bool(row[0]), "cursor": row[1], "since": row[2]} if row else None


async def ensure_memory_state(owner: str) -> dict:
    """Lần đầu ghi nhớ thì bắt đầu từ tin người dùng mới nhất: lịch sử có từ trước khi có trí nhớ không bị lục lại,
    cả để ghi nhớ lẫn để tóm tắt."""
    async with db_connection.connect() as db:
        start = max(await _last_companion_message_id(db, owner, "user") - 1, 0)
        await db.execute(
            "INSERT OR IGNORE INTO companion_memory_state (owner, enabled, cursor, since, updated_at) "
            "VALUES (?, 1, ?, ?, ?)",
            (owner, start, start, time.time()),
        )
        await db.commit()
    return await memory_state(owner) or {"enabled": True, "cursor": start, "since": start}


async def _last_companion_message_id(db: aiosqlite.Connection, owner: str, role: str | None = None) -> int:
    query = (
        "SELECT MAX(m.id) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
        "WHERE c.owner = ? AND c.mode = 'companion'"
    )
    params: tuple = (owner,)
    if role:
        query += " AND m.role = ?"
        params += (role,)
    row = await (await db.execute(query, params)).fetchone()
    return row[0] or 0


async def set_memory_enabled(owner: str, enabled: bool) -> None:
    """Bật lại thì bắt đầu đọc từ tin mới nhất: điều người dùng nói lúc đang tắt không bị ghi nhớ hay tóm tắt về sau."""
    async with db_connection.connect() as db:
        latest = await _last_companion_message_id(db, owner)
        await db.execute(
            """
            INSERT INTO companion_memory_state (owner, enabled, cursor, since, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET
                enabled = excluded.enabled,
                cursor = CASE WHEN excluded.enabled = 1 AND companion_memory_state.enabled = 0
                              THEN excluded.cursor ELSE companion_memory_state.cursor END,
                since = CASE WHEN excluded.enabled = 1 AND companion_memory_state.enabled = 0
                             THEN excluded.since ELSE companion_memory_state.since END,
                updated_at = excluded.updated_at
            """,
            (owner, int(enabled), latest, latest, time.time()),
        )
        await db.commit()


async def companion_messages_after(owner: str, after_id: int, limit: int) -> list[dict]:
    """Tin Companion mới hơn ``after_id``, lấy ``limit`` tin gần nhất, xếp cũ trước mới sau.

    Người dùng chưa từng có vị trí đã đọc (``after_id`` âm) thì chỉ đọc từ tin người dùng mới nhất: lịch sử có từ
    trước khi có trí nhớ không bị lục lại.
    """
    async with db_connection.connect() as db:
        if after_id < 0:
            after_id = max(await _last_companion_message_id(db, owner, "user") - 1, 0)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT m.id, m.role, m.content FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.owner = ? AND c.mode = 'companion' AND m.id > ? AND m.role IN ('user', 'assistant') "
            "ORDER BY m.id DESC LIMIT ?",
            (owner, after_id, limit),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
    return rows[::-1]


async def apply_memory_changes(
    owner: str, *, add: list[str], update: dict[int, str], remove: list[int], cursor: int, limit: int
) -> list[dict]:
    """Ghi các thay đổi trong một giao dịch rồi dời vị trí đã đọc; trả về ghi nhớ vừa thêm hay vừa sửa.

    Chỉ đụng tới dòng của đúng ``owner``; thêm quá ``limit`` dòng thì bỏ phần thừa.
    """
    now = time.time()
    changed: list[int] = []
    async with db_connection.connect() as db:
        for memory_id in remove:
            await db.execute("DELETE FROM companion_memories WHERE id = ? AND owner = ?", (memory_id, owner))
        for memory_id, text in update.items():
            result = await db.execute(
                "UPDATE companion_memories SET text = ?, updated_at = ? WHERE id = ? AND owner = ? AND text != ?",
                (text, now, memory_id, owner, text),
            )
            if result.rowcount:
                changed.append(memory_id)
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM companion_memories WHERE owner = ?", (owner,)
        )).fetchone())[0]
        for text in add[: max(limit - count, 0)]:
            result = await db.execute(
                "INSERT INTO companion_memories (owner, text, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (owner, text, now, now),
            )
            changed.append(result.lastrowid)
        await db.execute(
            """
            INSERT INTO companion_memory_state (owner, enabled, cursor, since, updated_at) VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET cursor = MAX(companion_memory_state.cursor, excluded.cursor),
                                             updated_at = excluded.updated_at
            """,
            (owner, cursor, cursor, now),
        )
        await db.commit()
        if not changed:
            return []
        db.row_factory = aiosqlite.Row
        marks = ",".join("?" * len(changed))
        rows = await (await db.execute(
            f"SELECT id, text, created_at, updated_at FROM companion_memories WHERE owner = ? AND id IN ({marks}) ORDER BY id",
            (owner, *changed),
        )).fetchall()
    return [dict(row) for row in rows]


async def delete_memory(owner: str, memory_id: int) -> bool:
    """Xóa một ghi nhớ, và bỏ luôn bản tóm tắt: điều vừa xóa có thể nằm trong đó, mà không gỡ riêng ra được."""
    async with db_connection.connect() as db:
        result = await db.execute("DELETE FROM companion_memories WHERE id = ? AND owner = ?", (memory_id, owner))
        if result.rowcount:
            await _forget_summaries(db, owner)
        await db.commit()
    return result.rowcount > 0


async def clear_memories(owner: str) -> int:
    async with db_connection.connect() as db:
        result = await db.execute("DELETE FROM companion_memories WHERE owner = ?", (owner,))
        await _forget_summaries(db, owner)
        await db.commit()
    return result.rowcount


async def _forget_summaries(db: aiosqlite.Connection, owner: str) -> None:
    """Xóa trắng bản tóm tắt của mọi mạch Companion và bỏ qua mọi tin đang có: tóm tắt về sau chỉ từ tin mới hơn."""
    await db.execute(
        """
        INSERT INTO companion_summaries (conversation_id, owner, text, upto, updated_at)
        SELECT c.id, c.owner, '', COALESCE((SELECT MAX(m.id) FROM messages m WHERE m.conversation_id = c.id), 0), ?
          FROM conversations c
         WHERE c.owner = ? AND c.mode = 'companion'
        ON CONFLICT(conversation_id) DO UPDATE SET text = '', upto = excluded.upto, updated_at = excluded.updated_at
        """,
        (time.time(), owner),
    )


async def companion_summary(owner: str, conversation_id: str) -> dict | None:
    async with db_connection.connect() as db:
        row = await (await db.execute(
            "SELECT text, upto FROM companion_summaries WHERE conversation_id = ? AND owner = ?",
            (conversation_id, owner),
        )).fetchone()
    return {"text": row[0], "upto": row[1]} if row else None


async def messages_before_window(
    owner: str, conversation_id: str, *, after_id: int, window: int, limit: int
) -> list[dict]:
    """Tin cũ hơn ``window`` tin gần nhất (tức không còn được gửi kèm lượt Companion) và mới hơn ``after_id``: lấy tối
    đa ``limit`` tin cũ nhất, xếp cũ trước mới sau."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT m.id, m.role, m.content FROM messages m JOIN conversations c ON c.id = m.conversation_id
             WHERE c.id = ? AND c.owner = ? AND m.id > ? AND m.role IN ('user', 'assistant')
               AND m.id < (SELECT MIN(id) FROM (
                     SELECT id FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?))
             ORDER BY m.id
             LIMIT ?
            """,
            (conversation_id, owner, after_id, conversation_id, window, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def save_companion_summary(
    owner: str, conversation_id: str, *, text: str, upto: int, expected_upto: int | None
) -> bool:
    """Lưu bản tóm tắt mới nếu không ai đổi nó trong lúc model đang viết (``expected_upto`` là ``upto`` lúc đọc, None
    khi chưa có). Người dùng xóa ghi nhớ giữa chừng thì ``upto`` đã đổi: bỏ kết quả, không đem điều vừa xóa quay lại."""
    now = time.time()
    async with db_connection.connect() as db:
        if expected_upto is None:
            result = await db.execute(
                "INSERT INTO companion_summaries (conversation_id, owner, text, upto, updated_at) "
                "SELECT id, owner, ?, ?, ? FROM conversations WHERE id = ? AND owner = ? "
                "ON CONFLICT(conversation_id) DO NOTHING",
                (text, upto, now, conversation_id, owner),
            )
        else:
            result = await db.execute(
                "UPDATE companion_summaries SET text = ?, upto = ?, updated_at = ? "
                "WHERE conversation_id = ? AND owner = ? AND upto = ?",
                (text, upto, now, conversation_id, owner, expected_upto),
            )
        await db.commit()
    return result.rowcount > 0
