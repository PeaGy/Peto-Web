"""Chuẩn bị context dài của Chat; giữ lịch sử gốc, phạm vi và cursor khi tóm tắt từng lô."""
import asyncio
from contextlib import aclosing
from dataclasses import dataclass
import json
import logging
import weakref
from time import perf_counter

import aiosqlite
import anyio
from ai import ChatMessage, ProviderError, StreamChunk, get_provider
from core import config
from core import usage_events
from ai.models import MODELS
from features.chat.context_budget import policy, tokens, current as budget_context, ContextOverflow
from features.chat.history import _to_chat_messages, context_rows
from prompts.chat_context import SUMMARY_PROMPT, CONTEXT_NOTE
from shared.chat_history_tools import ChatHistory
from storage import chat_context as store, connection

logger = logging.getLogger('peto_web.chat_context')
_locks = weakref.WeakValueDictionary()
KEYS = ('constraints', 'facts', 'decisions', 'pending')
MIN_BATCH = 8


@dataclass
class Prepared:
    history: list
    prompt: str
    budget: dict
    history_tools: ChatHistory | None
    detail: str = ''
    # Envelope tóm tắt (CONTEXT_NOTE + JSON). Từ G1.1 không ghép vào prompt: nó đổi theo lượt nên đi trong khối runtime
    # ở đuôi đầu vào (features/chat/request_context.py).
    note: str = ''
    # Lượt Chat chuẩn bị với ``summarize_now=False`` (G1.3): có phần cũ đủ để tóm tắt nhưng chưa tóm tắt; service gọi
    # ``compact`` sau khi trả lời xong.
    summary_due: bool = False


def parse_summary(text, batch, previous):
    if len(text) > 6000:
        raise ValueError('Bản tóm tắt quá dài.')
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'version', *KEYS} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Cấu trúc bản tóm tắt không hợp lệ.')
    allowed = {part['id'] for part in batch}
    if previous:
        allowed.update(i for key in KEYS for row in previous[key] for i in row['source_ids'])
    for key in KEYS:
        if not isinstance(value[key], list) or len(value[key]) > 8:
            raise ValueError('Danh sách dữ kiện quá dài.')
        for row in value[key]:
            if (not isinstance(row, dict) or set(row) != {'text', 'source_ids'}
                    or not isinstance(row['text'], str) or not row['text'].strip() or not 1 <= len(row['text']) <= 400
                    or not isinstance(row['source_ids'], list) or not 1 <= len(row['source_ids']) <= 4
                    or any(type(i) is not int or i not in allowed for i in row['source_ids'])):
                raise ValueError('Dữ kiện thiếu nguồn hoặc trỏ tới tin chưa được đọc.')
    if not any(value[key] for key in KEYS) and any(part['text'].strip() for part in batch):
        raise ValueError('Bản tóm tắt rỗng không được làm trôi watermark.')
    return value


async def summarize(model, previous, batch, budget):
    text = json.dumps({'previous_summary': previous, 'fragments': batch}, ensure_ascii=False)
    if tokens(SUMMARY_PROMPT, text) > budget['input']:
        raise ContextOverflow('Lô tóm tắt vượt ngân sách.')
    pieces = []
    token = budget_context.set({**budget, 'summary_output': min(3072, budget['output'])})
    try:
        with usage_events.measurement(surface='chat', effort='low', purpose='summary'):
            async with asyncio.timeout(config.CHAT_SUMMARY_TIMEOUT):
                async with aclosing(get_provider(model).stream(system_prompt=SUMMARY_PROMPT,
                                    messages=[ChatMessage('user', text)], effort='low', web_search='off', tools_enabled=False)) as stream:
                    async for chunk in stream:
                        piece = chunk if isinstance(chunk, str) else chunk.text if isinstance(chunk, StreamChunk) and chunk.kind == 'text' else ''
                        pieces.append(piece)
                        if sum(map(len, pieces)) > 6000:
                            raise ValueError('Bản tóm tắt vượt giới hạn.')
    finally:
        budget_context.reset(token)
    return parse_summary(''.join(pieces), batch, previous)


