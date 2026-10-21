"""Context Chat bền vững, chia lô, quyền và ngân sách; không gọi model thật."""
import json
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from conftest import TEST_OWNER, OTHER_DISCORD_ID, read_events
from features.chat import context, context_budget, service
from shared import attachment_tools
from shared import chat_history_tools
from shared.chat_history_tools import ChatHistory
from storage import chat_context as store, connection
import storage as db
from ai import ChatMessage, ProviderError


async def conversation(count=14, first='Ràng buộc: alpha phải bằng 7.'):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    ids = []
    for index in range(count):
        ids.append(await db.add_message(cid, 'user' if index % 2 == 0 else 'assistant',
                     first if index == 0 else f'Tin thử {index}'))
    return cid, ids


def summary_value(batch, previous=None):
    return {'version': 1, 'constraints': (previous or {}).get('constraints') or [
        {'text': batch[0]['text'][:300] or 'Tin trống.', 'source_ids': [batch[0]['id']]}],
            'facts': [], 'decisions': [], 'pending': []}


@pytest.fixture
def summarizer(monkeypatch):
    calls = []
    async def fake(model, previous, batch, budget):
        calls.append((model, previous, batch))
        return summary_value(batch, previous)
    monkeypatch.setattr(context, 'summarize', fake)
    monkeypatch.setattr(context, 'MIN_BATCH', 2)
    return calls


@pytest.mark.parametrize('model', ['peto', 'luna', 'haiku'])
async def test_chat_uses_its_own_summary_with_saved_memory_off_and_portable_model_selection(client, monkeypatch, summarizer, model):
    cid, ids = await conversation()
    await db.set_memory_enabled(TEST_OWNER, False)
    seen = []
    class Provider:
        async def stream(self, **kwargs):
            seen.append(kwargs)
            yield 'Đã nhận yêu cầu mới.'
    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    monkeypatch.setattr(service, 'MAX_HISTORY_MESSAGES', 4)
    result = await read_events(await client.post('/api/chat', json={
        'conversation_id': cid, 'message': 'Sửa lại: alpha phải bằng 8.', 'model': model, 'effort': 'low'}))
    assert result[-1]['type'] == 'done', result
    saved = await store.state(TEST_OWNER, cid)
    assert saved and saved['model'] == context_budget.policy(model)['identity']
    assert summarizer[0][0] == model and 'alpha phải bằng 7' in seen[0]['system_prompt']
    assert seen[0]['messages'][-1].content == 'Sửa lại: alpha phải bằng 8.'
    assert 'current user corrections win' in seen[0]['system_prompt']
    assert len(await db.get_messages(TEST_OWNER, cid)) == 16
    assert (await db.memory_state(TEST_OWNER))['enabled'] == 0


async def test_character_cursor_does_not_skip_the_tail_of_a_large_message(summarizer):
    cid, ids = await conversation(count=1, first='prefix ' + 'x' * 40_000 + ' IMPORTANT_TAIL')
    await db.add_message(cid, 'assistant', 'đã nhận')
    await db.add_message(cid, 'user', 'tiếp tục')
    rows = await db.get_messages(TEST_OWNER, cid, limit=2)
    offsets = []
    for _ in range(3):
        await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 2)
        offsets.append((await store.state(TEST_OWNER, cid))['cursor_offset'])
    assert offsets[0] == 16_000 and offsets[1] == 32_000 and offsets[2] > 40_000
    assert summarizer[-1][2][0]['text'].endswith('IMPORTANT_TAIL')
    assert len((await db.get_messages(TEST_OWNER, cid))[0]['content']) > 40_000


