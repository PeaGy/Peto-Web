"""False confirmations must never reach UI/speech, even when the fake model insists success."""
import asyncio
import json
from contextlib import aclosing
from types import SimpleNamespace

import pytest

from ai.base import ChatMessage, StreamChunk
from ai import byok
from features.chat import service
from features.companion import player_tools as pt, player_reply as guard
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider
from test_player_tools import STATE


def text_stream(text):
    return FakeStream([SimpleNamespace(type='response.output_text.delta', delta=text), done()])


def tool_stream(arguments):
    item = call(pt.NAME, json.dumps(arguments))
    return FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Swapped. Draft before execution.'),
                       SimpleNamespace(type='response.output_item.done', item=item), done(item)])


@pytest.mark.parametrize('text', ['Swapped. The new song is playing.', "I've just swapped the video.",
    '<|EMOTE_HAPPY|> Swapped.', 'Done. Switched the song.', 'Peto opened the player.', 'Đã đổi bài rồi.', 'Mình vừa chuyển bài.'])
def test_affirmative_change_claims(text):
    assert guard.claims_change(text)


@pytest.mark.parametrize('text', ["I haven't swapped it.", 'Want me to put on music?', 'Can I pause it?',
    "I can't play it yet.", 'The song title is “Swapped”.', 'What does swapped mean?', 'I paused to think.',
    'Mình chưa đổi bài.', 'Bạn muốn mình đổi bài không?', 'Playing cards is fun.', 'Mình đã mở lòng.', 'I opened the book.'])
def test_discussion_negation_and_song_names_are_not_change_claims(text):
    assert not guard.claims_change(text)


async def dispatch(client, streams, monkeypatch, replies=(), message='Replace the current song.'):
    provider, requests = fake_provider(monkeypatch, streams)
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    task = asyncio.create_task(client.post('/api/chat', json=dict(mode='companion', message=message, player_control=3, web_search='off')))
    try:
        seen = set()
        for reply in replies:
            async with asyncio.timeout(5):
                while not (keys := set(pt.pending) - seen): await asyncio.sleep(.01)
            assert not task.done()
            key = keys.pop(); seen.add(key)
            assert (await client.post(f'/api/companion/player/commands/{key}/result', json=reply)).status_code == 200
        events = await read_events(await task)
        assert events[-1]['type'] == 'done', events
        saved = (await client.get('/api/companion')).json()['messages'][-1]
        return events, saved, requests
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_no_call_false_swap_is_repaired_once_and_only_confirmed_track_is_spoken(client, monkeypatch):
    events, saved, requests = await dispatch(client, [text_stream('Swapped. Hallucinated song is playing.'),
        tool_stream(dict(action='play')), text_stream('<|EMOTE_HAPPY|> Swapped. Another invented song.')], monkeypatch,
        [dict(ok=True, state=STATE)])
    text = ''.join(event.get('text', '') for event in events if event['type'] == 'delta')
    assert 'Tetris' in text and 'Hallucinated' not in text and 'invented' not in text and 'Swapped' not in text
    assert saved['content'] == text
    assert saved['emotion'] == 'happy'
    assert len(requests) == 3 and 'PLAYER EXECUTION CHECK' in requests[1]['instructions']
    assert saved['player_trace']['commands'][0]['action'] == 'play'
    assert saved['player_trace']['commands'][0]['ok'] is True
    assert 'work' not in saved


@pytest.mark.parametrize('reply', [dict(ok=False, error='YouTube cannot play this video. (150)'),
                                  dict(ok=False, error='Acknowledgement lost; outcome unknown.')])
async def test_failed_action_cannot_be_overridden_by_success_text_or_automatically_replayed(client, monkeypatch, reply):
    events, saved, requests = await dispatch(client, [tool_stream(dict(action='play')),
        text_stream('Swapped. The requested song is playing now.')], monkeypatch, [reply])
    text = ''.join(event.get('text', '') for event in events if event['type'] == 'delta')
    assert 'Swapped' not in text and 'playing now' not in text and reply['error'] in text
    assert len(requests) == 2
    assert len([event for event in events if event['type'] == 'player_command']) == 1
    assert saved['player_trace']['commands'][0]['error'] == reply['error']
    assert saved['player_trace']['commands'][0]['sent'] is True


async def test_second_unexecuted_confirmation_is_blocked_without_infinite_ai_retries(client, monkeypatch):
    events, saved, requests = await dispatch(client, [text_stream('Swapped.'), text_stream('Swapped.')], monkeypatch)
    assert saved['content'] == "I haven't made a confirmed Player change."
    assert not saved['player_trace']['commands']
    assert len(requests) == 2 and not any(event['type'] == 'player_command' for event in events)


