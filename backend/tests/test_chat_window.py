"""Cửa sổ lịch sử theo ngân sách của tab Trò chuyện (G1.2): gửi hết khi vừa, cắt một khối lớn khi vượt, giữ mốc cắt."""
import pytest

import storage as db
from conftest import TEST_OWNER, read_events
from features.chat import context, context_budget, service
from storage import chat_context as store
from test_chat_context import summary_value


@pytest.fixture
def summarizer(monkeypatch):
    calls = []

    async def fake(model, previous, batch, budget):
        calls.append([part['id'] for part in batch])
        return summary_value(batch, previous)
    monkeypatch.setattr(context, 'summarize', fake)
    return calls


async def add_turns(cid, count, size=40, start=0):
    for index in range(start, start + count):
        await db.add_message(cid, 'user', f'Câu hỏi {index}: ' + 'a' * size)
        await db.add_message(cid, 'assistant', f'Trả lời {index}: ' + 'b' * size)


async def test_sixty_short_messages_are_all_sent(client, monkeypatch, summarizer):
    """Trước G1.2 chỉ 20 tin gần nhất được gửi nguyên văn; giờ 60 tin ngắn vừa ngân sách thì gửi đủ, không tóm tắt."""
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    await add_turns(cid, 30)
    seen = []

    class Provider:
        async def stream(self, **kwargs):
            seen.append(kwargs['messages'])
            yield 'Đã nhận.'
    monkeypatch.setattr(service, 'get_provider', lambda _: Provider())
    events = await read_events(await client.post('/api/chat', json={
        'conversation_id': cid, 'message': 'Câu thứ 61', 'model': 'luna', 'effort': 'low'}))
    assert events[-1]['type'] == 'done', events
    assert len(seen[0]) == 61 and seen[0][0].content.startswith('Câu hỏi 0:')
    assert not summarizer
    assert await store.window_start(TEST_OWNER, cid) == 0


def small_budget(monkeypatch, value=9000):
    real = context.policy

    def policy(model):
        return {**real(model), 'input': value}
    monkeypatch.setattr(context, 'policy', policy)


async def test_over_budget_cuts_one_big_block_then_keeps_the_cut_for_several_turns(monkeypatch, summarizer):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    small_budget(monkeypatch)
    await add_turns(cid, 14, size=600)
    starts, firsts, histories = [], [], []
    for turn in range(7):
        await db.add_message(cid, 'user', f'Lượt mới {turn}: ' + 'c' * 600)
        rows = await db.get_messages(TEST_OWNER, cid, limit=200)
        result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 200)
        starts.append(await store.window_start(TEST_OWNER, cid))
        firsts.append(result.history[0].content)
        histories.append([message.content for message in result.history])
        await db.add_message(cid, 'assistant', f'Đáp {turn}: ' + 'd' * 600)
    # Lượt đầu vượt ngân sách: cắt còn khoảng một nửa, đúng ở đầu một tin người dùng.
    assert starts[0] and firsts[0].startswith('Câu hỏi')
    assert len(histories[0]) < 30 // 2 + 2
    # Năm lượt tiếp theo giữ nguyên mốc: lịch sử lượt trước (trừ tin hiện tại) là phần đầu của lượt sau.
    assert len(set(starts[:6])) == 1, starts
    for earlier, later in zip(histories[:5], histories[1:6]):
        assert later[:len(earlier)] == earlier
    # Tóm tắt chỉ chạy ở lần cắt, không chạy lại ở mỗi lượt.
    assert len(summarizer) == len(set(starts))


async def test_over_the_message_cap_cuts_to_half_and_keeps_it(monkeypatch, summarizer):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    await add_turns(cid, 5)
    starts, sizes = [], []
    for turn in range(6):
        await db.add_message(cid, 'user', f'Lượt mới {turn}')
        rows = await db.get_messages(TEST_OWNER, cid, limit=12)
        result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 12)
        starts.append(await store.window_start(TEST_OWNER, cid))
        sizes.append(len(result.history))
        await db.add_message(cid, 'assistant', f'Đáp {turn}')
    # 10 tin cũ + 1: chưa đầy 12. Lượt 2 đầy trần: ghi mốc, chưa cắt (1 tin vừa rời 12 tin mới nhất được giữ nguyên văn
    # như trước nay, vì chưa đủ một lô tóm tắt). Lượt 3 vượt: cắt còn tối đa 6 tin, rồi giữ mốc.
    assert starts[0] == 0 and sizes[0] == 11
    assert starts[1] and sizes[1] == 13
    assert starts[2] > starts[1] and sizes[2] <= 6
    assert starts[3] == starts[4] == starts[2] and sizes[3] == sizes[2] + 2 and sizes[4] == sizes[2] + 4


async def test_a_saved_cut_newer_than_the_conversation_is_ignored(summarizer):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    await add_turns(cid, 3)
    await store.set_window_start(TEST_OWNER, cid, 10 ** 9)
    rows = await db.get_messages(TEST_OWNER, cid, limit=200)
    result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 200)
    assert len(result.history) == 6


async def test_window_start_is_owner_scoped(summarizer):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    await store.set_window_start('discord:someone-else', cid, 5)
    assert await store.window_start(TEST_OWNER, cid) == 0
    await store.set_window_start(TEST_OWNER, cid, 5)
    assert await store.window_start('discord:someone-else', cid) == 0
    assert await store.window_start(TEST_OWNER, cid) == 5


async def test_a_turn_does_not_wait_for_a_background_summary_holding_the_lock(summarizer):
    """G1.3b: trên app thật, lượt gửi ngay sau lượt trước chờ thêm 1,9 giây vì tóm tắt nền giữ khóa hội thoại. Lượt Chat
    chỉ đọc bản tóm tắt đã lưu nên không lấy khóa đó."""
    import asyncio
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    await add_turns(cid, 4)
    lock = context._locks.setdefault((TEST_OWNER, cid), asyncio.Lock())
    await lock.acquire()
    try:
        rows = await db.get_messages(TEST_OWNER, cid, limit=200)
        result = await asyncio.wait_for(context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 200,
                                                        summarize_now=False), 2)
        assert len(result.history) == 8
    finally:
        lock.release()


async def test_background_summary_never_moves_the_window(monkeypatch, summarizer):
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    small_budget(monkeypatch)
    await add_turns(cid, 14, size=600)
    await context.compact(TEST_OWNER, cid, 'peto', 'Peto', 200)
    assert await store.window_start(TEST_OWNER, cid) == 0
    # Vẫn tóm tắt tới mốc mà lượt sau sẽ cắt, không vượt quá nó.
    assert summarizer
    rows = await db.get_messages(TEST_OWNER, cid, limit=200)
    await db.add_message(cid, 'user', 'Lượt mới: ' + 'c' * 600)
    rows = await db.get_messages(TEST_OWNER, cid, limit=200)
    result = await context.prepare(TEST_OWNER, cid, 'peto', 'Peto', rows, [], 200, summarize_now=False)
    start = await store.window_start(TEST_OWNER, cid)
    assert start and (await store.state(TEST_OWNER, cid))['cursor_id'] < start
    assert result.history[0].content.startswith('Câu hỏi')
