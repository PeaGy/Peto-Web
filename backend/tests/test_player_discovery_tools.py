"""Discovery/control protocol v3: paid providers and YouTube are always mocked."""
import asyncio
import json
from contextlib import aclosing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from ai.base import StreamChunk
from features.chat import service
from features.companion import player_tools as pt
from features.companion import player_discovery_tools as discovery
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider
from test_player_tools import STATE as OLD_STATE

STATE = {**OLD_STATE, 'window_revision': 0}
VIDEO = dict(video_id='aircAruvnKk', title='But what is a neural network?', artist='3Blue1Brown', duration=1133)
URL = 'https://www.youtube.com/watch?v=N6DMXNyvAxs&list=RDNA0EfgZH8&index=8&t=1m20s'
PLAYLIST = 'https://www.youtube.com/playlist?list=PLtestplaylist123'


@pytest.fixture
def catalog(monkeypatch):
    search = AsyncMock(return_value={'tracks': [VIDEO], 'next_page_token': 'page-next'})
    playlist = AsyncMock(return_value={'tracks': [VIDEO, VIDEO], 'skipped': 2, 'truncated': True})
    lookup = AsyncMock(return_value={'title': 'A supplied video', 'channel': 'Actual channel'})
    monkeypatch.setattr(discovery.catalog, 'search', search)
    monkeypatch.setattr(discovery.catalog, 'playlist', playlist)
    monkeypatch.setattr(discovery.youtube, 'lookup', lookup)
    return SimpleNamespace(search=search, playlist=playlist, lookup=lookup)


async def run(session, command, replies):
    sent, results = [], []
    async with aclosing(session.run(json.dumps(command))) as stream:
        async for item in stream:
            if isinstance(item, StreamChunk):
                sent.append(item.info)
                assert len(sent) <= len(replies)
                assert pt.acknowledge(TEST_OWNER, item.info['id'], pt.Result.model_validate(replies[len(sent) - 1]))
            else:
                results.append(item)
    assert len(sent) == len(replies) and len(results) == 1 and not pt.pending
    return results[0], sent


def status(**changes):
    return dict(ok=True, state={**STATE, **changes})


@pytest.mark.parametrize('version', [1, 2])
async def test_old_tabs_are_not_advertised_or_sent_discovery_actions(version, catalog):
    session = pt.PlayerSession(TEST_OWNER, version)
    assert 'query' not in session.schema['parameters']['properties']
    assert 'search_videos' not in session.schema['parameters']['properties']['action']['enum']
    result, _ = await run(session, dict(action='search_videos', query='music'), [])
    assert result['ok'] is False
    catalog.search.assert_not_called()


@pytest.mark.parametrize('command', [
    dict(action='search_videos'), dict(action='search_videos', query='a' * 201),
    dict(action='search_videos', query='music', page_token='bad token'), dict(action='play_video'),
    dict(action='play_video', video_id='aircAruvnKk', url=URL), dict(action='enqueue_playlist', video_id='aircAruvnKk'),
    dict(action='play_video', video_id='aircAruvnKk', tracks=[VIDEO]),
])
def test_native_model_cannot_supply_metadata_or_invalid_discovery_arguments(command):
    with pytest.raises(ValidationError): pt.Command.model_validate(command)


@pytest.mark.parametrize('url', [
    'https://youtube.com.evil.test/watch?v=N6DMXNyvAxs', 'https://evil.test/youtube.com/watch?v=N6DMXNyvAxs',
    'https://user@youtube.com/watch?v=N6DMXNyvAxs', 'https://youtube.com:443/watch?v=N6DMXNyvAxs',
    'https://youtube.com/watch?v=N6DMXNyvAxs&v=Soy4jGPHr3g', 'https://youtube.com/embed/N6DMXNyvAxs/extra',
    'https://youtu.be/N6DMXNyvAxs/extra', 'javascript:alert(1)', 'https://youtube.com\\@evil.test/watch?v=N6DMXNyvAxs',
    'https://youtube.com/playlist?list=PLtestplaylist123&list=PLanother123',
])
def test_untrusted_or_ambiguous_urls_are_not_sources(url):
    assert discovery.source(url) is None


