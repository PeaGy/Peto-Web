"""Queue evidence comes from the sending browser in this turn; no AI/network calls."""
import json
from contextlib import aclosing
from types import SimpleNamespace

import pytest

from ai.base import ChatMessage, StreamChunk
from features.companion import player_tools as pt
from conftest import TEST_OWNER
from test_clock_tools import FakeStream, call, done, fake_provider
from test_player_tools import STATE


FIRST = dict(video_id='first000001', title='愛の詩（V3）', artist='LamazeP', index=1, entry_id='entry-first')
SECOND = dict(video_id='second00001', title='ラストスコア / 初音ミク', artist='Uka', index=2, entry_id='entry-second')
MOVE = dict(action='move_queue_entry', entry_id=SECOND['entry_id'], queue_revision=7, position=1)


def track(item):
    return {key: item[key] for key in ('video_id', 'title', 'artist')}


def queue(items=None, revision=7, offset=0, total=2):
    return dict(ok=True, state=STATE, data=dict(kind='queue', items=[FIRST, SECOND] if items is None else items,
                queue_revision=revision, offset=offset, total=total))


def mutation(target=SECOND):
    return dict(ok=True, state=STATE, data=dict(kind='mutation', target=track(target), queue_revision=8))


async def run(session, command, replies):
    """Drive exactly the commands actually sent; unexpected sends fail rather than hang."""
    sent, results = [], []
    async with aclosing(session.run(json.dumps(command))) as stream:
        async for item in stream:
            if isinstance(item, StreamChunk):
                sent.append(item.info)
                assert len(sent) <= len(replies)
                assert pt.acknowledge(TEST_OWNER, item.info['id'], pt.Result.model_validate(replies[len(sent) - 1]))
            else:
                results.append(item)
    assert len(sent) == len(replies)
    assert len(results) == 1
    assert not pt.pending
    return results[0], sent


@pytest.mark.parametrize('action', ['move_queue_entry', 'remove_queue_entry', 'play_queue_entry'])
async def test_guessed_or_previous_turn_entry_never_reaches_browser(action):
    session = pt.PlayerSession(TEST_OWNER, 2)
    await run(session, dict(action='list_queue'), [queue()])
    command = {**MOVE, 'action': action}
    if action != 'move_queue_entry': command.pop('position')
    # A new session represents the next turn, where assistant history is not a queue observation.
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 2), command, [])
    assert result['ok'] is False and 'nothing was executed' in result['error']
    for changes in ({'entry_id': 'invented'}, {'queue_revision': 6}):
        result, _ = await run(session, {**command, **changes}, [])
        assert result['ok'] is False


async def test_move_returns_fresh_order_and_exact_song_without_repeating_mutation():
    session = pt.PlayerSession(TEST_OWNER, 2)
    await run(session, dict(action='list_queue'), [queue()])
    after = [{**SECOND, 'index': 1}, {**FIRST, 'index': 2}]
    result, sent = await run(session, MOVE, [mutation(), queue(after, revision=8)])
    assert [item['action'] for item in sent] == ['move_queue_entry', 'list_queue']
    assert sent[1]['offset'] == 0
    assert result['ok'] is True
    assert result['change'] == dict(action='move_queue_entry', entry_id='entry-second', from_position=2, to_position=1)
    assert result['data']['target'] == track(SECOND)
    assert result['data']['items'] == after
    assert 'Stay With Me' not in json.dumps(result)


@pytest.mark.parametrize('after', [
    queue(revision=8),  # Browser acknowledged a move, but the selected entry is still second.
    queue([{**SECOND, 'index': 1}, {**FIRST, 'index': 2}], revision=9),  # Changed again before readback.
    queue([{**FIRST, 'entry_id': SECOND['entry_id']}, {**SECOND, 'entry_id': FIRST['entry_id']}], revision=8),
    dict(ok=False, error='Player unavailable'),
    dict(ok=True, state=STATE),
])
async def test_unverified_readback_is_not_success_and_never_repeats_move(after):
    session = pt.PlayerSession(TEST_OWNER, 2)
    await run(session, dict(action='list_queue'), [queue()])
    result, sent = await run(session, MOVE, [mutation(), after])
    assert result['ok'] is False and 'Do not repeat' in result['error']
    assert [item['action'] for item in sent] == ['move_queue_entry', 'list_queue']


