"""Peto im lặng có chủ đích ở tab Trò chuyện: dịch vụ AI chạy xong mà không viết chữ nào (thử thật 13/11/2026 với
"intelligent test: do not reply": Grok chỉ suy nghĩ, 0 chữ). Chủ web chọn: lượt hoàn tất, không báo lỗi."""
import storage as db
from conftest import TEST_OWNER, read_events
from features.chat import service
from storage import chat_turns


def provider(seen, replies):
    class Provider:
        async def stream(self, **kwargs):
            seen.append(kwargs['messages'])
            text = replies.pop(0)
            if text:
                yield text
    return Provider()


async def test_an_empty_normal_reply_completes_and_is_left_out_of_later_history(client, monkeypatch):
    seen = []
    monkeypatch.setattr(service, 'get_provider', lambda _: provider(seen, ['', 'Chào bạn.']))
    events = await read_events(await client.post('/api/chat', json={'message': 'intelligent test: do not reply',
                                                                     'effort': 'low', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done', events
    assert not any(event['type'] == 'error' for event in events)
    cid = events[0]['conversation_id']
    rows = await db.get_messages(TEST_OWNER, cid)
    assert [row['role'] for row in rows] == ['user', 'assistant'] and rows[1]['content'] == ''
    assert rows[1]['turn_state'] == 'complete' and rows[1]['status'] == 'complete'
    events = await read_events(await client.post('/api/chat', json={'message': 'Giờ thì chào đi', 'conversation_id': cid,
                                                                     'effort': 'low', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done', events
    # Không gửi tin trợ lý rỗng cho model: hai tin người dùng liền nhau.
    assert [(m.role, m.content) for m in seen[1]] == [('user', 'intelligent test: do not reply'), ('user', 'Giờ thì chào đi')]


async def test_regenerating_a_silent_reply_stays_in_the_same_conversation(client, monkeypatch):
    """17/11/2026: Grok nghĩ 25 giây không viết chữ nào; bấm tạo lại tách ra hội thoại thứ hai trùng tên."""
    calls = []

    class Provider:
        # Lượt đầu im lặng; mọi lần gọi sau (cả lúc đặt tiêu đề) đều có chữ.
        async def stream(self, **kwargs):
            calls.append(1)
            if len(calls) > 1:
                yield 'Trả lời lại đây.'
    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    events = await read_events(await client.post('/api/chat', json={'message': 'Hex của jojo mạnh không?',
                                                                     'effort': 'low', 'web_search': 'off'}))
    cid = events[0]['conversation_id']
    question = (await db.get_messages(TEST_OWNER, cid))[0]['id']
    events = await read_events(await client.post('/api/chat', json={
        'conversation_id': cid, 'branch_message_id': question, 'message': 'Hex của jojo mạnh không?',
        'effort': 'low', 'web_search': 'off'}))
    meta = next(e for e in events if e['type'] == 'meta')
    assert meta['conversation_id'] == cid and events[-1]['type'] == 'done', events
    rows = await db.get_messages(TEST_OWNER, cid)
    assert [(r['role'], r['content']) for r in rows] == [('user', 'Hex của jojo mạnh không?'), ('assistant', 'Trả lời lại đây.')]
    assert len((await client.get(f'/api/conversations/{cid}/versions')).json()['versions']) == 1
    # Câu trả lời có chữ thì tạo lại vẫn tách phiên bản mới, giữ nguyên bản cũ như trước.
    events = await read_events(await client.post('/api/chat', json={
        'conversation_id': cid, 'branch_message_id': question, 'message': 'Hex của jojo mạnh không?',
        'effort': 'low', 'web_search': 'off'}))
    assert next(e for e in events if e['type'] == 'meta')['conversation_id'] != cid


async def test_companion_still_treats_an_empty_reply_as_not_answered(client, monkeypatch):
    seen = []
    monkeypatch.setattr(service, 'get_provider', lambda _: provider(seen, ['']))
    events = await read_events(await client.post('/api/chat', json={'message': 'đừng nói gì', 'mode': 'companion'}))
    assert events[-1]['type'] == 'error'
    assert 'chưa trả lời được' in events[-1]['message']


async def test_a_provider_error_with_no_text_is_still_an_error(client, monkeypatch):
    from ai import ProviderError

    class Broken:
        async def stream(self, **kwargs):
            raise ProviderError('Peto gặp lỗi khi đang trả lời. Thử lại nha.')
            yield ''
    monkeypatch.setattr(service, 'get_provider', lambda _: Broken())
    events = await read_events(await client.post('/api/chat', json={'message': 'chào', 'effort': 'low'}))
    assert events[-1]['type'] == 'error'
    request = events[0]
    assert request['type'] == 'meta'
    turn = await chat_turns.latest(TEST_OWNER, request['conversation_id']) if hasattr(chat_turns, 'latest') else None
    assert turn is None or turn['state'] != 'complete'


def test_only_grok_is_told_to_stay_silent_without_narrating():
    """Thử thật 13/11/2026: chỉ Grok viết câu thuật lại quyết định không trả lời; Luna và Haiku không cần câu này."""
    from prompts.chat import chat_prompt
    rule = '## Requests for no reply'
    assert rule in chat_prompt('peto')
    assert rule not in chat_prompt('luna') and rule not in chat_prompt('haiku')


async def test_closing_the_turn_stream_closes_the_provider_stream_at_once(client, monkeypatch):
    """G3.2: lượt chat tách thành nhiều bước; đóng lượt vẫn phải đóng ngay luồng của provider, như khi mọi thứ còn nằm
    trong một hàm. Từ 23/11/2026 trình duyệt ngắt không còn đóng lượt (lượt chạy nền tới hết), nên lượt được đóng như lúc
    tắt máy chủ."""
    import asyncio
    from features.chat import schemas
    from test_chat_turns import consume
    closed = asyncio.Event()

    class Provider:
        async def stream(self, **kwargs):
            try:
                yield 'Đang viết'
                await asyncio.Event().wait()
            finally:
                closed.set()
    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    original = chat_turns.persist
    seen = []

    async def persist(*args, **kwargs):
        # Lần lưu chốt (có state) phải xảy ra sau khi provider đã đóng, không chờ bộ thu gom rác của Python.
        if kwargs.get('state') is not None:
            seen.append(closed.is_set())
        return await original(*args, **kwargs)
    monkeypatch.setattr(chat_turns, 'persist', persist)
    response = await service.chat(schemas.ChatRequest(message='chào', effort='low', web_search='off'), owner=TEST_OWNER)
    body = response.body_iterator
    async for chunk in body:
        if 'Đang viết' in chunk:
            break
    await body.aclose()
    assert not closed.is_set()          # trình duyệt ngắt: lượt vẫn chạy
    await service.stop_detached_turns()
    assert closed.is_set() and seen == [True]
