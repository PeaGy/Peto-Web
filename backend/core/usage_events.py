"""Số liệu vận hành cho trang Quản trị: không nội dung chat, không owner, không mã hội thoại.

Giữ số đo tại ``model_usage``, ``chat_timing`` và ``agent_timing``; sự kiện Chat bổ sung chỉ ghi trạng thái định trước.
``record`` chỉ thêm một dòng vào hàng đợi trong bộ nhớ (đồng bộ, không I/O, không bao giờ báo lỗi ra ngoài), nên đường gửi tin nhắn không chờ
database. Một tác vụ nền ghi cả lô vào SQLite vài giây một lần và ghi nốt khi tắt máy chủ. Ngoài máy chủ (test,
benchmark, lệnh ops) hàng đợi tắt, nên số liệu thử nghiệm không lẫn vào. Cần chạy một tiến trình backend, như
voice và Imagine đã yêu cầu.
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
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
    "cache_write_tokens",
    'effort', 'cost_ticks', 'prefix_hash',
)
KINDS = {"call", "turn", 'chat_event'}
_scope: ContextVar[dict | None] = ContextVar('usage_measurement_scope', default=None)

# Sổ mức dùng theo tài khoản (bảng usage_ledger, 23/11/2026, bước "chỉ đo" của pool hằng tuần như Grok): mỗi lần gọi
# model của một tài khoản thành một dòng số đo, không nội dung. Khác usage_events (cố ý không có owner), owner ở đây chỉ
# do máy chủ gắn: tham số ``owner`` ở chỗ gọi đã biết tài khoản, hoặc phạm vi ``account()`` quanh lượt chat.
LEDGER_COLUMNS = (
    'owner', 'at', 'surface', 'service', 'model', 'slug', 'input_tokens', 'cached_tokens', 'output_tokens',
    'cache_write_tokens', 'search_calls', 'cost_ticks', 'images',
)
# Cửa sổ đo 7 ngày bắt đầu từ lần dùng đầu tiên sau khi cửa sổ trước hết hạn (như "Resets …" của Grok).
WINDOW_SECONDS = 7 * 86_400
_account: ContextVar[dict | None] = ContextVar('usage_account_scope', default=None)
OWNER = re.compile(r"[a-z]+:[A-Za-z0-9_.@+-]{1,200}\Z")


@contextmanager
def account(owner: str, surface: str | None = None):
    """Gắn tài khoản cho mọi lần gọi model bên trong (lượt chat, đặt tiêu đề, tóm tắt). ``surface`` dùng cho lần gọi
    không tự ghi mục (ví dụ đặt tiêu đề)."""
    token = _account.set({'owner': owner, 'surface': surface})
    try:
        yield
    finally:
        _account.reset(token)


@contextmanager
def measurement(*, surface=None, effort=None, purpose=None):
    """Nhãn đo do server bind; không nhận owner/request ID hoặc nội dung từ model/client."""
    token = _scope.set({'surface': surface, 'effort': effort, 'purpose': purpose})
    try:
        yield
    finally:
        _scope.reset(token)
# Nhãn kỹ thuật như trong log (tên model, kết quả…); chuỗi lạ bị bỏ thay vì lưu nguyên.
LABEL = re.compile(r"[a-zA-Z0-9_.:-]{1,100}\Z")

_pending: deque[tuple] = deque(maxlen=MAX_PENDING)
_ledger: deque[tuple] = deque(maxlen=MAX_PENDING)
_active = False
_dropped = 0
_task: asyncio.Task | None = None


def _label(value: object) -> str | None:
    return value.lower() if isinstance(value, str) and LABEL.fullmatch(value) else None


def _hash(value: object) -> str | None:
    return value if isinstance(value, str) and len(value) == 8 and all(c in '0123456789abcdef' for c in value) else None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def record(
    kind: str, *, service: str, model: str | None = None, slug: str | None = None, surface: str | None = None,
    purpose: str | None = None, outcome: str | None = None, complete: bool | None = None,
    elapsed_ms: int | None = None, first_text_ms: int | None = None, input_tokens: int | None = None,
    output_tokens: int | None = None, cached_tokens: int | None = None, reasoning_tokens: int | None = None,
    search_calls: int | None = None, cache_write_tokens: int | None = None,
    effort: str | None = None, cost_ticks: int | None = None, prefix_hash: str | None = None,
    owner: str | None = None,
) -> None:
    """Thêm một sự kiện vào hàng đợi. Số liệu hỏng chỉ thành ô trống; không bao giờ làm hỏng lượt chat."""
    global _dropped
    if not _active or kind not in KINDS:
        return
    try:
        scope = _scope.get() or {}
        surface, effort = surface or scope.get('surface'), effort or scope.get('effort')
        if kind == 'call' and scope.get('purpose'):
            purpose = scope['purpose']
        row = (
            time.time(), kind, _label(surface), _label(purpose), _label(service) or "unknown", _label(model),
            _label(slug), _label(outcome), None if complete is None else int(bool(complete)), _count(elapsed_ms),
            _count(first_text_ms), _count(input_tokens), _count(output_tokens), _count(cached_tokens),
            _count(reasoning_tokens), _count(search_calls), _count(cache_write_tokens), _label(effort),
            # Số tiền nhà cung cấp tự báo đã tính cho lần gọi (xAI: cost_in_usd_ticks, 1 USD = 10^10 tick).
            _count(cost_ticks),
            # 8 ký tự hex của SHA-256 phần đầu cố định (instructions + tools), không chứa chữ nào: hai lần gọi liền nhau
            # khác giá trị là phần đầu đã đổi nên prompt cache không đọc được (G1.1b).
            _hash(prefix_hash),
        )
        if len(_pending) == MAX_PENDING:
            _dropped += 1
        _pending.append(row)
        if kind == 'call':
            bound = _account.get() or {}
            _charge(owner or bound.get('owner'), at=row[0], surface=row[2] or _label(bound.get('surface')),
                    service=row[4], model=row[5], slug=row[6], input_tokens=row[11], cached_tokens=row[13],
                    output_tokens=row[12], cache_write_tokens=row[16], search_calls=row[15], cost_ticks=row[18])
    except Exception:  # Không để một dòng số liệu làm hỏng lượt của người dùng.
        logger.warning("Bỏ qua một sự kiện số liệu không hợp lệ")


def _charge(owner, *, at, surface, service, model, slug, input_tokens=None, cached_tokens=None, output_tokens=None,
            cache_write_tokens=None, search_calls=None, cost_ticks=None, images=None) -> None:
    if not isinstance(owner, str) or not OWNER.fullmatch(owner):
        return
    _ledger.append((owner, at, surface, service, model, slug, input_tokens, cached_tokens, output_tokens,
                    cache_write_tokens, search_calls, cost_ticks, images))


def charge_images(owner: str, *, service: str, model: str | None, slug: str | None, images: int,
                  cost_ticks: int | None = None) -> None:
    """Ảnh của Tạo ảnh vào sổ mức dùng (không vào usage_events: trang Quản trị đếm lần gọi chat/agent)."""
    if not _active:
        return
    try:
        _charge(owner, at=time.time(), surface='imagine', service=_label(service) or 'unknown', model=_label(model),
                slug=_label(slug), cost_ticks=_count(cost_ticks), images=_count(images))
    except Exception:
        logger.warning("Bỏ qua một dòng mức dùng không hợp lệ")


def dropped() -> int:
    return _dropped


async def flush() -> int:
    """Ghi những gì đang chờ; lỗi database chỉ làm mất lô đó (có log), không thử lại vô hạn."""
    if not _pending and not _ledger:
        return 0
    rows = [_pending.popleft() for _ in range(len(_pending))]
    ledger = [_ledger.popleft() for _ in range(len(_ledger))]
    try:
        with anyio.CancelScope(shield=True):
            async with connect() as db:
                await db.executemany(
                    f"INSERT INTO usage_events ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})", rows)
                await db.executemany(
                    f"INSERT INTO usage_ledger ({', '.join(LEDGER_COLUMNS)}) "
                    f"VALUES ({', '.join('?' * len(LEDGER_COLUMNS))})", ledger)
                # Mở cửa sổ 7 ngày mới khi chưa có hoặc cửa sổ cũ đã hết hạn, tính từ lần dùng đầu tiên của lô.
                first: dict[str, float] = {}
                for item in ledger:
                    first[item[0]] = min(first.get(item[0], item[1]), item[1])
                await db.executemany(
                    """INSERT INTO usage_windows (owner, started_at) VALUES (?, ?)
                       ON CONFLICT(owner) DO UPDATE SET started_at = excluded.started_at
                       WHERE usage_windows.started_at + ? <= excluded.started_at""",
                    [(owner, at, WINDOW_SECONDS) for owner, at in first.items()])
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
            await db.execute("DELETE FROM usage_ledger WHERE at < ?", (cutoff,))
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
    _ledger.clear()


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
