"""Grok hứa tra web rồi kết thúc lượt mà không tra (22/11/2026, model peto, tìm web tự động: hỏi "thế regera đắt hơn
agera rs nhỉ?" thì chỉ nhận "…để mình lục xem đồ ngốc này đoán đúng không~"). Prompt cấm hứa suông; nhà cung cấp nhắc
tra một lần, lần nhắc bắt buộc tra: câu hứa thành câu dẫn trong nhật ký, câu trả lời có nguồn thay vào."""
import logging
from types import SimpleNamespace

import pytest

from ai import xai
from ai.base import ChatMessage, StreamChunk
from features.chat import service as chat_service
from prompts.chat import SEARCH_PROMISE_RULE, search_prompt
from conftest import read_events
from test_clock_tools import FakeStream, done, fake_provider
from test_follow_up import message, said, started, text
from test_web_search import SOURCE, search_call

PROMISE = 'Hỏi giá mà không chịu tra, để mình lục xem đồ ngốc này đoán đúng không~'
ANSWER = 'Regera đắt hơn: khoảng 1,9 triệu USD, Agera RS khoảng 1,5 triệu USD.'


def searched(answer=ANSWER):
    return FakeStream([started(search_call('in_progress')),
                       SimpleNamespace(type='response.output_item.done', item=search_call()),
                       text(answer), done(search_call(), message(answer))])


async def run(monkeypatch, streams, web_search='auto'):
    provider, requests = fake_provider(monkeypatch, streams)
    chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', web_search=web_search,
                                                       messages=[ChatMessage('user', 'thế regera đắt hơn agera rs nhỉ?')])]
    return chunks, requests


def kept(chunks) -> str:
    """Chữ cuối cùng người dùng thấy: "replace" bỏ bản nháp đang hiện."""
    out: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, StreamChunk) and chunk.kind == 'replace':
            out = []
        elif isinstance(chunk, str):
            out.append(chunk)
    return ''.join(out)


@pytest.mark.parametrize('reply', [
    PROMISE,
    'Hụt là đúng rồi... Mình kiểm tra lại cho chắc rồi spoil tiếp cho ad.',
    # Lần thứ hai, sau bản sửa đầu (22/11/2026 07:20 UTC, câu hỏi về arc Ringo trong manga).
    'Ba câu này mình không đoán tiếp nữa, đang đối lại đúng cảnh trong manga.',
    'Đợi xíu, đang xác minh lại.',
    "I'm checking the chapter now.",
    'Chờ tí mình tra giá mới nhất nha.',
    'Để Peto tìm thử nhé!',
    'Let me check the latest prices.',
    'I’ll look it up for you.',
])
def test_search_promises_are_recognised(reply):
    assert xai.announces_search(reply)


@pytest.mark.parametrize('reply', [
    ANSWER,
    'Bạn kiểm tra lại cấu hình rồi chạy lại nhé.',
    'Xin chào! Hôm nay bạn thế nào?',
    'Để xem nào, 2 + 2 = 4.',
    'You can check the docs later.',
    'Bạn đang tìm bản nào vậy?',          # hỏi lại người dùng
    'Cửa hàng đang mở cửa tới 9 giờ.',
    'Gyro sống vì Ringo chỉ bắn trúng vai.',
])
def test_plain_answers_are_not_promises(reply):
    assert not xai.announces_search(reply)


def test_search_prompt_forbids_empty_promises():
    for mode in ('auto', 'on'):
        assert SEARCH_PROMISE_RULE in search_prompt(mode, True)
    assert 'prices, specs and comparisons' in search_prompt('auto', True)
    assert 'promise to search' in search_prompt('off', True)
    assert 'promise to search' in search_prompt('auto', False)


async def test_a_search_promise_gets_one_forced_search(monkeypatch, caplog):
    with caplog.at_level('INFO', logger='peto_web.xai'):
        chunks, requests = await run(monkeypatch, [said(PROMISE), searched()])
    assert len(requests) == 2
    assert 'tool_choice' not in requests[0]
    assert requests[1]['tool_choice'] == 'required' and requests[1]['tools'] == [{'type': 'web_search'}]
    sent = requests[1]['input']
    assert sent[-1] == {'role': 'user', 'content': [{'type': 'input_text', 'text': xai.SEARCH_FOLLOW_UP}]}
    assert sent[-2]['type'] == 'message' and sent[-2]['content'][0]['text'] == PROMISE
    # Lần nhắc không có mốc "round" riêng: tra web thì câu hứa (bản nháp đang hiện) bị thay, rồi câu trả lời có nguồn.
    shape = [chunk if isinstance(chunk, str) else chunk.kind for chunk in chunks]
    assert shape.count('round') == 1 and shape.index('replace') > shape.index(PROMISE)
    assert kept(chunks) == ANSWER
    assert any('Nhắc tìm web' in record.message for record in caplog.records)


async def test_still_no_search_after_the_reminder_keeps_the_reply_and_warns(monkeypatch, caplog):
    with caplog.at_level('INFO', logger='peto_web.xai'):
        chunks, requests = await run(monkeypatch, [said(PROMISE), said(' ' + ANSWER + ' (chưa kiểm chứng)')])
    assert len(requests) == 2
    assert kept(chunks) == PROMISE + ' ' + ANSWER + ' (chưa kiểm chứng)'
    assert any(record.levelno == logging.WARNING and 'vẫn không tra' in record.message for record in caplog.records)


@pytest.mark.parametrize('reply, mode', [
    (ANSWER, 'auto'),                              # trả lời thẳng: không nhắc
    (PROMISE + ' ' + 'Chi tiết dài. ' * 30, 'auto'),  # câu dài là câu trả lời thật
    (PROMISE, 'off'),                              # người dùng tắt tìm web
])
async def test_no_reminder_outside_short_search_promises(monkeypatch, reply, mode):
    chunks, requests = await run(monkeypatch, [said(reply)], web_search=mode)
    assert len(requests) == 1 and kept(chunks) == reply


async def test_no_reminder_after_a_real_search(monkeypatch):
    stream = FakeStream([SimpleNamespace(type='response.output_item.done', item=search_call()),
                         text('Để mình kiểm tra thêm nhé.'), done(search_call(), message('Để mình kiểm tra thêm nhé.'))])
    _, requests = await run(monkeypatch, [stream])
    assert len(requests) == 1


async def test_chat_logs_the_promise_and_stores_the_searched_answer(client, monkeypatch):
    provider, requests = fake_provider(monkeypatch, [said(PROMISE), searched()])
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'thế regera đắt hơn agera rs nhỉ?'}))
    assert len(requests) == 2 and events[-1]['type'] == 'done'
    work = next(event['work'] for event in events if event['type'] == 'work')
    assert [step['label'] for step in work['steps'] if step['kind'] == 'note'] == [PROMISE]
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    stored = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages'][-1]
    assert stored['content'] == ANSWER
    assert [source['url'] for source in stored.get('sources') or []] == [SOURCE['url']]
