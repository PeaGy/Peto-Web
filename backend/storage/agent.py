"""Truy vấn thiết bị và quyền truy cập Peto Agent."""

from __future__ import annotations
import time
import uuid
import aiosqlite
from storage import connection as db_connection


async def create_agent_device(*, owner: str, name: str, token_hash: str) -> dict:
    device_id = uuid.uuid4().hex
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            "INSERT INTO agent_devices (id, owner, name, token_hash, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (device_id, owner, name, token_hash, now, now),
        )
        await db.commit()
    return {"id": device_id, "name": name, "created_at": now, "last_used_at": now}


async def find_agent_device(token_hash: str, *, idle_seconds: float) -> dict | None:
    """Máy ứng với token, bỏ qua token đã thu hồi hoặc lâu không dùng."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, owner, name, created_at, last_used_at
              FROM agent_devices
             WHERE token_hash = ? AND revoked_at IS NULL AND last_used_at >= ?
            """,
            (token_hash, time.time() - idle_seconds),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def touch_agent_device(owner: str, device_id: str) -> None:
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE agent_devices SET last_used_at = ? WHERE id = ? AND owner = ?",
            (time.time(), device_id, owner),
        )
        await db.commit()


async def list_agent_devices(owner: str) -> list[dict]:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, name, created_at, last_used_at
              FROM agent_devices
             WHERE owner = ? AND revoked_at IS NULL
             ORDER BY last_used_at DESC
            """,
            (owner,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def revoke_agent_device(owner: str, device_id: str) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "UPDATE agent_devices SET revoked_at = ? WHERE id = ? AND owner = ? AND revoked_at IS NULL",
            (time.time(), device_id, owner),
        )
        await db.commit()
        return cursor.rowcount > 0
