"""Citation mapping through native provider events, SSE, checkpoints and owner-scoped history."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ai import xai, claude
from features.chat import service
from shared.web_search import citation_ids, normalize_sources, source_reference
from test_clock_tools import FakeStream, Item, done, fake_provider
from test_claude import sdk_with_responses, message_events, CITATION
from conftest import read_events

SOURCE = {'url': 'https://example.com/story', 'title': 'Bài viết', 'citation_ids': ['web:21']}


def test_aliases_survive_every_normalization_without_using_array_order():
    sources = normalize_sources([SOURCE, {**SOURCE, 'citation_ids': ['web:26'], 'access': 'page', 'kind': 'citation'}])
    assert sources == [{**SOURCE, 'citation_ids': ['web:21', 'web:26'], 'access': 'page', 'kind': 'citation'}]
    assert normalize_sources(sources) == sources
    assert citation_ids({'id': 'web:21', 'ref_id': 'web:22', 'source_id': '21', 'index': 26}) == ['web:22', 'web:21']
    assert 'citation_ids' not in normalize_sources([{'url': SOURCE['url'], 'id': '21'}])[0]


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,x', 'https://user:pw@example.com', 'https://example.com/\\bad', 'https://example.com/\x7f'])
def test_unsafe_sources_do_not_keep_a_clickable_reference(url):
    assert normalize_sources([{**SOURCE, 'url': url}]) == []


def test_native_annotation_span_proves_id_and_bad_span_never_guesses():
    text = 'Có liên lạc. [web:21]'
    annotation = {'type': 'url_citation', 'url': SOURCE['url'], 'title': SOURCE['title'],
                  'start_index': text.index('['), 'end_index': len(text)}
    item = {'type': 'message', 'content': [{'type': 'output_text', 'text': text, 'annotations': [annotation]}]}
    assert xai._item_sources(item)[0]['citation_ids'] == ['web:21']
    annotation['start_index'] = 0
    assert 'citation_ids' not in xai._item_sources(item)[0]
    assert citation_ids({'citation_ids':['web:21', '<script>', 'web:abc', 'web:21']}) == ['web:21']


@pytest.mark.parametrize('metadata_first', [True, False])
async def test_provider_chunks_metadata_sse_persistence_reload_and_other_owner(client, anon_client, monkeypatch, metadata_first):
    search = Item(type='web_search_call', id='call-search', status='completed',
                  action={'type':'search', 'sources':[SOURCE]})
    text = 'Có liên lạc. [web:21]'
    deltas = [SimpleNamespace(type='response.output_text.delta', delta=part) for part in ['Có liên lạc. [', 'web:', '2', '1]']]
    source_event = SimpleNamespace(type='response.output_item.done', item=search)
    stream = FakeStream(([source_event, *deltas] if metadata_first else [*deltas, source_event]) + [done(search)])
    provider, _ = fake_provider(monkeypatch, [stream])
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    events = await read_events(await client.post('/api/chat', json={'message':'Kiểm tra citation giả', 'effort':'low'}))
    assert events[-1]['type'] == 'done'
    assert ''.join(event['text'] for event in events if event['type'] == 'delta') == text
    assert next(event for event in events if event['type'] == 'sources')['sources'][0]['citation_ids'] == ['web:21']
    cid = events[0]['conversation_id']
    message = (await client.get(f'/api/conversations/{cid}/messages')).json()['messages'][-1]
    assert message['content'] == text and message['sources'][0]['citation_ids'] == ['web:21']
    assert (await anon_client.get(f'/api/conversations/{cid}/messages')).status_code in {401,403,404}
    await provider._client.close()


async def test_anthropic_native_citation_gets_inline_reference_in_web_chat_only(client, monkeypatch):
    provider = claude.ClaudeProvider('claude-haiku-5-5', 'Haiku')
    sdk, _, _ = sdk_with_responses(message_events([{'type':'text', 'text':'Theo nguồn thật trong fixture.', 'citations':[CITATION]}]))
    provider._client.sdk = sdk
    monkeypatch.setattr(provider, '_prepare', AsyncMock())
    monkeypatch.setattr(service, 'get_provider', lambda _: provider)
    async with sdk:
        events = await read_events(await client.post('/api/chat', json={'message':'Citation fixture', 'model':'haiku', 'effort':'low'}))
    assert events[-1]['type'] == 'done'
    ref = source_reference(CITATION['url'])
    text = ''.join(event['text'] for event in events if event['type'] == 'delta')
    assert text == f'Theo nguồn thật trong fixture. [{ref}]'
    source = next(event for event in events if event['type'] == 'sources')['sources'][0]
    assert source['citation_ids'] == [ref] and source['url'] == CITATION['url']
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()['messages'][-1]
    assert saved['content'] == text and saved['sources'][0]['citation_ids'] == [ref]
    # Outside Web Chat the adapter retains its previous plain-text protocol (including Companion).
    assert 'citation_id' not in claude._citation(CITATION)


async def test_failed_stream_keeps_partial_text_and_citation_ids_for_history(client, monkeypatch):
    stream = FakeStream([
        SimpleNamespace(type='response.output_text.delta', delta='Một phần [web:21]'),
        SimpleNamespace(type='response.output_item.done', item=Item(type='web_search_call', id='search-partial',
            status='completed', action={'type':'search', 'sources':[SOURCE]})),
        SimpleNamespace(type='response.incomplete'),
    ])
    provider, _ = fake_provider(monkeypatch, [stream])
    monkeypatch.setattr(service, 'get_provider', lambda _:provider)
    try:
        events = await read_events(await client.post('/api/chat', json={'message':'Partial fixture', 'effort':'low'}))
        cid = events[0]['conversation_id']
        saved = (await client.get(f'/api/conversations/{cid}/messages')).json()['messages'][-1]
        assert saved['status'] == 'incomplete' and saved['content'] == 'Một phần [web:21]'
        assert saved['sources'][0]['citation_ids'] == ['web:21']
    finally:
        await provider._client.close()
