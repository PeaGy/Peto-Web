"""Lượt nhờ sửa tệp Excel mà Grok chỉ viết câu báo sắp làm rồi dừng, không gọi công cụ (ngày 5/10/2026, mức Thấp: "Peto
sửa lại từ file gốc, không đụng sheet Quy_dinh." sau 46 giây suy nghĩ, không có tệp nào). Nhà cung cấp nhắc làm tiếp một
lần: gọi công cụ thì câu báo thành câu dẫn trong nhật ký, không gọi thì câu trả lời giữ nguyên."""
import json
import unicodedata
from types import SimpleNamespace

import pytest

from ai import xai
from ai.base import ChatMessage, StreamChunk
from features.chat import service as chat_service
from features.documents import tools as document_tools
from conftest import read_events
from test_clock_tools import FakeStream, Item, call, done, fake_provider
from test_workbook_edit import change, salary, upload
from test_workbook_reader import workbook

ANNOUNCEMENT = 'Peto sửa lại từ file gốc, không đụng sheet Quy_dinh.'


class FakeSession:
    """Phiên tài liệu giả: hội thoại có một tệp Excel sửa được."""

    def __init__(self, edit_request=True):
        self.workbooks = [{'name': 'luong.xlsx', 'kind': 'upload', 'path': 'luong.xlsx', 'mime': 'x'}]
        self.edit_request = edit_request
        self.edits = []

    async def edit(self, arguments):
        self.edits.append(arguments)
        return {'ok': True, 'artifact': {'id': 'doc-1', 'filename': 'luong.xlsx'}, '_ui': {'label': 'Đã sửa luong.xlsx'}}


def text(delta):
    return SimpleNamespace(type='response.output_text.delta', delta=delta)


def message(content):
    return Item(type='message', id='msg_1', role='assistant', status='completed',
                content=[{'type': 'output_text', 'text': content, 'annotations': []}])


def started(item):
    return SimpleNamespace(type='response.output_item.added', item=item)


def said(content):
    return FakeStream([text(content), done(message(content))])


async def run(monkeypatch, streams, session):
    provider, requests = fake_provider(monkeypatch, streams)
    token = document_tools.current_session.set(session)
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto',
                                                           messages=[ChatMessage('user', 'Sửa file giúp mình')])]
    finally:
        document_tools.current_session.reset(token)
    return chunks, requests


def answer(chunks) -> str:
    return ''.join(chunk for chunk in chunks if isinstance(chunk, str))


async def test_short_announcement_without_a_tool_call_gets_one_follow_up(monkeypatch):
    edit = call('edit_spreadsheet', '{"file":"luong.xlsx","changes":[]}')
    second = FakeStream([text('Có 3 lỗi.'), started(edit), done(message('Có 3 lỗi.'), edit)])
    session = FakeSession()
    chunks, requests = await run(monkeypatch, [said(ANNOUNCEMENT), second, said('Đã sửa xong 3 lỗi.')], session)
    assert len(requests) == 3 and len(session.edits) == 1
    sent = requests[1]['input']
    assert sent[-1] == {'role': 'user', 'content': [{'type': 'input_text', 'text': xai.FOLLOW_UP}]}
    assert sent[-2]['type'] == 'message' and sent[-2]['content'][0]['text'] == ANNOUNCEMENT
    # Lần gọi nhắc không có mốc "round" riêng: câu báo và chữ của lần nhắc cùng thành câu dẫn khi Grok gọi công cụ.
    shape = [chunk if isinstance(chunk, str) else chunk.kind for chunk in chunks]
    assert shape == ['round', ANNOUNCEMENT, '\n\nCó 3 lỗi.', 'note', 'tool', 'document_status', 'artifact',
                     'tool_result', 'document_status', 'round', 'Đã sửa xong 3 lỗi.']


async def test_a_complete_short_answer_stays_as_it_was(monkeypatch):
    reply = 'Tệp có 5 trang tính, không có ô nào cần sửa.'
    chunks, requests = await run(monkeypatch, [said(reply), said('XONG')], FakeSession())
    assert len(requests) == 2 and answer(chunks) == reply


async def test_a_long_reply_after_the_follow_up_is_kept(monkeypatch):
    listing = 'Lỗi ở ô B9: thừa khoảng trắng cuối. ' * 12
    chunks, _ = await run(monkeypatch, [said(ANNOUNCEMENT), said(listing)], FakeSession())
    assert answer(chunks) == ANNOUNCEMENT + '\n\n' + listing.strip()


@pytest.mark.parametrize('session, reply', [
    (FakeSession(edit_request=False), ANNOUNCEMENT),
    (FakeSession(), 'Một câu trả lời dài thật sự. ' * 20),
    (None, ANNOUNCEMENT),
])
async def test_no_follow_up_outside_short_replies_to_edit_requests(monkeypatch, session, reply):
    chunks, requests = await run(monkeypatch, [said(reply)], session)
    assert len(requests) == 1 and answer(chunks) == reply


def test_edit_requests_are_recognised():
    for text_ in ('Sửa file giúp mình', 'chỉnh lại công thức H5', 'Gộp ô A1:C1', 'Fix the totals',
                  unicodedata.normalize('NFD', 'Điền tổng vào hàng 14')):
        assert document_tools.asks_edit(text_), text_
    for text_ in ('File này có mấy trang tính?', 'Một hộp sữa tươi', 'Tóm tắt bảng điểm'):
        assert not document_tools.asks_edit(text_), text_


async def test_chat_follow_up_edits_the_upload_and_logs_the_announcement(client, monkeypatch):
    events = await read_events(await client.post('/api/chat', json={
        'message': 'Bảng lương đây', 'attachments': [upload('Bảng lương.xlsx', workbook(salary))]}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    arguments = json.dumps({'file': 'Bảng lương.xlsx', 'changes': [change(range='B3', values=[['13000000']]).model_dump()]},
                           ensure_ascii=False)
    edit = call('edit_spreadsheet', arguments)
    second = FakeStream([started(edit), done(edit)])
    provider, requests = fake_provider(monkeypatch, [said(ANNOUNCEMENT), second, said('Đã sửa lương của Bình.')])
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    events = await read_events(await client.post('/api/chat', json={
        'message': 'Sửa lương của Bình thành 13 triệu giúp mình', 'conversation_id': conversation}))
    assert len(requests) == 3 and [event['type'] for event in events].count('artifact') == 1
    work = next(event['work'] for event in events if event['type'] == 'work')
    notes = [step['label'] for step in work['steps'] if step['kind'] == 'note']
    assert notes == [ANNOUNCEMENT] and any(step['kind'] == 'tool' for step in work['steps'])
    stored = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]
    assert stored['content'] == 'Đã sửa lương của Bình.' and stored['artifacts']