async def test_summary_failure_preserves_the_good_projection_and_watermark(monkeypatch, summarizer):
    cid, _ = await conversation()
    rows = await db.get_messages(TEST_OWNER, cid, limit=4)
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)
    before = await store.state(TEST_OWNER, cid)
    for index in range(4):
        await db.add_message(cid, 'user', f'phần mới {index}')
    async def fail(*args):
        raise TimeoutError
    monkeypatch.setattr(context, 'summarize', fail)
    result = await context.prepare(TEST_OWNER, cid, 'luna', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    assert (await store.state(TEST_OWNER, cid))['digest'] == before['digest']
    assert 'Chưa tóm tắt' in result.detail and result.history_tools is not None
    assert 'unrepresented_messages' in result.prompt


async def test_source_edit_during_summary_cannot_publish_a_stale_result(monkeypatch, summarizer):
    cid, ids = await conversation()
    async def race(model, previous, batch, budget):
        async with connection.connect() as sql:
            await sql.execute('UPDATE messages SET content=? WHERE id=?', ('đã sửa', ids[0]))
            await sql.commit()
        return summary_value(batch)
    monkeypatch.setattr(context, 'summarize', race)
    result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    assert await store.state(TEST_OWNER, cid) is None
    assert 'Nguồn vừa thay đổi' in result.detail
    assert '"summary": null' in result.prompt


async def test_edit_delete_and_project_move_invalidate_only_their_own_context(summarizer):
    cid, ids = await conversation()
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    assert await store.state(TEST_OWNER, cid)
    async with connection.connect() as sql:
        await sql.execute('UPDATE messages SET content=? WHERE id=?', ('sửa nguồn', ids[0]))
        await sql.commit()
    assert await store.state(TEST_OWNER, cid) is None
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    async with connection.connect() as sql:
        await sql.execute('UPDATE conversations SET project_id=? WHERE id=?', ('project-other', cid))
        await sql.commit()
    assert await store.state(TEST_OWNER, cid) is None
    assert await db.delete_conversation(TEST_OWNER, cid)


async def test_fork_starts_its_own_context_and_other_owner_cannot_read_it(summarizer):
    from features.chat.conversations import fork
    cid, ids = await conversation()
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    new_id, _ = await fork(TEST_OWNER, cid, ids[-2], 'nhánh mới')
    assert await store.state(TEST_OWNER, new_id) is None
    assert await store.state('discord:' + OTHER_DISCORD_ID, cid) is None
    assert (await ChatHistory('discord:' + OTHER_DISCORD_ID, cid, ids[-1]+1).run('{}'))['messages'] == []
    branch_rows = await db.get_messages(TEST_OWNER, new_id)
    assert (await ChatHistory(TEST_OWNER, new_id, branch_rows[-1]['id']+1).run(json.dumps({'query': 'alpha'})))['messages']


async def test_old_uploaded_file_stays_readable_outside_recent_window(tmp_path, summarizer):
    cid, ids = await conversation()
    path = tmp_path / 'old.log'
    path.write_text('ROOT_CAUSE at original file', encoding='utf-8')
    await db.add_attachment(attachment_id='old-file', owner=TEST_OWNER, conversation_id=cid, message_id=ids[0],
                            filename=path.name, mime='text/plain', kind='file', size=path.stat().st_size, path=str(path))
    index = await store.file_index(TEST_OWNER, cid)
    assert len(index) == 1 and 'document' not in index[0]
    files = attachment_tools.AttachmentFiles([], TEST_OWNER, cid)
    result = await files.run('search_attachment', json.dumps({'file': path.name, 'query': 'ROOT_CAUSE', 'context_lines': 0}))
    assert result['matches'] == 1
    other, _ = await conversation(count=1)
    result = await attachment_tools.AttachmentFiles([], TEST_OWNER, other).run('search_attachment', json.dumps({'file': path.name, 'query': 'ROOT_CAUSE'}))
    assert 'error' in result


async def test_history_reader_paginates_original_text_and_rejects_permission_fields():
    cid, ids = await conversation(count=1, first='x' * 9000 + ' ORIGINAL_TAIL')
    tool = ChatHistory(TEST_OWNER, cid, ids[-1]+1)
    first = await tool.run('{}')
    assert len(first['messages'][0]['content']) == 4000 and first['next_character'] == 4000
    second = await tool.run(json.dumps({'start_id': first['next_id'], 'start_character': first['next_character']}))
    assert second['messages'][0]['start_character'] == 4000
    assert 'error' in await tool.run('{"owner":"other"}')
    assert 'error' in await tool.run('{"start_id":false}')


@pytest.mark.parametrize('change', ['bad-source', 'empty', 'extra', 'bad-version', 'oversized-padded-text'])
def test_summary_validation_does_not_accept_invented_provenance(change):
    batch = [{'id': 2, 'text': 'real source'}]
    value = summary_value(batch)
    if change == 'bad-source': value['constraints'][0]['source_ids'] = [999]
    elif change == 'empty': value['constraints'] = []
    elif change == 'extra': value['permissions'] = 'allow'
    elif change == 'oversized-padded-text': value['constraints'][0]['text'] = ' ' * 500 + 'padded'
    else: value['version'] = True
    with pytest.raises(ValueError):
        context.parse_summary(json.dumps(value), batch, None)


def test_web_catalog_matches_existing_verified_ids_without_using_agent_runtime():
    from features.agent.assembly import CATALOG
    for slug, (window, output) in context_budget.CATALOG.items():
        assert window == CATALOG[slug][0]
        assert not CATALOG[slug][1] or output == CATALOG[slug][1]


def test_actual_request_budget_handles_images_without_counting_base64_and_refuses_overflow():
    assert context_budget.estimate({'type': 'input_image', 'image_url': 'data:' + 'x' * 100_000}) == 4096
    token = context_budget.current.set({'input': 100, 'output': 50, 'context': 4000})
    try:
        with pytest.raises(ProviderError):
            context_budget.enforce({'instructions': 'x' * 1000, 'max_output_tokens': 100, 'input': [], 'tools': []})
    finally:
        context_budget.current.reset(token)


async def test_small_gap_keeps_exact_messages_without_an_extra_model_call(summarizer):
    cid, _ = await conversation(count=5)
    rows = await db.get_messages(TEST_OWNER, cid, limit=4)
    result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)
    assert not summarizer and len(result.history) == 5
    assert result.history[0].content == 'Ràng buộc: alpha phải bằng 7.'


