"""Lựa chọn model/effort theo hội thoại; API giả và database tạm, không gọi dịch vụ trả phí."""
import sqlite3

import pytest

import storage as db
from storage import connection
from features.chat import conversations
from core import config
from conftest import TEST_OWNER, read_events, sign_in


async def test_selection_saved_without_send_and_read_from_another_device(client, anon_client):
    cid = await db.create_conversation(TEST_OWNER)
    before = (await db.list_conversations(TEST_OWNER))[0]['updated_at']
    response = await client.patch(f'/api/conversations/{cid}', json={'model': 'haiku', 'effort': 'max'})
    assert response.status_code == 200
    anon_client.cookies.update(client.cookies)
    data = (await anon_client.get(f'/api/conversations/{cid}/messages')).json()
    assert (data['model'], data['effort'], data['messages']) == ('haiku', 'max', [])
    settings = (await anon_client.get(f'/api/conversations/{cid}/settings')).json()
    assert (settings['model'], settings['effort']) == ('haiku', 'max')
    assert (await db.list_conversations(TEST_OWNER))[0]['updated_at'] == before
    other = await db.create_conversation(TEST_OWNER)
    data = (await client.get(f'/api/conversations/{other}/messages')).json()
    assert (data['model'], data['effort']) == ('peto', 'auto')


@pytest.mark.parametrize('selection', [
    {'model': 'luna', 'effort': 'none'}, {'model': 'haiku', 'effort': 'auto'}, {'model': 'peto', 'effort': 'high'},
])
async def test_sent_selection_is_saved_including_auto(client, selection):
    events = await read_events(await client.post('/api/chat', json={'message': 'chào', **selection}))
    cid = events[0]['conversation_id']
    assert events[-1]['type'] == 'done'
    data = (await client.get(f'/api/conversations/{cid}/messages')).json()
    assert {key: data[key] for key in selection} == selection
    assert len(data['messages']) == 2
    events = await read_events(await client.post('/api/chat', json={'message': 'tiếp', 'conversation_id': cid, 'model': 'haiku', 'effort': 'low'}))
    assert events[-1]['type'] == 'done'
    assert (await db.conversation_settings(TEST_OWNER, cid))['model'] == 'haiku'


@pytest.mark.parametrize('change', [
    {'model': 'sonnet', 'effort': 'low'}, {'model': 'unknown', 'effort': 'low'},
    {'model': 'haiku', 'effort': 'none'}, {'model': 'peto', 'effort': 'max'},
    {'model': 'peto'}, {'effort': 'low'}, {'model': None, 'effort': 'low'},
    {'model': 'haiku', 'effort': 'low', 'title': 'Đổi tên'},
])
async def test_invalid_pair_does_not_change_settings(client, change):
    cid = await db.create_conversation(TEST_OWNER)
    assert (await client.patch(f'/api/conversations/{cid}', json=change)).status_code == 400
    saved = await db.conversation_settings(TEST_OWNER, cid)
    assert (saved['model'], saved['effort']) == ('peto', 'auto')


async def test_ownership_roleplay_companion_archived_and_provider_access(client, anon_client, monkeypatch):
    cid = await db.create_conversation(TEST_OWNER)
    await sign_in(anon_client)
    assert (await anon_client.get(f'/api/conversations/{cid}/messages')).status_code == 404
    assert (await anon_client.get(f'/api/conversations/{cid}/settings')).status_code == 404
    assert (await anon_client.patch(f'/api/conversations/{cid}', json={'model': 'haiku', 'effort': 'low'})).status_code == 404
    for mode, persona in [('chat', 'roleplay'), ('companion', 'assistant')]:
        special = await db.create_conversation(TEST_OWNER, mode=mode, persona=persona)
        assert (await client.patch(f'/api/conversations/{special}', json={'model': 'haiku', 'effort': 'low'})).status_code == 400
    await client.patch(f'/api/conversations/{cid}', json={'archived': True})
    assert (await client.patch(f'/api/conversations/{cid}', json={'model': 'peto', 'effort': 'low'})).status_code == 409
    await client.patch(f'/api/conversations/{cid}', json={'archived': False})
    monkeypatch.setattr(config, 'AI_PROVIDER', 'xai')
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', '')
    assert (await client.patch(f'/api/conversations/{cid}', json={'model': 'haiku', 'effort': 'low'})).status_code == 503


async def test_unavailable_model_has_notice_without_destroying_saved_choice(client, monkeypatch):
    cid = await db.create_conversation(TEST_OWNER)
    await client.patch(f'/api/conversations/{cid}', json={'model': 'haiku', 'effort': 'max'})
    monkeypatch.setattr(config, 'AI_PROVIDER', 'xai')
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', '')
    data = (await client.get(f'/api/conversations/{cid}/messages')).json()
    assert (data['model'], data['effort']) == ('peto', 'auto')
    assert data['selection_notice']
    saved = await db.conversation_settings(TEST_OWNER, cid)
    assert (saved['model'], saved['effort']) == ('haiku', 'max')


async def test_branch_copies_selection(client):
    cid = await db.create_conversation(TEST_OWNER)
    await client.patch(f'/api/conversations/{cid}', json={'model': 'luna', 'effort': 'xhigh'})
    mid = await db.add_message(cid, 'user', 'chào')
    branch, _ = await conversations.fork(TEST_OWNER, cid, mid, 'chào lại')
    for item in (cid, branch):
        settings = await db.conversation_settings(TEST_OWNER, item)
        assert (settings['model'], settings['effort']) == ('luna', 'xhigh')


async def test_migration_keeps_history_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as legacy:
        legacy.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        legacy.execute("INSERT INTO conversations VALUES('old', ?, 'Tên cũ', 1, 2)", (TEST_OWNER,))
    monkeypatch.setattr(connection, 'DB_PATH', path)
    await db.init_db(); await db.init_db()
    saved = await db.conversation_settings(TEST_OWNER, 'old')
    assert (saved['model'], saved['effort']) == ('peto', 'auto')
    assert (await db.list_conversations(TEST_OWNER))[0]['title'] == 'Tên cũ'
