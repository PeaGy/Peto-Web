"""Trừ và hoàn lại quota Agent, giọng nói bằng câu SQL nguyên tử."""

from __future__ import annotations
import aiosqlite
from storage import connection as db_connection


async def take_agent_step(owner: str, day: str, limit: int, cost: int = 1) -> int | None:
    """Trừ ``cost`` bước của ngày (mức suy nghĩ cao tính 2). Trả về số bước đã dùng sau khi trừ, hoặc None nếu
    không còn đủ lượt.

    Một câu lệnh vừa kiểm vừa cộng, nên hai bước chạy cùng lúc không vượt được giới hạn.
    """
    if cost > limit:
        return None
    async with db_connection.connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO agent_usage (owner, day, steps) VALUES (?, ?, ?)
            ON CONFLICT(owner, day) DO UPDATE SET steps = steps + excluded.steps WHERE steps + excluded.steps <= ?
            """,
            (owner, day, cost, limit),
        )
        if cursor.rowcount == 0:
            await db.commit()
            return None
        cursor = await db.execute("SELECT steps FROM agent_usage WHERE owner = ? AND day = ?", (owner, day))
        (steps,) = await cursor.fetchone()
        await db.commit()
        return int(steps)


async def take_voice_chars(owner: str, month: str, chars: int, limit: int) -> int | None:
    """Trừ ``chars`` ký tự Giọng Peto của tháng. Trả về số ký tự đã dùng sau khi trừ, hoặc None nếu không còn đủ lượt.

    Như take_agent_step: một câu lệnh vừa kiểm vừa cộng, nên hai câu đọc cùng lúc không vượt được lượt.
    """
    if chars > limit:
        return None
    async with db_connection.connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO voice_usage (owner, month, chars) VALUES (?, ?, ?)
            ON CONFLICT(owner, month) DO UPDATE SET chars = chars + excluded.chars WHERE chars + excluded.chars <= ?
            """,
            (owner, month, chars, limit),
        )
        if cursor.rowcount == 0:
            await db.commit()
            return None
        cursor = await db.execute("SELECT chars FROM voice_usage WHERE owner = ? AND month = ?", (owner, month))
        (used,) = await cursor.fetchone()
        await db.commit()
        return int(used)


async def refund_voice_chars(owner: str, month: str, chars: int) -> None:
    """Trả lại ký tự khi câu không đọc được, để người dùng không mất lượt oan."""
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE voice_usage SET chars = MAX(chars - ?, 0) WHERE owner = ? AND month = ?",
            (chars, owner, month),
        )
        await db.commit()


async def voice_chars_used(owner: str, month: str) -> int:
    async with db_connection.connect() as db:
        cursor = await db.execute("SELECT chars FROM voice_usage WHERE owner = ? AND month = ?", (owner, month))
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def refund_agent_step(owner: str, day: str, cost: int = 1) -> None:
    """Trả lại bước khi mô hình lỗi trước khi làm được gì, để người dùng không mất lượt oan."""
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE agent_usage SET steps = MAX(steps - ?, 0) WHERE owner = ? AND day = ?",
            (cost, owner, day),
        )
        await db.commit()


async def add_agent_tokens(owner: str, day: str, input_tokens: int, output_tokens: int) -> None:
    async with db_connection.connect() as db:
        await db.execute(
            "UPDATE agent_usage SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ? "
            "WHERE owner = ? AND day = ?",
            (max(0, input_tokens), max(0, output_tokens), owner, day),
        )
        await db.commit()


async def get_agent_usage(owner: str, day: str) -> dict:
    """Số bước và token Peto Agent đã dùng trong ngày."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT steps, input_tokens, output_tokens FROM agent_usage WHERE owner = ? AND day = ?", (owner, day)
        )
        row = await cursor.fetchone()
    steps, input_tokens, output_tokens = row if row else (0, 0, 0)
    return {"steps": int(steps), "input_tokens": int(input_tokens), "output_tokens": int(output_tokens)}


async def get_agent_steps(owner: str, day: str) -> int:
    async with db_connection.connect() as db:
        cursor = await db.execute("SELECT steps FROM agent_usage WHERE owner = ? AND day = ?", (owner, day))
        row = await cursor.fetchone()
        return int(row[0]) if row else 0
