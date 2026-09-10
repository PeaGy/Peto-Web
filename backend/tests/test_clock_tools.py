import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import chat_tools
import main
from ai.base import ChatMessage, ProviderError, StreamChunk
from ai.xai import MAX_TOOL_ROUNDS, XAIProvider
from config import XAI_MAX_OUTPUT_TOKENS
from conftest import read_events

FIXED = datetime(2026, 9, 9, 18, 5, 6, tzinfo=UTC)


@pytest.fixture
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED.astimezone(tz or UTC)
    monkeypatch.setattr(chat_tools, 'datetime', Clock)


def test_local_date_crosses_midnight():
    result = chat_tools.current_datetime('Asia/Barnaul', now=FIXED)
    assert result['date'] == '2026-09-10'
    assert result['time'] == '01:05:06'
    assert result['weekday'] == 'Thứ Năm'
    assert result['utc_offset'] == 'UTC+07:00'
    assert chat_tools.current_datetime('America/Los_Angeles', now=FIXED)['date'] == '2026-09-09'


@pytest.mark.parametrize(('month', 'offset'), [(1, 'UTC-05:00'), (7, 'UTC-04:00')])
def test_daylight_saving_is_applied(month, offset):
    assert chat_tools.current_datetime('America/New_York', now=datetime(2026, month, 10, tzinfo=UTC))['utc_offset'] == offset


@pytest.mark.parametrize('arguments', ['[]', '{bad', '{"timezone":"../../etc/passwd"}', '{"timezone":123}', '{"timezone":"Not/AZone"}', '{"command":"anything"}'])
def test_tool_arguments_are_validated(arguments):
    assert 'error' in chat_tools.execute_tool('get_current_datetime', arguments)


def test_only_registered_tool_can_run():
    assert 'error' in chat_tools.execute_tool('run_command', '{}')


async def test_web_clock_reaches_chat_and_persists_plain_text(client, fixed_clock):
    response = await client.post('/api/chat', json={'message':'Bây giờ mấy giờ?', 'timezone':'Asia/Barnaul'})
    events = await read_events(response)
    assert events[-1]['type'] == 'done'
    text = ''.join(e['text'] for e in events if e['type'] == 'delta')
    assert '01:05:06' in text and '10/09/2026' in text and 'Asia/Barnaul' in text
    assert 'function_call' not in text and 'checked_at_utc' not in text
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()['messages']
    assert saved[-1]['content'] == text.strip()


async def test_mui_gio_la_thi_roi_ve_mac_dinh_chu_khong_chan_chat(client, fixed_clock):
    """Trình duyệt gửi múi giờ lạ vẫn phải chat được.

    Bản trước trả 400 và chặn hẳn tin nhắn. Nhưng gửi RỖNG thì vốn đã được rơi
    về mặc định, nên chặn cứng trường hợp "có gửi nhưng dạng lạ" là bất đối
    xứng — và nó làm cả một loại thiết bị không chat được (điện thoại gửi những
    thứ như 'GMT+7').
    """
    response = await client.post('/api/chat', json={'message':'Bây giờ mấy giờ?', 'timezone':'GMT+7'})
    events = await read_events(response)
    assert events[-1]['type'] == 'done'
    text = ''.join(e['text'] for e in events if e['type'] == 'delta')
    # Rơi về PETO_DEFAULT_TIMEZONE, và lượt chat được lưu bình thường.
    assert 'Asia/Ho_Chi_Minh' in text
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()['messages']
    assert saved[-1]['content'] == text.strip()


def test_cong_cu_van_bao_loi_khi_model_doi_mui_gio_sai():
    """Chỉ múi giờ của trình duyệt mới được rơi về mặc định.

    Model gọi get_current_datetime là nó đòi ĐÚNG một múi giờ cụ thể; lặng lẽ
    đổi sang mặc định sẽ khiến Peto trả lời giờ Việt Nam khi được hỏi giờ Paris.
    """
    ket_qua = chat_tools.execute_tool('get_current_datetime', '{"timezone": "GMT+7"}')
    assert 'GMT+7' in ket_qua['error']
    assert 'datetime' not in ket_qua


async def test_each_request_gets_own_timezone_and_fresh_clock(client, monkeypatch, fixed_clock):
    seen = []
    class Spy:
        async def stream(self, **kwargs):
            seen.append(kwargs)
            await asyncio.sleep(0)
            yield 'OK'
    monkeypatch.setattr(main, 'get_provider', lambda: Spy())
    await asyncio.gather(*[
        client.post('/api/chat', json={'message':'hi', 'timezone':zone})
        for zone in ['UTC', 'Asia/Barnaul']
    ])
    by_zone = {entry['timezone']:entry['system_prompt'] for entry in seen}
    assert '2026-09-09, 18:05:06' in by_zone['UTC']
    assert '2026-09-10, 01:05:06' in by_zone['Asia/Barnaul']
    class NextDay(datetime):
        @classmethod
        def now(cls, tz=None):
            return (FIXED + timedelta(days=1)).astimezone(tz or UTC)
    monkeypatch.setattr(chat_tools, 'datetime', NextDay)
    await client.post('/api/chat', json={'message':'Hôm nay?', 'timezone':'UTC'})
    assert '2026-09-10, 18:05:06' in seen[-1]['system_prompt']


