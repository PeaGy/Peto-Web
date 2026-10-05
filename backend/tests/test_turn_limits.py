"""Giới hạn thời gian của một lượt chat: chỉ dừng khi bị kẹt hoặc cả lượt quá dài, không cắt lúc Peto vẫn đang làm."""

import asyncio
from types import SimpleNamespace

from ai import xai
from ai.base import StreamChunk
from features.chat import service as chat_service
from conftest import read_events
from test_clock_tools import FakeStream, call, done, fake_provider


def limits(monkeypatch, idle: float, turn: float):
    monkeypatch.setitem(chat_service.RESPONSE_TIMEOUTS, 'low', idle)
    monkeypatch.setattr(chat_service, 'TURN_TIMEOUT_SECONDS', turn)


async def saved_reply(client, events) -> dict:
    conversation = events[0]['conversation_id']
    return (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]


async def test_steady_work_outlives_the_silence_limit(client, monkeypatch):
    """Trước đây cả lượt chỉ được 3/5/8 phút; giờ còn nhận được gì mới thì Peto làm tiếp."""
    limits(monkeypatch, idle=0.3, turn=10)

    class Working:
        async def stream(self, **kwargs):
            for _ in range(6):
                await asyncio.sleep(0.12)
                yield StreamChunk('pulse')
            yield 'Xong cả bảng.'

    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Working())
    events = await read_events(await client.post('/api/chat', json={'message': 'Sửa bảng', 'effort': 'low'}))
    assert events[-1]['type'] == 'done'
    assert (await saved_reply(client, events))['content'] == 'Xong cả bảng.'


async def test_silence_stops_the_turn_and_keeps_partial_text(client, monkeypatch):
    limits(monkeypatch, idle=0.3, turn=10)

    class Stuck:
        async def stream(self, **kwargs):
            yield 'Đã sửa một phần.'
            await asyncio.sleep(30)

    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Stuck())
    events = await read_events(await client.post('/api/chat', json={'message': 'Sửa bảng', 'effort': 'low'}))
    assert events[-1]['type'] == 'error'
    assert 'không nhận được gì thêm' in events[-1]['message']
    saved = await saved_reply(client, events)
    assert saved['content'] == 'Đã sửa một phần.' and saved['status'] == 'incomplete'


async def test_whole_turn_limit_stops_endless_work(client, monkeypatch):
    limits(monkeypatch, idle=0.3, turn=0.6)

    class Endless:
        async def stream(self, **kwargs):
            yield 'Đang làm.'
            while True:
                await asyncio.sleep(0.05)
                yield StreamChunk('pulse')

    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Endless())
    response = await client.post('/api/chat', json={'message': 'Sửa bảng', 'effort': 'low'})
    raw = ''.join([line async for line in response.aiter_text()])
    # Nhịp "vẫn đang làm" đi dưới dạng chú thích SSE: trình duyệt bỏ qua, kết nối không im lặng.
    assert ': ping' in raw
    error = [line for line in raw.split('\n') if line.startswith('data: ') and '"error"' in line]
    assert error and 'mức tối đa của một lượt' in error[0]


def test_timeout_messages_say_how_long():
    assert chat_service._duration(300) == '5 phút'
    assert chat_service._duration(90) == '1 phút 30 giây'
    assert chat_service._duration(45) == '45 giây'
    idle = chat_service._timeout_message(chat_service.TurnTimeout('idle', 300), 'medium')
    assert 'Peto chờ 5 phút' in idle
    turn = chat_service._timeout_message(chat_service.TurnTimeout('turn', 900), 'medium')
    assert 'đã chạy 15 phút' in turn and 'tiếp tục' in turn
    # TimeoutError lạ (không do bộ đếm của lượt) vẫn có lời báo theo mức suy nghĩ.
    assert 'không nhận được gì thêm' in chat_service._timeout_message(TimeoutError(), 'low')


async def test_provider_pulses_while_grok_writes_a_long_tool_call(monkeypatch):
    """Lệnh công cụ dài (nhiều thay đổi Excel) stream từng mảnh tham số mà không có chữ nào để hiện."""
    monkeypatch.setattr(xai, 'PULSE_SECONDS', 0)
    writing = [SimpleNamespace(type='response.function_call_arguments.delta', delta='{"a":') for _ in range(3)]
    first = FakeStream([*writing, done(call())])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Xong.'), done()])
    provider, _ = fake_provider(monkeypatch, [first, second])
    chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[], web_search='off')]
    pulses = [chunk for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == 'pulse']
    assert len(pulses) >= 3
    assert ''.join(chunk for chunk in chunks if isinstance(chunk, str)) == 'Xong.'


async def test_workbook_conversations_get_more_tool_rounds(monkeypatch):
    """Sửa một bảng nhiều lỗi cần vài lần edit_spreadsheet và lần làm lại khi bị từ chối."""
    from features.documents.tools import current_session

    session = SimpleNamespace(workbooks=[{'name': 'bang.xlsx', 'kind': 'attachment', 'id': 1}])
    token = current_session.set(session)
    try:
        rounds = xai.MAX_TOOL_ROUNDS + 2
        streams = [FakeStream([done(call())]) for _ in range(rounds)]
        streams.append(FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã sửa xong.'), done()]))
        provider, requests = fake_provider(monkeypatch, streams)
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[], web_search='off')]
    finally:
        current_session.reset(token)
    assert ''.join(chunk for chunk in chunks if isinstance(chunk, str)).endswith('Đã sửa xong.')
    # Quá 3 vòng mà vẫn được gọi công cụ: không bị ép tổng hợp sớm.
    assert all(request['tools'] for request in requests[:rounds])
    assert xai.MAX_WORKBOOK_TOOL_ROUNDS > xai.MAX_TOOL_ROUNDS
