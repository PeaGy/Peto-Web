"""Dừng được xác nhận, không lẫn mất mạng, và ngữ cảnh không sống lại qua Thử lại/F5."""
import asyncio
import base64
import json
import uuid

import pytest
from fastapi import HTTPException
import storage as db
from storage import chat_turns
from features.chat import service, schemas, turn_control, history
from conftest import TEST_OWNER, read_events, sign_in


async def consume(response, events):
    async for chunk in response.body_iterator:
        events.extend(json.loads(line[6:]) for line in chunk.splitlines() if line.startswith('data: '))


@pytest.mark.parametrize('partial', [False, True])
async def test_stop_then_new_question_filters_pending_task_and_persists_label(client, monkeypatch, partial):
    ready = asyncio.Event()
    payloads, questions = [], []
    original_prompt = service._build_system_prompt

    async def prompt(*args, **kwargs):
        questions.append(kwargs['agent_question'])
        return await original_prompt(*args, **kwargs)

    class Provider:
        async def stream(self, **kwargs):
            payloads.append(kwargs['messages'])
            if kwargs['messages'][-1].content == 'Giải thích Docker.':
                if partial:
                    yield 'Phần giải thích đã hiện'
                ready.set()
                await asyncio.Event().wait()
            else:
                yield 'Giải thích Python'

    monkeypatch.setattr(service, 'get_provider', lambda model='peto': Provider())
    monkeypatch.setattr(service, '_build_system_prompt', prompt)
    request_id = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Giải thích Docker.', request_id=request_id), owner=TEST_OWNER)
    events = []
    task = asyncio.create_task(consume(response, events))
    await asyncio.wait_for(ready.wait(), 3)
    stopped = (await client.post('/api/chat/stop', json={'request_id': request_id})).json()
    await asyncio.wait_for(task, 3)
    assert stopped['stopped'] and stopped['message']['content'] == 'Giải thích Docker.'
    assert events[-1]['type'] == 'stopped'
    conversation = stopped['conversation_id']
    saved = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    assert saved[-1]['stopped'] and saved[-1]['status'] == 'incomplete'
    assert saved[-1]['content'] == ('Phần giải thích đã hiện' if partial else '')
    response = await service.chat(schemas.ChatRequest(message='Giải thích Python.', conversation_id=conversation), owner=TEST_OWNER)
    await consume(response, [])
    assert not any(row.role == 'user' and 'Docker' in row.content for row in payloads[-1])
    assert 'Docker' not in questions[-1]
    if partial:
        assert any('Phần giải thích đã hiện' in row.content for row in payloads[-1])
    else:
        assert not any('Docker' in row.content for row in payloads[-1])
    assert (TEST_OWNER, request_id) not in turn_control.running


async def test_stop_arrives_before_post_and_repeated_post_never_runs_ai(client, monkeypatch):
    calls = []
    monkeypatch.setattr(service, 'get_provider', lambda *args: calls.append('Không được gọi'))
    request_id = uuid.uuid4().hex
    assert (await client.post('/api/chat/stop', json={'request_id': request_id})).json()['stopped']
    for _ in range(2):
        events = await read_events(await client.post('/api/chat', json={'message': 'Câu đã bỏ', 'request_id': request_id}))
        assert events == [{'type': 'stopped'}]
    assert calls == []
    assert (await chat_turns.get(TEST_OWNER, request_id))['user_message_id'] is None


async def test_retry_uses_new_attempt_old_stop_cannot_cancel_it(client, monkeypatch):
    cid = await db.create_conversation(TEST_OWNER)
    user_id = await db.add_message(cid, 'user', 'Câu hỏi cũ')
    old_id = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, old_id)
    await chat_turns.bind(TEST_OWNER, old_id, cid, user_id)
    await chat_turns.stop(TEST_OWNER, old_id)
    assistant_id = await db.add_message(cid, 'assistant', '', status='incomplete')
    await chat_turns.attach_reply(TEST_OWNER, old_id, assistant_id)
    ready, release = asyncio.Event(), asyncio.Event()
    class Provider:
        async def stream(self, **kwargs):
            assert kwargs['messages'][-1].content == 'Câu hỏi cũ'
            ready.set()
            await release.wait()
            yield 'Trả lời lần thử mới'
    monkeypatch.setattr(service, 'get_provider', lambda *args: Provider())
    new_id = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Câu hỏi cũ', conversation_id=cid, branch_message_id=user_id, request_id=new_id), owner=TEST_OWNER)
    events = []
    task = asyncio.create_task(consume(response, events))
    await asyncio.wait_for(ready.wait(), 3)
    await client.post('/api/chat/stop', json={'request_id': old_id})
    assert (await chat_turns.get(TEST_OWNER, new_id))['state'] == 'running'
    release.set()
    await asyncio.wait_for(task, 3)
    rows = await db.get_messages(TEST_OWNER, cid)
    assert len(rows) == 2 and rows[-1]['turn_state'] == 'complete'
    assert not history._public_message(rows[-1]).get('stopped')
    assert history.context_rows(rows)[0]['content'] == 'Câu hỏi cũ'


