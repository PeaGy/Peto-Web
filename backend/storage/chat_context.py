"""Context Chat theo hội thoại; cursor theo ký tự, CAS và nguồn gốc trước khi thay bản tốt."""
import hashlib
import json
import time
import logging

import aiosqlite
from storage import connection
from storage import chat_quotes

logger = logging.getLogger('peto_web.chat_context')


class ContextVersionError(ValueError):
    pass


async def init_tables(db):
    await db.execute('''CREATE TABLE IF NOT EXISTS chat_contexts (
        conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
        owner TEXT NOT NULL, project_id TEXT, version INTEGER NOT NULL,
        cursor_id INTEGER NOT NULL, cursor_offset INTEGER NOT NULL, digest TEXT NOT NULL,
        data TEXT NOT NULL, model TEXT NOT NULL, updated_at REAL NOT NULL)''')
    for operation, ref in [('UPDATE OF content,status', 'NEW'), ('DELETE', 'OLD')]:
        name = 'update' if operation.startswith('UPDATE') else 'delete'
        await db.execute(f'''CREATE TRIGGER IF NOT EXISTS chat_context_invalidate_{name}
            AFTER {operation} ON messages BEGIN
            DELETE FROM chat_contexts WHERE conversation_id={ref}.conversation_id AND cursor_id>={ref}.id;
            END''')
    await db.execute('''CREATE TRIGGER IF NOT EXISTS chat_context_quote
        AFTER UPDATE OF quoted_source ON messages WHEN OLD.quoted_source IS NOT NEW.quoted_source BEGIN
        DELETE FROM chat_contexts WHERE conversation_id=NEW.conversation_id AND cursor_id>=NEW.id; END''')
    await db.execute('''CREATE TRIGGER IF NOT EXISTS chat_context_project
        AFTER UPDATE OF project_id ON conversations WHEN OLD.project_id IS NOT NEW.project_id BEGIN
        DELETE FROM chat_contexts WHERE conversation_id=NEW.id; END''')
    installed = await (await db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='chat_context_turn_state'")).fetchone()
    if not installed:
        # Migration một lần: cache cũ có thể đã xếp câu hỏi lỗi vào pending trước khi có quy tắc mới.
        await db.execute('''DELETE FROM chat_contexts WHERE version=1 AND EXISTS (SELECT 1 FROM chat_turns t
            WHERE t.owner=chat_contexts.owner AND t.conversation_id=chat_contexts.conversation_id
            AND t.user_message_id<=chat_contexts.cursor_id AND t.state IN ('error','timeout','interrupted','running'))''')
    await db.execute('''CREATE TRIGGER IF NOT EXISTS chat_context_turn_state
        AFTER UPDATE OF state ON chat_turns WHEN OLD.state != NEW.state BEGIN
        DELETE FROM chat_contexts WHERE conversation_id=NEW.conversation_id AND cursor_id>=NEW.user_message_id;
        END''')


async def state(owner, conversation_id):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute('''SELECT s.* FROM chat_contexts s JOIN conversations c ON c.id=s.conversation_id
            WHERE c.owner=? AND s.owner=? AND c.id=? AND c.mode='chat' AND c.persona='assistant'
            AND s.project_id IS c.project_id''', (owner, owner, conversation_id))).fetchone()
        if row is None:
            return None
        if row['version'] != 1:
            raise ContextVersionError('Phiên bản context Chat mới hơn backend; cần cập nhật backend trước khi tiếp tục.')
        try:
            data = json.loads(row['data'])
            summary = data['summary']
            valid = (fingerprint(data) == row['digest'] and len(row['data']) <= 16000
                     and row['cursor_id'] > 0 and row['cursor_offset'] >= 0 and isinstance(summary, dict)
                     and set(summary) == {'version', 'constraints', 'facts', 'decisions', 'pending'}
                     and type(summary['version']) is int and summary['version'] == 1
                     and all(isinstance(summary[key], list) and len(summary[key]) <= 8
                             for key in ('constraints', 'facts', 'decisions', 'pending')))
            for key in ('constraints', 'facts', 'decisions', 'pending'):
                for item in summary[key]:
                    valid = valid and (isinstance(item, dict) and set(item) == {'text', 'source_ids'}
                        and isinstance(item['text'], str) and 1 <= len(item['text']) <= 400
                        and isinstance(item['source_ids'], list) and 1 <= len(item['source_ids']) <= 4
                        and all(type(i) is int and 0 < i <= row['cursor_id'] for i in item['source_ids']))
            if not valid:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            # Cache hỏng được dựng lại từ lịch sử; chỉ xóa đúng bản vừa đọc, không đè một bản ghi đồng thời mới hơn.
            await db.execute('DELETE FROM chat_contexts WHERE conversation_id=? AND owner=? AND digest=?',
                             (conversation_id, owner, row['digest']))
            await db.commit()
            logger.warning('Bỏ context Chat không hợp lệ; giữ nguyên lịch sử gốc.')
            return None
        return dict(row)