async def test_summary_uses_the_selected_provider_without_web_tools_and_restores_budget(monkeypatch):
    from test_clock_tools import FakeStream, done, fake_provider
    batch = [{'id': 1, 'text': 'alpha = 7'}]
    value = summary_value(batch)
    stream = FakeStream([SimpleNamespace(type='response.output_text.delta', delta=json.dumps(value)), done()])
    provider, requests = fake_provider(monkeypatch, [stream])
    selected = []
    def choose(key):
        selected.append(key)
        return provider
    monkeypatch.setattr(context, 'get_provider', choose)
    assert await context.summarize('luna', None, batch, context_budget.policy('luna')) == value
    assert selected == ['luna'] and len(requests) == 1 and stream.closed
    assert requests[0]['tools'] == [] and requests[0]['max_output_tokens'] == 3072
    assert 'tool_choice' not in requests[0] and requests[0]['store'] is False
    assert context_budget.current.get() is None


async def test_history_tool_roundtrip_is_native_scoped_and_budget_checked_on_every_round(monkeypatch):
    from test_clock_tools import FakeStream, done, call, fake_provider
    cid, ids = await conversation(count=1, first='ORIGINAL ' + 'x' * 8000)
    first = FakeStream([done(call('read_chat_history', '{}'))])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='đã đối chiếu'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    token = chat_history_tools.current.set(ChatHistory(TEST_OWNER, cid, ids[-1]+1))
    budget = context_budget.policy('peto')
    budget_token = context_budget.current.set(budget)
    try:
        chunks = [part async for part in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'tra lại')])]
        assert any(schema.get('name') == 'read_chat_history' for schema in requests[0]['tools'])
        result = json.loads(requests[1]['input'][-1]['output'])
        assert result['messages'][0]['message_id'] == ids[0]
        assert result['messages'][0]['content'].startswith('ORIGINAL')
        assert any(getattr(part, 'kind', '') == 'file_lookup_done' for part in chunks)
        # Làm tràn bằng kết quả đọc: lượt đầu vẫn hợp lệ, lượt sau phải dừng trước khi gọi API.
        provider, requests = fake_provider(monkeypatch, [FakeStream([done(call('read_chat_history', '{}'))])])
        create = provider._client.responses.create
        async def tighten(**kwargs):
            result = await create(**kwargs)
            budget['input'] = context_budget.tokens(kwargs['instructions'], kwargs['input'], kwargs['tools']) + 200
            return result
        monkeypatch.setattr(provider._client.responses, 'create', tighten)
        with pytest.raises(ProviderError, match='vượt ngân sách'):
            _ = [part async for part in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'tra lại')])]
        assert len(requests) == 1
    finally:
        chat_history_tools.current.reset(token)
        context_budget.current.reset(budget_token)


async def test_history_query_returns_the_match_deep_in_a_message_with_file_and_source_refs(tmp_path):
    cid, ids = await conversation(count=1, first='x' * 12000 + ' DEEP_FACT alpha = 7')
    async with connection.connect() as sql:
        await sql.execute('UPDATE messages SET sources=? WHERE id=?',
                          (json.dumps([{'url': 'https://example.com/original', 'title': 'Bản gốc'}]), ids[0]))
        await sql.commit()
    path = tmp_path / 'source.txt'
    path.write_text('source', encoding='utf-8')
    await db.add_attachment(attachment_id='source-file', owner=TEST_OWNER, conversation_id=cid, message_id=ids[0],
                            filename=path.name, mime='text/plain', kind='file', size=6, path=str(path))
    result = await ChatHistory(TEST_OWNER, cid, ids[0]+1).run('{"query":"DEEP_FACT"}')
    row = result['messages'][0]
    assert 'DEEP_FACT' in row['content'] and row['start_character'] > 10000
    assert row['sources'][0]['url'] == 'https://example.com/original'
    assert row['files'][0]['name'] == 'source.txt' and str(path) not in json.dumps(result)


