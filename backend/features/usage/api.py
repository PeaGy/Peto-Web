"""Mức dùng trong tuần của tài khoản (Cài đặt → Mức dùng), bước "chỉ đo" của pool hằng tuần như Grok (23/11/2026).

Sổ ``usage_ledger`` (core/usage_events.py) ghi từng lần gọi model và ảnh của mỗi tài khoản. Chi phí mỗi dòng tính
lúc đọc, giống trang Quản trị: Grok dùng số tiền xAI tự báo, model khác dùng tệp đơn giá PETO_COST_RATES_FILE, ảnh dùng
PETO_USAGE_IMAGE_USD. Phần trăm so với PETO_USAGE_WEEKLY_USD (pool tạm, chỉnh sau khi đo). Chưa chặn ai: hết pool chỉ
là con số trên 100%. Trang chỉ thấy phần trăm, không thấy số tiền.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Response

from core import config
from core.usage_events import WINDOW_SECONDS
from features.accounts.auth import current_owner
from features.admin import rates as rate_file
from features.admin.stats import call_cost
from storage.connection import connect

router = APIRouter()

# Nhóm hiển thị theo mục của lần gọi. Lần gọi phụ của lượt chat (đặt tiêu đề, tóm tắt) mang mục "chat".
GROUPS = (
    ('chat', 'Trò chuyện', {'chat'}),
    ('agent', 'Peto Agent', {'agent'}),
    ('companion', 'Companion', {'companion', 'airi'}),
    ('imagine', 'Tạo ảnh', {'imagine'}),
)


def group_of(surface: str | None) -> str:
    for key, _, surfaces in GROUPS:
        if surface in surfaces:
            return key
    return 'chat'


def row_cost(row: dict, rates: dict) -> float | None:
    if row.get('images'):
        price = config.USAGE_IMAGE_USD
        return row['images'] * price if price > 0 else None
    return call_cost(row, rates)


def summarize(rows: list[dict], *, started_at: float | None, now: float, rates: dict, owner_account: bool) -> dict:
    pool = config.USAGE_WEEKLY_USD
    spent = {key: 0.0 for key, _, _ in GROUPS}
    unpriced = 0
    for row in rows:
        cost = row_cost(row, rates)
        if cost is None:
            unpriced += 1
            continue
        spent[group_of(row.get('surface'))] += cost

    def percent(value: float) -> float:
        return round(value / pool * 100, 1) if pool > 0 else 0.0

    return {
        'measuring': True,
        'unlimited': owner_account,
        'started_at': started_at,
        'resets_at': started_at + WINDOW_SECONDS if started_at is not None else None,
        'used_percent': percent(sum(spent.values())),
        'groups': [{'key': key, 'label': label, 'percent': percent(spent[key])} for key, label, _ in GROUPS],
        'unpriced_calls': unpriced,
    }


async def weekly_usage(owner: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    async with connect() as db:
        window = await (await db.execute('SELECT started_at FROM usage_windows WHERE owner=?', (owner,))).fetchone()
        started_at = window[0] if window and window[0] + WINDOW_SECONDS > now else None
        rows = []
        if started_at is not None:
            cursor = await db.execute(
                '''SELECT surface, service, slug, input_tokens, cached_tokens, output_tokens, cache_write_tokens,
                          search_calls, cost_ticks, images
                     FROM usage_ledger WHERE owner=? AND at >= ? ORDER BY at''', (owner, started_at))
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, row)) for row in await cursor.fetchall()]
    rates, _ = rate_file.load()
    return summarize(rows, started_at=started_at, now=now, rates=rates, owner_account=owner in config.OWNER_ACCOUNTS)


@router.get('/api/usage')
async def get_usage(response: Response, owner: str = Depends(current_owner)) -> dict:
    response.headers['Cache-Control'] = 'private, no-store'
    return await weekly_usage(owner)
