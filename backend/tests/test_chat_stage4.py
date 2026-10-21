"""Bằng chứng nguồn, phép đo và phục hồi đúng lượt; chỉ SQLite/stream giả, không AI thật."""
import asyncio
import json
from types import SimpleNamespace

import pytest
import storage as db
from storage import chat_turns
from core import config, usage_events
from features.admin import stats
from features.chat import context, context_budget, request_context, service
from shared.web_search import normalize_sources
from ai import xai, StreamChunk
from conftest import TEST_OWNER, OTHER_DISCORD_ID, read_events
from test_admin import clear_events, stored_rows, row, local, ZONE, RATES
from test_chat_context import conversation, summary_value
from test_chat_recovery import bound
from test_clock_tools import FakeStream, Item, call, done, fake_provider


def test_stage4_quality_fixtures_use_existing_bounded_eval_schema():
    from pathlib import Path
    from evals.schema import load_cases, Settings
    cases = load_cases(Path(__file__).parents[1] / 'evals' / 'chat-stage4-cases.json')
    assert len(cases) == 4 and all(case.persona == 'chat' for case in cases)
    assert Settings(models=('peto', 'luna', 'haiku'), max_calls=15).validate(cases) == 15


@pytest.fixture
def recorder():
    usage_events.enable()
    yield usage_events
    usage_events.disable()


def test_source_access_upgrades_only_from_observed_evidence_and_bad_metadata_falls_back():
    url = 'https://example.com/article'
    result = normalize_sources([None, {'url': 'javascript:bad'}, {'url': url, 'kind': [], 'access': {}},
        {'url': url, 'kind': 'citation', 'access': 'search'}, {'url': url, 'access': 'tool', 'partial': True},
        {'url': url, 'access': 'page'}, {'url': url, 'access': 'search'}])
    assert result == [{'url': url, 'title': 'example.com', 'kind': 'citation', 'access': 'page', 'partial': True}]


@pytest.mark.parametrize('status,access', [('completed', 'page'), ('in_progress', 'search'), ('failed', None)])
def test_native_fetch_requires_completed_result(status, access):
    source = {'url': 'https://example.com/a', 'title': 'A'}
    item = {'type': 'web_search_call', 'status': status, 'action': {'type': 'fetch', 'sources': [source]}}
    result = xai._item_sources(item)
    assert result == ([{**source, 'kind': 'result', 'access': access}] if access else [])
    # Chỉ có native citation không chứng minh đã mở trang.
    cited = xai._item_sources({'type': 'message', 'content': [{'type': 'output_text',
        'annotations': [{'type': 'url_citation', **source}]}]})
    assert cited == [{**source, 'kind': 'citation'}]


@pytest.mark.parametrize('action', ['open_page', 'find_in_page'])
async def test_openai_page_actions_use_actual_url_and_only_completed_evidence(monkeypatch, action):
    url = 'https://example.com/opened'
    opened = Item(type='web_search_call', id='page-1', status='completed', action={'type': action, 'url': url})
    assert xai._item_sources({**vars(opened), 'status': 'in_progress'}) == []
    cited = Item(type='message', content=[{'type': 'output_text', 'annotations': [
        {'type': 'url_citation', 'url': url, 'title': 'Tiêu đề từ citation'}]}])
    provider, _ = fake_provider(monkeypatch, [FakeStream([done(opened, cited)])])
    chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[])]
    source_events = [chunk.sources for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == 'sources']
    assert source_events[-1] == ({'url': url, 'title': 'Tiêu đề từ citation', 'kind': 'citation', 'access': 'page'},)
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == 'page' and chunk.text == 'fetched' for chunk in chunks)


async def test_source_provenance_survives_checkpoint_and_reload(client, monkeypatch):
    class Provider:
        async def stream(self, **kwargs):
            yield StreamChunk('sources', sources=(
                {'url': 'https://youtu.be/demo', 'title': 'Video', 'kind': 'result', 'access': 'search'},
                {'url': 'https://example.com/page', 'title': 'Page', 'kind': 'result', 'access': 'page'},
                {'url': 'https://github.com/test/repo', 'title': 'Repo', 'kind': 'result', 'access': 'tool', 'partial': True}))
            yield 'Chỉ dùng bằng chứng được trả về.'
    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    events = await read_events(await client.post('/api/chat', json={'message': 'Đối chiếu nguồn'}))
    cid = events[0]['conversation_id']
    sources = (await client.get(f'/api/conversations/{cid}/messages')).json()['messages'][-1]['sources']
    assert [item['access'] for item in sources] == ['search', 'page', 'tool']
    assert sources[-1]['partial'] is True


