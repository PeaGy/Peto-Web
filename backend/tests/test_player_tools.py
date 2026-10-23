"""Player actions: native provider loop, sending-client results and owner/turn lifecycle. No paid calls."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ai.base import ChatMessage, StreamChunk
from ai import byok
from features.chat import capabilities, service
from features.companion import player_tools as pt
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider

STATE = dict(window='hidden', status='playing', track=dict(video_id='Soy4jGPHr3g', title='Tetris', artist='Kasane Teto'),
             position=12, duration=143, volume=30, shuffle=False, repeat='off', queue_count=2)


@pytest.mark.parametrize('value', [
    {'action': 'set_volume', 'volume': -1}, {'action': 'set_volume', 'volume': 101},
    {'action': 'set_volume', 'volume': True}, {'action': 'set_volume'},
    {'action': 'seek', 'seconds': float('nan')}, {'action': 'seek', 'seconds': -1},
    {'action': 'set_shuffle', 'enabled': 'true'}, {'action': 'set_repeat', 'repeat': 'queue'},
    {'action': 'status', 'volume': 50}, {'action': 'search', 'query': 'Tetris'},
    {'action': 'list_favorites', 'offset': -1}, {'action': 'list_queue', 'limit': 51},
    {'action': 'remove_queue_entry', 'entry_id': 'q1'}, {'action': 'remove_queue_entry', 'entry_id': 'q1', 'queue_revision': True},
    {'action': 'move_queue_entry', 'entry_id': 'q1', 'queue_revision': 1, 'position': 0},
    {'action': 'set_favorite'}, {'action': 'enqueue_favorite', 'video_id': 'not a video'},
    {'action': 'enqueue_favorites', 'entry_id': 'q1'},
])
def test_rejects_invalid_or_future_stage_actions(value):
    with pytest.raises(ValidationError):
        pt.Command.model_validate(value)


async def test_invalid_arguments_never_send_browser_command():
    assert [item async for item in pt.PlayerSession(TEST_OWNER).run('{"action":"seek"}')][0]['ok'] is False
    assert not pt.pending


async def test_legacy_browser_never_gets_library_actions_or_new_schema_fields():
    old = pt.PlayerSession(TEST_OWNER)
    new = pt.PlayerSession(TEST_OWNER, 2)
    assert 'list_queue' not in old.schema['parameters']['properties']['action']['enum']
    assert 'entry_id' not in old.schema['parameters']['properties']
    assert 'list_queue' in new.schema['parameters']['properties']['action']['enum']
    assert [item async for item in old.run('{"action":"list_favorites"}')][0]['ok'] is False
    assert not pt.pending


async def test_library_results_are_bounded_and_sent_back_to_provider(client):
    stream = pt.PlayerSession(TEST_OWNER, 2).run('{"action":"list_queue","limit":50}')
    key = (await anext(stream)).info['id']
    item = dict(**STATE['track'], index=1, entry_id='queued-1')
    endpoint = f'/api/companion/player/commands/{key}/result'
    data = dict(kind='queue', total=200, offset=0, queue_revision=12, items=[item] * 51)
    assert (await client.post(endpoint, json={'ok': True, 'state': STATE, 'data': data})).status_code == 422
    data['items'] = [item]
    assert (await client.post(endpoint, json={'ok': True, 'state': STATE, 'data': data})).status_code == 200
    result = await anext(stream)
    assert result['data']['queue_revision'] == 12 and result['data']['items'][0]['entry_id'] == 'queued-1'
    await stream.aclose()


async def test_native_library_read_then_remove_preserves_identity_and_revision(client, monkeypatch):
    read = call(pt.NAME, '{"action":"list_queue","offset":2,"limit":1}')
    remove = call(pt.NAME, '{"action":"remove_queue_entry","entry_id":"queued-third","queue_revision":7}')
    streams = [FakeStream([SimpleNamespace(type='response.output_item.done', item=item), done(item)]) for item in (read, remove)]
    streams.append(FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Removed the third queued song.'), done()]))
    provider, requests = fake_provider(monkeypatch, streams)
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    task = asyncio.create_task(client.post('/api/chat', json={'mode': 'companion', 'message': 'Remove third queued song.', 'player_control': 2, 'web_search': 'off'}))
    responses = [dict(kind='queue', total=3, offset=2, queue_revision=7, items=[{**STATE['track'], 'index': 3, 'entry_id': 'queued-third'}]),
                 dict(kind='mutation', target=STATE['track'], queue_revision=8)]
    try:
        seen = set()
        for data in responses:
            async with asyncio.timeout(5):
                while not (keys := set(pt.pending) - seen): await asyncio.sleep(.01)
            key = keys.pop(); seen.add(key)
            assert (await client.post(f'/api/companion/player/commands/{key}/result', json={'ok': True, 'state': STATE, 'data': data})).status_code == 200
        events = await read_events(await task)
        assert events[-1]['type'] == 'done'
        schema = next(schema for schema in requests[0]['tools'] if schema.get('name') == pt.NAME)
        assert 'list_queue' in schema['parameters']['properties']['action']['enum']
        assert 'entry_id/queue_revision' in requests[0]['instructions']
        assert json.loads(requests[1]['input'][-1]['output'])['data']['items'][0]['entry_id'] == 'queued-third'
        assert json.loads(requests[2]['input'][-1]['output'])['data']['queue_revision'] == 8
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_strict_native_schema_accepts_unused_nulls_and_validates_required_value():
    empty = {'action': 'status', 'volume': None, 'seconds': None, 'enabled': None, 'repeat': None}
    assert pt.Command.model_validate(empty).action == 'status'
    assert set(pt.SCHEMA['parameters']['required']) == set(pt.SCHEMA['parameters']['properties'])
    assert pt.Command.model_validate({**empty, 'action': 'set_shuffle', 'enabled': False}).enabled is False
    with pytest.raises(ValidationError): pt.Command.model_validate({**empty, 'action': 'seek'})


async def test_ack_is_owner_scoped_one_use_and_requires_state(client, anon_client):
    stream = pt.PlayerSession(TEST_OWNER).run('{"action":"status"}')
    command = (await anext(stream)).info
    key = command['id']
    endpoint = f'/api/companion/player/commands/{key}/result'
    assert (await anon_client.post(endpoint, json={'ok': True, 'state': STATE})).status_code == 401
    assert not pt.acknowledge('different-owner', key, pt.Result(ok=True, state=pt.Snapshot(**STATE)))
    assert (await client.post(endpoint, json={'ok': True, 'state': {**STATE, 'volume': 200}})).status_code == 422
    assert (await client.post(endpoint, json={'ok': True})).status_code == 200
    result = await anext(stream)
    assert result['ok'] is False and 'unconfirmed' in result['error']
    assert (await client.post(endpoint, json={'ok': True, 'state': STATE})).status_code == 404
    await stream.aclose()
    assert key not in pt.pending


async def test_timeout_and_cancellation_remove_pending_and_never_replay(monkeypatch):
    monkeypatch.setattr(pt, 'ACK_TIMEOUT', .01)
    stream = pt.PlayerSession(TEST_OWNER).run('{"action":"next"}')
    key = (await anext(stream)).info['id']
    result = await anext(stream)
    assert result['ok'] is False and 'unknown' in result['error']
    await stream.aclose()
    assert key not in pt.pending
    assert not pt.acknowledge(TEST_OWNER, key, pt.Result(ok=True, state=pt.Snapshot(**STATE)))
    stream = pt.PlayerSession(TEST_OWNER).run('{"action":"next"}')
    key = (await anext(stream)).info['id']
    await stream.aclose()
    assert key not in pt.pending


async def test_closing_native_provider_while_browser_is_pending_cleans_command_immediately(monkeypatch):
    tool = call(pt.NAME, '{"action":"next"}')
    provider, _ = fake_provider(monkeypatch, [FakeStream([SimpleNamespace(type='response.output_item.done', item=tool), done(tool)])])
    token = pt.current.set(pt.PlayerSession(TEST_OWNER))
    stream = provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Next')], web_search='off')
    try:
        async for item in stream:
            if isinstance(item, StreamChunk) and item.kind == 'player_command':
                break
        assert pt.pending
        await stream.aclose()
        assert not pt.pending
    finally:
        await stream.aclose()
        pt.current.reset(token)


@pytest.mark.parametrize('ok', [True, False])
async def test_native_ai_waits_for_observed_result_before_final_text(client, monkeypatch, ok):
    tool = call(pt.NAME, '{"action":"pause"}')
    first = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Unconfirmed draft.'),
                        SimpleNamespace(type='response.output_item.done', item=tool), done(tool)])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Observed result.'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    monkeypatch.setattr(service, 'get_provider', lambda *args: provider)
    request = asyncio.create_task(client.post('/api/chat', json={
        'mode': 'companion', 'message': 'Pause please.', 'player_control': 1, 'web_search': 'off'}))
    try:
        async with asyncio.timeout(5):
            while not pt.pending:
                await asyncio.sleep(.01)
        key = next(iter(pt.pending))
        assert len(requests) == 1 and not request.done()
        result = {'ok': ok, 'state': {**STATE, 'status': 'paused'}} if ok else {'ok': False, 'error': 'Browser blocked playback.'}
        assert (await client.post(f'/api/companion/player/commands/{key}/result', json=result)).status_code == 200
        events = await read_events(await request)
        assert events[-1]['type'] == 'done'
        assert next(e for e in events if e['type'] == 'player_command')['command']['id'] == key
        assert any(e['type'] == 'replace' for e in events)
        assert json.loads(requests[1]['input'][-1]['output']) == result
        assert any(s.get('name') == pt.NAME for s in requests[0]['tools'])
        assert 'PLAYER' in requests[0]['instructions']
        text = ''.join(e.get('text', '') for e in events if e['type'] == 'delta')
        assert 'Unconfirmed draft' not in text
        assert ('Browser blocked' in text) is not ok
        assert not pt.pending and pt.current.get() is None
    finally:
        if not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)


async def test_scope_not_in_web_chat_old_companion_or_side_calls(client, monkeypatch):
    seen = []
    class Spy:
        async def stream(self, **kwargs):
            seen.append(pt.current.get())
            yield 'Hello.'
    monkeypatch.setattr(service, 'get_provider', lambda *args: Spy())
    assert (await client.post('/api/chat', json={'message': 'Hi', 'player_control': 1})).status_code == 400
    await client.post('/api/chat', json={'message': 'Hi', 'mode': 'companion'})
    assert seen and all(session is None for session in seen)


async def test_gemini_does_not_claim_unimplemented_player_capability(client, monkeypatch):
    seen = []
    class Spy:
        async def stream(self, **kwargs):
            seen.append(kwargs['system_prompt'])
            assert pt.current.get() is None
            yield 'Player control unavailable here.'
    monkeypatch.setattr(byok, 'build', lambda *args: Spy())
    response = await client.post('/api/chat', json={'message': 'Pause', 'mode': 'companion', 'player_control': 1,
        'provider': {'id': 'gemini', 'model': 'gemini-test'}}, headers={'X-Peto-Provider-Key': 'test-gemini-key'})
    assert response.status_code == 200
    assert seen and 'Player control is unavailable' in seen[0]


def test_tool_plan_and_byok_only_advertise_in_current_companion_context():
    args = dict(documents=None, files=None, history=None, github_state='unavailable', github_reason='chat_only',
                search_enabled=False, web_search='off', tools_enabled=True, finalizing=False, required_search=False)
    assert not capabilities.select(**args).allows(pt.NAME)
    assert not any(t['function']['name'] == pt.NAME for t in byok._function_tools(False))
    token = pt.current.set(pt.PlayerSession(TEST_OWNER))
    try:
        assert capabilities.select(**args).allows(pt.NAME)
        assert not capabilities.select(**{**args, 'finalizing': True}).allows(pt.NAME)
        assert not capabilities.select(**{**args, 'tools_enabled': False}).allows(pt.NAME)
        assert any(t['function']['name'] == pt.NAME for t in byok._function_tools(False))
    finally:
        pt.current.reset(token)


async def test_byok_tool_loop_receives_player_failure_before_reply():
    class Fake(byok._ToolLoopProvider):
        def _history(self, messages): return []
        def _assistant_with_calls(self, text, calls): return {'role': 'assistant', 'calls': calls}
        def _tool_message(self, call, content): return {'role': 'tool', 'content': content}
        async def _round(self, client, messages, tools):
            if messages[-1]['role'] == 'tool':
                assert json.loads(messages[-1]['content'])['ok'] is False
                yield 'text', 'Could not play.'
            else:
                yield 'call', {'id': '1', 'name': pt.NAME, 'arguments': '{"action":"play"}'}
    choice = byok.choose('deepseek', 'deepseek-chat', None, 'sk-test-12345678', None)
    token = pt.current.set(pt.PlayerSession(TEST_OWNER))
    try:
        result = []
        async for item in Fake(choice).stream(system_prompt='Peto', messages=[ChatMessage('user', 'play')], web_search='off'):
            if isinstance(item, StreamChunk) and item.kind == 'player_command':
                pt.acknowledge(TEST_OWNER, item.info['id'], pt.Result(ok=False, error='No video.'))
            result.append(item)
        assert 'Could not play.' in result
    finally:
        pt.current.reset(token)
