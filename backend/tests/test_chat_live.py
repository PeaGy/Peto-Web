"""Đồng bộ trực tiếp tab Trò chuyện (features/chat/live.py): tab khác của cùng tài khoản nhận lượt đang chạy, tab mở
giữa chừng nhận lại từ đầu, tài khoản khác không nhận gì, và phát hỏng không làm hỏng lượt chat."""
import asyncio
import json

import pytest

from features.chat import live
from conftest import read_events, sign_in


def decode(data: str) -> dict:
    assert data.startswith('data: ')
    return json.loads(data[6:].strip())


@pytest.fixture(autouse=True)
def fresh_hub(monkeypatch):
    monkeypatch.setattr(live, 'hub', live.Hub())


def test_hub_replays_running_turns_and_keeps_accounts_apart():
    hub = live.hub
    hub.publish('a', 'r1', 'c1', {'type': 'meta', 'conversation_id': 'c1'})
    hub.publish('a', 'r1', 'c1', {'type': 'delta', 'text': 'Xin'})
    subscriber, replay = hub.subscribe('a')
    assert [decode(item)['event']['type'] for item in replay] == ['meta', 'delta']
    assert hub.subscribe('b')[1] == []
    hub.publish('a', 'r1', 'c1', {'type': 'delta', 'text': ' chào'})
    hub.publish('a', 'r1', 'c1', {'type': 'done', 'message_id': 7})
    got = [decode(subscriber.queue.get_nowait()) for _ in range(2)]
    assert [item['event']['type'] for item in got] == ['delta', 'done']
    assert all(item['request_id'] == 'r1' and item['conversation_id'] == 'c1' for item in got)
    # Lượt đã xong không còn để phát lại cho tab mở sau.
    assert hub.subscribe('a')[1] == []


def test_a_closed_stream_without_an_ending_tells_the_other_tabs():
    hub = live.hub
    hub.publish('a', 'r1', 'c1', {'type': 'meta', 'conversation_id': 'c1'})
    subscriber, _ = hub.subscribe('a')
    hub.finish('a', 'r1')
    assert decode(subscriber.queue.get_nowait())['event'] == {'type': 'live_end'}
    hub.finish('a', 'r1')  # lần hai không phát gì
    assert subscriber.queue.empty()


def test_huge_turns_stop_replaying_and_slow_tabs_are_dropped(monkeypatch):
    monkeypatch.setattr(live, 'MAX_REPLAY_BYTES', 300)
    hub = live.hub
    for index in range(10):
        hub.publish('a', 'r1', 'c1', {'type': 'delta', 'text': f'đoạn {index} ' * 3})
    replay = hub.subscribe('a')[1]
    assert [decode(item)['event']['type'] for item in replay] == ['live_partial']
    slow, _ = hub.subscribe('a')
    for _ in range(live.MAX_QUEUE + 1):
        hub.publish('a', 'r2', 'c1', {'type': 'delta', 'text': 'x'})
    assert slow.closed and slow not in hub.subscribers.get('a', set())


def test_too_many_tabs_are_refused(monkeypatch):
    monkeypatch.setattr(live, 'MAX_SUBSCRIBERS_PER_OWNER', 2)
    assert live.hub.subscribe('a') and live.hub.subscribe('a')
    assert live.hub.subscribe('a') is None and live.full('a')


async def _collect(stream, until: str, limit: int = 400) -> list[dict]:
    """Đọc luồng live tới khi thấy sự kiện ``until`` của một lượt (bỏ qua ping)."""
    found = []
    for _ in range(limit):
        data = await asyncio.wait_for(anext(stream), 10)
        if data.startswith(':'):
            continue
        payload = decode(data)
        found.append(payload)
        if payload.get('event', {}).get('type') == until:
            break
    return found


