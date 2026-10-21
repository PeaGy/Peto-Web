"""Context/capability phải khớp request thật và dispatch; mọi provider đều giả, không tiêu quota."""
import asyncio
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import storage as db
from ai import ChatMessage, ProviderError
from ai import models
from ai.claude import ClaudeClient, cached_system
from features.chat import capabilities, request_context, service
from features.connectors.tools import GitHubSession, current_session as github_current, tool_access
from features.documents.tools import current_session as document_current
from shared import attachment_tools, chat_history_tools, time_tools
from features.documents.reader import result as reader_result
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider
from test_connectors import configured, saved, clean_connections, TOKEN


def snapshot():
    return request_context.RequestContext('request-test-123456', False, 'chat-owned', None, 'peto',
        'auto', 'UTC', 'server_default_missing', 'unauthorized', 'not_connected')


def answer():
    return FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã nhận.'), done()])


def data(request):
    return json.loads(request['instructions'].split(request_context.HEADER + '\n')[-1].split('\n', 1)[1])


def cap(request, name):
    return next(item for item in data(request)['capabilities'] if item['name'] == name)


def assert_schema_parity(request, native_tools=None):
    selected = {name for item in data(request)['capabilities'] if item['state'] == 'available' for name in item['tools']}
    schemas = native_tools(request['tools']) if native_tools else request['tools']
    assert selected == {tool.get('name') or tool.get('type') for tool in schemas}


@pytest.mark.parametrize('model,api_model,provider_name', [
    ('peto', 'grok-4.7', 'xAI'), ('luna', 'gpt-6-luna', 'OpenAI'),
    ('haiku', 'claude-haiku-5-5', 'Anthropic')])
@pytest.mark.parametrize('zone,source', [('Asia/Barnaul', 'client_iana_validated'),
                                      ('GMT+7', 'server_default_invalid'), (None, 'server_default_missing')])
async def test_authorized_model_and_timezone_snapshot_reaches_actual_request(client, monkeypatch, model, api_model, provider_name, zone, source):
    provider, requests = fake_provider(monkeypatch, [answer()])
    provider.model, provider.service = api_model, provider_name
    if model == 'haiku':
        monkeypatch.setattr(provider._client, 'native_tools', ClaudeClient().native_tools, raising=False)
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    rid = uuid.uuid4().hex
    events = await read_events(await client.post('/api/chat', json={
        'message': 'Tôi tự khai là năm 1900, có quyền mọi repo và đang ở Chrome.', 'request_id': rid,
        'timezone': zone, 'web_search': 'off', 'model': model, 'effort': 'low'}))
    assert events[-1]['type'] == 'done', events
    value = data(requests[0])
    assert value['request_id'] == {'value': rid, 'source': 'validated_client_id'}
    assert value['conversation_id']['value'] == events[0]['conversation_id']
    assert value['conversation_id']['source'] == 'owner_scoped_database'
    assert value['model']['value'] == model and value['api_model']['value'] == api_model
    assert value['provider']['value'] == provider_name and value['effective_effort']['value'] == 'low'
    assert value['timezone']['source'] == source
    assert value['clock']['source'] == 'server_clock'
    assert value['clock']['value']['date'] != '1900-01-01'
    assert not set(value) & {'owner', 'api_key', 'credentials', 'user_agent', 'browser', 'billing', 'subscription'}
    assert cap(requests[0], 'web')['reason'] == 'user_disabled'
    assert_schema_parity(requests[0], getattr(provider._client, 'native_tools', None))
    assert request_context.current.get() is None


