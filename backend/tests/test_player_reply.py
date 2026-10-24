"""False confirmations must never reach UI/speech, even when the fake model insists success."""
import asyncio
import json
from contextlib import aclosing
from copy import deepcopy
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


APPROVED = '{"supported":true,"reason":""}'
REJECTED = '{"supported":false,"reason":"Draft contradicts the execution result."}'


async def dispatch(client, streams, monkeypatch, replies=(), message='Replace the current song.', *, checks=(), rewrites=(), version=3):
    provider, requests = fake_provider(monkeypatch, streams)
    create = provider._client.responses.create
    pending = {'PLAYER REPLY FACT CHECK': list(checks), 'PLAYER REPLY REVISION': list(rewrites)}
    unexpected = []
    async def checked_create(**kwargs):
        for marker, values in pending.items():
            if marker in kwargs['instructions']:
                requests.append(deepcopy(kwargs))
                if pt.current.get() is not None or kwargs.get('tools'):
                    unexpected.append('Side call has access to tools or Player context')
                if not values:
                    unexpected.append(f'Unexpected {marker} call')
                    raise AssertionError(unexpected[-1])
                return text_stream(values.pop(0))
        return await create(**kwargs)
    monkeypatch.setattr(provider._client.responses, 'create', checked_create)
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    task = asyncio.create_task(client.post('/api/chat', json=dict(mode='companion', message=message, player_control=version, web_search='off')))
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
        assert not unexpected and not any(pending.values()), (unexpected, pending)
        return events, saved, requests
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_no_call_false_swap_is_repaired_once_and_only_confirmed_track_is_spoken(client, monkeypatch):
    natural = 'There we go—Tetris is on now. Settle in.'
    events, saved, requests = await dispatch(client, [text_stream('Swapped. Hallucinated song is playing.'),
        tool_stream(dict(action='play')), text_stream('<|EMOTE_HAPPY|> Swapped. Another invented song.')], monkeypatch,
        [dict(ok=True, state=STATE)], checks=[REJECTED, APPROVED], rewrites=['<|EMOTE_HAPPY|> ' + natural])
    text = ''.join(event.get('text', '') for event in events if event['type'] == 'delta')
    assert 'Tetris' in text and 'Hallucinated' not in text and 'invented' not in text and 'Swapped' not in text
    assert saved['content'] == text == natural
    assert saved['emotion'] == 'happy'
    assert len(requests) == 6 and 'PLAYER EXECUTION CHECK' in requests[1]['instructions']
    assert saved['player_trace']['reply_guard'] == 'natural_rewritten'
    assert saved['player_trace']['commands'][0]['action'] == 'play'
    assert saved['player_trace']['commands'][0]['ok'] is True
    assert 'work' not in saved


@pytest.mark.parametrize('reply', [dict(ok=False, error='YouTube cannot play this video. (150)'),
                                  dict(ok=False, error='Acknowledgement lost; outcome unknown.')])
async def test_failed_action_cannot_be_overridden_by_success_text_or_automatically_replayed(client, monkeypatch, reply):
    events, saved, requests = await dispatch(client, [tool_stream(dict(action='play')),
        text_stream('Swapped. The requested song is playing now.')], monkeypatch, [reply],
        checks=[REJECTED, APPROVED], rewrites=["That didn't go through. Player reported: " + reply['error']])
    text = ''.join(event.get('text', '') for event in events if event['type'] == 'delta')
    assert 'Swapped' not in text and 'playing now' not in text and reply['error'] in text
    assert len(requests) == 5
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
        text_stream('Swapped.')], monkeypatch, [dict(ok=False, error='YouTube 150')],
        checks=[REJECTED, APPROVED], rewrites=["It didn't switch; Player reported YouTube 150."])
    commands = saved['player_trace']['commands']
    assert [item['sent'] for item in commands] == [True, False]
    assert not any(item['ok'] for item in commands)
    assert len([event for event in events if event['type'] == 'player_command']) == 1
    assert 'Swapped' not in saved['content']


async def test_native_video_mismatch_does_not_become_success_receipt(client, monkeypatch):
    result = dict(ok=True, state={**STATE, 'native_video_id': 'aircAruvnKk', 'native_state': 1})
    _, saved, _ = await dispatch(client, [tool_stream(dict(action='play')), text_stream('Swapped.')], monkeypatch, [result],
        checks=[REJECTED, APPROVED], rewrites=['Player does not confirm that the requested video started.'])
    assert saved['player_trace']['commands'][0]['ok'] is False
    assert 'does not confirm' in saved['content']


async def test_ordinary_companion_reply_needs_no_extra_ai_call(client, monkeypatch):
    events, saved, requests = await dispatch(client, [text_stream('Long day? Want some relaxing music?')], monkeypatch, message="I'm tired.")
    assert saved['content'] == 'Long day? Want some relaxing music?'
    assert len(requests) == 1 and 'player_trace' not in saved


