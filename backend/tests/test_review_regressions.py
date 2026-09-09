"""Kiểm thử hồi quy: quyền bị thu hồi, lưu dở dang, phân trang và ẩn danh."""
import asyncio
import sqlite3

import httpx
import pytest

import auth
import db
import main
from ai.base import ProviderError
from conftest import TEST_DISCORD_ID, TEST_OWNER, read_events
from discord_memory import DiscordMemory
from rate_limit import Admission


async def test_revoked_cookie_cannot_use_any_private_endpoint(client, monkeypatch):
    conversation = await db.create_conversation(TEST_OWNER)
    monkeypatch.setattr(auth, "ALLOWED_DISCORD_IDS", set())
    assert (await client.get('/api/auth/me')).json()['authenticated'] is False
    for method, path in [
        ('GET', '/api/conversations'),
        ('GET', f'/api/conversations/{conversation}/messages'),
        ('DELETE', f'/api/conversations/{conversation}'),
        ('GET', '/api/attachments/anything'),
    ]:
        assert (await client.request(method, path)).status_code == 401
    assert (await client.post('/api/chat', json={'message': 'hello'})).status_code == 401
    assert await db.owns_conversation(TEST_OWNER, conversation)


@pytest.mark.parametrize('failure', [ProviderError('fake'), TimeoutError(), RuntimeError('fake')])
async def test_partial_reply_survives_errors(client, monkeypatch, failure):
    class BrokenProvider:
        async def stream(self, **kwargs):
            yield 'Phần đã nhìn thấy'
            raise failure
    monkeypatch.setattr(main, 'get_provider', lambda: BrokenProvider())
    response = await client.post('/api/chat', json={'message': 'hello'})
    events = await read_events(response)
    assert events[-1]['type'] == 'error'
    conversation = events[0]['conversation_id']
    stored = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    assert stored[-1]['content'] == 'Phần đã nhìn thấy'
    assert stored[-1]['status'] == 'incomplete'
    assert len(stored) == 2


async def test_cancelled_stream_saves_partial_text(client, monkeypatch):
    class SlowProvider:
        async def stream(self, **kwargs):
            yield 'Đã nhận một phần'
            await asyncio.sleep(3600)
    monkeypatch.setattr(main, 'get_provider', lambda: SlowProvider())
    response = await main.chat(main.ChatRequest(message='cancel test'), owner=TEST_OWNER)
    stream = response.body_iterator
    import json
    meta = json.loads((await anext(stream)).split('data: ')[1])
    await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    stored = await db.get_messages(TEST_OWNER, meta['conversation_id'])
    assert stored[-1]['content'] == 'Đã nhận một phần'
    assert stored[-1]['status'] == 'incomplete'


async def test_cooldown_does_not_save_rejected_message(client, monkeypatch):
    gate = Admission(cooldown=300)
    async with gate.slot(TEST_OWNER):
        pass
    monkeypatch.setattr(main, 'admission', gate)
    before = await db.list_conversations(TEST_OWNER, limit=1000)
    response = await client.post('/api/chat', json={'message': 'not accepted'})
    events = await read_events(response)
    assert events[0]['type'] == 'error'
    assert await db.list_conversations(TEST_OWNER, limit=1000) == before


async def test_old_conversations_are_accessible_in_next_page(client):
    created = {await db.create_conversation(TEST_OWNER, f'Page {i}') for i in range(55)}
    first = (await client.get('/api/conversations?limit=50')).json()
    second = (await client.get('/api/conversations?offset=50&limit=50')).json()
    assert first['has_more'] is True
    first_ids = {row['id'] for row in first['conversations']}
    second_ids = {row['id'] for row in second['conversations']}
    assert first_ids.isdisjoint(second_ids)
    assert created <= first_ids | second_ids
    assert (await client.get('/api/conversations?offset=-1')).status_code == 422


async def test_schema_upgrade_preserves_existing_messages(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, created_at REAL)')
        connection.execute("INSERT INTO messages VALUES (1, 'legacy', 'user', 'Giữ nguyên', 0)")
    monkeypatch.setattr(db, 'DB_PATH', path)
    await db.init_db()
    await db.init_db()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT content, status FROM messages').fetchone() == ('Giữ nguyên', 'complete')


@pytest.mark.parametrize('second', [
    {'available': False, 'reason': 'anonymous'},
    {'available': True, 'summary': '', 'explicit': []},
    [],
])
async def test_memory_never_reuses_permission_or_deleted_data(monkeypatch, second):
    responses = iter([{'available': True, 'summary': 'Trí nhớ cũ'}, second])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses)))
    original = httpx.AsyncClient
    monkeypatch.setattr('discord_memory.httpx.AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    memory = DiscordMemory(base_url='http://gateway.test', token='fake', ttl=300)
    assert (await memory.fetch(TEST_DISCORD_ID)).summary == 'Trí nhớ cũ'
    assert (await memory.fetch(TEST_DISCORD_ID)).is_empty
