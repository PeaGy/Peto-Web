import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from pypdf import PdfReader
from PIL import Image
import db
import main
import document_store
from ai.base import StreamChunk, ProviderError, ChatMessage
from ai.mock import DOCUMENT_SAMPLE
from document_tools import DocumentSession, current_session
from conftest import TEST_OWNER, read_events

ARGS = json.dumps({'title': 'Giữ sự tử tế trong xã hội số', 'content': DOCUMENT_SAMPLE, 'format': 'docx', 'style': 'essay'}, ensure_ascii=False)


async def generate(client):
    events = await read_events(await client.post('/api/chat', json={'message': 'Tạo file docx viết một bài nghị luận xã hội'}))
    assert events[-1]['type'] == 'done'
    artifact = next(event['artifact'] for event in events if event['type'] == 'artifact')
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    return events, artifact, conversation


async def test_natural_request_creates_real_files_inline_and_persists(client, anon_client, monkeypatch):
    events, artifact, conversation = await generate(client)
    text = ''.join(event['text'] for event in events if event['type'] == 'delta')
    assert len(text) < 400 and 'Trong một thế giới' not in text
    assert artifact['pages'] >= 2
    base = f"/api/documents/{artifact['id']}"
    listing = (await client.get(f'/api/documents?conversation_id={conversation}')).json()['documents']
    assert listing[0]['format'] == 'docx' and listing[0]['pages'] == artifact['pages']
    assert 'content' not in listing[0] and 'pdf' not in listing[0]
    detail = (await client.get(base + '?version=1')).json()
    assert detail['format'] == 'docx' and detail['pages'] == artifact['pages']
    word = await client.get(base + '/export/docx?version=1')
    doc = Document(BytesIO(word.content))
    assert doc.styles['Normal'].font.name == 'Times New Roman'
    assert abs(doc.sections[0].page_width.cm - 21) < .01
    assert 'Trong một thế giới' in '\n'.join(p.text for p in doc.paragraphs)
    pdf = await client.get(base + '/export/pdf?version=1')
    assert len(PdfReader(BytesIO(pdf.content)).pages) == artifact['pages']
    for page in [1, artifact['pages']]:
        preview = await client.get(base + f'/preview?version=1&page={page}')
        assert preview.status_code == 200
        assert preview.headers['cache-control'] == 'private, no-store'
        assert Image.open(BytesIO(preview.content)).width > 600
    assert (await client.get(base + '/preview?version=1&page=40')).status_code == 404
    assert (await anon_client.get(base + '/preview?version=1')).status_code == 401
    history = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    assert history[-1]['artifacts'] == [artifact]
    assert 'generated_documents' not in history[-1]
    assert current_session.get() is None
    seen = []
    class FollowUp:
        async def stream(self, **kwargs):
            seen.extend(kwargs['messages'])
            yield 'Đã đọc bản trước.'
    monkeypatch.setattr(main, 'get_provider', lambda model="peto": FollowUp())
    await client.post('/api/chat', json={'message': 'Tóm tắt file vừa tạo', 'conversation_id': conversation})
    assert any('Trong một thế giới' in a.text_excerpt for m in seen for a in m.attachments)
    await client.delete(base)
    assert (await client.get(base + '/preview?version=1')).status_code == 404
    history = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    assert all(not m['artifacts'] for m in history)


async def test_tool_is_private_validated_and_idempotent(client):
    conversation = await db.create_conversation('another-account', 'Private')
    session = DocumentSession('another-account', conversation)
    result = await session.create(ARGS)
    assert result['ok']
    assert await session.create(ARGS) == result
    assert len(session.created) == 1
    id = result['artifact']['id']
    for suffix in ['?version=1', '/preview?version=1', '/export/docx?version=1']:
        assert (await client.get(f'/api/documents/{id}' + suffix)).status_code == 404
    malformed = json.loads(ARGS) | {'owner': TEST_OWNER, 'path': '/etc/passwd'}
    assert 'error' in await session.create(json.dumps(malformed))
    assert len(session.created) == 1


async def test_obvious_unaccented_vietnamese_is_rejected_before_render(client):
    conversation = await db.create_conversation('accent-account', 'Dấu tiếng Việt')
    session = DocumentSession('accent-account', conversation)
    result = await session.create(json.dumps({
        'title': 'Nghi luan xa hoi doc sach trong thoi dai so',
        'content': '# Nghi luan xa hoi\n\nDay la noi dung ve trach nhiem cua gioi tre trong thoi dai so.',
        'format': 'pdf', 'style': 'essay',
    }))
    assert 'không dấu' in result['error']
    assert not session.created
    assert not await document_store.list_documents('accent-account', conversation)


async def test_quota_or_render_failure_never_publishes_an_artifact(client, monkeypatch):
    monkeypatch.setattr(document_store, 'MAX_ASSET_BYTES', 1)
    events = await read_events(await client.post('/api/chat', json={'message': 'Tạo file PDF bài văn'}))
    assert not any(event['type'] == 'artifact' for event in events)
    assert 'Chưa tạo được tệp' in ''.join(event['text'] for event in events if event['type'] == 'delta')
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    assert not (await document_store.list_documents(TEST_OWNER, conversation))


async def test_file_survives_failure_after_tool_completed(client, monkeypatch):
    class FailsAfterCreate:
        async def stream(self, **kwargs):
            session = current_session.get()
            if session is None: yield 'Tài liệu'; return
            result = await session.create(ARGS)
            yield StreamChunk('artifact', artifact=result['artifact'])
            raise ProviderError('Lỗi kết nối sau khi tạo tệp')
    monkeypatch.setattr(main, 'get_provider', lambda model="peto": FailsAfterCreate())
    events = await read_events(await client.post('/api/chat', json={'message': 'Tạo file Word'}))
    assert events[-1]['type'] == 'error'
    artifact = next(e['artifact'] for e in events if e['type'] == 'artifact')
    conversation = next(e['conversation_id'] for e in events if e['type'] == 'meta')
    history = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    assert history[-1]['artifacts'] == [artifact]
    assert history[-1]['status'] == 'incomplete'
    assert (await client.get(f"/api/documents/{artifact['id']}/export/docx?version=1")).status_code == 200


async def test_real_provider_tool_loop_receives_only_verified_success(client, monkeypatch):
    from test_clock_tools import FakeStream, done, call, fake_provider
    first = FakeStream([done(call('create_document', ARGS))])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã tạo tệp Word.'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    conversation = await db.create_conversation(TEST_OWNER, 'Tool loop')
    token = current_session.set(DocumentSession(TEST_OWNER, conversation))
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tạo Word')])]
    finally: current_session.reset(token)
    assert any(tool.get('name') == 'create_document' for tool in requests[0]['tools'])
    result = json.loads(requests[1]['input'][-1]['output'])
    assert result['ok'] is True
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == 'artifact' and chunk.artifact == result['artifact'] for chunk in chunks)
    assert DOCUMENT_SAMPLE not in ''.join(chunk for chunk in chunks if isinstance(chunk, str))
