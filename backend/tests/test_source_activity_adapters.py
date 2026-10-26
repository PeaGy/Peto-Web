"""Native HTTP/Responses fixtures only; no real keys, API calls or paid searches."""
from contextlib import contextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai import ChatMessage
from ai import claude, xai
from ai.gpt import GPTProvider
from ai.base import ProviderError
from features.chat.request_context import RequestContext, current
from shared.source_activity import SourceActivity
from test_clock_tools import FakeStream, Item, call, done, fake_provider
from test_claude import sdk_with_responses, message_events, SEARCH, RESULT, TEXT, FETCH, FETCH_FAILED, CITATION


@contextmanager
def web_context(model='peto'):
    token = current.set(RequestContext('source-test', False, 'conversation', None, model, 'low', 'UTC',
                                       'validated_preference', 'unauthorized', 'not_connected'))
    try:
        yield
    finally:
        current.reset(token)


def native_search(ident='search-1', *, status='completed', query='monitor', size=1):
    return Item(type='web_search_call', id=ident, status=status,
                action={'type': 'search', 'query': query, 'sources': [
                    {'url': f'https://example.com/{i}', 'title': f'Monitor {i}', 'snippet': f'Excerpt {i}'} for i in range(size)]})


async def collect(provider):
    return [chunk async for chunk in provider.stream(system_prompt='Fixture only', messages=[ChatMessage('user', 'monitor')])]


def catalogue(chunks):
    activity = SourceActivity()
    for chunk in chunks:
        if getattr(chunk, 'kind', None) == 'source_activity':
            activity.update(chunk.info)
    return activity.snapshot()


@pytest.mark.parametrize('provider_name', ['xai', 'openai'])
async def test_responses_keep_full_call_membership_before_30_cap_and_deduplicate_completion(monkeypatch, provider_name):
    search = native_search(size=105)
    stream = FakeStream([SimpleNamespace(type='response.output_item.added', item=native_search(status='in_progress')),
                         SimpleNamespace(type='response.output_item.done', item=search),
                         SimpleNamespace(type='response.output_text.delta', delta='Fixture answer.'), done(search)])
    provider, requests = fake_provider(monkeypatch, [stream])
    if provider_name == 'openai':
        original = provider
        provider = GPTProvider('gpt-6-luna', 'Luna')
        provider._client = original._client
        monkeypatch.setattr(provider, '_prepare', AsyncMock())
    with web_context('luna' if provider_name == 'openai' else 'peto'):
        chunks = await collect(provider)
    web = catalogue(chunks)
    assert len(web['sources']) == 105 and len(web['calls']) == 1
    assert web['calls'][0]['id'] == f'{provider_name}:0:search-1'
    assert web['calls'][0]['queries'] == ['monitor'] and len(web['calls'][0]['source_urls']) == 105
    assert all(len(chunk.sources) <= 30 for chunk in chunks if getattr(chunk, 'kind', None) == 'sources')
    assert len(requests) == 1 and 'work' not in json.dumps(requests[0]['input'])


async def test_native_call_ids_are_qualified_by_provider_round_and_not_query(monkeypatch):
    first = native_search()
    second = native_search(query='same id, next round')
    provider, requests = fake_provider(monkeypatch, [FakeStream([done(first, call())]),
        FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Answer.'), done(second)])])
    with web_context():
        chunks = await collect(provider)
    assert [item['id'] for item in catalogue(chunks)['calls']] == ['xai:0:search-1', 'xai:1:search-1']
    assert len(requests) == 2


async def test_failed_native_item_is_visible_before_provider_error_and_cannot_add_sources(monkeypatch):
    failed = native_search(status='failed')
    provider, _ = fake_provider(monkeypatch, [FakeStream([done(failed)])])
    received = []
    with web_context(), pytest.raises(ProviderError):
        async for chunk in provider.stream(system_prompt='Fixture', messages=[ChatMessage('user', 'monitor')]):
            received.append(chunk)
    web = catalogue(received)
    assert web['calls'][0]['state'] == 'failed' and web['calls'][0]['source_urls'] == []
    assert web['sources'] == []


def test_missing_native_id_keeps_sources_ungrouped_and_unknown_fields_are_not_inferred():
    item = vars(native_search()).copy()
    item.pop('id')
    data = xai._source_activity(item, 'openai', 1)
    assert 'call' not in data and len(data['sources']) == 1
    item['id'] = 'known'
    item['action'].pop('query')
    assert xai._source_activity(item, 'openai', 1)['call']['queries'] == []


async def test_standalone_protocol_does_not_gain_web_chat_activity(monkeypatch):
    provider, _ = fake_provider(monkeypatch, [FakeStream([done(native_search())])])
    assert not any(getattr(chunk, 'kind', None) == 'source_activity' for chunk in await collect(provider))


async def test_claude_queries_bind_to_native_result_and_pause_keeps_native_replay(monkeypatch):
    sdk, calls, _ = sdk_with_responses(message_events([SEARCH, RESULT], 'pause_turn'), message_events([{**TEXT, 'citations': [CITATION]}]))
    provider = claude.ClaudeProvider('claude-haiku-5-5', 'Haiku')
    provider._client = claude.ClaudeClient(sdk)
    monkeypatch.setattr(provider, '_prepare', AsyncMock())
    async with sdk:
        with web_context('haiku'):
            chunks = await collect(provider)
    web = catalogue(chunks)
    assert len(web['calls']) == 1
    assert web['calls'][0]['queries'] == [SEARCH['input']['query']]
    assert web['calls'][0]['id'] == 'anthropic:0:srvtoolu_search'
    assert web['calls'][0]['source_urls'] == [RESULT['content'][0]['url']]
    assert web['sources'][0]['snippet'] == CITATION['cited_text']
    assert 'ket-qua-ma-hoa' not in json.dumps(web)
    assert calls[1]['messages'][-1] == {'role': 'assistant', 'content': [SEARCH, RESULT]}
    portable = claude._portable_output([SEARCH, RESULT])
    assert len(portable) == 1 and 'query' not in portable[0]['action']


async def test_claude_fetch_failure_has_target_and_remains_distinct_from_search(monkeypatch):
    sdk, _, _ = sdk_with_responses(message_events([FETCH, FETCH_FAILED, TEXT]))
    provider = claude.ClaudeProvider('claude-haiku-5-5', 'Haiku')
    provider._client = claude.ClaudeClient(sdk)
    monkeypatch.setattr(provider, '_prepare', AsyncMock())
    async with sdk:
        with web_context('haiku'):
            chunks = await collect(provider)
    web = catalogue(chunks)
    assert web['calls'][0]['kind'] == 'page' and web['calls'][0]['operation'] == 'fetch'
    assert web['calls'][0]['state'] == 'failed' and web['calls'][0]['url'] == FETCH['input']['url']
    assert web['calls'][0]['source_urls'] == []
