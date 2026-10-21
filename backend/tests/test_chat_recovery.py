"""Fault injection và phạm vi giai đoạn 3; SQLite tạm, không gọi AI/công cụ thật."""
import asyncio
import uuid

import pytest
from fastapi import HTTPException
import storage as db
from storage import chat_turns, connection, projects, chat_context
from features.chat import service, schemas, conversations, work_log
from conftest import TEST_OWNER, read_events
from shared.chat_history_tools import ChatHistory
from ai import StreamChunk
from storage import documents


async def bound(owner=TEST_OWNER, project=None):
    cid = await db.create_conversation(owner, project_id=project)
    rid = uuid.uuid4().hex
    await chat_turns.reserve(owner, rid)
    uid = await chat_turns.bind(owner, rid, cid, None, 'Câu hỏi thử')
    return cid, rid, uid


async def test_bind_rolls_back_user_insert_if_link_fails(client):
    cid = await db.create_conversation(TEST_OWNER)
    rid = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, rid)
    async with connection.connect() as sql:
        await sql.execute("CREATE TRIGGER fail_bind BEFORE UPDATE OF user_message_id ON chat_turns BEGIN SELECT RAISE(ABORT,'fault-bind'); END")
        await sql.commit()
    try:
        with pytest.raises(Exception, match='fault-bind'):
            await chat_turns.bind(TEST_OWNER, rid, cid, None, 'Không được để lại tin mồ côi')
        assert await db.get_messages(TEST_OWNER, cid) == []
        assert (await chat_turns.get(TEST_OWNER, rid))['user_message_id'] is None
    finally:
        async with connection.connect() as sql:
            await sql.execute('DROP TRIGGER fail_bind')
            await sql.commit()


async def test_failure_between_reply_and_terminal_state_rolls_back_then_one_retry_commits(client):
    cid, rid, _ = await bound()
    async with connection.connect() as sql:
        await sql.execute("CREATE TRIGGER fail_final BEFORE UPDATE OF assistant_message_id ON chat_turns BEGIN SELECT RAISE(ABORT,'fault-final'); END")
        await sql.commit()
    try:
        with pytest.raises(Exception, match='fault-final'):
            await chat_turns.persist(TEST_OWNER, rid, content='Chưa commit', state='complete')
        assert len(await db.get_messages(TEST_OWNER, cid)) == 1
        assert (await chat_turns.get(TEST_OWNER, rid))['state'] == 'running'
    finally:
        async with connection.connect() as sql:
            await sql.execute('DROP TRIGGER fail_final')
            await sql.commit()
    assert await chat_turns.persist(TEST_OWNER, rid, content='Đã commit', state='complete') == 'complete'
    # Mất ACK sau commit: đọc/gọi lưu lại không tạo thêm reply và không đổi nội dung đã chốt.
    await chat_turns.persist(TEST_OWNER, rid, content='Bản tới muộn', state='complete')
    rows = await db.get_messages(TEST_OWNER, cid)
    assert len(rows) == 2 and rows[-1]['content'] == 'Đã commit'
    assert rows[-1]['turn_state'] == rows[-1]['status'] == 'complete'
    with pytest.raises(HTTPException):
        await chat_turns.reserve(TEST_OWNER, rid)


async def test_checkpoint_survives_restart_without_replaying_any_model_or_tool(client):
    cid, rid, uid = await bound()
    log = work_log.WorkLog()
    log.thinking('Đang đối chiếu dữ liệu')
    snapshot = log.snapshot()
    assert any(step['state'] == 'live' for step in snapshot['steps'])
    assert any(step.state == 'live' for step in log.steps)
    await chat_turns.persist(TEST_OWNER, rid, content='Phần đã phát', work=snapshot)
    before = (await chat_turns.get(TEST_OWNER, rid))['assistant_message_id']
    await chat_turns.interrupt_running()
    await chat_turns.interrupt_running()
    turn = await chat_turns.get(TEST_OWNER, rid)
    rows = await db.get_messages(TEST_OWNER, cid)
    assert turn['assistant_message_id'] == before and turn['user_message_id'] == uid
    assert turn['state'] == 'interrupted' and turn['outcome'] == 'process_restarted'
    assert len(rows) == 2 and rows[-1]['content'] == 'Phần đã phát'
    assert rows[-1]['status'] == 'incomplete' and not rows[-1]['work']['complete']
    assert all(step['state'] != 'live' for step in rows[-1]['work']['steps'])
    assert await chat_turns.persist(TEST_OWNER, rid, content='Không được chạy tiếp', state='complete') == 'interrupted'