async def test_receipt_history_is_available_for_followup_without_replaying_commands(client, monkeypatch):
    _, _, _ = await dispatch(client, [tool_stream(dict(action='play')), text_stream('Swapped.')], monkeypatch,
        [dict(ok=False, error='YouTube 150')], checks=[REJECTED, APPROVED], rewrites=["It didn't switch. YouTube 150."])
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
        checks = 0
        rewrites = 0
        def _history(self, messages): return []
        def _assistant_with_calls(self, text, calls): return {'role': 'assistant', 'calls': calls}
        def _tool_message(self, call, content): return {'role': 'tool', 'content': content}
        async def _round(self, client, messages, tools):
            if 'PLAYER REPLY FACT CHECK' in messages[0]['content']:
                assert not tools and pt.current.get() is None
                self.checks += 1
                yield 'text', REJECTED if self.checks == 1 else APPROVED
            elif 'PLAYER REPLY REVISION' in messages[0]['content']:
                assert not tools and pt.current.get() is None
                self.rewrites += 1
                yield 'text', "No luck yet—Player reported Playback blocked. Want to try another one?"
            elif messages[-1]['role'] == 'tool': yield 'text', 'Swapped. Playing now.'
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
    assert text == 'No luck yet—Player reported Playback blocked. Want to try another one?'
    assert provider.checks == 2 and provider.rewrites == 1
    assert pt.current.get() is None and not pt.pending


@pytest.mark.parametrize('natural', [
    '<|EMOTE_HAPPY|> There we go. Much better for winding down, huh?',
    "All yours—Tetris is on. I'll keep you company.",
    '<|EMOTE_HAPPY|> Xong rồi nè, cứ thả lỏng một chút nhé.',
    'Đổi sang Tetris rồi nhé. Hôm nay mình nghe bài này cùng nhau đi.',
])
async def test_supported_natural_wording_is_preserved_without_rewrite(client, monkeypatch, natural):
    events, saved, requests = await dispatch(client,
        [tool_stream(dict(action='play')), text_stream(natural)], monkeypatch,
        [dict(ok=True, state=STATE)], checks=[APPROVED])
    assert saved['content'] == guard.visible(natural)
    assert saved['player_trace']['reply_guard'] == 'natural_verified'
    assert len(requests) == 3 and sum(e['type'] == 'player_command' for e in events) == 1
    check_data = json.loads(requests[-1]['input'][0]['content'][0]['text'])
    assert check_data['draft'] == guard.visible(natural)
    assert check_data['execution'][0]['state']['track']['title'] == 'Tetris'


async def test_honest_natural_failure_is_preserved(client, monkeypatch):
    natural = "That one wouldn't start. Player reported YouTube 150; I don't know more than that yet."
    _, saved, requests = await dispatch(client,
        [tool_stream(dict(action='play')), text_stream(natural)], monkeypatch,
        [dict(ok=False, error='YouTube 150')], checks=[APPROVED])
    assert saved['content'] == natural and len(requests) == 3
    assert saved['player_trace']['reply_guard'] == 'natural_verified'


async def test_partial_success_is_corrected_without_replaying_either_action(client, monkeypatch):
    natural = "Player's open, but the song didn't start—YouTube reported 150."
    events, saved, requests = await dispatch(client,
        [tool_stream(dict(action='open')), tool_stream(dict(action='play')), text_stream('All set, your song is playing!')],
        monkeypatch, [dict(ok=True, state={**STATE, 'window': 'visible'}), dict(ok=False, error='YouTube 150')],
        checks=[REJECTED, APPROVED], rewrites=[natural])
    assert saved['content'] == natural and len(requests) == 6
    assert [e['command']['action'] for e in events if e['type'] == 'player_command'] == ['open', 'play']


@pytest.mark.parametrize('invalid', ['not JSON', '{"supported":"true"}', '{"supported":true,"extra":"bad"}'])
async def test_invalid_checker_output_uses_receipt_fallback_without_executing_again(client, monkeypatch, invalid):
    events, saved, requests = await dispatch(client,
        [tool_stream(dict(action='play')), text_stream('Swapped. Made up title.')], monkeypatch,
        [dict(ok=True, state=STATE)], checks=[invalid])
    assert saved['content'] == 'Playing “Tetris”.' and len(requests) == 3
    assert saved['player_trace']['reply_guard'] == 'receipt_fallback_check_unavailable'
    assert sum(e['type'] == 'player_command' for e in events) == 1


async def test_failed_action_brake_overrides_mistaken_checker_approval(client, monkeypatch):
    natural = "It didn't switch. Player reported Playback blocked."
    events, saved, requests = await dispatch(client,
        [tool_stream(dict(action='play')), text_stream('Swapped.')], monkeypatch,
        [dict(ok=False, error='Playback blocked.')], checks=[APPROVED, APPROVED], rewrites=[natural])
    assert saved['content'] == natural and len(requests) == 5
    assert sum(e['type'] == 'player_command' for e in events) == 1