async def test_stop_is_scoped_to_owner_and_duplicate_completed_request_is_rejected(client):
    request_id = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, request_id)
    other_owner = await sign_in(client)
    await client.post('/api/chat/stop', json={'request_id': request_id})
    assert (await chat_turns.get(TEST_OWNER, request_id))['state'] == 'running'
    assert (await chat_turns.get(other_owner, request_id))['state'] == 'stopped'
    await chat_turns.finish(other_owner, request_id, 'complete')
    assert (await chat_turns.get(other_owner, request_id))['state'] == 'stopped'
    await chat_turns.finish(TEST_OWNER, request_id, 'complete')
    result = await turn_control.stop(TEST_OWNER, request_id)
    assert result['state'] == 'complete'
    with pytest.raises(HTTPException) as error:
        await chat_turns.reserve(TEST_OWNER, request_id)
    assert error.value.status_code == 409


async def test_transport_disconnect_is_not_user_stop(client, monkeypatch):
    class Provider:
        async def stream(self, **kwargs):
            yield 'Phần đã nhận'
            await asyncio.Event().wait()
    monkeypatch.setattr(service, 'get_provider', lambda *args: Provider())
    request_id = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Câu bị mất mạng', request_id=request_id), owner=TEST_OWNER)
    stream = response.body_iterator
    await anext(stream)
    await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    turn = await chat_turns.get(TEST_OWNER, request_id)
    assert turn['state'] == 'interrupted'
    rows = await db.get_messages(TEST_OWNER, turn['conversation_id'])
    assert not history._public_message(rows[-1]).get('stopped')
    assert not any(row['role'] == 'user' and row['content'] == 'Câu bị mất mạng' for row in history.context_rows(rows))


def test_stopped_attachments_and_partial_reply_remain_reference_data():
    files = [{'id': 'photo', 'kind': 'image'}]
    rows = history.context_rows([
        {'id': 1, 'role': 'user', 'content': 'Yêu cầu đã bỏ', 'turn_state': 'stopped', 'attachments': files},
        {'id': 2, 'role': 'assistant', 'content': '', 'turn_state': 'stopped', 'turn_user_id': 1},
        {'id': 3, 'role': 'user', 'content': 'Phân tích ảnh đó'},
    ])
    assert len(rows) == 2 and rows[0]['attachments'] == files
    assert 'Yêu cầu đã bỏ' not in rows[0]['content']


async def test_stop_during_save_before_meta_returns_stored_message(client, monkeypatch):
    saving, release = asyncio.Event(), asyncio.Event()
    original_bind = chat_turns.bind
    async def bind(*args):
        result = await original_bind(*args)
        saving.set()
        await release.wait()
        return result
    monkeypatch.setattr(chat_turns, 'bind', bind)
    monkeypatch.setattr(service, 'get_provider', lambda *args: pytest.fail('Lượt đã dừng không gọi AI'))
    request_id = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Chưa có metadata', request_id=request_id), owner=TEST_OWNER)
    events = []
    task = asyncio.create_task(consume(response, events))
    await asyncio.wait_for(saving.wait(), 3)
    stopping = asyncio.create_task(client.post('/api/chat/stop', json={'request_id': request_id}))
    for _ in range(100):
        if (await chat_turns.get(TEST_OWNER, request_id))['state'] == 'stopped':
            break
        await asyncio.sleep(.01)
    assert not stopping.done()
    release.set()
    result = (await asyncio.wait_for(stopping, 3)).json()
    await asyncio.wait_for(task, 3)
    assert result['message']['content'] == 'Chưa có metadata'
    rows = await db.get_messages(TEST_OWNER, result['conversation_id'])
    assert rows[-1]['content'] == '' and rows[-1]['turn_state'] == 'stopped'
    assert events[-1]['type'] == 'stopped'


async def test_fork_preserves_stopped_history_without_abandoning_new_target(client):
    from features.chat import conversations
    cid = await db.create_conversation(TEST_OWNER)
    user_id = await db.add_message(cid, 'user', 'Docker bị dừng')
    request_id = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, request_id)
    await chat_turns.bind(TEST_OWNER, request_id, cid, user_id)
    await chat_turns.stop(TEST_OWNER, request_id)
    assistant_id = await db.add_message(cid, 'assistant', '', status='incomplete')
    await chat_turns.attach_reply(TEST_OWNER, request_id, assistant_id)
    target = await db.add_message(cid, 'user', 'Python')
    new_cid, new_target = await conversations.fork(TEST_OWNER, cid, target, 'Python mới')
    rows = await db.get_messages(TEST_OWNER, new_cid)
    assert rows[0]['turn_state'] == rows[1]['turn_state'] == 'stopped'
    assert history.context_rows(rows) == [rows[-1]]
    assert rows[-1]['id'] == new_target and rows[-1]['content'] == 'Python mới'