async def test_github_excerpt_is_tool_evidence_and_never_promoted_to_opened_page(monkeypatch):
    from features.connectors.tools import GitHubSession, current_session
    from test_chat_request_context import snapshot
    url = 'https://github.com/test/repo/blob/HEAD/file.py'
    class Excerpt(GitHubSession):
        async def availability(self):
            return 'available', 'connected'
        async def run(self, name, arguments):
            return {'ok': True, 'text': 'excerpt', 'truncated': True, 'sources': [{'url': url, 'title': 'file.py'}]}
    provider, _ = fake_provider(monkeypatch, [FakeStream([done(call('github_read_repository', '{}'))]), FakeStream([done()])])
    token = current_session.set(Excerpt(TEST_OWNER))
    scope = request_context.current.set(snapshot())
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[])]
    finally:
        current_session.reset(token)
        request_context.current.reset(scope)
    sources = [chunk.sources for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == 'sources']
    assert sources[-1] == ({'url': url, 'title': 'file.py', 'kind': 'result', 'access': 'tool', 'partial': True},)


async def test_measurement_context_is_task_local_and_reset_after_cancellation(recorder):
    await clear_events()
    ready, release = asyncio.Event(), asyncio.Event()
    async def worker():
        with usage_events.measurement(surface='chat', effort='low', purpose='summary'):
            ready.set()
            try:
                await release.wait()
            finally:
                recorder.record('call', service='openai', purpose='side')
    task = asyncio.create_task(worker())
    await ready.wait()
    with usage_events.measurement(surface='agent', effort='high'):
        recorder.record('call', service='openai', purpose='chat')
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    recorder.record('call', service='openai', purpose='side')
    await recorder.flush()
    rows = await stored_rows()
    assert [(r['surface'], r['effort'], r['purpose']) for r in rows] == [
        ('agent', 'high', 'chat'), ('chat', 'low', 'summary'), (None, None, 'side')]