async def test_another_tab_sees_the_whole_turn_while_it_runs(client):
    owner = await sign_in(client)
    watcher = live.stream(owner)
    assert decode(await anext(watcher)) == {'type': 'live_ready'}
    async with client.stream('POST', '/api/chat', json={'message': 'chào Peto', 'request_id': 'request-live-0001'}) as response:
        own = await read_events(response)
    seen = await _collect(watcher, 'done')
    await watcher.aclose()
    events = [item['event'] for item in seen]
    assert events[0]['type'] == 'meta' and events[0]['message']['content'] == 'chào Peto'
    assert {item['request_id'] for item in seen} == {'request-live-0001'}
    assert {item['conversation_id'] for item in seen} == {events[0]['conversation_id']}
    # Cùng chữ với tab gửi, cùng thứ tự.
    assert ''.join(e['text'] for e in events if e['type'] == 'delta') == ''.join(e['text'] for e in own if e['type'] == 'delta')
    assert [e['type'] for e in own if e['type'] != 'reading'][-1] == 'done'
    assert not live.hub.turns  # lượt xong thì không còn giữ gì


async def test_a_tab_opened_mid_turn_gets_it_from_the_start():
    """Qua chính relay với một luồng giả (httpx ASGITransport gom cả phản hồi nên không mở giữa lượt được)."""
    from shared.events import sse

    async def turn():
        yield sse({'type': 'reading', 'text': 'Peto đang đọc tệp…'})  # trước meta: chỉ tab gửi thấy
        yield sse({'type': 'meta', 'conversation_id': 'c9', 'message': {'id': 1, 'role': 'user', 'content': 'kể chuyện'}})
        yield sse({'type': 'delta', 'text': 'Ngày xưa'})
        yield sse({'type': 'delta', 'text': ' có một'}) + sse({'type': 'delta', 'text': ' chú mèo'})
        yield sse({'type': 'done', 'message_id': 2})

    sender = live.relay('owner-x', 'request-mid-00001', turn())
    sent = [await anext(sender) for _ in range(3)]
    assert 'reading' in sent[0]
    late = live.stream('owner-x')
    assert decode(await anext(late)) == {'type': 'live_ready'}
    replay = [decode(await anext(late))['event'] for _ in range(2)]
    assert [event['type'] for event in replay] == ['meta', 'delta']
    async for _ in sender:
        pass
    rest = await _collect(late, 'done')
    await late.aclose()
    assert [item['event'].get('text') for item in rest] == [' có một', ' chú mèo', None]


async def test_other_accounts_and_companion_turns_are_not_shared(client, anon_client):
    owner = await sign_in(client)
    other = await sign_in(anon_client)
    mine, theirs = live.stream(owner), live.stream(other)
    await anext(mine), await anext(theirs)
    async with anon_client.stream('POST', '/api/chat', json={'message': 'tin riêng', 'request_id': 'request-other-0001'}) as response:
        await read_events(response)
    async with client.stream('POST', '/api/chat', json={'message': 'Companion', 'mode': 'companion',
                                                         'request_id': 'request-companion-1'}) as response:
        await read_events(response)
    seen = await _collect(theirs, 'done')
    assert {item['request_id'] for item in seen} == {'request-other-0001'}
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(anext(mine), 0.5)
    await mine.aclose(), await theirs.aclose()


async def test_live_endpoint_needs_a_session_and_caps_tabs(client, anon_client, monkeypatch):
    assert (await anon_client.get('/api/chat/live')).status_code == 401
    owner = await sign_in(client)
    monkeypatch.setattr(live, 'MAX_SUBSCRIBERS_PER_OWNER', 1)
    held = live.stream(owner)
    await anext(held)
    response = await client.get('/api/chat/live')
    assert response.status_code == 429
    await held.aclose()


async def test_a_broken_publish_never_breaks_the_chat(client, monkeypatch):
    await sign_in(client)

    def boom(*args, **kwargs):
        raise RuntimeError('hỏng')
    monkeypatch.setattr(live.hub, 'publish', boom)
    async with client.stream('POST', '/api/chat', json={'message': 'vẫn trả lời', 'request_id': 'request-boom-00001'}) as response:
        events = await read_events(response)
    assert events[-1]['type'] == 'done'
