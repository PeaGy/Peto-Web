"""Nhật ký "Đang làm" (kiểu Dòng thời gian): máy chủ ghi từng bước, gửi qua sự kiện "step", lưu cùng tin nhắn."""

import json

import aiosqlite

import storage as db
from ai.base import ProviderError, StreamChunk
from conftest import TEST_OWNER, read_events
from features.chat import service as chat_service
from features.chat.work_log import NOTE_LIMIT, SHORT_THOUGHT_MS, WorkLog, read_detail
from storage import connection as db_connection


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def tick(self, seconds: float):
        self.value += seconds


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]


def test_steps_follow_the_turn_with_their_own_times():
    clock = Clock()
    log = WorkLog(clock=clock)
    events = events_of(log.round())
    assert events == [{'type': 'step', 'step': {'id': 'think-1', 'kind': 'think', 'label': 'Đang suy nghĩ…', 'state': 'live', 'start': 0}}]
    clock.tick(3)
    thought = events_of(log.thinking('**Checking codes**\n\nNV003 appears twice.'))
    assert thought == [{'type': 'thinking', 'step': 'think-1', 'text': '**Checking codes**\n\nNV003 appears twice.'}]
    clock.tick(60)
    done = events_of(log.text())[0]['step']
    assert done['state'] == 'done' and done['end'] == 63_000 and done['label'] == 'Đã suy nghĩ'
    clock.tick(2)
    note = events_of(log.note('Mình sửa bảng lương trước.'))[0]['step']
    assert note == {'id': 'note-2', 'kind': 'note', 'label': 'Mình sửa bảng lương trước.', 'state': 'done', 'start': 63_000, 'end': 63_000}
    events_of(log.tool('edit_spreadsheet'))
    clock.tick(21)
    compose, tool = (event['step'] for event in events_of(log.tool_start('Đang sửa tệp Excel…')))
    assert compose['label'] == 'Đã soạn lệnh sửa tệp Excel' and compose['end'] - compose['start'] == 21_000
    assert tool['kind'] == 'tool' and tool['state'] == 'live'
    clock.tick(4)
    refused = events_of(log.tool_result({'tool': 'edit_spreadsheet', 'ok': False, 'label': 'Sửa tệp bị từ chối, chưa ghi gì',
                                         'problems': ['Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10', '  ']}))[0]['step']
    assert refused['state'] == 'failed' and refused['problems'] == ['Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10']
    assert log.tool_end() == ''
    log.round()
    clock.tick(0.4)
    log.text()
    work = log.close(True)
    # Lần gọi sau chỉ chờ chữ đầu 0,4 giây, không có tóm tắt: không đáng một dòng trong nhật ký đã lưu.
    assert [step['kind'] for step in work['steps']] == ['think', 'note', 'compose', 'tool']
    assert work['ms'] == 90_400 and work['complete'] is True


def test_results_lookups_github_and_search_read_naturally():
    clock = Clock()
    log = WorkLog(clock=clock)
    log.tool('create_document')
    log.tool_start('Đang dàn trang và tạo tệp…')
    made = events_of(log.tool_result({'tool': 'create_document', 'ok': True},
                                      {'filename': 'Báo cáo.docx', 'format': 'docx', 'pages': 3}))[0]['step']
    assert made['label'] == 'Đã tạo Báo cáo.docx' and made['detail'] == '3 trang'
    log.tool_start('Đang sửa tệp Excel…')
    failed = events_of(log.tool_result({'tool': 'edit_spreadsheet', 'ok': False, 'error': 'Tệp lớn quá.'}))[0]['step']
    assert failed['label'] == 'Chưa sửa được tệp' and failed['problems'] == ['Tệp lớn quá.']
    log.lookup('Đang tìm “ERROR” trong app.log…', True)
    found = events_of(log.lookup('Đã tìm “ERROR” trong app.log: 2 dòng khớp', False))[0]['step']
    assert found['state'] == 'done' and found['label'].endswith('2 dòng khớp')
    for index in range(5):
        log.github('Đang đọc GitHub…', True)
        log.github('Đã đọc GitHub' if index != 2 else 'Không tìm thấy missing.ts', False)
    github = [step for step in log.close(True)['steps'] if step['kind'] == 'github']
    assert len(github) == 1, 'các lần đọc GitHub liền nhau gom một dòng'
    assert github[0]['label'] == 'Đọc GitHub · 4 mục đã đọc · 1 mục chưa đọc được'
    assert github[0]['problems'] == ['Không tìm thấy missing.ts']
    other = WorkLog(clock=Clock())
    other.search('searching')
    other.sources(3)
    searched = other.close(True)['steps'][0]
    assert searched['label'] == 'Đã tìm trên web' and searched['detail'] == '3 nguồn'


