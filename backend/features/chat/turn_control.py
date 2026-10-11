"""Điều khiển lượt đang chạy trong tiến trình; trạng thái xác nhận nằm trong SQLite."""
import asyncio
from dataclasses import dataclass
import anyio
from fastapi import HTTPException
from storage import chat_turns


@dataclass
class RunningTurn:
    scope: anyio.CancelScope
    done: asyncio.Event


running: dict[tuple[str, str], RunningTurn] = {}


async def stop(owner, request_id):
    row = await chat_turns.stop(owner, request_id)
    turn = running.get((owner, request_id))
    if row and row['state'] == 'stopped' and turn:
        turn.scope.cancel()
        try:
            await asyncio.wait_for(turn.done.wait(), timeout=10)
        except TimeoutError:
            raise HTTPException(503, 'Đang chốt lượt đã dừng. Bấm Dừng lần nữa để xác nhận nhé.') from None
    row = await chat_turns.get(owner, request_id)
    if not row:
        raise HTTPException(404, 'Hội thoại của lượt này đã bị xóa.')
    return row
