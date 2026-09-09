"""Lưu hội thoại của Peto Web bằng SQLite riêng.

Tham khảo cách tổ chức của ``user_memory.py`` trong bot Discord (WAL, bảng
lịch sử phẳng theo role/content), nhưng schema là mới: web chưa có khái niệm
guild/channel, và ``owner`` là chỗ dành sẵn cho tài khoản sau này.

Nguyên tắc: mọi truy vấn đọc/sửa/xóa đều lọc theo ``owner`` ở backend. Không
tin conversation_id do trình duyệt gửi là bằng chứng sở hữu.
"""

from __future__ import annotations

import time
import uuid

import aiosqlite

from config import DB_PATH


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner "
            "ON conversations(owner, updated_at DESC)"
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation "
            "ON messages(conversation_id, id)"
        )
        # Migration bổ sung, giữ nguyên tin nhắn trong database hiện có.
        columns = await (await db.execute("PRAGMA table_info(messages)")).fetchall()
        if "status" not in {column[1] for column in columns}:
            await db.execute(
                "ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'"
            )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                kind TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_message "
            "ON attachments(message_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_conversation "
            "ON attachments(conversation_id)"
        )

        # Danh tính đã được máy chủ xác minh qua OAuth Discord. Đây là chỗ
        # duy nhất ánh xạ người dùng web sang Discord user ID — và là nền cho
        # việc liên kết trí nhớ sau này, NẾU được duyệt. Không bao giờ nhận
        # discord_id do trình duyệt gửi lên.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                owner TEXT PRIMARY KEY,
                discord_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                first_login_at REAL NOT NULL,
                last_login_at REAL NOT NULL
            )
            """
        )
        await db.commit()


async def upsert_user(
    *,
    owner: str,
    discord_id: str,
    username: str,
    display_name: str,
    avatar_url: str,
) -> None:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (owner, discord_id, username, display_name,
                               avatar_url, first_login_at, last_login_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                last_login_at = excluded.last_login_at
            """,
            (owner, discord_id, username, display_name, avatar_url, now, now),
        )
        await db.commit()


async def get_user(owner: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT owner, discord_id, username, display_name, avatar_url, "
            "first_login_at, last_login_at FROM users WHERE owner = ?",
            (owner,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_conversation(owner: str, title: str = "") -> str:
    conversation_id = uuid.uuid4().hex
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversations (id, owner, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, owner, title[:120], now, now),
        )
        await db.commit()
    return conversation_id


async def owns_conversation(owner: str, conversation_id: str) -> bool:
    """Kiểm tra quyền sở hữu. Gọi trước mọi thao tác trên một hội thoại."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND owner = ?",
            (conversation_id, owner),
        )
        return await cursor.fetchone() is not None


async def list_conversations(owner: str, limit: int = 50, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m
                     WHERE m.conversation_id = c.id) AS message_count
              FROM conversations c
             WHERE c.owner = ?
             ORDER BY c.updated_at DESC, c.id DESC
             LIMIT ? OFFSET ?
            """,
            (owner, limit, offset),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_messages(
    owner: str, conversation_id: str, limit: int | None = None
) -> list[dict]:
    """Trả về tin nhắn theo thứ tự cũ -> mới, chỉ khi đúng chủ sở hữu."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if limit is None:
            cursor = await db.execute(
                """
                SELECT m.id, m.role, m.content, m.created_at, m.status
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
                SELECT m.id, m.role, m.content, m.created_at, m.status
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
        return await _attach_files(db, rows)


async def _attach_files(db: aiosqlite.Connection, rows: list[dict]) -> list[dict]:
    """Gắn danh sách tệp vào từng tin. ``path`` chỉ dùng nội bộ, không đưa ra API."""
    if not rows:
        return rows
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    cursor = await db.execute(
        f"""
        SELECT id, message_id, filename, mime, kind, size, path, created_at
          FROM attachments
         WHERE message_id IN ({placeholders})
         ORDER BY created_at, id
        """,
        ids,
    )
    grouped: dict[int, list[dict]] = {}
    for item in await cursor.fetchall():
        grouped.setdefault(int(item["message_id"]), []).append(dict(item))
    for row in rows:
        row["attachments"] = grouped.get(int(row["id"]), [])
    return rows


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
) -> None:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO attachments (
                id, owner, conversation_id, message_id, filename,
                mime, kind, size, path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        await db.commit()


async def get_attachment(owner: str, attachment_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
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


async def list_attachment_paths(conversation_id: str) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT path FROM attachments WHERE conversation_id = ?",
            (conversation_id,),
        )
        return [str(row[0]) for row in await cursor.fetchall()]


async def add_message(
    conversation_id: str, role: str, content: str, status: str = "complete"
) -> int:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, now, status),
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title = ''",
            (cleaned, conversation_id),
        )
        await db.commit()


async def delete_conversation(owner: str, conversation_id: str) -> bool:
    paths = await list_attachment_paths(conversation_id)
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()
    if deleted:
        from attachments import delete_files

        delete_files(paths)
    return deleted