def test_unfinished_steps_stop_when_the_turn_fails():
    clock = Clock()
    log = WorkLog(clock=clock)
    log.round()
    clock.tick(1)
    log.thinking('Planning the fix.')
    log.text()
    log.tool('edit_spreadsheet')
    clock.tick(SHORT_THOUGHT_MS / 1000)
    work = log.close(False)
    assert work['complete'] is False
    assert [(step['kind'], step['state']) for step in work['steps']] == [('think', 'done'), ('compose', 'stopped')]
    assert work['steps'][1]['label'] == 'Đang soạn lệnh sửa tệp Excel…', 'trình duyệt tự thêm "Đã dừng"'


def test_read_details():
    assert read_detail({'status': 'ready', 'sheets': 5, 'formulas': 1520}) == '5 trang tính · 1.520 công thức'
    assert read_detail({'status': 'partial', 'pages': 12, 'ocr_pages': 3}) == '12 trang · có OCR · đọc được một phần'
    assert read_detail({'status': 'unreadable'}) == 'chưa đọc được chữ'
    assert read_detail(None) == ''


class Scripted:
    """Một lượt sửa Excel như Grok: suy nghĩ, câu dẫn, soạn lệnh, bị từ chối, rồi trả lời."""

    def __init__(self, fail: Exception | None = None, before_tool: str = 'Mình sửa bảng lương trước.'):
        self.fail, self.before_tool = fail, before_tool

    async def stream(self, **kwargs):
        yield StreamChunk('round')
        yield StreamChunk('thinking', '**Checking codes**\n\nNV003 appears twice.')
        yield self.before_tool
        yield StreamChunk('note')
        yield StreamChunk('tool', 'edit_spreadsheet')
        yield StreamChunk('document_status', 'Đang sửa tệp Excel…')
        yield StreamChunk('tool_result', info={'tool': 'edit_spreadsheet', 'ok': False, 'label': 'Sửa tệp bị từ chối, chưa ghi gì',
                                               'problems': ['Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10']})
        yield StreamChunk('document_status', '')
        if self.fail:
            raise self.fail
        yield StreamChunk('round')
        yield 'Xong rồi.'


async def test_chat_streams_steps_moves_the_lead_in_out_of_the_answer_and_saves_the_log(client, monkeypatch):
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Scripted())
    events = await read_events(await client.post('/api/chat', json={'message': 'Sửa bảng giúp mình'}))
    assert events[-1]['type'] == 'done'
    kinds = [event['step']['kind'] for event in events if event['type'] == 'step']
    assert kinds[:3] == ['think', 'think', 'note'] and 'compose' in kinds and 'tool' in kinds
    assert any(event['type'] == 'thinking' and event.get('step') == 'think-1' for event in events)
    # Câu dẫn đã hiện trong bong bóng lúc stream; khi biết là câu dẫn thì máy chủ thay bong bóng bằng phần còn lại.
    assert {'type': 'replace', 'text': ''} in events
    work = next(event['work'] for event in events if event['type'] == 'work')
    assert events.index(next(event for event in events if event['type'] == 'work')) == len(events) - 2
    assert [step['kind'] for step in work['steps']] == ['think', 'note', 'compose', 'tool']
    assert work['steps'][3]['problems'] == ['Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10']
    conversation = events[0]['conversation_id'] if 'conversation_id' in events[0] else next(
        event['conversation_id'] for event in events if event['type'] == 'meta')
    saved = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]
    assert saved['content'] == 'Xong rồi.', 'câu dẫn nằm trong nhật ký, không trong câu trả lời'
    assert saved['work'] == work