async def test_model_cannot_replay_a_failed_mutation_in_same_turn(client, monkeypatch):
    events, saved, _ = await dispatch(client, [tool_stream(dict(action='play')), tool_stream(dict(action='play')),
        text_stream('Swapped.')], monkeypatch, [dict(ok=False, error='YouTube 150')])
    commands = saved['player_trace']['commands']
    assert [item['sent'] for item in commands] == [True, False]
    assert not any(item['ok'] for item in commands)
    assert len([event for event in events if event['type'] == 'player_command']) == 1
    assert 'Swapped' not in saved['content']


async def test_native_video_mismatch_does_not_become_success_receipt(client, monkeypatch):
    result = dict(ok=True, state={**STATE, 'native_video_id': 'aircAruvnKk', 'native_state': 1})
    _, saved, _ = await dispatch(client, [tool_stream(dict(action='play')), text_stream('Swapped.')], monkeypatch, [result])
    assert saved['player_trace']['commands'][0]['ok'] is False
    assert 'does not confirm' in saved['content']


async def test_ordinary_companion_reply_needs_no_extra_ai_call(client, monkeypatch):
    events, saved, requests = await dispatch(client, [text_stream('Long day? Want some relaxing music?')], monkeypatch, message="I'm tired.")
    assert saved['content'] == 'Long day? Want some relaxing music?'
    assert len(requests) == 1 and 'player_trace' not in saved


async def test_receipt_history_is_available_for_followup_without_replaying_commands(client, monkeypatch):
    _, _, _ = await dispatch(client, [tool_stream(dict(action='play')), text_stream('Swapped.')], monkeypatch,
        [dict(ok=False, error='YouTube 150')])
    provider, requests = fake_provider(monkeypatch, [text_stream('The recorded play request failed with YouTube 150.')])
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    response = await client.post('/api/chat', json=dict(mode='companion', message='Why did that fail?', player_control=3,
        conversation_id=(await client.get('/api/companion')).json()['conversation_id'], web_search='off'))
    events = await read_events(response)
    assert not any(event['type'] == 'player_command' for event in events)
    assert 'PLAYER EXECUTION RECORDS' in requests[0]['instructions'] and 'YouTube 150' in requests[0]['instructions']


async def test_interruption_keeps_an_unknown_receipt_and_no_replayable_command_id():
    session = pt.PlayerSession(TEST_OWNER, 3)
    stream = session.run('{"action":"next"}')
    command = (await anext(stream)).info
    await stream.aclose()
    trace = session.trace()
    assert trace['commands'][0]['sent'] is True and trace['commands'][0]['ok'] is False
    assert 'unknown' in trace['commands'][0]['error']
    assert command['id'] not in json.dumps(trace) and not pt.pending


async def test_private_notes_cannot_hide_an_affirmative_confirmation_from_guard():
    assert guard.claims_change('<|EMOTE_NEUTRAL|> Swapped.')


def test_partial_failure_keeps_only_observed_successes_and_real_failure():
    receipts = [dict(action='open', result=dict(ok=True, state=STATE)),
                dict(action='play', result=dict(ok=False, error='Blocked playback.'))]
    text = guard.confirmations(receipts, False)
    assert 'Player is open.' in text and 'Blocked playback.' in text and 'Playing' not in text


async def test_status_answer_is_not_mistaken_for_an_unexecuted_pause(client, monkeypatch):
    _, saved, requests = await dispatch(client, [tool_stream(dict(action='status')), text_stream('Paused.')], monkeypatch,
        [dict(ok=True, state={**STATE, 'status': 'paused'})], message='Is it playing?')
    assert saved['content'] == 'Paused.' and len(requests) == 2


async def test_byo_adapter_also_uses_receipts_before_speech():
    class Fake(byok._ToolLoopProvider):
        def _history(self, messages): return []
        def _assistant_with_calls(self, text, calls): return {'role': 'assistant', 'calls': calls}
        def _tool_message(self, call, content): return {'role': 'tool', 'content': content}
        async def _round(self, client, messages, tools):
            if messages[-1]['role'] == 'tool': yield 'text', 'Swapped. Playing now.'
            else: yield 'call', {'id': 'one', 'name': pt.NAME, 'arguments': '{"action":"play"}'}
    provider = Fake(byok.choose('deepseek', 'deepseek-chat', None, 'sk-test-key', None))
    session = pt.PlayerSession(TEST_OWNER, 3)
    result = []
    async for item in service._stream_reply('Peto', [ChatMessage('user', 'Play')], 'low', provider=provider, player_session=session):
        if item.kind == 'player_command':
            pt.acknowledge(TEST_OWNER, item.info['id'], pt.Result(ok=False, error='Playback blocked.'))
        result.append(item)
    text = ''.join(item.text for item in result if item.kind == 'text')
    assert 'Playback blocked.' in text and 'Swapped' not in text
    assert pt.current.get() is None and not pt.pending