async def test_search_is_metadata_only_then_observed_id_can_play(catalog):
    session = pt.PlayerSession(TEST_OWNER, 3)
    result, sent = await run(session, dict(action='search_videos', query='3Blue1Brown'), [status()])
    assert [item['action'] for item in sent] == ['status']
    assert result['data']['items'][0]['title'] == VIDEO['title']
    assert result['data']['next_page_token'] == 'page-next'
    played = status(track={key: VIDEO[key] for key in ('video_id', 'title', 'artist')})
    result, sent = await run(session, dict(action='play_video', video_id=VIDEO['video_id']), [status(), played])
    assert result['ok'] is True and sent[-1]['tracks'][0]['title'] == VIDEO['title']
    assert sent[-1]['window_revision'] == 0
    catalog.search.assert_awaited_once_with(TEST_OWNER, '3Blue1Brown', '')
    catalog.lookup.assert_not_called()


async def test_unobserved_id_or_invented_url_never_reaches_playback(catalog):
    session = pt.PlayerSession(TEST_OWNER, 3)
    for command in (dict(action='play_video', video_id=VIDEO['video_id']), dict(action='play_video', url=URL)):
        result, sent = await run(session, command, [status()])
        assert result['ok'] is False and len(sent) == 1
    catalog.lookup.assert_not_called()


async def test_video_with_list_selects_only_supplied_video_and_preserves_timestamp(catalog):
    session = pt.PlayerSession(TEST_OWNER, 3, user_text=f'Add this please: {URL}')
    target = dict(video_id='N6DMXNyvAxs', title='A supplied video', artist='Actual channel')
    result, sent = await run(session, dict(action='enqueue_video', url=URL), [status(), dict(ok=True, state=STATE, data=dict(kind='mutation', added=1, target=target))])
    assert result['ok'] is True
    assert sent[-1]['tracks'][0]['video_id'] == 'N6DMXNyvAxs' and sent[-1]['tracks'][0]['start_seconds'] == 80
    catalog.playlist.assert_not_called()
    catalog.search.assert_not_called()


async def test_invalid_catalogue_metadata_is_a_tool_error_not_a_chat_crash(catalog):
    catalog.search.return_value = dict(tracks=[{**VIDEO, 'video_id': 'invalid'}], next_page_token='')
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 3), dict(action='search_videos', query='music'), [status()])
    assert result['ok'] is False and 'metadata' in result['error']


async def test_playlist_appends_with_real_counts_preserves_duplicates_and_reports_truncation(catalog):
    session = pt.PlayerSession(TEST_OWNER, 3, user_text=PLAYLIST)
    result, sent = await run(session, dict(action='enqueue_playlist', url=PLAYLIST),
                             [status(queue_count=198), dict(ok=True, state=STATE, data=dict(kind='mutation', added=1))])
    catalog.playlist.assert_awaited_once_with(TEST_OWNER, 'PLtestplaylist123', 2)
    assert sent[-1]['tracks'][0] == sent[-1]['tracks'][1]
    assert result['data'] == dict(kind='mutation', items=[], added=1, skipped_unavailable=2, truncated=True, not_added_capacity=1)


async def test_full_queue_does_not_spend_playlist_quota(catalog):
    result, sent = await run(pt.PlayerSession(TEST_OWNER, 3, PLAYLIST), dict(action='enqueue_playlist', url=PLAYLIST), [status(queue_count=200)])
    assert result['ok'] is False and len(sent) == 1
    catalog.playlist.assert_not_called()


@pytest.mark.parametrize('failure', [HTTPException(503, 'Quota exhausted.'), HTTPException(504, 'Timed out.')])
async def test_catalog_failure_is_not_success_or_a_fallback_song(catalog, failure):
    catalog.search.side_effect = failure
    result, sent = await run(pt.PlayerSession(TEST_OWNER, 3), dict(action='search_videos', query='music'), [status()])
    assert result == dict(ok=False, error=failure.detail) and len(sent) == 1


async def test_empty_search_and_missing_metadata_never_start_another_video(catalog):
    catalog.search.return_value = dict(tracks=[], next_page_token='')
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 3), dict(action='search_videos', query='missing'), [status()])
    assert result['ok'] is True and not result['data']['items']
    catalog.lookup.return_value = None
    result, sent = await run(pt.PlayerSession(TEST_OWNER, 3, URL), dict(action='play_video', url=URL), [status()])
    assert result['ok'] is False and len(sent) == 1