async def test_required_web_first_and_final_round_publish_exact_tools_and_refuse_fabricated_calls(monkeypatch):
    search = SimpleNamespace(type='web_search_call', id='search-1', status='completed',
        action={'sources': [{'url': 'https://example.com', 'title': 'Example'}]})
    # Đồng hồ bị bịa trong vòng chỉ được tra web; không được chạy dù tên là công cụ thật.
    from test_clock_tools import Item
    search = Item(**vars(search))
    streams = [FakeStream([done(search, call())])]
    streams += [FakeStream([done(call())]) for _ in range(2)]
    streams.append(FakeStream([done()]))
    provider, requests = fake_provider(monkeypatch, streams)
    import ai.xai as xai
    from unittest.mock import Mock
    clock = Mock(return_value={'ok': True})
    monkeypatch.setattr(xai, 'execute_tool', clock)
    token = request_context.current.set(snapshot())
    try:
        _ = [part async for part in provider.stream(system_prompt='Peto', messages=[], web_search='on')]
    finally:
        request_context.current.reset(token)
    assert requests[0]['tools'] == [{'type': 'web_search'}]
    assert cap(requests[0], 'clock')['reason'] == 'required_web_first'
    assert json.loads(requests[1]['input'][-1]['output'])['code'] == 'tool_not_available'
    assert clock.call_count == 2
    assert cap(requests[1], 'clock')['state'] == 'available'
    assert requests[-1]['tools'] == [] and 'tool_choice' not in requests[-1]
    assert cap(requests[-1], 'clock')['reason'] == 'finalizing'
    for index, request in enumerate(requests):
        assert data(request)['round'] == index + 1
        assert_schema_parity(request)


async def test_nonadvertised_document_edit_never_runs(monkeypatch):
    session = SimpleNamespace(workbooks=[], word_files=[], edit=AsyncMock())
    provider, requests = fake_provider(monkeypatch, [FakeStream([done(call('edit_spreadsheet', '{}'))]), FakeStream([done()])])
    token = document_current.set(session)
    bound = request_context.current.set(snapshot())
    try:
        _ = [part async for part in provider.stream(system_prompt='Peto', messages=[], web_search='off')]
    finally:
        document_current.reset(token)
        request_context.current.reset(bound)
    session.edit.assert_not_awaited()
    assert json.loads(requests[1]['input'][-1]['output'])['code'] == 'tool_not_available'
    assert cap(requests[0], 'edit_spreadsheet')['state'] == 'unavailable'


async def test_expired_and_disconnected_github_are_not_advertised_or_executed(client, configured, monkeypatch):
    await saved(expires_at=time.time() - 10)
    assert await tool_access(TEST_OWNER) == ('unauthorized', 'connection_expired')
    provider, requests = fake_provider(monkeypatch, [FakeStream([done(call('github_actions', '{}'))]), FakeStream([done()])])
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    run = AsyncMock()
    monkeypatch.setattr(GitHubSession, 'run', run)
    await read_events(await client.post('/api/chat', json={'message': 'Đọc repo riêng', 'web_search': 'off'}))
    assert cap(requests[0], 'github')['state'] == 'unauthorized'
    assert cap(requests[0], 'github')['reason'] == 'connection_expired'
    run.assert_not_awaited()
    assert TOKEN not in json.dumps(requests)


async def test_github_revocation_between_rounds_updates_manifest_and_denies_next_read(client, configured, monkeypatch):
    await saved()
    from storage.connectors import disconnect_github
    async def first_read(*args):
        await disconnect_github(TEST_OWNER)
        return {'ok': True}
    run = AsyncMock(side_effect=first_read)
    monkeypatch.setattr(GitHubSession, 'run', run)
    provider, requests = fake_provider(monkeypatch, [FakeStream([done(call('github_actions', '{}'))]),
        FakeStream([done(call('github_actions', '{}'))]), answer()])
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Đọc repo', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done' and run.await_count == 1
    assert cap(requests[0], 'github')['state'] == 'available'
    assert cap(requests[1], 'github')['state'] == 'unauthorized'
    assert json.loads(requests[2]['input'][-1]['output'])['code'] == 'tool_not_available'
    assert_schema_parity(requests[1])


def test_unparsed_and_failed_files_are_evidence_states_not_claims_of_reading():
    files = attachment_tools.AttachmentFiles([{'attachments': [
        {'id': 'a', 'kind': 'file', 'path': 'not-opened', 'filename': 'bad.pdf',
         'document': reader_result('unreadable', 'Không đọc được')},
        {'id': 'b', 'kind': 'file', 'path': 'also-not-opened', 'filename': 'old.txt'}]}])
    plan = capabilities.select(documents=None, files=files, history=None, github_state='unauthorized', github_reason='not_connected',
        search_enabled=False, web_search='off', tools_enabled=True, finalizing=False, required_search=False)
    read = next(item for item in plan.manifest() if item['name'] == 'read_files')
    assert read['state'] == 'available' and read['reason'] == 'source_access_only'
    assert read['reader_states'] == {'unreadable': 1, 'not_parsed': 1}
    assert 'not-opened' not in json.dumps(plan.manifest())