async def test_unsupported_rewrite_falls_back_once_and_never_loops(client, monkeypatch):
    events, saved, requests = await dispatch(client,
        [tool_stream(dict(action='play')), text_stream('Playing an invented song.')], monkeypatch,
        [dict(ok=True, state=STATE)], checks=[REJECTED, REJECTED], rewrites=['Still an invented song.'])
    assert saved['content'] == 'Playing “Tetris”.' and len(requests) == 5
    assert saved['player_trace']['reply_guard'] == 'receipt_fallback_unsupported'
    assert sum(e['type'] == 'player_command' for e in events) == 1


def test_checker_gets_full_counts_and_observations_without_expanding_saved_trace():
    session = pt.PlayerSession(TEST_OWNER, 3)
    session.receipts = [dict(action='enqueue_favorites', sent=True, result=dict(ok=True,
        data=dict(added=2, skipped_duplicates=3, not_added_capacity=1))),
        dict(action='list_queue', sent=True, result=dict(ok=True, data=dict(items=[STATE['track']])))]
    data = guard.check_data(session, [ChatMessage('user', 'Add favorites; what is next?')], 'Added all six!')
    assert data['execution'][0]['data']['skipped_duplicates'] == 3
    assert data['execution'][1]['data']['items'][0]['title'] == 'Tetris'
    assert 'items' not in session.trace()['commands'][1]['data']


@pytest.mark.parametrize('failure', ['timeout', 'network', 'command'])
async def test_checker_failure_is_bounded_and_restores_context(monkeypatch, failure):
    class FailedCheck:
        calls = 0
        closed = False
        async def stream(self, **kwargs):
            self.calls += 1
            assert kwargs['tools_enabled'] is False and kwargs['web_search'] == 'off'
            assert pt.current.get() is None
            try:
                if failure == 'timeout': await asyncio.Event().wait()
                if failure == 'network': raise ConnectionError('private error details')
                yield StreamChunk('player_command', info={'id': 'must-not-be-forwarded'})
            finally:
                self.closed = True
    provider = FailedCheck()
    monkeypatch.setattr(guard, 'CHECK_TIMEOUT', .01)
    session = pt.PlayerSession(TEST_OWNER, 3)
    session.receipts = [dict(action='play', sent=True, result=dict(ok=True, state=STATE))]
    token = pt.current.set(session)
    try:
        text = await guard.natural_confirmation(provider, session, [], 'Swapped.', {'system_prompt': 'Peto'})
        assert text == 'Playing “Tetris”.' and provider.calls == 1 and provider.closed
        assert pt.current.get() is session and not pt.pending
    finally:
        pt.current.reset(token)


async def test_cancelling_check_closes_side_stream_without_fallback_or_replay():
    entered, closed = asyncio.Event(), asyncio.Event()
    class Check:
        async def stream(self, **kwargs):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield APPROVED
            finally:
                closed.set()
    session = pt.PlayerSession(TEST_OWNER, 3)
    token = pt.current.set(session)
    try:
        task = asyncio.create_task(guard.side_reply(Check(), guard.CHECK_PROMPT, {}, 'player_check'))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert closed.is_set() and pt.current.get() is session and not pt.pending
    finally:
        pt.current.reset(token)


@pytest.mark.parametrize('cancel', [False, True])
async def test_text_and_speech_input_wait_for_fact_check_even_after_browser_success(monkeypatch, cancel):
    entered, release = asyncio.Event(), asyncio.Event()
    natural = "There we go, Tetris is on. Take a breather."
    provider, requests = fake_provider(monkeypatch, [tool_stream(dict(action='play')), text_stream(natural)])
    create = provider._client.responses.create
    async def checked_create(**kwargs):
        if 'PLAYER REPLY FACT CHECK' in kwargs['instructions']:
            assert pt.current.get() is None and not kwargs.get('tools')
            entered.set()
            await release.wait()
            return text_stream(APPROVED)
        return await create(**kwargs)
    monkeypatch.setattr(provider._client.responses, 'create', checked_create)
    session = pt.PlayerSession(TEST_OWNER, 3)
    chunks = []
    async def collect():
        async for chunk in service._stream_reply('Peto', [ChatMessage('user', 'Play please.')], 'low',
                provider=provider, player_session=session):
            chunks.append(chunk)
            if chunk.kind == 'player_command':
                assert pt.acknowledge(TEST_OWNER, chunk.info['id'], pt.Result(ok=True, state=pt.Snapshot(**STATE)))
    task = asyncio.create_task(collect())
    try:
        async with asyncio.timeout(5): await entered.wait()
        assert session.receipts[0]['result']['ok'] is True
        assert not [chunk for chunk in chunks if chunk.kind == 'text']
        assert len([chunk for chunk in chunks if chunk.kind == 'player_command']) == 1
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert not [chunk for chunk in chunks if chunk.kind == 'text']
        else:
            release.set()
            await task
            assert ''.join(chunk.text for chunk in chunks if chunk.kind == 'text') == natural
            assert session.reply_guard == 'natural_verified'
        assert len(requests) == 2 and not pt.pending and pt.current.get() is None
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)