async def spans(owner, conversation_id, before, cursor_id=0, cursor_offset=0, *, max_chars=16_000):
    result, left = [], max_chars
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute('''SELECT m.id,m.role,m.status,m.quoted_source,length(m.content) AS total,
            substr(m.content,CASE WHEN m.id=? THEN ?+1 ELSE 1 END,?) AS text,
            COALESCE((SELECT state FROM chat_turns WHERE owner=c.owner AND (user_message_id=m.id OR assistant_message_id=m.id) ORDER BY id DESC LIMIT 1),'') AS turn_state
            FROM messages m JOIN conversations c ON c.id=m.conversation_id
            WHERE c.owner=? AND c.id=? AND c.mode='chat' AND c.persona='assistant'
            AND m.id>=? AND m.id<? AND m.role IN ('user','assistant') ORDER BY m.id LIMIT 32''',
            (cursor_id, cursor_offset, max_chars, owner, conversation_id, cursor_id, before))).fetchall()
        for row in rows:
            offset = cursor_offset if row['id'] == cursor_id else 0
            if row['id'] == cursor_id and offset >= row['total']:
                continue
            quote = chat_quotes.normalize(row['quoted_source']) if row['role'] == 'user' else None
            cost = len(quote['text']) if quote else 0
            if left <= cost:
                break
            text = row['text'][:left - cost]
            part = {'id': row['id'], 'role': row['role'], 'status': row['status'], 'turn_state': row['turn_state'],
                    'start': offset, 'end': offset + len(text), 'total': row['total'], 'text': text}
            if quote:
                part['quoted_source'] = quote
            result.append(part)
            left -= len(text) + cost
            if left <= 0:
                break
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


async def save(owner, conversation_id, project_id, previous, batch, before, data, model):
    # Kiểm lại chính các đoạn đã đọc, kể cả source bị sửa/xóa trong lúc model tóm tắt.
    latest = await spans(owner, conversation_id, before, previous['cursor_id'] if previous else 0,
                         previous['cursor_offset'] if previous else 0)
    if latest != batch:
        return False
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        scope = await (await db.execute("SELECT project_id FROM conversations WHERE id=? AND owner=? AND mode='chat' AND persona='assistant' AND archived=0",
                                        (conversation_id, owner))).fetchone()
        old = await (await db.execute('SELECT digest FROM chat_contexts WHERE conversation_id=? AND owner=?',
                                      (conversation_id, owner))).fetchone()
        if scope is None or scope[0] != project_id or (old[0] if old else None) != (previous['digest'] if previous else None):
            return False
        # Chốt nguồn dưới cùng write lock: không để update/delete chen giữa kiểm nguồn và ghi summary.
        for part in batch:
            row = await (await db.execute('''SELECT substr(content,?+1,?),length(content),role,status,
                COALESCE((SELECT state FROM chat_turns WHERE owner=? AND (user_message_id=messages.id OR assistant_message_id=messages.id) ORDER BY id DESC LIMIT 1),'')
                ,quoted_source FROM messages WHERE id=? AND conversation_id=?''',
                                          (part['start'], len(part['text']), owner, part['id'], conversation_id))).fetchone()
            if (not row or tuple(row[:5]) != (part['text'], part['total'], part['role'], part['status'], part['turn_state'])
                    or (chat_quotes.normalize(row[5]) if part['role'] == 'user' else None) != part.get('quoted_source')):
                return False
        cursor = batch[-1]
        envelope = {'summary': data, 'sources': [{'message_id': p['id'], 'start': p['start'], 'end': p['end']} for p in batch],
                    'previous_digest': previous['digest'] if previous else None, 'source_digest': fingerprint(batch)}
        digest = fingerprint(envelope)
        await db.execute('''INSERT OR REPLACE INTO chat_contexts VALUES(?,?,?,?,?,?,?,?,?,?)''',
                         (conversation_id, owner, project_id, 1, cursor['id'], cursor['end'], digest,
                          json.dumps(envelope, ensure_ascii=False), model, time.time()))
        await db.commit()
        return True


async def file_index(owner, conversation_id):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute('''SELECT a.id,a.message_id,a.filename,a.kind,a.mime,a.path,a.size
            FROM attachments a JOIN conversations c ON c.id=a.conversation_id
            WHERE c.owner=? AND a.owner=? AND c.id=? AND c.mode='chat' AND a.kind='file'
            ORDER BY a.created_at DESC,a.rowid DESC LIMIT 128''', (owner, owner, conversation_id))).fetchall()
        return [dict(row) for row in reversed(rows)]


async def artifact_index(owner, conversation_id):
    """Danh mục metadata của 128 phiên bản tài liệu đã xuất hiện trong chat; không kéo nội dung/BLOB vào prompt."""
    # json_each chỉ chạy trên JSON hợp lệ; chỉ extract object. Phiên bản phải còn thuộc đúng owner/chat.
    obj = "CASE WHEN j.type='object' THEN j.value ELSE '{}' END"
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(f'''SELECT m.id AS message_id,d.id,v.version,v.style,
            json_extract({obj},'$.filename') AS filename
            FROM messages m JOIN conversations c ON c.id=m.conversation_id
            JOIN json_each(CASE WHEN json_valid(m.artifacts) THEN m.artifacts ELSE '[]' END) j
            JOIN chat_documents d ON d.id=json_extract({obj},'$.id')
            JOIN chat_document_versions v ON v.document_id=d.id AND v.version=json_extract({obj},'$.version')
            WHERE c.owner=? AND c.id=? AND c.mode='chat' AND c.persona='assistant'
            AND d.owner=c.owner AND d.conversation_id=c.id AND j.type='object'
            ORDER BY m.id DESC LIMIT 128''', (owner, conversation_id))).fetchall()
        return [dict(row) for row in reversed(rows) if isinstance(row['filename'], str) and 0 < len(row['filename']) <= 250]
