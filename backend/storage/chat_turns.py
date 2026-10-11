"""Vòng đời một lần tạo câu trả lời; mã yêu cầu riêng cho mỗi lần Thử lại."""
import time
import aiosqlite
from fastapi import HTTPException
from storage import connection


async def init_tables(db):
    await db.execute('''CREATE TABLE IF NOT EXISTS chat_turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, request_id TEXT NOT NULL,
        state TEXT NOT NULL, conversation_id TEXT, user_message_id INTEGER, assistant_message_id INTEGER,
        created_at REAL NOT NULL, UNIQUE(owner,request_id),
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE)''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_chat_turn_user ON chat_turns(user_message_id,id)')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_chat_turn_assistant ON chat_turns(assistant_message_id,id)')


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


async def bind(owner, request_id, conversation_id, message_id):
    async with connection.connect() as db:
        await db.execute('UPDATE chat_turns SET conversation_id=?,user_message_id=? WHERE owner=? AND request_id=?',
                         (conversation_id, message_id, owner, request_id))
        await db.commit()


async def finish(owner, request_id, state):
    async with connection.connect() as db:
        await db.execute("UPDATE chat_turns SET state=? WHERE owner=? AND request_id=? AND state='running'", (state, owner, request_id))
        await db.commit()
    row = await get(owner, request_id)
    return row['state'] if row else 'interrupted'


async def attach_reply(owner, request_id, message_id):
    async with connection.connect() as db:
        await db.execute('UPDATE chat_turns SET assistant_message_id=? WHERE owner=? AND request_id=?', (message_id, owner, request_id))
        await db.commit()


async def interrupt_running():
    async with connection.connect() as db:
        await db.execute("UPDATE chat_turns SET state='interrupted' WHERE state='running'")
        await db.commit()
