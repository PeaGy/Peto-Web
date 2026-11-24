"""Tìm trong cuộc Trò chuyện cũ (24/11/2026, kiểu Claude, cách 1): phạm vi, tìm không dấu, đọc từng phần, công tắc và
bước "Đang làm" có danh sách cuộc mở lại được. Không gọi AI thật."""
import json
import time
from types import SimpleNamespace

import aiosqlite

from conftest import TEST_OWNER, read_events
from core import config
from features.chat import service as chat_service
import storage as db
from storage.connection import connect
from shared import past_chat_tools
from shared.past_chat_tools import PastChats
from test_clock_tools import FakeStream, call, done
from test_follow_up import message, said, started

OTHER = 'google:nguoi-khac'


async def chat(owner, title, lines, project_id=None, persona='assistant', archived=False, updated=None):
    cid = await db.create_conversation(owner, title, persona=persona, project_id=project_id)
    for role, text in lines:
        await db.add_message(cid, role, text)
    async with connect() as conn:
        await conn.execute('UPDATE conversations SET archived=?, updated_at=COALESCE(?, updated_at) WHERE id=?',
                           (int(archived), updated, cid))
        await conn.commit()
    return cid


async def fresh():
    await db.init_db()
    async with connect() as conn:
        await conn.execute('DELETE FROM conversations WHERE owner IN (?, ?)', (TEST_OWNER, OTHER))
        await conn.execute('DELETE FROM chat_settings WHERE owner=?', (TEST_OWNER,))
        await conn.commit()


async def test_search_stays_in_scope_and_ignores_accents(client):
    await fresh()
    current = await chat(TEST_OWNER, 'Cuộc đang mở', [('user', 'Excel ở đây không được tìm')])
    excel = await chat(TEST_OWNER, 'Sửa bảng lương', [('user', 'Bảng lương bị lỗi #VALUE! trong Excel'),
                                                     ('assistant', 'Bỏ khoảng trắng ở cột B rồi dùng SUMIFS thay SUM.')])
    await chat(TEST_OWNER, 'Đã lưu trữ', [('user', 'excel cũ đã lưu trữ')], archived=True)
    await chat(TEST_OWNER, 'Nhập vai cũ', [('user', 'excel nhập vai')], persona='roleplay')
    await chat(OTHER, 'Của người khác', [('user', 'excel của người khác')])
    project = (await client.post('/api/projects', json={'name': 'Dự án riêng'})).json()['id']
    in_project = await chat(TEST_OWNER, 'Trong dự án', [('user', 'excel trong dự án')], project_id=project)
    result = await PastChats(TEST_OWNER, current, None).run('search_past_chats', json.dumps({'query': 'bang luong excel', 'days': None}))
    assert result['ok'] and [item['conversation_id'] for item in result['chats']] == [excel]
    assert result['chats'][0]['title'] == 'Sửa bảng lương' and 'Excel' in result['chats'][0]['snippets'][0]['text']
    assert result['_chats'] == [{'id': excel, 'title': 'Sửa bảng lương', 'at': result['_chats'][0]['at']}]
    # Trong dự án chỉ thấy cuộc của dự án đó.
    inside = await PastChats(TEST_OWNER, current, project).search('excel', None)
    assert [item['conversation_id'] for item in inside['chats']] == [in_project]
    # Không có gì khớp.
    assert (await PastChats(TEST_OWNER, current, None).search('khong co gi', None))['chats'] == []


async def test_recent_list_days_filter_and_versions_count_once(client):
    await fresh()
    current = await chat(TEST_OWNER, 'Đang mở', [('user', 'chào')])
    old = await chat(TEST_OWNER, 'Cũ lắm', [('user', 'chuyện cũ')], updated=time.time() - 40 * 86_400)
    recent = await chat(TEST_OWNER, 'Hôm qua', [('user', 'chuyện hôm qua')])
    sibling = await chat(TEST_OWNER, 'Hôm qua', [('user', 'chuyện hôm qua')])
    version_of_current = await chat(TEST_OWNER, 'Đang mở', [('user', 'chào')])
    async with connect() as conn:
        await conn.execute('UPDATE conversations SET branch_group=? WHERE id IN (?, ?)', (recent, recent, sibling))
        await conn.execute('UPDATE conversations SET branch_group=? WHERE id IN (?, ?)', (current, current, version_of_current))
        await conn.commit()
    listed = await PastChats(TEST_OWNER, current, None).search('', 7)
    ids = [item['conversation_id'] for item in listed['chats']]
    assert old not in ids and version_of_current not in ids and len(set(ids) & {recent, sibling}) == 1
    assert old in [item['conversation_id'] for item in (await PastChats(TEST_OWNER, current, None).search('', None))['chats']]