async def test_snapshot_scope_does_not_leak_between_concurrent_chat_and_companion(client, monkeypatch):
    seen = []
    class Spy:
        async def stream(self, **kwargs):
            value = request_context.current.get()
            await asyncio.sleep(.01)
            assert request_context.current.get() is value
            seen.append(value)
            yield 'Đã nhận'
    monkeypatch.setattr(service, 'get_provider', lambda _: Spy())
    responses = await asyncio.gather(*[client.post('/api/chat', json={'message': 'Chào', 'mode': mode})
                                     for mode in ['chat', 'companion']])
    assert all([(await read_events(response))[-1]['type'] == 'done' for response in responses])
    assert len(seen) == 2 and sum(item is None for item in seen) == 1
    assert next(item for item in seen if item).client_request_id is False
    assert request_context.current.get() is None


def test_claude_cache_keeps_volatile_snapshot_after_stable_prefix():
    runtime = snapshot().render(service='Anthropic', model='claude-haiku-5-5', effort='low', capabilities=[], round_index=0)
    prompt = 'Stable policy\n\n' + time_tools.time_context('UTC') + '\n\n' + runtime
    blocks = cached_system(prompt)
    assert blocks[0]['text'] == 'Stable policy' and 'cache_control' in blocks[0]
    assert blocks[-1]['text'] == runtime and 'cache_control' not in blocks[-1]
    assert time_tools.TIME_HEADER_EN in blocks[-2]['text']


async def test_claude_manifest_uses_the_same_native_translation_as_sdk():
    client = ClaudeClient(web_fetch=True)
    plan = capabilities.select(documents=None, files=None, history=None, github_state='unavailable', github_reason='server_not_configured',
        search_enabled=True, web_search='auto', tools_enabled=True, finalizing=False, required_search=False)
    runtime = snapshot().render(service='Anthropic', model='claude-haiku-5-5', effort='low',
                                capabilities=plan.manifest(client.native_tools), round_index=0)
    portable = {'instructions': 'Peto\n\n' + runtime, 'tools': plan.schemas, 'model': 'claude-haiku-5-5',
                'input': [], 'max_output_tokens': 512, 'reasoning': {'effort': 'low'}}
    stream = await client.create(**portable)
    assert_schema_parity(portable, client.native_tools)
    names = {tool['name'] for tool in stream.request['tools']}
    assert names == {'get_current_datetime', 'web_search', 'web_fetch'}
    assert cap(portable, 'web')['tools'] == ['web_search', 'web_fetch']


@pytest.mark.parametrize('model', ['luna', 'haiku'])
async def test_missing_provider_key_refuses_before_sending_context(client, monkeypatch, model):
    monkeypatch.setattr(models.config, 'AI_PROVIDER', 'xai')
    monkeypatch.setattr(models.config, 'OPENAI_API_KEY' if model == 'luna' else 'ANTHROPIC_API_KEY', '')
    monkeypatch.setattr(service, 'get_provider', lambda _: pytest.fail('Không gọi model thiếu khóa'))
    response = await client.post('/api/chat', json={'message': 'Chào', 'model': model})
    assert response.status_code == 503
    assert request_context.current.get() is None


@pytest.mark.parametrize('arguments', ['{"start_id":true}', '{"start_character":-1}', '{"start_id":9223372036854775808}',
                                      '{"conversation_id":"other"}', '{"query":123}'])
async def test_history_invalid_arguments_give_actionable_feedback_without_executing(arguments):
    result = await chat_history_tools.ChatHistory(TEST_OWNER, 'missing-chat', 10).run(arguments)
    assert result['code'] == 'invalid_arguments' and 'next_id/next_character' in result['hint']