@pytest.mark.parametrize('ack', [dict(ok=False, error='YouTube 150'), status(status='ready'), status()])
async def test_unconfirmed_or_wrong_video_is_not_playback_success(catalog, ack):
    session = pt.PlayerSession(TEST_OWNER, 3)
    await run(session, dict(action='search_videos', query='music'), [status()])
    result, _ = await run(session, dict(action='play_video', video_id=VIDEO['video_id']), [status(), ack])
    assert result['ok'] is False


async def test_closing_after_search_prevents_late_playback(catalog):
    session = pt.PlayerSession(TEST_OWNER, 3)
    await run(session, dict(action='search_videos', query='music'), [status()])
    result, sent = await run(session, dict(action='play_video', video_id=VIDEO['video_id']), [status(window_revision=1)])
    assert result['ok'] is False and len(sent) == 1


async def test_native_companion_v3_search_then_play_round_trip(client, monkeypatch, catalog):
    calls = [call(pt.NAME, '{"action":"search_videos","query":"relaxing piano"}'),
             call(pt.NAME, '{"action":"play_video","video_id":"aircAruvnKk"}')]
    streams = [FakeStream([SimpleNamespace(type='response.output_item.done', item=item), done(item)]) for item in calls]
    streams.append(FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Playing the selected video.'), done()]))
    streams.append(FakeStream([SimpleNamespace(type='response.output_text.delta', delta='{"supported":true,"reason":""}'), done()]))
    provider, requests = fake_provider(monkeypatch, streams)
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    task = asyncio.create_task(client.post('/api/chat', json=dict(mode='companion', message='Sure, put on something relaxing.', player_control=3, web_search='off')))
    replies = [status(), status(), status(track={key: VIDEO[key] for key in ('video_id', 'title', 'artist')})]
    try:
        seen = set()
        for reply in replies:
            async with asyncio.timeout(5):
                while not (keys := set(pt.pending) - seen): await asyncio.sleep(.01)
            key = keys.pop(); seen.add(key)
            assert (await client.post(f'/api/companion/player/commands/{key}/result', json=reply)).status_code == 200
        events = await read_events(await task)
        assert events[-1]['type'] == 'done'
        assert [event['command']['action'] for event in events if event['type'] == 'player_command'] == ['status', 'status', 'play_video']
        schema = next(schema for schema in requests[0]['tools'] if schema.get('name') == pt.NAME)
        assert 'search_videos' in schema['parameters']['properties']['action']['enum']
        assert set(schema['parameters']['required']) == set(schema['parameters']['properties'])
        assert 'clear acceptance' in requests[0]['instructions']
        assert json.loads(requests[2]['input'][-1]['output'])['state']['track']['title'] == VIDEO['title']
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_native_companion_url_comes_from_user_history_and_never_imports_its_list(client, monkeypatch, catalog):
    tool = call(pt.NAME, json.dumps(dict(action='enqueue_video', url=URL)))
    provider, _ = fake_provider(monkeypatch, [FakeStream([SimpleNamespace(type='response.output_item.done', item=tool), done(tool)]),
        FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Added the video.'), done()]),
        FakeStream([SimpleNamespace(type='response.output_text.delta', delta='{"supported":true,"reason":""}'), done()])])
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    task = asyncio.create_task(client.post('/api/chat', json=dict(mode='companion', message=f'Add this please {URL}', player_control=3, web_search='off')))
    try:
        seen = set()
        target = dict(video_id='N6DMXNyvAxs', title='A supplied video', artist='Actual channel')
        for reply in (status(), dict(ok=True, state=STATE, data=dict(kind='mutation', added=1, target=target))):
            async with asyncio.timeout(5):
                while not (keys := set(pt.pending) - seen): await asyncio.sleep(.01)
            key = keys.pop(); seen.add(key)
            assert (await client.post(f'/api/companion/player/commands/{key}/result', json=reply)).status_code == 200
        events = await read_events(await task)
        commands = [event['command'] for event in events if event['type'] == 'player_command']
        assert commands[-1]['tracks'][0]['video_id'] == target['video_id']
        assert commands[-1]['tracks'][0]['start_seconds'] == 80
        catalog.playlist.assert_not_called()
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_ordinary_mood_does_not_itself_dispatch_music(client, monkeypatch, catalog):
    provider, _ = fake_provider(monkeypatch, [FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Long day? Want some relaxing music?'), done()])])
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    events = await read_events(await client.post('/api/chat', json=dict(mode='companion', message="I'm tired, Peto.", player_control=3, web_search='off')))
    assert not any(event['type'] == 'player_command' for event in events)
    catalog.search.assert_not_called()