async def test_wrong_target_ack_cannot_confirm_unrelated_song():
    session = pt.PlayerSession(TEST_OWNER, 2)
    await run(session, dict(action='list_queue'), [queue()])
    result, sent = await run(session, MOVE, [mutation(FIRST)])
    assert result['ok'] is False and 'selected song' in result['error']
    assert len(sent) == 1


async def test_paginated_entry_and_destination_near_queue_limit():
    session = pt.PlayerSession(TEST_OWNER, 2)
    target = {**SECOND, 'index': 101}
    await run(session, dict(action='list_queue', offset=100, limit=1), [queue([target], offset=100, total=200)])
    after = [{**FIRST, 'index': 198, 'entry_id': 'entry-198'}, {**FIRST, 'index': 199, 'entry_id': 'entry-199'}, {**SECOND, 'index': 200}]
    result, sent = await run(session, {**MOVE, 'position': 200}, [mutation(), queue(after, revision=8, offset=197, total=200)])
    assert sent[1]['offset'] == 197 and result['change']['to_position'] == 200


async def test_failed_or_inconsistent_read_and_unknown_mutation_invalidate_cached_entries():
    session = pt.PlayerSession(TEST_OWNER, 2)
    for response in (dict(ok=False, error='Offline'), queue([SECOND]), dict(ok=True, state=STATE)):
        await run(session, dict(action='list_queue'), [queue()])
        await run(session, dict(action='list_queue'), [response])
        result, _ = await run(session, MOVE, [])
        assert result['ok'] is False
    await run(session, dict(action='list_queue'), [queue()])
    await run(session, MOVE, [dict(ok=False, error='Outcome unknown')])
    result, _ = await run(session, MOVE, [])
    assert result['ok'] is False


async def test_cancel_during_readback_cleans_pending_without_replaying_move():
    session = pt.PlayerSession(TEST_OWNER, 2)
    await run(session, dict(action='list_queue'), [queue()])
    stream = session.run(json.dumps(MOVE))
    first = (await anext(stream)).info
    assert pt.acknowledge(TEST_OWNER, first['id'], pt.Result.model_validate(mutation()))
    readback = (await anext(stream)).info
    assert readback['action'] == 'list_queue'
    await stream.aclose()
    assert not pt.pending


async def test_native_provider_gets_verified_move_after_two_ai_tool_rounds(monkeypatch):
    calls = [call(pt.NAME, '{"action":"list_queue"}'), call(pt.NAME, json.dumps(MOVE))]
    streams = [FakeStream([SimpleNamespace(type='response.output_item.done', item=item), done(item)]) for item in calls]
    streams.append(FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Verified reply.'), done()]))
    provider, requests = fake_provider(monkeypatch, streams)
    token = pt.current.set(pt.PlayerSession(TEST_OWNER, 2))
    actions, results = [], [queue(), mutation(), queue([{**SECOND, 'index': 1}, {**FIRST, 'index': 2}], revision=8)]
    try:
        async for item in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Move second upcoming song to first.')], web_search='off'):
            if isinstance(item, StreamChunk) and item.kind == 'player_command':
                actions.append(item.info['action'])
                assert pt.acknowledge(TEST_OWNER, item.info['id'], pt.Result.model_validate(results[len(actions) - 1]))
        assert actions == ['list_queue', 'move_queue_entry', 'list_queue']
        assert len(requests) == 3  # Readback is a browser read, not another paid model call.
        observed = json.loads(requests[-1]['input'][-1]['output'])
        assert observed['change']['from_position'] == 2 and observed['change']['to_position'] == 1
        assert observed['data']['target'] == track(SECOND)
    finally:
        pt.current.reset(token)
    assert not pt.pending
