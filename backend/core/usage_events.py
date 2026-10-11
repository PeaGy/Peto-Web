"""Số liệu vận hành cho trang Quản trị: không nội dung chat, không owner, không mã hội thoại.

Ghi đúng tại ba chỗ đã log ``model_usage``, ``chat_timing`` và ``agent_timing``. ``record`` chỉ thêm một dòng vào
hàng đợi trong bộ nhớ (đồng bộ, không I/O, không bao giờ báo lỗi ra ngoài), nên đường gửi tin nhắn không chờ
database. Một tác vụ nền ghi cả lô vào SQLite vài giây một lần và ghi nốt khi tắt máy chủ. Ngoài máy chủ (test,
benchmark, lệnh ops) hàng đợi tắt, nên số liệu thử nghiệm không lẫn vào. Cần chạy một tiến trình backend, như
voice và Imagine đã yêu cầu.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import re
import time

import anyio

from storage.connection import connect

logger = logging.getLogger("peto_web")

FLUSH_SECONDS = 5
MAX_PENDING = 10_000
RETENTION_DAYS = 90
PRUNE_SECONDS = 86_400

COLUMNS = (
    "at", "kind", "surface", "purpose", "service", "model", "slug", "outcome", "complete", "elapsed_ms",
    "first_text_ms", "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens", "search_calls",
)
KINDS = {"call", "turn"}
# Nhãn kỹ thuật như trong log (tên model, kết quả…); chuỗi lạ bị bỏ thay vì lưu nguyên.
LABEL = re.compile(r"[a-zA-Z0-9_.:-]{1,100}\Z")

_pending: deque[tuple] = deque(maxlen=MAX_PENDING)
_active = False
_dropped = 0
_task: asyncio.Task | None = None


def _label(value: object) -> str | None:
    return value.lower() if isinstance(value, str) and LABEL.fullmatch(value) else None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def record(
    kind: str, *, service: str, model: str | None = None, slug: str | None = None, surface: str | None = None,
    purpose: str | None = None, outcome: str | None = None, complete: bool | None = None,
    elapsed_ms: int | None = None, first_text_ms: int | None = None, input_tokens: int | None = None,
    output_tokens: int | None = None, cached_tokens: int | None = None, reasoning_tokens: int | None = None,
    search_calls: int | None = None,
) -> None:
    """Thêm một sự kiện vào hàng đợi. Số liệu hỏng chỉ thành ô trống; không bao giờ làm hỏng lượt chat."""
    global _dropped
    if not _active or kind not in KINDS:
        return
    try:
        row = (
            time.time(), kind, _label(surface), _label(purpose), _label(service) or "unknown", _label(model),
            _label(slug), _label(outcome), None if complete is None else int(bool(complete)), _count(elapsed_ms),
            _count(first_text_ms), _count(input_tokens), _count(output_tokens), _count(cached_tokens),
            _count(reasoning_tokens), _count(search_calls),
        )
        if len(_pending) == MAX_PENDING:
            _dropped += 1
        _pending.append(row)
    except Exception:  # Không để một dòng số liệu làm hỏng lượt của người dùng.
        logger.warning("Bỏ qua một sự kiện số liệu không hợp lệ")


def dropped() -> int:
    return _dropped


async def flush() -> int:
    """Ghi những gì đang chờ; lỗi database chỉ làm mất lô đó (có log), không thử lại vô hạn."""
    if not _pending:
        return 0
    rows = [_pending.popleft() for _ in range(len(_pending))]
    try:
        with anyio.CancelScope(shield=True):
            async with connect() as db:
                await db.executemany(
                    f"INSERT INTO usage_events ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})", rows)
                await db.commit()
    except Exception as err:
        logger.warning("Chưa ghi được %d sự kiện số liệu: %s", len(rows), type(err).__name__)
        return 0
    return len(rows)


async def prune(now: float | None = None) -> None:
    """Chỉ giữ chi tiết trong RETENTION_DAYS ngày gần nhất."""
    cutoff = (now or time.time()) - RETENTION_DAYS * 86_400
    try:
        async with connect() as db:
            await db.execute("DELETE FROM usage_events WHERE at < ?", (cutoff,))
            await db.commit()
    except Exception as err:
        logger.warning("Chưa dọn được số liệu cũ: %s", type(err).__name__)


def enable() -> None:
    global _active
    _active = True


def disable() -> None:
    global _active
    _active = False
    _pending.clear()


async def _loop() -> None:
    last_prune = 0.0
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        await flush()
        if time.monotonic() - last_prune >= PRUNE_SECONDS:
            last_prune = time.monotonic()
            await prune()


def start() -> None:
    """Bật ghi số liệu cho tiến trình máy chủ (gọi trong lifespan)."""
    global _task
    enable()
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    """Tắt máy chủ: dừng vòng lặp rồi ghi nốt phần còn lại."""
    global _task, _active
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    await flush()
    _active = False