async def test_long_web_messages_and_replies_are_not_cut(client, monkeypatch):
    long_input = 'Nội dung dài. ' * 500
    long_reply = 'Phân tích đầy đủ. ' * 1000
    class LongProvider:
        async def stream(self, **kwargs):
            assert kwargs['messages'][-1].content == long_input.strip()
            yield long_reply
    monkeypatch.setattr(main, 'get_provider', lambda: LongProvider())
    events = await read_events(await client.post('/api/chat', json={'message':long_input}))
    assert events[-1]['type'] == 'done'
    assert ''.join(e['text'] for e in events if e['type'] == 'delta') == long_reply
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()['messages']
    assert saved[-1]['content'] == long_reply.strip()


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return vars(self).copy()


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.closed = False
    async def __aiter__(self):
        for event in self.events:
            yield event
    async def close(self):
        self.closed = True


def done(*items):
    return SimpleNamespace(type='response.completed', response=SimpleNamespace(status='completed', output=list(items)))


def call(name='get_current_datetime', arguments='{"timezone":null}'):
    return Item(type='function_call', id='fc_1', call_id='call_1', name=name, arguments=arguments, status='completed')


def fake_provider(monkeypatch, streams):
    requests = []
    iterator = iter(streams)
    async def create(**kwargs):
        requests.append(deepcopy(kwargs))
        return next(iterator)
    provider = XAIProvider()
    monkeypatch.setattr(provider, '_prepare', AsyncMock())
    monkeypatch.setattr(provider._client.responses, 'create', create)
    return provider, requests


async def test_xai_tool_roundtrip_preserves_context_and_hides_tool_data(monkeypatch, fixed_clock):
    tool = call()
    reasoning = Item(type='reasoning', id='r1', summary=[], encrypted_content='opaque-test-value')
    first = FakeStream([SimpleNamespace(type='response.output_item.done', item=tool), done(reasoning, tool)])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Bây giờ là 01:05.'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    chunks = [part async for part in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Mấy giờ?')], timezone='Asia/Barnaul')]
    assert ''.join(chunks) == 'Bây giờ là 01:05.'
    assert len(requests) == 2 and first.closed and second.closed
    assert requests[0]['tools'][0]['name'] == 'get_current_datetime'
    assert requests[0]['max_output_tokens'] == XAI_MAX_OUTPUT_TOKENS
    assert requests[0]['store'] is False
    assert 'reasoning.encrypted_content' in requests[0]['include']
    assert requests[1]['input'][0]['role'] == 'user'
    result = requests[1]['input'][-1]
    assert result['call_id'] == 'call_1'
    assert json.loads(result['output'])['datetime'] == '2026-09-10T01:05:06+07:00'
    assert any(item.get('encrypted_content') == 'opaque-test-value' for item in requests[1]['input'])


async def test_reasoning_summary_is_not_mixed_into_the_answer(monkeypatch):
    stream = FakeStream([
        SimpleNamespace(type='response.reasoning_summary_text.delta', delta='Xét vận tốc rơi.'),
        SimpleNamespace(type='response.reasoning_text.delta', delta=' g=10.'),
        SimpleNamespace(type='response.output_text.delta', delta='42 m/s'),
        done(),
    ])
    provider, _ = fake_provider(monkeypatch, [stream])
    chunks = [part async for part in provider.stream(system_prompt='Peto', messages=[])]
    thinking = ''.join(part.text for part in chunks if isinstance(part, StreamChunk) and part.kind == 'thinking')
    answer = ''.join(part if isinstance(part, str) else part.text for part in chunks if not isinstance(part, StreamChunk) or part.kind == 'text')
    assert thinking == 'Xét vận tốc rơi. g=10.'
    assert answer == '42 m/s'
    assert stream.closed


async def test_incomplete_xai_reply_is_reported_and_stream_closed(monkeypatch):
    stream = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Chưa xong'), SimpleNamespace(type='response.incomplete')])
    provider, _ = fake_provider(monkeypatch, [stream])
    chunks = []
    with pytest.raises(ProviderError, match='giới hạn'):
        async for chunk in provider.stream(system_prompt='Peto', messages=[]):
            chunks.append(chunk)
    assert chunks == ['Chưa xong'] and stream.closed


async def test_endless_tool_requests_are_bounded(monkeypatch):
    streams = [FakeStream([done(call())]) for _ in range(MAX_TOOL_ROUNDS + 1)]
    provider, requests = fake_provider(monkeypatch, streams)
    with pytest.raises(ProviderError, match='tra cứu'):
        _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[])]
    assert len(requests) == MAX_TOOL_ROUNDS + 1
    assert all(stream.closed for stream in streams)


async def test_model_receives_tool_validation_error_instead_of_crashing(monkeypatch):
    first = FakeStream([done(call(arguments='{"timezone":"bad-zone"}'))])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Cậu muốn xem múi giờ nào?'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[])]
    assert 'error' in json.loads(requests[1]['input'][-1]['output'])