async def test_empty_bound_turn_gets_recoverable_placeholder_and_unbound_error_keeps_reason(client):
    cid, rid, _ = await bound()
    await chat_turns.interrupt_running()
    rows = await db.get_messages(TEST_OWNER, cid)
    assert len(rows) == 2 and rows[-1]['content'] == '' and rows[-1]['turn_state'] == 'interrupted'
    other = uuid.uuid4().hex
    await chat_turns.reserve(TEST_OWNER, other)
    assert await chat_turns.persist(TEST_OWNER, other, content='', state='error', outcome='queue_full') == 'error'
    assert (await chat_turns.get(TEST_OWNER, other))['outcome'] == 'queue_full'


async def test_checkpoint_bound_and_replace_then_stop_cannot_become_complete(client):
    cid, rid, _ = await bound()
    await chat_turns.persist(TEST_OWNER, rid, content='x' * (chat_turns.CHECKPOINT_CHARS + 500))
    assert (await chat_turns.get(TEST_OWNER, rid))['checkpoint_truncated']
    assert len((await db.get_messages(TEST_OWNER, cid))[-1]['content']) < chat_turns.CHECKPOINT_CHARS + 200
    await chat_turns.persist(TEST_OWNER, rid, content='Bản đã thay')
    assert (await db.get_messages(TEST_OWNER, cid))[-1]['content'] == 'Bản đã thay'
    await chat_turns.stop(TEST_OWNER, rid)
    assert await chat_turns.persist(TEST_OWNER, rid, content='Phần cuối tới muộn', state='complete') == 'stopped'
    row = (await db.get_messages(TEST_OWNER, cid))[-1]
    assert row['status'] == 'incomplete' and row['turn_outcome'] == 'user_stopped'


@pytest.mark.parametrize('change', ['delete', 'project', 'archive', 'edit'])
async def test_scope_changes_prevent_late_reply_and_never_recreate_chat(client, change):
    p1 = await projects.create_project(TEST_OWNER, 'Thử phạm vi A')
    p2 = await projects.create_project(TEST_OWNER, 'Thử phạm vi B')
    cid, rid, uid = await bound(project=p1['id'])
    await chat_turns.persist(TEST_OWNER, rid, content='Checkpoint ban đầu')
    if change == 'delete':
        await db.delete_conversation(TEST_OWNER, cid)
    else:
        async with connection.connect() as sql:
            if change == 'project':
                await sql.execute('UPDATE conversations SET project_id=? WHERE id=?', (p2['id'], cid))
            elif change == 'archive':
                await sql.execute('UPDATE conversations SET archived=1 WHERE id=?', (cid,))
            else:
                await sql.execute('UPDATE messages SET content=? WHERE id=?', ('Câu đã sửa', uid))
            await sql.commit()
    assert await chat_turns.persist(TEST_OWNER, rid, content='Kết quả tới muộn', state='complete') == 'interrupted'
    rows = await db.get_messages(TEST_OWNER, cid)
    assert not any(row['content'] == 'Kết quả tới muộn' for row in rows)
    if change == 'delete':
        assert not await db.owns_conversation(TEST_OWNER, cid)


async def test_other_owner_cannot_checkpoint_or_read_and_running_retry_is_rejected(client):
    cid, rid, uid = await bound()
    await chat_turns.persist(TEST_OWNER, rid, content='Checkpoint')
    assert await chat_turns.persist('discord:other', rid, content='Ghi đè', state='complete') == 'interrupted'
    assert await db.get_messages('discord:other', cid) == []
    with pytest.raises(HTTPException) as err:
        await conversations.retry_in_place(TEST_OWNER, cid, uid, 'Câu mới')
    assert err.value.status_code == 409
    assert (await db.get_messages(TEST_OWNER, cid))[-1]['content'] == 'Checkpoint'


async def test_new_question_after_empty_provider_failure_is_last_user_task(client, monkeypatch):
    payloads, guides = [], []
    original = service._build_system_prompt
    async def prompt(*args, **kwargs):
        guides.append(kwargs['agent_question'])
        return await original(*args, **kwargs)
    class Provider:
        async def stream(self, **kwargs):
            payloads.append(kwargs['messages'])
            if len(payloads) == 1:
                raise service.ProviderError('Lỗi giả lập trước chữ đầu')
            yield 'Trạng thái tệp mới'
    monkeypatch.setattr(service, 'get_provider', lambda *args: Provider())
    monkeypatch.setattr(service, '_build_system_prompt', prompt)
    rid = uuid.uuid4().hex
    events = await read_events(await client.post('/api/chat', json={'message': 'Đồng hồ cũ', 'request_id': rid}))
    assert events[-1]['type'] == 'error'
    cid = (await chat_turns.get(TEST_OWNER, rid))['conversation_id']
    events = await read_events(await client.post('/api/chat', json={'conversation_id': cid, 'message': 'Tệp mới đã đọc chưa?'}))
    assert events[-1]['type'] == 'done'
    assert [m.content for m in payloads[-1] if m.role == 'user'] == ['Tệp mới đã đọc chưa?']
    assert 'Đồng hồ cũ' not in guides[-1]
    assert any('not a pending task' in m.content for m in payloads[-1])
    result = await ChatHistory(TEST_OWNER, cid, 2**31).run('{}')
    assert result['messages'][0]['turn_state'] == 'error' and 'không phải yêu cầu đang chờ' in result['note']