def test_partial_turn_images_keep_user_role():
    files = [{'id': 'photo', 'kind': 'image'}]
    rows = history.context_rows([
        {'id': 1, 'role': 'user', 'content': 'Yêu cầu cũ', 'turn_state': 'stopped', 'attachments': files},
        {'id': 2, 'role': 'assistant', 'content': 'Phần đã trả lời', 'turn_state': 'stopped', 'turn_user_id': 1},
        {'id': 3, 'role': 'user', 'content': 'Câu mới'},
    ])
    assert rows[0]['role'] == 'user' and rows[0]['attachments'] == files
    assert 'Yêu cầu cũ' not in rows[0]['content']
    assert all(not row.get('attachments') for row in rows if row['role'] == 'assistant')
    assert any('Phần đã trả lời' in row['content'] for row in rows)


async def test_restart_marks_running_interrupted_and_keeps_stopped(client):
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, first)
    await chat_turns.stop(TEST_OWNER, second)
    await chat_turns.interrupt_running()
    assert (await chat_turns.get(TEST_OWNER, first))['state'] == 'interrupted'
    assert (await chat_turns.get(TEST_OWNER, second))['state'] == 'stopped'


async def test_titles_ignore_stopped_first_turn(client, monkeypatch):
    from features.chat import titles
    cid = await db.create_conversation(TEST_OWNER)
    uid = await db.add_message(cid, 'user', 'Docker đã bỏ')
    aid = await db.add_message(cid, 'assistant', '', status='incomplete')
    rid = uuid.uuid4().hex
    await chat_turns.stop(TEST_OWNER, rid)
    await chat_turns.bind(TEST_OWNER, rid, cid, uid)
    await chat_turns.attach_reply(TEST_OWNER, rid, aid)
    contexts = []
    async def suggest(*args, **kwargs):
        contexts.append(kwargs['context'])
        return 'Học Python'
    monkeypatch.setattr(titles, 'suggest_title', suggest)
    await titles.maybe_generate(TEST_OWNER, cid)
    assert contexts == []
    await db.add_message(cid, 'user', 'Python')
    await db.add_message(cid, 'assistant', 'Giải thích Python')
    await titles.maybe_generate(TEST_OWNER, cid)
    assert [m.content for m in contexts[0]] == ['Python', 'Giải thích Python']


async def test_stop_while_reading_keeps_request_unbound_and_never_calls_ai(client, monkeypatch):
    reading = asyncio.Event()
    async def read(*args):
        reading.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(service.document_reader, 'read_document', read)
    monkeypatch.setattr(service, 'get_provider', lambda *args: pytest.fail('Dừng đọc tệp không gọi AI'))
    rid = uuid.uuid4().hex
    request = schemas.ChatRequest(message='Đọc giúp', request_id=rid, attachments=[schemas.AttachmentIn(
        name='notes.txt', mime='text/plain', data=base64.b64encode(b'Noi dung tai lieu').decode())])
    response = await service.chat(request, owner=TEST_OWNER)
    events = []
    task = asyncio.create_task(consume(response, events))
    await asyncio.wait_for(reading.wait(), 3)
    result = (await client.post('/api/chat/stop', json={'request_id': rid})).json()
    await asyncio.wait_for(task, 3)
    assert result['stopped'] and result['message'] is None and result['conversation_id'] is None
    assert (await chat_turns.get(TEST_OWNER, rid))['user_message_id'] is None
    assert events[-1]['type'] == 'stopped'


@pytest.mark.parametrize('failure,state', [(TimeoutError(), 'timeout'), (service.ProviderError('Lỗi dịch vụ giả'), 'error')])
async def test_failures_are_not_explicit_stops(client, monkeypatch, failure, state):
    class Provider:
        async def stream(self, **kwargs):
            yield 'Đã có một phần'
            raise failure
    monkeypatch.setattr(service, 'get_provider', lambda *args: Provider())
    rid = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Câu còn cần trả lời', request_id=rid), owner=TEST_OWNER)
    await consume(response, [])
    turn = await chat_turns.get(TEST_OWNER, rid)
    assert turn['state'] == state
    rows = await db.get_messages(TEST_OWNER, turn['conversation_id'])
    assert not any(row['role'] == 'user' and row['content'] == 'Câu còn cần trả lời' for row in history.context_rows(rows))
    assert not history._public_message(rows[-1]).get('stopped')
