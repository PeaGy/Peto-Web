"""Truy vấn tài khoản, hồ sơ và xác nhận chế độ nhập vai."""

from __future__ import annotations
import time
import aiosqlite
from storage import connection as db_connection


async def upsert_user(
    *,
    owner: str,
    provider: str,
    username: str,
    display_name: str,
    avatar_url: str,
    discord_id: str | None = None,
) -> None:
    """Ghi hồ sơ đăng nhập. ``discord_id`` để None với Google và GitHub."""
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            """
            INSERT INTO users (owner, provider, discord_id, username, display_name,
                               avatar_url, first_login_at, last_login_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET
                provider = excluded.provider,
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                last_login_at = excluded.last_login_at
            """,
            (owner, provider, discord_id, username, display_name, avatar_url, now, now),
        )
        await db.commit()


PROFILE_FIELDS = ("full_name", "nickname", "occupation", "instructions")


async def get_profile(owner: str) -> dict:
    """Hồ sơ tự điền của owner. Chưa từng lưu thì trả về các trường rỗng."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT full_name, nickname, occupation, instructions "
            "FROM user_profiles WHERE owner = ?",
            (owner,),
        )
        row = await cursor.fetchone()
    return dict(row) if row else {field: "" for field in PROFILE_FIELDS}


async def save_profile(
    *, owner: str, full_name: str, nickname: str, occupation: str, instructions: str
) -> None:
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            """
            INSERT INTO user_profiles (owner, full_name, nickname, occupation,
                                       instructions, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET
                full_name = excluded.full_name,
                nickname = excluded.nickname,
                occupation = excluded.occupation,
                instructions = excluded.instructions,
                updated_at = excluded.updated_at
            """,
            (owner, full_name, nickname, occupation, instructions, now),
        )
        await db.commit()


async def get_user(owner: str) -> dict | None:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT owner, provider, discord_id, username, display_name, "
            "avatar_url, first_login_at, last_login_at FROM users WHERE owner = ?",
            (owner,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def has_roleplay_consent(owner: str) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute("SELECT 1 FROM roleplay_consents WHERE owner = ?", (owner,))
        return await cursor.fetchone() is not None


async def add_roleplay_consent(owner: str) -> None:
    async with db_connection.connect() as db:
        await db.execute(
            "INSERT INTO roleplay_consents (owner, confirmed_at) VALUES (?, ?) ON CONFLICT(owner) DO NOTHING",
            (owner, time.time()),
        )
        await db.commit()