async def _metadata(owner, cid, boundary, state):
    cursor_id, offset = (state['cursor_id'], state['cursor_offset']) if state else (0, 0)
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        scope = await (await db.execute("SELECT project_id FROM conversations WHERE id=? AND owner=? AND mode='chat' AND archived=0",
                                        (cid, owner))).fetchone()
        if scope is None:
            raise ProviderError('Hội thoại đã bị xóa hoặc lưu trữ; mở lại trước khi tiếp tục.')
        first = await (await db.execute('''SELECT id,substr(content,1,2000) AS excerpt,length(content)>2000 AS truncated,
            COALESCE((SELECT state FROM chat_turns WHERE owner=? AND user_message_id=m.id ORDER BY id DESC LIMIT 1),'complete') AS turn_state
            FROM messages m WHERE conversation_id=? AND role='user' ORDER BY id LIMIT 1''', (owner, cid))).fetchone()
        count = await (await db.execute('''SELECT COUNT(*) FROM messages WHERE conversation_id=? AND id<?
            AND (id>? OR (id=? AND length(content)>?))''', (cid, boundary, cursor_id, cursor_id, offset))).fetchone()
        return scope['project_id'], dict(first) if first else None, count[0]


async def _window(owner, cid, prompt, rows, cap, info, convert, save=True):
    """Cửa sổ lịch sử gửi nguyên văn (G1.2): bắt đầu từ mốc đã lưu, chỉ dời mốc một khối lớn.

    Trước đây cửa sổ là 20 tin mới nhất nên mỗi lượt mới đẩy tin cũ nhất ra và tiền tố request đổi ở mọi lượt (prompt
    cache không đọc lại được). Giờ: tin từ mốc trở đi được gửi hết nếu vừa ngân sách (``info['input']`` trừ phần dành
    sẵn) và không quá ``cap`` tin. Vượt một trong hai thì cắt phần đầu tới khi còn tối đa nửa phần ngân sách dành cho lịch
    sử và nửa ``cap``, ở đầu một tin người dùng, rồi lưu mốc mới; các lượt sau giữ mốc đó tới lần vượt kế tiếp.
    ``rows`` là tối đa ``cap`` tin mới nhất (cũ trước); tin đầu tiên của ``rows`` mới hơn mốc nghĩa là từ mốc tới nay
    đã quá ``cap`` tin. ``save=False`` (tóm tắt nền): tính mốc như thường nhưng không lưu; chỉ lượt Chat dời mốc."""
    reserve = min(12_000, info['input'] // 3)
    start = await store.window_start(owner, cid)
    if start and (not rows or start > rows[-1]['id']):
        start = 0          # Hội thoại đã bị cắt bớt (thử lại, rẽ nhánh): mốc cũ không còn dùng được.
    recent = [row for row in rows if row['id'] >= start] if start else list(rows)
    history = await convert(recent)
    over_cap = bool(start) and len(rows) >= cap and rows[0]['id'] > start
    if over_cap or tokens(prompt, history) + reserve > info['input']:
        target = tokens(prompt) + max(0, info['input'] - reserve - tokens(prompt)) // 2
        keep = max(2, cap // 2)
        cuts = [index for index, row in enumerate(recent) if row['role'] == 'user'] or [len(recent) - 1]
        low, high, best = 0, len(cuts) - 1, None
        # Tìm mốc sớm nhất còn vừa (càng cắt nhiều càng ít token, nên tìm nhị phân được).
        while low <= high:
            middle = (low + high) // 2
            candidate = recent[cuts[middle]:]
            converted = await convert(candidate)
            if len(candidate) <= keep and tokens(prompt, converted) <= target:
                best, high = (candidate, converted), middle - 1
            else:
                low = middle + 1
        recent, history = best if best else (recent[cuts[-1]:], await convert(recent[cuts[-1]:]))
        if save:
            await store.set_window_start(owner, cid, recent[0]['id'])
    elif save and not start and len(rows) >= cap and recent:
        # Lần đầu đầy trần: ghi mốc để lượt sau không trượt theo "cap tin mới nhất".
        await store.set_window_start(owner, cid, recent[0]['id'])
    return recent, history


async def prepare(owner, cid, model, prompt, rows, project_documents, window, *, summarize_now=True, save_window=True):
    """``summarize_now=False`` (lượt Chat, G1.3): không gọi model tóm tắt trước câu trả lời; dùng bản tóm tắt đã có, phần
    chưa tóm tắt ghi là chưa đại diện trong envelope, và báo ``summary_due`` để chạy ``compact`` sau lượt.

    Khóa theo hội thoại chỉ dành cho lần chạy có tóm tắt (ghi bản tóm tắt). Lượt Chat không lấy khóa: chỉ đọc bản đã lưu
    nên không phải chờ một lần tóm tắt nền của lượt trước còn đang chạy (đo trên app thật 13/11/2026: lượt gửi ngay sau
    chờ thêm 1,9 giây ở bước chuẩn bị). ``save_window=False``: không dời mốc cửa sổ (tóm tắt nền)."""
    if not summarize_now:
        return await _prepare(owner, cid, model, prompt, rows, project_documents, window, summarize_now, save_window)
    key = (owner, cid)
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    async with lock:
        return await _prepare(owner, cid, model, prompt, rows, project_documents, window, summarize_now, save_window)


async def compact(owner, cid, model, prompt, window, project_documents=()):
    """Tóm tắt phần cũ của hội thoại sau khi lượt đã trả lời xong (G1.3), cùng chỗ với đặt tên và ghi nhớ.

    Trước đây việc này chạy trong lượt, trước chữ đầu tiên (có thể chờ tới ``PETO_CHAT_SUMMARY_TIMEOUT_SECONDS``). Đọc lại
    tin mới nhất, rồi chạy đúng bước chuẩn bị có tóm tắt (cùng khóa theo hội thoại, cùng kiểm CAS khi lưu). Không bao giờ
    raise: lỗi chỉ để lại watermark cũ, lượt sau ghi phần đó là chưa đại diện như mọi khi."""
    from storage.conversations import get_messages
    try:
        rows = await get_messages(owner, cid, limit=window)
        if rows:
            # Không dời mốc cửa sổ: lượt Chat (không giữ khóa) là nơi duy nhất ghi mốc, nên hai bên không ghi đè nhau.
            await prepare(owner, cid, model, prompt, rows, list(project_documents), window, save_window=False)
    except Exception as error:
        logger.warning('Chưa tóm tắt được context Chat sau lượt (%s).', type(error).__name__)


async def _prepare(owner, cid, model, prompt, rows, project_documents, window, summarize_now=True, save_window=True):
    from storage.conversations import get_messages
    info = policy(model)
    # Dành chỗ cho schema, tool kết quả, summary và mốc thời gian; adapter kiểm lại request thật ở từng vòng.
    free = info['input'] - tokens(prompt) - min(12_000, info['input'] // 3)
    if free < 1024:
        raise ContextOverflow('Hướng dẫn và tài liệu dự án đã chiếm hết ngân sách Chat; hãy giảm phần tài liệu được chọn.')
    document_budget = max(256, min(config.MAX_DOCUMENT_CONTEXT_CHARS, int(free * .8)))
    recent = list(rows)
    async def convert(source):
        return await anyio.to_thread.run_sync(lambda: _to_chat_messages(context_rows(source), project_documents,
                                                                       document_budget=document_budget))
    recent, history = await _window(owner, cid, prompt, recent, window, info, convert, save=save_window)
    if tokens(prompt, history) + 2048 > info['input']:
        raise ContextOverflow('Tin nhắn và tài liệu hiện tại quá dài cho ngân sách Chat; hãy chia nhỏ nội dung.')
    boundary = recent[0]['id']
    try:
        saved = await store.state(owner, cid)
    except store.ContextVersionError as error:
        raise ProviderError(str(error)) from None
    summary = json.loads(saved['data'])['summary'] if saved else None
    project_id, anchor, pending = await _metadata(owner, cid, boundary, saved)
    detail = ''
    batch = await store.spans(owner, cid, boundary, saved['cursor_id'] if saved else 0, saved['cursor_offset'] if saved else 0)
    due = bool(config.CHAT_SUMMARY_ENABLED and batch and (pending >= MIN_BATCH or batch[0]['start'] > 0
                                                         or sum(len(p['text']) for p in batch) >= 8000))
    if due and summarize_now:
        summary_started, summary_outcome = perf_counter(), 'cancelled'
        try:
            value = await summarize(model, summary, batch, info)
            if await store.save(owner, cid, project_id, saved, batch, boundary, value, info['identity']):
                saved = await store.state(owner, cid)
                summary = json.loads(saved['data'])['summary'] if saved else None
                detail = ('Đã cập nhật tóm tắt ngữ cảnh; lịch sử gốc vẫn được giữ.' if saved else
                          'Nguồn vừa thay đổi; chưa dùng bản tóm tắt mới.')
                summary_outcome = 'complete' if saved else 'source_changed'
            else:
                summary_outcome = 'source_changed'
                detail = 'Nguồn vừa thay đổi; chưa dùng bản tóm tắt mới.'
                # Bản cũ có thể đã bị trigger xóa; không đưa dữ kiện lỗi thời vào lượt này.
                saved = await store.state(owner, cid)
                summary = json.loads(saved['data'])['summary'] if saved else None
        except Exception as error:
            summary_outcome = 'overflow' if isinstance(error, ContextOverflow) else 'timeout' if isinstance(error, TimeoutError) else 'error'
            detail = 'Chưa tóm tắt được phần cũ; giữ nguyên lịch sử để tra lại, không đánh dấu đã đọc phần đó.'
            logger.warning('Chưa cập nhật được context Chat (%s); giữ watermark cũ.', type(error).__name__)
        finally:
            usage_events.record('chat_event', service=MODELS[model].service, model=model, surface='chat', effort='low',
                purpose='summary', outcome=summary_outcome, complete=summary_outcome == 'complete',
                elapsed_ms=round((perf_counter() - summary_started) * 1000))
    # Trigger có thể vừa vô hiệu bản đã đọc trong lúc chờ model/I/O; lấy snapshot mới trước khi ghép prompt.
    try:
        saved = await store.state(owner, cid)
    except store.ContextVersionError as error:
        raise ProviderError(str(error)) from None
    summary = json.loads(saved['data'])['summary'] if saved else None
    # Lô nhỏ chưa cần gọi model: giữ nguyên văn vài tin vừa rời cửa sổ thay vì tóm tắt mỗi lượt.
    _, anchor, pending = await _metadata(owner, cid, boundary, saved)
    if 0 < pending < MIN_BATCH:
        expanded = await get_messages(owner, cid, limit=max(window, len(recent)) + MIN_BATCH)
        cursor_id = saved['cursor_id'] if saved else 0
        prefix = [row for row in expanded if cursor_id <= row['id'] < boundary]
        if MODELS[model].service == 'xai' and prefix:
            # G1.1c: tin cũ nạp lại cũng mang khối runtime đã gửi Grok, như các tin service đã nạp.
            from storage.conversations import message_runtimes
            runtimes = await message_runtimes(owner, cid)
            prefix = [{**row, 'runtime': runtimes[row['id']]} if row['id'] in runtimes else row for row in prefix]
        candidate = prefix + recent
        candidate_history = await convert(candidate)
        if tokens(prompt, candidate_history) + min(12_000, info['input'] // 3) <= info['input']:
            recent, history = candidate, candidate_history
            boundary = recent[0]['id']
    _, anchor, gap = await _metadata(owner, cid, boundary, saved)
    old_files = await store.file_index(owner, cid)
    generated = await store.artifact_index(owner, cid)
    hidden = bool(saved or gap or (anchor and anchor['id'] < boundary) or
                  any(file['message_id'] < boundary for file in [*old_files, *generated]))
    if hidden:
        envelope = {'version': 1, 'summary': summary, 'summary_model': saved['model'] if saved else None,
                    'summary_updated_at': saved['updated_at'] if saved else None,
                    'coverage': {'message_id': saved['cursor_id'], 'character': saved['cursor_offset'],
                                 'digest': saved['digest']} if saved else None,
                    'first_user_message': anchor if anchor and anchor['id'] < boundary else None,
                    'unrepresented_messages': gap, 'recent_from_id': boundary,
                    'files': [{'name': f['filename'], 'message_id': f['message_id'],
                               'origin': 'generated' if 'version' in f else 'upload'}
                              for f in sorted([*old_files, *generated], key=lambda item: item['message_id'])][-64:],
                    'file_index_is_bounded': True}
        note = CONTEXT_NOTE + json.dumps(envelope, ensure_ascii=False)
    else:
        note = ''
    # Ngân sách tính envelope như khi nó còn nằm trong prompt (cùng ký tự, chỉ đổi chỗ).
    counted = prompt + '\n\n' + note if note else prompt
    if tokens(counted, history) + 2048 > info['input']:
        raise ContextOverflow('Bản tóm tắt và ngữ cảnh hiện tại vượt ngân sách; hãy giảm tài liệu dự án hoặc chia nhỏ yêu cầu.')
    logger.info('chat_context model=%s estimated_tokens=%d input_limit=%d summary=%s gap=%d',
                model, tokens(counted, history), info['input'], bool(summary), gap)
    return Prepared(history, prompt, info, ChatHistory(owner, cid, rows[-1]['id'] + 1) if hidden else None, detail, note,
                    summary_due=due and not summarize_now)