async def test_read_pages_and_refuses_out_of_scope(client, monkeypatch):
    await fresh()
    current = await chat(TEST_OWNER, 'Đang mở', [('user', 'chào')])
    long_chat = await chat(TEST_OWNER, 'Dài', [('user' if i % 2 == 0 else 'assistant', f'Đoạn {i} ' + 'x' * 2900) for i in range(8)])
    other = await chat(OTHER, 'Khác', [('user', 'bí mật')])
    tools = PastChats(TEST_OWNER, current, None)
    first = await tools.read(long_chat, 0)
    assert first['ok'] and first['next_id'] and len(first['messages']) < 8
    rest = await tools.read(long_chat, first['next_id'])
    assert [m['text'][:7] for m in first['messages'] + rest['messages']] == [f'Đoạn {i} ' for i in range(8)]
    assert rest['next_id'] is None
    assert not (await tools.read(other, 0))['ok']
    assert not (await tools.run('read_past_chat', '{"conversation_id": 5}'))['ok']


async def test_memory_settings_switch(client):
    await fresh()
    body = (await client.get('/api/companion/memory')).json()
    assert body['past_chats'] is True
    assert (await client.put('/api/companion/memory/settings', json={'past_chats': False})).json() == {'past_chats': False}
    body = (await client.get('/api/companion/memory')).json()
    assert body['past_chats'] is False and body['enabled'] is True
    assert (await client.put('/api/companion/memory/settings', json={})).status_code == 400


async def test_chat_turn_searches_old_chats_and_logs_them(client, monkeypatch):
    await fresh()
    excel = await chat(TEST_OWNER, 'Sửa bảng lương', [('user', 'Bảng lương lỗi Excel'), ('assistant', 'Dùng SUMIFS.')])
    search = call('search_past_chats', json.dumps({'query': 'excel', 'days': None}))
    first = FakeStream([started(search), done(search)])
    answer = 'Hôm trước mình chỉ bạn dùng SUMIFS.'
    from test_clock_tools import fake_provider
    provider, requests = fake_provider(monkeypatch, [first, said(answer), said('Tiêu đề')])
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Hôm trước bạn chỉ mình sửa Excel sao?',
                                                                    'web_search': 'off'}))
    assert events[-1]['type'] == 'done'
    assert any(tool.get('name') == 'search_past_chats' for tool in requests[0]['tools'])
    output = next(item for item in requests[1]['input'] if item.get('type') == 'function_call_output')
    sent = json.loads(output['output'])
    assert '_chats' not in sent and sent['chats'][0]['conversation_id'] == excel
    work = next(event['work'] for event in events if event['type'] == 'work')
    step = next(step for step in work['steps'] if step['kind'] == 'chats')
    assert step['label'] == 'Đã tìm trong cuộc trò chuyện cũ' and step['detail'] == '“excel”'
    assert [item['id'] for item in step['chats']] == [excel]


async def test_switch_off_hides_the_tools(client, monkeypatch):
    await fresh()
    await past_chat_tools.set_enabled(TEST_OWNER, False)
    from test_clock_tools import fake_provider
    provider, requests = fake_provider(monkeypatch, [said('Chào.'), said('Tiêu đề')])
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    await read_events(await client.post('/api/chat', json={'message': 'Chào', 'web_search': 'off'}))
    assert not any(tool.get('name') in past_chat_tools.NAMES for tool in requests[0]['tools'])


def test_all_past_chat_calls_of_a_turn_share_one_step():
    """24/11/2026: ba lần gọi (tìm, đọc, tìm) xen giữa các bước suy nghĩ thành ba bước lặp lại danh sách; giờ là một bước."""
    from features.chat.work_log import WorkLog
    log = WorkLog()
    regera = {'id': 'r', 'title': 'Giá Regera so với Agera RS', 'at': 1795400000}
    ssc = {'id': 's', 'title': 'So sánh SSC Tuatara và SVJ', 'at': 1795300000}
    log.thinking('Đang nghĩ')
    log.past_chats('Đang tìm…', True)
    log.past_chats('Đã tìm', False, {'ok': True, 'query': 'Regera Agera RS', 'chats': [regera, ssc]})
    log.thinking('Nghĩ tiếp')
    log.past_chats('Đang tìm…', True)
    log.past_chats('Đã tìm', False, {'ok': True, 'query': None, 'chats': [ssc], 'read': True})
    log.thinking('Nghĩ nữa')
    log.past_chats('Đang tìm…', True)
    log.past_chats('Đã tìm', False, {'ok': True, 'query': 'Regera đắt', 'chats': [regera, ssc]})
    steps = [step for step in log.close(True)['steps'] if step['kind'] == 'chats']
    assert len(steps) == 1
    assert steps[0]['detail'] == '“Regera Agera RS”, “Regera đắt” · đọc lại 1 cuộc'
    assert [chat['id'] for chat in steps[0]['chats']] == ['r', 's'] and steps[0]['state'] == 'done'
