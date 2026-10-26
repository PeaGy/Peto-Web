"""Display provenance stays intact through SSE/checkpoints/history without widening model context."""
import uuid

import pytest
import storage as db
from ai.base import StreamChunk
from conftest import TEST_OWNER, read_events
from features.chat import service
from features.chat import conversations as conversation_actions
from features.chat.work_log import WorkLog
from shared.web_search import normalize_sources
from storage import chat_turns


def activity(count=105, state='done'):
    sources = [{'url': f'https://example.com/source/{n}', 'title': f'Source {n}', 'access': 'search', 'kind': 'result',
                'snippet': f'Explicit producer excerpt {n}'} for n in range(count)]
    sources[-1].update(kind='citation', citation_ids=['web:21'])
    return {'call': {'id': 'xai:1:native-search', 'kind': 'search', 'operation': 'search',
                     'queries': ['DISPLAY_QUERY_NOT_FOR_MODEL_CONTEXT'], 'state': state,
                     'source_urls': [source['url'] for source in sources]}, 'sources': sources}


def test_work_snapshot_keeps_live_calls_and_terminal_close_stops_only_live():
    log = WorkLog()
    info = activity(2, 'live')
    assert 'source_activity' in log.source_activity(info)
    assert log.source_activity(info) == ''
    assert log.snapshot()['web']['calls'][0]['state'] == 'live'
    assert log.close(False)['web']['calls'][0]['state'] == 'stopped'
    assert 'web' not in WorkLog().snapshot()


async def test_display_registry_sse_reload_citation_and_owner_scope(client, anon_client, monkeypatch):
    info = activity()
    payloads = []

    class Provider:
        async def stream(self, **kwargs):
            payloads.append(kwargs)
            if len(payloads) == 1:
                yield StreamChunk('source_activity', info=info)
                yield StreamChunk('source_activity', info=info)  # Native item repeated at completion.
                yield StreamChunk('sources', sources=tuple(normalize_sources(info['sources'])))
            yield 'Đã đối chiếu thông tin. [web:21]'

    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    events = await read_events(await client.post('/api/chat', json={'message': 'Đọc các nguồn giả lập', 'effort': 'low'}))
    assert events[-1]['type'] == 'done'
    updates = [event['web'] for event in events if event['type'] == 'source_activity']
    assert len(updates) == 1 and len(updates[0]['sources']) == 105
    cid = events[0]['conversation_id']
    saved = (await client.get(f'/api/conversations/{cid}/messages')).json()['messages'][-1]
    assert len(saved['sources']) == 30
    assert saved['sources'][0]['citation_ids'] == ['web:21']
    web = saved['work']['web']
    assert len(web['sources']) == 105 and len(web['calls']) == 1
    assert web['calls'][0]['queries'] == ['DISPLAY_QUERY_NOT_FOR_MODEL_CONTEXT']
    assert len(web['calls'][0]['source_urls']) == 105
    assert web['sources'][0]['snippet'].startswith('Explicit producer excerpt')
    assert (await anon_client.get(f'/api/conversations/{cid}/messages')).status_code in {401, 403, 404}
    await read_events(await client.post('/api/chat', json={'message': 'Tiếp tục', 'conversation_id': cid, 'effort': 'low'}))
    # Display-only provenance never becomes a hidden prompt or a synthetic tool result.
    assert 'DISPLAY_QUERY_NOT_FOR_MODEL_CONTEXT' not in repr(payloads[-1])
    assert 'Explicit producer excerpt' not in repr(payloads[-1])


@pytest.mark.parametrize('terminal', ['stop', 'restart'])
async def test_checkpoint_live_then_stop_or_restart_keeps_source_membership(client, terminal):
    cid = await db.create_conversation(TEST_OWNER)
    uid = await db.add_message(cid, 'user', 'Theo dõi lượt tra giả lập')
    rid = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, rid)
    await chat_turns.bind(TEST_OWNER, rid, cid, uid)
    log = WorkLog()
    log.source_activity(activity(2, 'live'))
    await chat_turns.persist(TEST_OWNER, rid, content='Đang đối chiếu', work=log.snapshot())
    rows = await db.get_messages(TEST_OWNER, cid)
    assert rows[-1]['work']['web']['calls'][0]['state'] == 'live'
    if terminal == 'restart':
        await chat_turns.interrupt_running()
    else:
        await chat_turns.stop(TEST_OWNER, rid)
        await chat_turns.persist(TEST_OWNER, rid, content='Đang đối chiếu', work=log.snapshot(), state='complete')
    rows = await db.get_messages(TEST_OWNER, cid)
    web = rows[-1]['work']['web']
    assert web['calls'][0]['state'] == 'stopped'
    assert len(web['sources']) == 2 and len(web['calls'][0]['source_urls']) == 2


async def test_edit_branch_preserves_prior_catalogue_without_copying_replaced_reply(client):
    cid = await db.create_conversation(TEST_OWNER)
    await db.add_message(cid, 'user', 'Câu đầu')
    log = WorkLog()
    log.source_activity(activity())
    work = log.close(True)
    await db.add_message(cid, 'assistant', 'Kết quả nguồn cũ. [web:21]',
                         sources=normalize_sources(activity()['sources']), work=work)
    target = await db.add_message(cid, 'user', 'Câu cần sửa')
    await db.add_message(cid, 'assistant', 'Câu trả lời bị thay thế')
    branch_id, _ = await conversation_actions.fork(TEST_OWNER, cid, target, 'Câu đã sửa')
    branch = (await client.get(f'/api/conversations/{branch_id}/messages')).json()['messages']
    assert len(branch) == 3 and branch[-1]['content'] == 'Câu đã sửa'
    assert branch[1]['work']['web'] == work['web']
    assert branch[1]['sources'][0]['citation_ids'] == ['web:21']
    assert len((await db.get_messages(TEST_OWNER, cid))) == 4
