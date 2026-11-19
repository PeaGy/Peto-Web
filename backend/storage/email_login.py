"""Bảng của lối đăng nhập bằng email: tài khoản email và mã 6 số.

Không lưu địa chỉ email. Cả hai bảng chỉ giữ ``email_hash`` (SHA-256 của email đã chuẩn hóa, xem
``features.accounts.email_login.email_hash``); địa chỉ thật chỉ nằm trong bộ nhớ lúc gửi thư.
"""

from __future__ import annotations

import secrets
import time

from storage import connection as db_connection


async def init_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS email_accounts (
            email_hash TEXT PRIMARY KEY,
            owner TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS email_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_login_codes_email ON email_login_codes(email_hash, created_at)"
    )


async def recent_sends(email_hash: str, since: float) -> list[float]:
    """Thời điểm các lần gửi mã cho email này từ ``since`` tới giờ, mới nhất trước."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT created_at FROM email_login_codes WHERE email_hash = ? AND created_at >= ? ORDER BY created_at DESC",
            (email_hash, since),
        )
        return [row[0] for row in await cursor.fetchall()]


async def add_code(email_hash: str, code_hash: str, ttl: float, keep_for: float) -> int:
    """Ghi mã mới, vô hiệu mọi mã cũ của email đó (chỉ mã gửi sau cùng còn dùng được) và dọn mã quá ``keep_for``."""
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute("DELETE FROM email_login_codes WHERE created_at < ?", (now - keep_for,))
        await db.execute("UPDATE email_login_codes SET used = 1 WHERE email_hash = ? AND used = 0", (email_hash,))
        cursor = await db.execute(
            "INSERT INTO email_login_codes (email_hash, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (email_hash, code_hash, now, now + ttl),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def drop_code(code_id: int) -> None:
    """Bỏ mã không gửi được: không để một mã người dùng chưa từng nhận chặn đường nhận mã sau."""
    async with db_connection.connect() as db:
        await db.execute("UPDATE email_login_codes SET used = 1 WHERE id = ?", (code_id,))
        await db.commit()


async def current_code(email_hash: str) -> dict | None:
    """Mã còn hiệu lực gần nhất của email, hoặc None."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT id, code_hash, attempts FROM email_login_codes "
            "WHERE email_hash = ? AND used = 0 AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            (email_hash, time.time()),
        )
        row = await cursor.fetchone()
    return {"id": row[0], "code_hash": row[1], "attempts": row[2]} if row else None


async def add_attempt(code_id: int, max_attempts: int) -> int:
    """Tính thêm một lần nhập sai; đủ ``max_attempts`` thì mã bị hủy. Trả về số lần sai sau khi cộng."""
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE email_login_codes SET attempts = attempts + 1, used = CASE WHEN attempts + 1 >= ? THEN 1 ELSE used END "
            "WHERE id = ?",
            (max_attempts, code_id),
        )
        cursor = await db.execute("SELECT attempts FROM email_login_codes WHERE id = ?", (code_id,))
        row = await cursor.fetchone()
        await db.commit()
    return int(row[0]) if row else max_attempts


async def consume_code(code_id: int) -> bool:
    """Đánh dấu mã đã dùng. False nếu một yêu cầu khác vừa dùng nó trước (hai lần bấm cùng lúc)."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "UPDATE email_login_codes SET used = 1 WHERE id = ? AND used = 0 AND expires_at > ?", (code_id, time.time())
        )
        await db.commit()
        return cursor.rowcount == 1


async def email_owner(email_hash: str) -> str:
    """Owner của tài khoản email; chưa có thì tạo với một mã ngẫu nhiên (``email:<32 ký tự hex>``)."""
    async with db_connection.connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO email_accounts (email_hash, owner, created_at) VALUES (?, ?, ?)",
            (email_hash, f"email:{secrets.token_hex(16)}", time.time()),
        )
        cursor = await db.execute("SELECT owner FROM email_accounts WHERE email_hash = ?", (email_hash,))
        row = await cursor.fetchone()
        await db.commit()
    return str(row[0])
