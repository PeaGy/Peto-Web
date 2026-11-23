"""Sổ mức dùng theo tài khoản và pool hằng tuần, bước chỉ đo (23/11/2026, chủ web chọn pool như Grok, reset 7 ngày,
Peto tính vào pool). Không gọi AI thật."""
import time

import aiosqlite
from storage.connection import connect
import pytest

from conftest import TEST_OWNER, read_events
from core import config, usage_events
from features.admin import rates as rate_file
from features.chat import service as chat_service
from features.usage import api as usage_api
import storage as db
from test_clock_tools import FakeStream, fake_provider
from test_follow_up import said

OTHER = 'google:khac-123'


@pytest.fixture
def recorder():
    usage_events.enable()
    yield usage_events
    usage_events.disable()


async def ledger(owner=TEST_OWNER):
    async with connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute('SELECT * FROM usage_ledger WHERE owner=? ORDER BY id', (owner,))).fetchall()
        return [dict(row) for row in rows]


async def window(owner=TEST_OWNER):
    async with connect() as conn:
        row = await (await conn.execute('SELECT started_at FROM usage_windows WHERE owner=?', (owner,))).fetchone()
        return row[0] if row else None


async def reset(owner=TEST_OWNER):
    await db.init_db()
    async with connect() as conn:
        await conn.execute('DELETE FROM usage_ledger WHERE owner=?', (owner,))
        await conn.execute('DELETE FROM usage_windows WHERE owner=?', (owner,))
        await conn.commit()


async def test_calls_with_an_owner_go_to_the_ledger_and_open_a_window(recorder):
    await reset(); await reset(OTHER)
    recorder.record('call', owner=TEST_OWNER, service='xai', model='peto', slug='grok-4.7', surface='agent',
                    input_tokens=1000, cached_tokens=400, output_tokens=50, search_calls=1, cost_ticks=20_000_000)
    with recorder.account(OTHER, 'chat'):
        # Lần gọi không tự ghi mục (đặt tiêu đề) lấy mục của phạm vi.
        recorder.record('call', service='xai', model='peto', slug='grok-4.7', input_tokens=10, output_tokens=2)
    recorder.record('call', service='xai', model='peto')                       # không có tài khoản: chỉ usage_events
    recorder.record('turn', owner=TEST_OWNER, service='xai', model='peto')     # lượt không phải lần gọi
    recorder.record('call', owner='không hợp lệ', service='xai')
    recorder.charge_images(TEST_OWNER, service='xai', model='grok-imagine-image-2.0', slug='grok-imagine-image-2.0', images=2)
    await recorder.flush()
    mine = await ledger()
    assert [(row['surface'], row['input_tokens'], row['cached_tokens'], row['output_tokens'], row['search_calls'],
             row['cost_ticks'], row['images']) for row in mine] == [
        ('agent', 1000, 400, 50, 1, 20_000_000, None), ('imagine', None, None, None, None, None, 2)]
    assert [row['surface'] for row in await ledger(OTHER)] == ['chat']
    assert await window() is not None and await window(OTHER) is not None


async def test_the_window_lasts_seven_days_then_restarts(recorder):
    await reset()
    old = time.time() - 3 * 86_400
    async with connect() as conn:
        await conn.execute('INSERT INTO usage_windows VALUES (?, ?)', (TEST_OWNER, old))
        await conn.commit()
    recorder.record('call', owner=TEST_OWNER, service='xai', surface='chat')
    await recorder.flush()
    assert await window() == old
    expired = time.time() - 8 * 86_400
    async with connect() as conn:
        await conn.execute('UPDATE usage_windows SET started_at=? WHERE owner=?', (expired, TEST_OWNER))
        await conn.commit()
    recorder.record('call', owner=TEST_OWNER, service='xai', surface='chat')
    await recorder.flush()
    assert await window() > time.time() - 60


async def test_weekly_usage_prices_rows_like_the_admin_page(recorder, monkeypatch):
    await reset()
    monkeypatch.setattr(config, 'USAGE_WEEKLY_USD', 2.0)
    monkeypatch.setattr(config, 'USAGE_IMAGE_USD', 0.05)
    monkeypatch.setattr(rate_file, 'load', lambda: ({'gpt-6-luna': {'input': 2, 'cached_input': 0.2, 'output': 10}}, 'ok'))
    recorder.record('call', owner=TEST_OWNER, service='xai', slug='grok-4.7', surface='chat', cost_ticks=5_000_000_000)
    recorder.record('call', owner=TEST_OWNER, service='openai', slug='gpt-6-luna', surface='agent',
                    input_tokens=100_000, cached_tokens=0, output_tokens=0)                            # 0,20 USD
    recorder.record('call', owner=TEST_OWNER, service='anthropic', slug='chua-co-gia', surface='airi',
                    input_tokens=10, output_tokens=1)                                                  # chưa có giá
    recorder.charge_images(TEST_OWNER, service='xai', model='img', slug='img', images=4)                # 0,20 USD
    await recorder.flush()
    usage = await usage_api.weekly_usage(TEST_OWNER)
    assert usage['measuring'] and usage['resets_at'] - usage['started_at'] == 7 * 86_400
    assert {group['key']: group['percent'] for group in usage['groups']} == {
        'chat': 25.0, 'agent': 10.0, 'companion': 0.0, 'imagine': 10.0}
    assert usage['used_percent'] == 45.0 and usage['unpriced_calls'] == 1
    # Không lộ số tiền cho trang.
    assert 'usd' not in str(usage).lower()


async def test_no_window_means_nothing_used_yet():
    await reset()
    usage = await usage_api.weekly_usage(TEST_OWNER)
    assert usage['started_at'] is None and usage['resets_at'] is None and usage['used_percent'] == 0


async def test_usage_api_is_per_account(client, anon_client, recorder, monkeypatch):
    await reset()
    monkeypatch.setattr(config, 'OWNER_ACCOUNTS', frozenset({TEST_OWNER}))
    recorder.record('call', owner=TEST_OWNER, service='xai', surface='chat', cost_ticks=10_000_000_000)
    await recorder.flush()
    body = (await client.get('/api/usage')).json()
    assert body['unlimited'] is True and body['used_percent'] > 0
    assert (await anon_client.get('/api/usage')).status_code == 401


async def test_a_chat_turn_is_charged_to_the_signed_in_account(client, recorder, monkeypatch):
    await reset()
    provider, _ = fake_provider(monkeypatch, [said('Chào bạn.'), said('Tiêu đề thử')])
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Chào Peto', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done'
    await recorder.flush()
    rows = await ledger()
    assert rows and {row['surface'] for row in rows} == {'chat'} and {row['service'] for row in rows} == {'xai'}