async def test_failed_turn_still_reports_what_was_tried(client, monkeypatch):
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Scripted(fail=ProviderError('Mất kết nối.')))
    events = await read_events(await client.post('/api/chat', json={'message': 'Sửa bảng giúp mình'}))
    assert [event['type'] for event in events[-2:]] == ['work', 'error']
    work = events[-2]['work']
    assert work['complete'] is False and [step['state'] for step in work['steps']] == ['done', 'done', 'done', 'failed']


async def test_long_text_before_a_tool_stays_in_the_answer(client, monkeypatch):
    long = 'Phần phân tích dài. ' * (NOTE_LIMIT // 10)
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Scripted(before_tool=long))
    events = await read_events(await client.post('/api/chat', json={'message': 'Phân tích rồi sửa'}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    saved = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]
    assert saved['content'].startswith('Phần phân tích dài.') and saved['content'].endswith('\n\nXong rồi.')
    assert not any(step['kind'] == 'note' for step in saved['work']['steps'])


async def test_mock_excel_edit_shows_the_whole_flow(client):
    """Bản chạy thử không tốn quota (__suaexcel__) cũng có đủ câu dẫn, soạn lệnh và kết quả sửa tệp."""
    from test_workbook_edit import salary, upload
    from test_workbook_reader import workbook

    events = await read_events(await client.post('/api/chat', json={
        'message': 'Bảng lương đây', 'attachments': [upload('Bảng lương.xlsx', workbook(salary))]}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    read = [event['step'] for event in events if event['type'] == 'step' and event['step']['kind'] == 'read']
    assert read[-1]['label'] == 'Đã đọc Bảng lương.xlsx' and 'trang tính' in read[-1]['detail']
    events = await read_events(await client.post('/api/chat', json={'message': '__suaexcel__', 'conversation_id': conversation}))
    work = next(event['work'] for event in events if event['type'] == 'work')
    steps = {step['kind']: step for step in work['steps']}
    assert steps['note']['label'].startswith('Mình thêm cột "Ghi chú Peto"')
    assert steps['tool']['label'] == 'Đã sửa Bảng lương.xlsx' and 'thay đổi' in steps['tool']['detail']
    saved = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]
    assert saved['content'].startswith('Đã sửa tệp **Bảng lương.xlsx**')


async def test_companion_turns_keep_their_own_status(client, monkeypatch):
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Scripted())
    events = await read_events(await client.post('/api/chat', json={'message': 'Chào', 'mode': 'companion'}))
    assert not any(event['type'] in ('step', 'work') for event in events)


async def test_branch_keeps_the_log_and_old_databases_gain_the_column(client, tmp_path, monkeypatch):
    conversation = await db.create_conversation(TEST_OWNER, 'Có nhật ký')
    await db.add_message(conversation, 'user', 'Câu đầu')
    work = {'ms': 4200, 'steps': [{'id': 'think-1', 'kind': 'think', 'label': 'Đã suy nghĩ', 'state': 'done', 'start': 0, 'end': 4200}], 'complete': True}
    await db.add_message(conversation, 'assistant', 'Trả lời', work=work)
    second = await db.add_message(conversation, 'user', 'Câu hai')
    events = await read_events(await client.post('/api/chat', json={'conversation_id': conversation, 'branch_message_id': second,
                                                                     'message': 'Câu hai đã sửa'}))
    branch = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    copied = await db.get_messages(TEST_OWNER, branch)
    assert copied[1]['work'] == work and copied[0]['work'] is None

    path = tmp_path / 'old.db'
    monkeypatch.setattr(db_connection, 'DB_PATH', path)
    async with aiosqlite.connect(path) as connection:
        await connection.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, created_at REAL)')
        await connection.execute("INSERT INTO messages VALUES (1, 'cu', 'assistant', 'Tin cũ', 1)")
        await connection.commit()
    await db.init_db()
    async with aiosqlite.connect(path) as connection:
        assert await (await connection.execute('SELECT content, work FROM messages')).fetchone() == ('Tin cũ', '')
