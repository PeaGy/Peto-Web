"""Discord import opt-out, using only local SQLite, fake gateway and mock model output."""
import uuid

import pytest
from ai import StreamChunk
from core.config import SESSION_COOKIE
from features.accounts import auth
from features.accounts.discord_memory import MemorySnapshot, discord_memory
from features.chat import prompt_context, service
import storage as db
from storage import connection, users
from conftest import TEST_OWNER, TEST_DISCORD_ID, OTHER_DISCORD_ID, read_events, sign_in

URL = '/api/account/discord-memory'


@pytest.fixture(autouse=True)
async def clean_preference(client):
    await users.set_discord_memory_enabled(TEST_OWNER, True)
    yield
    await users.set_discord_memory_enabled(TEST_OWNER, True)


async def test_default_and_toggle_persist_across_sessions_and_login_refresh(client, monkeypatch):
    monkeypatch.setattr(discord_memory, 'base_url', 'http://fake-gateway')
    monkeypatch.setattr(discord_memory, 'token', 'fake-token')
    async def never_fetch(_):
        raise AssertionError('Settings must not request actual bot memories')
    monkeypatch.setattr(discord_memory, 'fetch', never_fetch)
    response = await client.get(URL)
    assert response.json() == {'enabled': True, 'available': True}
    assert response.headers['cache-control'] == 'no-store'
    assert (await client.put(URL, json={'enabled': False})).json()['enabled'] is False
    await db.upsert_user(owner=TEST_OWNER, provider='discord', discord_id=TEST_DISCORD_ID,
                         username='refreshed', display_name='Refreshed', avatar_url='')
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, auth._sign(TEST_OWNER))
    assert (await client.get(URL)).json()['enabled'] is False
    assert (await client.put(URL, json={'enabled': True})).json()['enabled'] is True


async def test_preferences_are_scoped_to_session_owner(client):
    await client.put(URL, json={'enabled': False})
    other = f'discord:{OTHER_DISCORD_ID}'
    await db.upsert_user(owner=other, provider='discord', discord_id=OTHER_DISCORD_ID,
                         username='other', display_name='Other', avatar_url='')
    client.cookies.set(SESSION_COOKIE, auth._sign(other))
    assert (await client.get(URL)).json()['enabled'] is True
    assert (await client.put(URL, json={'enabled': True, 'owner': TEST_OWNER})).status_code == 422
    assert (await db.get_user(TEST_OWNER))['discord_memory_enabled'] == 0


@pytest.mark.parametrize('provider', ['google', 'github'])
async def test_other_providers_cannot_read_or_modify_import_setting(client, provider):
    await sign_in(client, provider)
    assert (await client.get(URL)).status_code == 403
    assert (await client.put(URL, json={'enabled': False})).status_code == 403


async def test_unauthenticated_requests_rejected(anon_client):
    assert (await anon_client.get(URL)).status_code == 401
    assert (await anon_client.put(URL, json={'enabled': False})).status_code == 401


@pytest.mark.parametrize('value', ['false', 0, 1, None, {}, []])
async def test_setting_requires_a_boolean(client, value):
    assert (await client.put(URL, json={'enabled': value})).status_code == 422
    assert (await client.get(URL)).json()['enabled'] is True


async def test_can_opt_out_while_gateway_unconfigured_without_touching_web_memory(client, monkeypatch):
    monkeypatch.setattr(discord_memory, 'token', '')
    before = await db.ensure_memory_state(TEST_OWNER)
    memories = await db.list_memories(TEST_OWNER)
    assert (await client.put(URL, json={'enabled': False})).json() == {'enabled': False, 'available': False}
    assert await db.memory_state(TEST_OWNER) == before
    assert await db.list_memories(TEST_OWNER) == memories


@pytest.mark.parametrize('mode', ['chat', 'companion'])
async def test_setting_reaches_real_chat_prompt_and_skips_gateway_when_off(client, monkeypatch, mode):
    fetched, prompts = [], []
    secret = 'Discord-only synthetic memory ' + uuid.uuid4().hex
    async def fetch(discord_id):
        fetched.append(discord_id)
        return MemorySnapshot(summary=secret)
    async def stream(prompt, *args, **kwargs):
        prompts.append(prompt)
        yield StreamChunk('text', 'Synthetic answer')
    monkeypatch.setattr(discord_memory, 'fetch', fetch)
    monkeypatch.setattr(service, '_stream_reply', stream)
    for enabled in (False, True):
        assert (await client.put(URL, json={'enabled': enabled})).status_code == 200
        response = await client.post('/api/chat', json={'message': 'Synthetic question', 'mode': mode})
        events = await read_events(response)
        assert events[-1]['type'] == 'done', events
        assert (secret in prompts[-1]) is enabled
        assert fetched == ([TEST_DISCORD_ID] if enabled else [])


async def test_byok_memory_false_still_overrides_enabled_preference(client, monkeypatch):
    async def never_fetch(_):
        raise AssertionError('memory=False must not call gateway')
    monkeypatch.setattr(discord_memory, 'fetch', never_fetch)
    await prompt_context._build_system_prompt(TEST_OWNER, 'companion', memory=False)


async def test_additive_migration_of_legacy_users_is_repeatable(tmp_path, monkeypatch):
    import aiosqlite
    with monkeypatch.context() as patch:
        patch.setattr(connection, 'DB_PATH', tmp_path / 'legacy.db')
        async with aiosqlite.connect(connection.DB_PATH) as sql:
            await sql.execute('''CREATE TABLE users (owner TEXT PRIMARY KEY, provider TEXT NOT NULL,
                discord_id TEXT UNIQUE, username TEXT, display_name TEXT, avatar_url TEXT,
                first_login_at REAL NOT NULL,last_login_at REAL NOT NULL)''')
            await sql.execute("INSERT INTO users VALUES(?, 'discord', ?, 'legacy', 'Legacy', '', 1, 2)", (TEST_OWNER, TEST_DISCORD_ID))
            await sql.commit()
        await db.init_db()
        assert (await db.get_user(TEST_OWNER))['discord_memory_enabled'] == 1
        await users.set_discord_memory_enabled(TEST_OWNER, False)
        await db.init_db()
        user = await db.get_user(TEST_OWNER)
        assert user['display_name'] == 'Legacy' and user['first_login_at'] == 1
        assert user['discord_memory_enabled'] == 0