async def test_artifacts_are_scoped_and_committed_with_the_same_reply(client):
    cid, rid, _ = await bound()
    valid = await documents.save_document(TEST_OWNER, cid, 'Tệp đúng', '# Bản thử')
    other_cid = await db.create_conversation(TEST_OWNER)
    wrong = await documents.save_document(TEST_OWNER, other_cid, 'Tệp khác chat', '# Không liên kết')
    artifacts = [{'id': d['id'], 'version': d['version'], 'filename': name} for d, name in
                 [(valid, 'valid.docx'), (wrong, 'wrong.docx')]]
    await chat_turns.persist(TEST_OWNER, rid, content='Có tệp', artifacts=artifacts, state='complete')
    rows = await db.get_messages(TEST_OWNER, cid)
    assert [item['id'] for item in rows[-1]['artifacts']] == [valid['id']]
    assert rows[-1]['turn_state'] == 'complete'


async def test_checkpoint_replacement_is_saved_before_sse_and_final_persist_failure_never_emits_done(client, monkeypatch):
    class Provider:
        async def stream(self, **kwargs):
            yield StreamChunk('text', 'Bản nháp ngắn')
            yield StreamChunk('replace', '')
            yield StreamChunk('text', 'Câu trả lời cuối')
    monkeypatch.setattr(service, 'get_provider', lambda *args: Provider())
    original = chat_turns.persist
    async def fail_final(*args, **kwargs):
        if kwargs.get('state') == 'complete':
            raise OSError('Giả lập không ghi được DB cuối lượt')
        return await original(*args, **kwargs)
    monkeypatch.setattr(chat_turns, 'persist', fail_final)
    rid = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='Thử phục hồi', request_id=rid), owner=TEST_OWNER)
    events = []
    async for chunk in response.body_iterator:
        import json
        current = [json.loads(line[6:]) for line in chunk.splitlines() if line.startswith('data: ')]
        events.extend(current)
        if any(e['type'] == 'replace' for e in current):
            turn = await chat_turns.get(TEST_OWNER, rid)
            assert (await db.get_messages(TEST_OWNER, turn['conversation_id']))[-1]['content'] == ''
    assert not any(event['type'] == 'done' for event in events)
    assert events[-1]['type'] == 'error'
    turn = await chat_turns.get(TEST_OWNER, rid)
    assert turn['state'] == 'interrupted' and turn['outcome'] == 'persistence_error'


async def test_turn_state_transition_invalidates_covered_summary_and_migrates_old_failed_cache_once(client):
    cid, rid, uid = await bound()
    batch = await chat_context.spans(TEST_OWNER, cid, uid + 1)
    value = {'version': 1, 'constraints': [], 'facts': [], 'decisions': [],
             'pending': [{'text': 'Việc cũ', 'source_ids': [uid]}]}
    assert await chat_context.save(TEST_OWNER, cid, None, None, batch, uid + 1, value, 'fake')
    await chat_turns.persist(TEST_OWNER, rid, content='', state='error')
    assert await chat_context.state(TEST_OWNER, cid) is None
    # Dựng cache đúng schema nhưng mang ngữ nghĩa cũ, như bản trước giai đoạn 3.
    batch = await chat_context.spans(TEST_OWNER, cid, uid + 1)
    assert await chat_context.save(TEST_OWNER, cid, None, None, batch, uid + 1, value, 'fake')
    async with connection.connect() as sql:
        await sql.execute('DROP TRIGGER chat_context_turn_state')
        await chat_context.init_tables(sql)
        await sql.commit()
    assert await chat_context.state(TEST_OWNER, cid) is None
    assert await chat_context.save(TEST_OWNER, cid, None, None, batch, uid + 1, value, 'fake')
    async with connection.connect() as sql:
        await chat_context.init_tables(sql)
        await sql.commit()
    assert await chat_context.state(TEST_OWNER, cid) is not None


@pytest.mark.parametrize('field', ['temporary', 'temporary_chat', 'retention', 'memory_scope'])
async def test_unsupported_privacy_flag_rejected_before_model(client, monkeypatch, field):
    monkeypatch.setattr(service, 'get_provider', lambda *args: pytest.fail('Không được gọi AI'))
    response = await client.post('/api/chat', json={'message': 'Dữ liệu thử', field: True})
    assert response.status_code == 422
