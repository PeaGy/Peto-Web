"""v5 history/Previous use fresh browser evidence; no network or real models."""
import pytest

from features.companion import player_tools as pt
from conftest import TEST_OWNER
from test_player_tools import STATE
from test_player_queue_readback import run, FIRST, track
from test_player_reply import dispatch, text_stream, tool_stream, APPROVED

HEARD = {**FIRST, 'played_at': 1700000000000}
PLAYING = {**STATE, 'track': track(HEARD), 'status': 'playing', 'native_video_id': HEARD['video_id'], 'native_state': 1, 'history_count': 1}
def history(items=None, revision=3):
    return dict(ok=True, state=PLAYING, data=dict(kind='history', items=[HEARD] if items is None else items,
        total=1, offset=0, history_revision=revision))
def playing(state=PLAYING):
    return dict(ok=True, state=state, data=dict(kind='mutation', target=track(HEARD), history_revision=4))

@pytest.mark.parametrize('version', [1, 2, 3, 4])
@pytest.mark.parametrize('action', ['previous', 'list_history', 'play_history_entry', 'clear_history'])
async def test_old_clients_never_advertise_or_execute_history(version, action):
    session = pt.PlayerSession(TEST_OWNER, version)
    assert action not in session.schema['parameters']['properties']['action']['enum']
    result, sent = await run(session, dict(action=action, **({'entry_id': HEARD['entry_id'], 'history_revision': 3} if action == 'play_history_entry' else {})), [])
    assert not result['ok'] and not sent

async def test_history_play_requires_an_entry_and_revision_observed_in_this_turn():
    session = pt.PlayerSession(TEST_OWNER, 5)
    command = dict(action='play_history_entry', entry_id=HEARD['entry_id'], history_revision=3)
    result, _ = await run(session, command, []); assert not result['ok']
    assert (await run(session, dict(action='list_history'), [history()]))[0]['ok']
    result, sent = await run(session, command, [playing()]); assert result['ok'] and len(sent) == 1

@pytest.mark.parametrize('changes', [{'native_state': 2}, {'native_video_id': 'wrong000001'}, {'status': 'ready'}])
async def test_previous_cannot_claim_success_without_correct_native_playing_state(changes):
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 5), dict(action='previous'), [playing({**PLAYING, **changes})])
    assert not result['ok']

@pytest.mark.parametrize('changes', [{'history_revision': None}, {'items': [{**HEARD, 'played_at': None}]}, {'total': 101}])
async def test_malformed_history_page_is_not_an_observation(changes):
    response = history(); response['data'].update(changes)
    result, _ = await run(pt.PlayerSession(TEST_OWNER, 5), dict(action='list_history'), [response])
    assert not result['ok']

async def test_clear_history_keeps_playback_and_reports_observed_count():
    response = dict(ok=True, state={**PLAYING, 'history_count': 0}, data=dict(kind='mutation', history_revision=4, total=0, removed=1))
    result, sent = await run(pt.PlayerSession(TEST_OWNER, 5), dict(action='clear_history'), [response])
    assert result['ok'] and result['state']['status'] == 'playing' and len(sent) == 1

async def test_v5_native_provider_receives_previous_receipt_before_natural_confirmation(client, monkeypatch):
    natural = 'Back to the one we just heard. I kept the queue in place.'
    events, saved, requests = await dispatch(client, [tool_stream(dict(action='previous')), text_stream(natural)],
        monkeypatch, [playing()], checks=[APPROVED], version=5)
    assert saved['content'] == natural
    assert [e['command']['action'] for e in events if e['type'] == 'player_command'] == ['previous']
    schema = next(item for item in requests[0]['tools'] if item.get('name') == pt.NAME)
    assert 'previous' in schema['parameters']['properties']['action']['enum']