async def test_generated_document_index_verifies_version_and_chat_and_keeps_old_source_readable():
    from storage import documents
    cid, ids = await conversation()
    draft = await documents.save_document(TEST_OWNER, cid, 'Bản kế hoạch', '# Bản gốc\nOLD_GENERATED_FACT alpha=7', style='minimal')
    async with connection.connect() as sql:
        await sql.execute('UPDATE messages SET artifacts=? WHERE id=?',
            (json.dumps([{'id': draft['id'], 'version': 1, 'filename': 'ke-hoach.docx'},
                         {'id': draft['id'], 'version': 999, 'filename': 'fake.docx'}]), ids[1]))
        await sql.commit()
    index = await store.artifact_index(TEST_OWNER, cid)
    assert len(index) == 1 and index[0]['message_id'] == ids[1] and 'content' not in index[0]
    files = attachment_tools.AttachmentFiles([{'generated_documents': index}], TEST_OWNER, cid)
    result = await files.run('search_attachment', '{"file":"ke-hoach.docx","query":"OLD_GENERATED_FACT"}')
    assert result['matches'] == 1 and 'phần chữ nguồn' in result['note']
    other, _ = await conversation(count=1)
    assert await store.artifact_index(TEST_OWNER, other) == []
    assert await store.artifact_index('discord:' + OTHER_DISCORD_ID, cid) == []
    # Nội dung thẻ JSON hỏng trong DB không làm hỏng truy vấn catalog.
    async with connection.connect() as sql:
        await sql.execute('UPDATE messages SET artifacts=? WHERE id=?', ('broken JSON', ids[3]))
        await sql.commit()
    assert len(await store.artifact_index(TEST_OWNER, cid)) == 1


async def test_corrupt_projection_is_rebuilt_but_future_schema_is_not_overwritten(summarizer):
    cid, _ = await conversation()
    rows = await db.get_messages(TEST_OWNER, cid, limit=4)
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)
    async with connection.connect() as sql:
        await sql.execute('UPDATE chat_contexts SET data=? WHERE conversation_id=?', ('broken', cid))
        await sql.commit()
    assert await store.state(TEST_OWNER, cid) is None
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)
    assert await store.state(TEST_OWNER, cid)
    async with connection.connect() as sql:
        await sql.execute('UPDATE chat_contexts SET version=999 WHERE conversation_id=?', (cid,))
        await sql.commit()
    with pytest.raises(ProviderError, match='Phiên bản context'):
        await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)


async def test_context_deleted_with_chat_and_migration_does_not_change_original_messages(summarizer):
    cid, _ = await conversation()
    rows = await db.get_messages(TEST_OWNER, cid)
    await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows[-4:], [], 4)
    await db.init_db()
    assert await db.get_messages(TEST_OWNER, cid) == rows
    assert await store.state(TEST_OWNER, cid)
    await db.delete_conversation(TEST_OWNER, cid)
    async with connection.connect() as sql:
        assert (await (await sql.execute('SELECT COUNT(*) FROM chat_contexts WHERE conversation_id=?', (cid,))).fetchone())[0] == 0


async def test_stop_during_compaction_never_starts_the_main_reply_or_advances_cursor(client, monkeypatch, summarizer):
    from features.chat import schemas, turn_control
    from storage import chat_turns
    from test_chat_turns import consume
    cid, _ = await conversation()
    ready = asyncio.Event()
    async def wait(*args):
        ready.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(context, 'summarize', wait)
    monkeypatch.setattr(service, 'MAX_HISTORY_MESSAGES', 4)
    monkeypatch.setattr(service, 'get_provider', lambda *args: pytest.fail('Lượt đã dừng không gọi trả lời.'))
    request_id = uuid.uuid4().hex
    response = await service.chat(schemas.ChatRequest(message='tiếp tục', conversation_id=cid, request_id=request_id), owner=TEST_OWNER)
    events = []
    task = asyncio.create_task(consume(response, events))
    await asyncio.wait_for(ready.wait(), 3)
    await turn_control.stop(TEST_OWNER, request_id)
    await asyncio.wait_for(task, 3)
    assert (await chat_turns.get(TEST_OWNER, request_id))['state'] == 'stopped'
    assert await store.state(TEST_OWNER, cid) is None
    assert (TEST_OWNER, request_id) not in turn_control.running