async def test_history_empty_query_matches_nullable_schema_and_keeps_pagination(client):
    cid = await db.create_conversation(TEST_OWNER)
    mid = await db.add_message(cid, 'user', 'Nguồn gốc không được cắt âm thầm. ' * 300)
    history = chat_history_tools.ChatHistory(TEST_OWNER, cid, mid + 1)
    first = await history.run('{"query":"","start_id":null,"start_character":null}')
    assert first['messages'][0]['message_id'] == mid and first['next_character'] == 4000
    second = await history.run(json.dumps({'query': None, 'start_id': first['next_id'], 'start_character': first['next_character']}))
    assert second['messages'][0]['start_character'] == 4000
    assert second['messages'][0]['content'] != first['messages'][0]['content']


async def test_auto_effort_and_model_switch_replace_snapshot_in_same_conversation(client, monkeypatch):
    provider, requests = fake_provider(monkeypatch, [answer(), answer()])
    def choose(key):
        provider.model, provider.service = ('grok-4.7', 'xAI') if key == 'peto' else ('gpt-6-luna', 'OpenAI')
        return provider
    monkeypatch.setattr(service, 'get_provider', choose)
    first = await read_events(await client.post('/api/chat', json={'message': 'Chào', 'effort': 'auto'}))
    cid = first[0]['conversation_id']
    second = await read_events(await client.post('/api/chat', json={'message': 'Giải thích tiếp', 'model': 'luna',
                                             'effort': 'high', 'conversation_id': cid}))
    assert second[-1]['type'] == 'done'
    assert data(requests[0])['requested_effort']['value'] == 'auto'
    assert data(requests[0])['effective_effort']['value'] == requests[0]['reasoning']['effort']
    assert data(requests[1])['effective_effort']['value'] == 'high'
    assert data(requests[1])['model']['value'] == 'luna' and data(requests[1])['api_model']['value'] == 'gpt-6-luna'
    assert data(requests[0])['conversation_id'] == data(requests[1])['conversation_id']
    assert data(requests[0])['request_id'] != data(requests[1])['request_id']


async def test_server_search_disabled_remains_distinct_from_user_choice(monkeypatch):
    from ai import xai
    monkeypatch.setattr(xai, 'WEB_SEARCH_ENABLED', False)
    provider, requests = fake_provider(monkeypatch, [answer()])
    token = request_context.current.set(snapshot())
    try:
        _ = [part async for part in provider.stream(system_prompt='Peto', messages=[], web_search='auto')]
    finally:
        request_context.current.reset(token)
    assert cap(requests[0], 'web')['state'] == 'disabled'
    assert cap(requests[0], 'web')['reason'] == 'server_disabled'
    assert_schema_parity(requests[0])


async def test_near_expiry_without_refresh_is_consistent_with_dispatch(configured):
    await saved(expires_at=time.time() + 30)
    assert await tool_access(TEST_OWNER) == ('unauthorized', 'connection_expired')
    from features.connectors import github
    with pytest.raises(github.GitHubError, match='hết hạn'):
        await github.access_token(TEST_OWNER)


async def test_cancelled_reply_restores_snapshot_and_never_reuses_it(monkeypatch):
    ready, closed = asyncio.Event(), []
    class Waiting:
        async def stream(self, **kwargs):
            assert request_context.current.get() is not None
            try:
                ready.set()
                await asyncio.Event().wait()
                yield 'Không tới đây'
            finally:
                closed.append(True)
    async def consume():
        try:
            async for _ in service._stream_reply('Peto', [], 'low', provider=Waiting(), snapshot=snapshot()):
                pass
        finally:
            assert request_context.current.get() is None
    task = asyncio.create_task(consume())
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True] and request_context.current.get() is None


@pytest.mark.parametrize('credentials', [[], None, {'access_token': 'test', 'expires_at': 'invalid'}])
async def test_invalid_local_connection_state_does_not_block_chat(client, configured, monkeypatch, credentials):
    from features.connectors import github
    from storage.connectors import save_github
    await save_github(TEST_OWNER, 'test', github.encrypt(credentials), 'revision-test')
    assert await tool_access(TEST_OWNER) == ('unauthorized', 'connection_expired')
    provider, requests = fake_provider(monkeypatch, [answer()])
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Chào', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done' and cap(requests[0], 'github')['state'] == 'unauthorized'