async def test_summary_attempt_and_sdk_request_are_separate_and_main_scope_is_restored(recorder, monkeypatch):
    await clear_events()
    cid, _ = await conversation()
    class Provider:
        async def stream(self, **kwargs):
            payload = json.loads(kwargs['messages'][0].content)
            recorder.record('call', service='openai', model='luna', slug='gpt-6-luna', purpose='side',
                input_tokens=150, output_tokens=30)
            yield json.dumps(summary_value(payload['fragments']))
    monkeypatch.setattr(context, 'get_provider', lambda _: Provider())
    with usage_events.measurement(surface='chat', effort='high'):
        await context.prepare(TEST_OWNER, cid, 'luna', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
        recorder.record('call', service='openai', purpose='chat')
    await recorder.flush()
    rows = await stored_rows()
    assert [(r['kind'], r['purpose'], r['effort']) for r in rows] == [
        ('call', 'summary', 'low'), ('chat_event', 'summary', 'low'), ('call', 'chat', 'high')]
    assert rows[1]['outcome'] == 'complete'
    assert not any(key in rows[1] for key in ('owner', 'conversation_id', 'content', 'request_id'))


async def test_context_overflow_and_turn_are_measured_once_without_provider_call(client, monkeypatch, recorder):
    await clear_events()
    async def overflow(*args, **kwargs):
        raise context_budget.ContextOverflow('Ngữ cảnh vượt giới hạn thử.')
    monkeypatch.setattr(service.chat_context, 'prepare', overflow)
    monkeypatch.setattr(service, 'get_provider', lambda _: pytest.fail('Không gọi AI khi context vượt hạn mức'))
    events = await read_events(await client.post('/api/chat', json={'message': 'Nội dung riêng', 'effort': 'low'}))
    assert events[-1]['type'] == 'error'
    await recorder.flush()
    rows = await stored_rows()
    assert [(r['kind'], r['outcome']) for r in rows] == [('chat_event', 'overflow'), ('turn', 'context_overflow')]
    assert rows[-1]['effort'] == 'low' and rows[-1]['slug'] == config.XAI_MODEL
    assert 'Nội dung riêng' not in json.dumps(rows)


async def test_clock_tool_results_include_errors_once_without_ui_tool_events(client, monkeypatch, recorder):
    await clear_events()
    first = FakeStream([done(call())])
    second = FakeStream([done(call(name='get_current_datetime', arguments='{"timezone":"invalid"}'))])
    third = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã đối chiếu.'), done()])
    provider, _ = fake_provider(monkeypatch, [first, second, third])
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Hỏi đồng hồ', 'effort': 'medium'}))
    assert events[-1]['type'] == 'done'
    await recorder.flush()
    tools = [r for r in await stored_rows() if r['purpose'] == 'tool']
    assert [r['outcome'] for r in tools] == ['ok', 'error']
    assert all(r['surface'] == 'chat' and r['effort'] == 'medium' for r in tools)


def test_admin_counts_events_without_double_counting_usage_or_mixing_configurations():
    now = local(2026, 10, 21)
    turn = lambda **kw: row(now-1, 'turn', surface='chat', effort='low', outcome='complete', complete=1, **kw)
    event = lambda purpose, outcome: row(now-1, 'chat_event', surface='chat', purpose=purpose, outcome=outcome, elapsed_ms=100)
    rows = [turn(elapsed_ms=2000, first_text_ms=400),
        row(now-1, 'turn', surface='chat', effort='high', outcome='stopped', complete=0, elapsed_ms=999999, first_text_ms=200),
        turn(slug='gpt-other'), row(now-1, 'turn', surface='chat'),
        row(now-1, 'call', surface='chat', purpose='summary', input_tokens=1000, output_tokens=10),
        event('summary', 'complete'), event('summary', 'timeout'), event('context', 'overflow'),
        event('tool', 'ok'), event('tool', 'error'), event('web', 'error'), event('recovery', 'partial'), event('recovery', 'pending'),
        row(now-1, 'chat_event', surface='companion', purpose='tool', outcome='error')]
    data = stats.summarize(rows, '24h', now, ZONE, RATES, 'ok', now-86400)
    assert data['calls'] == 1 and data['turns'] == 4 and data['models'][0]['side_calls'] == 1
    assert data['models'][0]['input_tokens'] == 1000
    chat = data['chat']
    assert len(chat['configs']) == 4 and chat['legacy_turns'] == 1
    low = next(c for c in chat['configs'] if c['effort'] == 'low' and c['slug'] == 'gpt-6-luna')
    assert (low['p50_ms'], low['p95_ms'], low['total_samples'], low['first_samples']) == (2000, 2000, 1, 1)
    high = next(c for c in chat['configs'] if c['effort'] == 'high')
    assert high['p95_ms'] is None and high['first_p50_ms'] == 200
    assert chat['summary'] == dict(attempts=2, complete=1, source_changed=0, errors=1, cancelled=0,
        sdk_calls=1, usage_calls=1, latency_samples=2, p50_ms=100, p95_ms=100)
    # code_runs/code_errors: lần Peto/xAI chạy mã (thí điểm 21/10/2026), không có trong dữ liệu giả này.
    assert chat['tools'] == dict(results=2, errors=1, web_errors=1, code_runs=0, code_errors=0)
    assert chat['context_overflows'] == 1 and chat['recovery']['checks'] == 2
    assert stats.summarize([], '24h', now, ZONE, {}, 'missing', None)['chat']['summary']['p50_ms'] is None


async def test_recovery_query_is_owner_chat_and_source_scoped_with_explicit_reply_link(client, recorder):
    await clear_events()
    cid, rid, uid = await bound()
    other_cid, _, other_uid = await bound()
    foreign_cid, _, foreign_uid = await bound(owner='discord:' + OTHER_DISCORD_ID)
    async def recovery():
        response = await client.get(f'/api/conversations/{cid}/messages?recovery_for={uid}')
        assert response.status_code == 200
        return response.json()['messages']
    assert len(await recovery()) == 1
    await chat_turns.persist(TEST_OWNER, rid, content='Checkpoint')
    assert (await recovery())[-1]['reply_to'] == uid
    await chat_turns.persist(TEST_OWNER, rid, content='Checkpoint', state='interrupted')
    assert (await recovery())[-1]['status'] == 'incomplete'
    complete_cid, complete_rid, complete_uid = await bound()
    await chat_turns.persist(TEST_OWNER, complete_rid, content='Đã xong', state='complete')
    assert (await client.get(f'/api/conversations/{complete_cid}/messages?recovery_for={complete_uid}')).status_code == 200
    legacy_uid = await db.add_message(other_cid, 'user', 'Legacy chưa có reply')
    assert (await client.get(f'/api/conversations/{other_cid}/messages?recovery_for={legacy_uid}')).status_code == 200
    for path in [f'{cid}/messages?recovery_for={other_uid}', f'{other_cid}/messages?recovery_for={uid}',
                 f'{foreign_cid}/messages?recovery_for={foreign_uid}', f'{cid}/messages?recovery_for={uid+100000}']:
        assert (await client.get('/api/conversations/' + path)).status_code == 404
    assert (await client.get(f'/api/conversations/{cid}/messages?recovery_for=-1')).status_code == 422
    await recorder.flush()
    events = [r for r in await stored_rows() if r['purpose'] == 'recovery']
    assert [r['outcome'] for r in events] == ['pending', 'pending', 'partial', 'complete', 'missing']
    assert all(r['model'] is None for r in events)
