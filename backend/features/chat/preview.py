"""Small read-only search preview; never hydrate files, documents, work logs or provider state."""
import aiosqlite
from fastapi import HTTPException
from storage import connection

MAX_MESSAGES = 12
MAX_CHARS = 24_000


async def read(owner, conversation_id):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        scope = await (await db.execute("SELECT 1 FROM conversations WHERE id=? AND owner=? AND mode='chat'",
                                       (conversation_id, owner))).fetchone()
        if not scope:
            raise HTTPException(404, 'Không tìm thấy hội thoại')
        rows = await (await db.execute('''SELECT id,role,status,substr(content,1,?) AS content,length(content) AS total
            FROM messages WHERE conversation_id=? AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?''',
            (MAX_CHARS, conversation_id, MAX_MESSAGES + 1))).fetchall()
    truncated = len(rows) > MAX_MESSAGES
    messages, remaining = [], MAX_CHARS
    for row in rows[:MAX_MESSAGES]:
        if remaining == 0:
            truncated = True
            break
        text = row['content'][:remaining]
        truncated = truncated or len(text) < row['total']
        messages.append({'id': row['id'], 'role': row['role'], 'content': text, 'status': row['status']})
        remaining -= len(text)
    messages.reverse()
    return {'messages': messages, 'truncated': truncated}
