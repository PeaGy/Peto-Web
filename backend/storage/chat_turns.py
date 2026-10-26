"""Vòng đời một lần tạo câu trả lời; mã yêu cầu riêng cho mỗi lần Thử lại."""
import time
import hashlib
import json
import aiosqlite
from fastapi import HTTPException
from storage import connection
from shared.source_activity import normalize_web, stop_web
from storage import chat_lineage, chat_quotes


async def init_tables(db):
    await db.execute('''CREATE TABLE IF NOT EXISTS chat_turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, request_id TEXT NOT NULL,
        state TEXT NOT NULL, conversation_id TEXT, user_message_id INTEGER, assistant_message_id INTEGER,
        created_at REAL NOT NULL, UNIQUE(owner,request_id),
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE)''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_chat_turn_user ON chat_turns(user_message_id,id)')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_chat_turn_assistant ON chat_turns(assistant_message_id,id)')
    columns = {row[1] for row in await (await db.execute('PRAGMA table_info(chat_turns)')).fetchall()}
    for name, definition in {'project_id': 'TEXT', 'scope_bound': 'INTEGER NOT NULL DEFAULT 0',
                             'user_digest': "TEXT NOT NULL DEFAULT ''", 'outcome': "TEXT NOT NULL DEFAULT ''",
                             'updated_at': 'REAL NOT NULL DEFAULT 0',
                             'checkpoint_truncated': 'INTEGER NOT NULL DEFAULT 0',
                             'model': "TEXT NOT NULL DEFAULT ''", 'effort': "TEXT NOT NULL DEFAULT ''"}.items():
        if name not in columns:
            await db.execute(f'ALTER TABLE chat_turns ADD COLUMN {name} {definition}')


async def get(owner, request_id):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute('SELECT * FROM chat_turns WHERE owner=? AND request_id=?', (owner, request_id))).fetchone()
        return dict(row) if row else None


async def reserve(owner, request_id):
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        row = await (await db.execute('SELECT state FROM chat_turns WHERE owner=? AND request_id=?', (owner, request_id))).fetchone()
        if row and row[0] != 'stopped':
            raise HTTPException(409, 'Lượt này đã được nhận. Kiểm tra lịch sử trước khi gửi lại nhé.')
        await db.execute('INSERT OR IGNORE INTO chat_turns(owner,request_id,state,created_at) VALUES(?,?,?,?)',
                         (owner, request_id, 'running', time.time()))
        await db.commit()


async def stop(owner, request_id):
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        # Có thể đến trước POST /chat: giữ dấu dừng để yêu cầu đến muộn không chạy AI.
        await db.execute('DELETE FROM chat_turns WHERE conversation_id IS NULL AND created_at<?', (time.time() - 86400,))
        await db.execute('INSERT OR IGNORE INTO chat_turns(owner,request_id,state,created_at) VALUES(?,?,?,?)',
                         (owner, request_id, 'stopped', time.time()))
        await db.execute("UPDATE chat_turns SET state='stopped' WHERE owner=? AND request_id=? AND state='running'", (owner, request_id))
        await db.commit()
    return await get(owner, request_id)


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


async def bind(owner, request_id, conversation_id, message_id=None, content=None, provider='', quote_id=None,
               quoted_source=None, model='', effort=''):
    """Tin người dùng mới và liên kết request cùng giao dịch; retry/fork truyền ID đã có.

    ``quote_id`` là tin Companion được trả lời (Reply). Chỉ giữ khi tin đó còn trong đúng hội thoại này, như
    resolveReplyTargetId của AIRI: tin vừa bị xóa thì lượt vẫn gửi, chỉ không trích."""
    async with connection.connect() as db:
        await db.execute('PRAGMA foreign_keys=ON')
        await db.execute('BEGIN IMMEDIATE')
        scope = await (await db.execute('SELECT project_id,mode FROM conversations WHERE owner=? AND id=? AND archived=0',
                                       (owner, conversation_id))).fetchone()
        turn = await (await db.execute('SELECT state,user_message_id FROM chat_turns WHERE owner=? AND request_id=?',
                                      (owner, request_id))).fetchone()
        if not scope or not turn or turn[0] not in {'running', 'stopped'} or turn[1] is not None:
            raise HTTPException(409, 'Lượt hoặc hội thoại đã thay đổi. Mở lại trước khi gửi nhé.')
        now = time.time()
        if message_id is None:
            if not isinstance(content, str):
                raise ValueError('Thiếu nội dung tin nhắn.')
            if quote_id is not None and not await (await db.execute(
                    "SELECT 1 FROM messages WHERE id=? AND conversation_id=? AND role IN ('user','assistant')",
                    (quote_id, conversation_id))).fetchone():
                quote_id = None
            quote = await chat_quotes.validate(db, owner, conversation_id, quoted_source) if quoted_source is not None and scope[1] == 'chat' else None
            row = await db.execute('INSERT INTO messages(conversation_id,role,content,created_at,provider,quote_id,quoted_source) VALUES(?,?,?,?,?,?,?)',
                                   (conversation_id, 'user', content, now, provider, quote_id, chat_quotes.encode(quote)))
            message_id = row.lastrowid
            await db.execute('UPDATE conversations SET updated_at=? WHERE id=?', (now, conversation_id))
        source = await (await db.execute("SELECT content FROM messages WHERE id=? AND conversation_id=? AND role='user'",
                                        (message_id, conversation_id))).fetchone()
        if not source:
            raise HTTPException(409, 'Tin nhắn nguồn không còn trong hội thoại.')
        if scope[1] == 'chat':
            await chat_lineage.user(db, message_id)
        await db.execute('''UPDATE chat_turns SET conversation_id=?,user_message_id=?,project_id=?,scope_bound=1,
            user_digest=?,updated_at=?,model=?,effort=? WHERE owner=? AND request_id=?''',
                         (conversation_id, message_id, scope[0], _digest(source[0]), now,
                          model if scope[1] == 'chat' else '', effort if scope[1] == 'chat' else '', owner, request_id))
        await db.commit()
        return message_id


async def finish(owner, request_id, state, outcome=''):
    async with connection.connect() as db:
        await db.execute("UPDATE chat_turns SET state=?,outcome=?,updated_at=? WHERE owner=? AND request_id=? AND state='running'",
                         (state, outcome, time.time(), owner, request_id))
        await db.commit()
    row = await get(owner, request_id)
    return row['state'] if row else 'interrupted'


async def attach_reply(owner, request_id, message_id):
    async with connection.connect() as db:
        await db.execute('UPDATE chat_turns SET assistant_message_id=? WHERE owner=? AND request_id=?', (message_id, owner, request_id))
        await db.commit()


async def interrupt_running():
    """Khởi động lại chỉ phục hồi dữ liệu đã lưu; tuyệt đối không chạy lại AI/công cụ."""
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN IMMEDIATE')
        rows = await (await db.execute("SELECT * FROM chat_turns WHERE state='running'")).fetchall()
        for row in rows:
            if row['conversation_id'] and row['user_message_id']:
                source = await (await db.execute('''SELECT c.mode FROM conversations c JOIN messages m ON m.conversation_id=c.id
                    WHERE c.id=? AND c.owner=? AND m.id=? AND m.role='user'
                    AND NOT EXISTS (SELECT 1 FROM chat_turns newer WHERE newer.owner=c.owner
                    AND newer.user_message_id=m.id AND newer.id>?)''',
                    (row['conversation_id'], row['owner'], row['user_message_id'], row['id']))).fetchone()
                if source and (source[0] == 'chat' or row['assistant_message_id']):
                    assistant_id = row['assistant_message_id']
                    if not assistant_id:
                        assistant_id = await _write_reply(db, row, '', [], [], None, '', False)
                    saved = await (await db.execute('SELECT work FROM messages WHERE id=?', (assistant_id,))).fetchone()
                    try:
                        work = json.loads(saved[0]) if saved and saved[0] else None
                    except (ValueError, TypeError):
                        work = None
                    if isinstance(work, dict):
                        work['complete'] = False
                        if 'web' in work:
                            web = stop_web(work['web'])
                            if web:
                                work['web'] = web
                            else:
                                work.pop('web', None)
                        for step in work.get('steps', []):
                            if isinstance(step, dict) and step.get('state') == 'live':
                                step.update(state='stopped', end=work.get('ms', 0))
                    await db.execute("UPDATE messages SET status='incomplete',work=? WHERE id=? AND conversation_id=?",
                                     (json.dumps(work, ensure_ascii=False) if work else '', assistant_id, row['conversation_id']))
                    await db.execute('UPDATE chat_turns SET assistant_message_id=? WHERE id=?', (assistant_id, row['id']))
        await db.execute("UPDATE chat_turns SET state='interrupted',outcome='process_restarted',updated_at=? WHERE state='running'", (time.time(),))
        await db.commit()


CHECKPOINT_CHARS = 200_000


async def _write_reply(db, turn, content, sources, artifacts, work, provider, complete):
    """Dùng kết nối giao dịch của caller; là ranh giới fault-injection trong test."""
    from shared.web_search import normalize_sources
    if isinstance(work, dict) and 'web' in work:
        work = dict(work)
        web = normalize_web(work.pop('web'))
        if web:
            work['web'] = web
    verified = []
    for artifact in artifacts[:16]:
        if not isinstance(artifact, dict):
            continue
        exists = await (await db.execute('''SELECT 1 FROM chat_documents d JOIN chat_document_versions v ON v.document_id=d.id
            WHERE d.owner=? AND d.conversation_id=? AND d.id=? AND v.version=?''',
            (turn['owner'], turn['conversation_id'], artifact.get('id'), artifact.get('version')))).fetchone()
        if exists:
            verified.append(artifact)
    values = (content, 'complete' if complete else 'incomplete', json.dumps(normalize_sources(sources), ensure_ascii=False),
              json.dumps(verified, ensure_ascii=False), json.dumps(work, ensure_ascii=False) if work else '', provider)
    mid = turn['assistant_message_id']
    if mid:
        result = await db.execute('''UPDATE messages SET content=?,status=?,sources=?,artifacts=?,work=?,provider=?
            WHERE id=? AND conversation_id=? AND role='assistant' ''', (*values, mid, turn['conversation_id']))
        if not result.rowcount:
            raise ValueError('Câu trả lời checkpoint không còn trong hội thoại.')
    else:
        result = await db.execute('''INSERT INTO messages(content,status,sources,artifacts,work,provider,conversation_id,role,created_at)
            VALUES(?,?,?,?,?,?,?,'assistant',?)''', (*values, turn['conversation_id'], time.time()))
        mid = result.lastrowid
    scope = await (await db.execute('SELECT mode FROM conversations WHERE id=?', (turn['conversation_id'],))).fetchone()
    if scope and scope[0] == 'chat':
        await chat_lineage.reply(db, mid, turn['user_message_id'], turn['model'], turn['effort'])
    await db.execute('UPDATE conversations SET updated_at=? WHERE id=?', (time.time(), turn['conversation_id']))
    return mid


async def persist(owner, request_id, *, content, sources=(), artifacts=(), work=None, provider='', state=None, outcome='', save_empty=True):
    """Checkpoint (state=None) hoặc chốt reply/link/state nguyên tử. Stop thắng nếu đã lấy write lock trước.

    Giao dịch không gọi model hoặc thực thi lại công cụ. Tệp đã xuất chỉ được liên kết nếu còn đúng owner/chat.
    """
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys=ON')
        await db.execute('BEGIN IMMEDIATE')
        turn = await (await db.execute('SELECT * FROM chat_turns WHERE owner=? AND request_id=?', (owner, request_id))).fetchone()
        if not turn:
            return 'interrupted'
        if turn['state'] not in {'running', 'stopped'} or (state is None and turn['state'] != 'running'):
            return turn['state']
        if turn['user_message_id'] is None:
            result_state = 'stopped' if turn['state'] == 'stopped' else state or 'running'
            await db.execute('UPDATE chat_turns SET state=?,outcome=?,updated_at=? WHERE id=?',
                             (result_state, 'user_stopped' if result_state == 'stopped' else outcome, time.time(), turn['id']))
            await db.commit()
            return result_state
        scope = await (await db.execute('''SELECT c.project_id,c.archived,m.content FROM conversations c JOIN messages m
            ON m.conversation_id=c.id WHERE c.owner=? AND c.id=? AND m.id=? AND m.role='user' ''',
            (owner, turn['conversation_id'], turn['user_message_id']))).fetchone()
        changed = bool(scope and turn['scope_bound'] and (scope['project_id'] != turn['project_id'] or scope['archived']
                       or _digest(scope['content']) != turn['user_digest']))
        if not scope or changed:
            await db.execute("UPDATE chat_turns SET state='interrupted',outcome='scope_changed',updated_at=? WHERE id=? AND state='running'",
                             (time.time(), turn['id']))
            await db.commit()
            return 'interrupted'
        result_state = 'stopped' if turn['state'] == 'stopped' else state or 'running'
        if result_state == 'complete' and not content.strip():
            result_state, outcome = 'error', 'empty'
        truncated = state is None and len(content) > CHECKPOINT_CHARS
        if truncated:
            content = content[:CHECKPOINT_CHARS] + '\n[Checkpoint bị giới hạn; phần cuối chưa được lưu trước khi ngắt.]'
        if work and result_state != 'complete':
            work = {**work, 'complete': False}
            if result_state != 'running' and 'web' in work:
                web = stop_web(work['web'])
                if web:
                    work['web'] = web
                else:
                    work.pop('web', None)
        mid = turn['assistant_message_id']
        if save_empty or content.strip() or artifacts or mid or result_state == 'stopped':
            mid = await _write_reply(db, turn, content, sources, artifacts, work, provider, result_state == 'complete')
        await db.execute('''UPDATE chat_turns SET state=?,outcome=?,assistant_message_id=?,updated_at=?,checkpoint_truncated=? WHERE id=?''',
                         (result_state, 'user_stopped' if result_state == 'stopped' else outcome, mid, time.time(), int(truncated), turn['id']))
        await db.commit()
        return result_state
