"""Bulk clear/one-step undo use client v4; no real model, account or YouTube calls."""
import pytest

from features.companion import player_tools as pt
from conftest import TEST_OWNER
from test_player_tools import STATE
from test_player_queue_readback import run, queue
from test_player_reply import dispatch, text_stream, tool_stream, APPROVED

EMPTY = {**STATE, 'status': 'empty', 'track': None, 'queue_count': 0, 'position': 0, 'duration': 0,
         'window_revision': 1, 'native_video_id': None, 'native_state': None, 'can_undo': True}


def cleared(state=EMPTY, **data):
    return dict(ok=True, state=state, data=dict(kind='mutation', queue_revision=8, removed=3, restored=0, **data))


@pytest.mark.parametrize('version', [1, 2, 3])
@pytest.mark.parametrize('action', ['clear_all', 'clear_queue', 'undo_queue'])
async def test_old_client_has_no_bulk_actions_and_never_receives_them(version, action):
    s = pt.PlayerSession(TEST_OWNER, version)
    assert action not in s.schema['parameters']['properties']['action']['enum']
    result, sent = await run(s, dict(action=action, **({'queue_revision': 7} if action == 'undo_queue' else {})), [])
    assert not result['ok'] and not sent


async def test_clear_all_is_one_bulk_command_and_records_observed_counts():
    s = pt.PlayerSession(TEST_OWNER, 4)
    result, sent = await run(s, dict(action='clear_all'), [cleared()])
    assert result['ok'] and [item['action'] for item in sent] == ['clear_all']
    assert s.trace()['commands'][0]['data']['removed'] == 3


@pytest.mark.parametrize('reply', [cleared(STATE), cleared({**EMPTY, 'native_state': 1}),
    dict(ok=True, state=EMPTY), cleared({**EMPTY, 'queue_count': 1})])
async def test_claimed_clear_without_empty_stopped_state_is_not_success(reply):
    result, sent = await run(pt.PlayerSession(TEST_OWNER, 4), dict(action='clear_all'), [reply])
    assert not result['ok'] and len(sent) == 1


async def test_undo_requires_current_turn_revision_and_restores_without_autoplay():
    s = pt.PlayerSession(TEST_OWNER, 4)
    result, sent = await run(s, dict(action='undo_queue', queue_revision=7), [])
    assert not result['ok'] and not sent
    await run(s, dict(action='list_queue', limit=0), [queue([], total=0)])
    ready = {**STATE, 'status': 'ready', 'native_state': 5, 'can_undo': False}
    response = dict(ok=True, state=ready, data=dict(kind='mutation', queue_revision=8, removed=0, restored=3, undo_action='clear_all'))
    result, sent = await run(s, dict(action='undo_queue', queue_revision=7), [response])
    assert result['ok'] and len(sent) == 1 and result['state']['status'] == 'ready'


async def test_clear_queue_keeps_observed_current_playback_and_does_not_claim_to_stop_it():
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 4), dict(action='clear_queue'),
        [cleared({**STATE, 'queue_count': 0})])
    assert result['ok'] and result['state']['status'] == 'playing'


async def test_native_chat_v4_receives_bulk_result_before_natural_confirmation(client, monkeypatch):
    natural = 'All cleared. We can start fresh whenever you like.'
    events, saved, requests = await dispatch(client, [tool_stream(dict(action='clear_all')), text_stream(natural)],
        monkeypatch, [cleared()], checks=[APPROVED], version=4)
    assert saved['content'] == natural
    assert [e['command']['action'] for e in events if e['type'] == 'player_command'] == ['clear_all']
    schema = next(item for item in requests[0]['tools'] if item.get('name') == pt.NAME)
    assert 'clear_all' in schema['parameters']['properties']['action']['enum']
