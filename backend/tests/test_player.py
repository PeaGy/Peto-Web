from __future__ import annotations

import pytest
import storage as db
from storage import player as store
from shared import youtube
from conftest import sign_in

BASE = '/api/companion/player'
VIDEO = 'Soy4jGPHr3g'


@pytest.fixture(autouse=True)
async def clean_player(monkeypatch):
    await db.init_db()
    from storage.connection import connect
    async with connect() as conn:
        await conn.execute('DELETE FROM player_favorites')
        await conn.commit()

    async def info(video_id):
        return {'title': f'Title {video_id}', 'channel': 'Channel'}
    monkeypatch.setattr(youtube, 'lookup', info)


async def test_favorites_persist_and_upsert_is_idempotent(client):
    assert (await client.get(f'{BASE}/favorites')).json() == {'favorites': []}
    first = await client.post(f'{BASE}/favorites/{VIDEO}', json={'owner': 'other', 'title': 'untrusted'})
    assert first.status_code == 200
    expected = [{'video_id': VIDEO, 'title': f'Title {VIDEO}', 'artist': 'Channel'}]
    assert first.json()['favorites'] == expected
    await client.post(f'{BASE}/favorites/{VIDEO}')
    await db.init_db()  # Additive, repeatable migration does not erase saved items.
    assert (await client.get(f'{BASE}/favorites')).json()['favorites'] == expected


async def test_favorites_are_separate_by_account(client, anon_client):
    await client.post(f'{BASE}/favorites/{VIDEO}')
    await sign_in(anon_client)
    assert (await anon_client.get(f'{BASE}/favorites')).json()['favorites'] == []
    await anon_client.delete(f'{BASE}/favorites/{VIDEO}')
    assert len((await client.get(f'{BASE}/favorites')).json()['favorites']) == 1
    await anon_client.post(f'{BASE}/favorites/aircAruvnKk')
    assert (await client.get(f'{BASE}/favorites')).json()['favorites'][0]['video_id'] == VIDEO
    await client.delete(f'{BASE}/favorites/{VIDEO}')
    assert (await client.get(f'{BASE}/favorites')).json()['favorites'] == []
    assert len((await anon_client.get(f'{BASE}/favorites')).json()['favorites']) == 1


async def test_authentication_required_for_all_player_routes(anon_client):
    for method, path in [('get', '/favorites'), ('post', f'/favorites/{VIDEO}'), ('delete', f'/favorites/{VIDEO}'), ('get', f'/videos/{VIDEO}')]:
        assert (await getattr(anon_client, method)(BASE + path)).status_code == 401


async def test_ids_validated_before_network_requests(client, monkeypatch):
    async def no_network(_):
        raise AssertionError('invalid ID must not reach lookup')
    monkeypatch.setattr(youtube, 'lookup', no_network)
    for value in ['short', 'youtube.com', 'Soy4jGPHr3g-more', 'abc$efghijk']:
        assert (await client.get(f'{BASE}/videos/{value}')).status_code == 400
        assert (await client.post(f'{BASE}/favorites/{value}')).status_code == 400
        assert (await client.delete(f'{BASE}/favorites/{value}')).status_code == 400


async def test_metadata_failure_does_not_block_saving_or_invent_a_title(client, monkeypatch):
    async def missing(_):
        return None
    monkeypatch.setattr(youtube, 'lookup', missing)
    info = (await client.get(f'{BASE}/videos/{VIDEO}')).json()
    assert info == {'video_id': VIDEO, 'title': '', 'artist': ''}
    saved = await client.post(f'{BASE}/favorites/{VIDEO}')
    assert saved.status_code == 200
    assert saved.json()['favorites'] == [info]


async def test_limit_is_per_account_and_existing_items_still_update(client, anon_client, monkeypatch):
    monkeypatch.setattr(store, 'MAX_FAVORITES', 1)
    assert (await client.post(f'{BASE}/favorites/{VIDEO}')).status_code == 200
    assert (await client.post(f'{BASE}/favorites/{VIDEO}')).status_code == 200
    assert (await client.post(f'{BASE}/favorites/aircAruvnKk')).status_code == 400
    await sign_in(anon_client)
    assert (await anon_client.post(f'{BASE}/favorites/aircAruvnKk')).status_code == 200
    await client.delete(f'{BASE}/favorites/{VIDEO}')
    assert (await client.post(f'{BASE}/favorites/aircAruvnKk')).status_code == 200