async def test_summary_disabled_keeps_raw_history_lookup_and_latest_message(monkeypatch, summarizer):
    cid, _ = await conversation()
    monkeypatch.setattr(context.config, 'CHAT_SUMMARY_ENABLED', False)
    rows = await db.get_messages(TEST_OWNER, cid, limit=4)
    prepared = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 4)
    assert not summarizer and await store.state(TEST_OWNER, cid) is None
    assert prepared.history[-1].content == rows[-1]['content']
    assert prepared.history_tools is not None and '"unrepresented_messages": 10' in prepared.prompt


@pytest.mark.parametrize('raw', ['{broken', '[]', '{"grok-4.7":{"input":true}}', '{"grok-4.7":{"bad":10000}}'])
def test_invalid_budget_overrides_fail_with_readable_configuration_error(monkeypatch, raw):
    monkeypatch.setenv('PETO_CHAT_CONTEXT_LIMITS', raw)
    with pytest.raises(ProviderError, match='Cấu hình'):
        context_budget.policy('peto')


def test_unknown_model_defaults_to_conservative_limits_and_can_be_configured(monkeypatch):
    monkeypatch.setattr(context.config, 'XAI_MODEL', 'unknown-model')
    result = context_budget.policy('peto')
    assert result['context'] == 32768 and not result['known'] and result['output'] <= 4096
    monkeypatch.setenv('PETO_CHAT_CONTEXT_LIMITS', '{"unknown-model":{"context":100000,"input":20000,"output":3000}}')
    result = context_budget.policy('peto')
    assert result['known'] and result['input'] == 20000 and result['output'] == 3000


async def test_oversized_current_message_is_not_silently_cut(monkeypatch, summarizer):
    cid, _ = await conversation(count=1, first='EXACT' * 50000)
    monkeypatch.setattr(context.config, 'CHAT_CONTEXT_TOKENS', 8192)
    with pytest.raises(ProviderError, match='quá dài'):
        await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid), [], 4)
    assert not summarizer and len((await db.get_messages(TEST_OWNER, cid))[0]['content']) == 250000


async def test_source_edit_immediately_after_commit_does_not_leak_the_invalidated_summary(monkeypatch, summarizer):
    cid, ids = await conversation()
    original = store.save
    async def race(*args):
        result = await original(*args)
        async with connection.connect() as sql:
            await sql.execute('UPDATE messages SET content=? WHERE id=?', ('NEW_CONSTRAINT beta=9', ids[0]))
            await sql.commit()
        return result
    monkeypatch.setattr(store, 'save', race)
    prepared = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', await db.get_messages(TEST_OWNER, cid, limit=4), [], 4)
    assert await store.state(TEST_OWNER, cid) is None
    assert 'alpha phải bằng 7' not in prepared.prompt and 'NEW_CONSTRAINT beta=9' in prepared.prompt


async def test_summary_timeout_closes_stream_and_restores_request_context(monkeypatch):
    closed = []
    class Waiting:
        async def stream(self, **kwargs):
            try:
                await asyncio.Event().wait()
                yield 'never'
            finally:
                closed.append(True)
    monkeypatch.setattr(context, 'get_provider', lambda _: Waiting())
    monkeypatch.setattr(context.config, 'CHAT_SUMMARY_TIMEOUT', .01)
    with pytest.raises(TimeoutError):
        await context.summarize('peto', None, [{'id': 1, 'text': 'source'}], context_budget.policy('peto'))
    assert closed == [True] and context_budget.current.get() is None


async def test_filename_fallback_cannot_replace_a_newer_generated_document_with_an_older_upload(tmp_path):
    from storage import documents
    cid, ids = await conversation(count=4)
    path = tmp_path / 'same.txt'
    path.write_text('OLD_UPLOAD', encoding='utf-8')
    await db.add_attachment(attachment_id='older-upload', owner=TEST_OWNER, conversation_id=cid, message_id=ids[0],
                            filename=path.name, mime='text/plain', kind='file', size=10, path=str(path))
    draft = await documents.save_document(TEST_OWNER, cid, 'same', 'NEW_GENERATED_SOURCE', style='minimal')
    # Mô phỏng upload cũ ở ngoài catalog hữu hạn nhưng tài liệu mới vẫn được chỉ mục.
    files = attachment_tools.AttachmentFiles([{'id': ids[3], 'generated_documents': [
        {'id': draft['id'], 'version': 1, 'filename': 'same.txt', 'style': 'minimal'}]}], TEST_OWNER, cid)
    result = await files.run('read_attachment_lines', '{"file":"same.txt","start_line":1,"end_line":1}')
    assert 'NEW_GENERATED_SOURCE' in result['text'] and 'OLD_UPLOAD' not in result['text']
