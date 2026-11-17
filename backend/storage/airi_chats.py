"""Hội thoại Companion bản AIRI đồng bộ giữa các máy của cùng một tài khoản (``features/companion/airi_sync.py``).

Theo đúng dịch vụ hội thoại của AIRI (``server/apps/api/src/services/domain/chats.ts`` trong bản fork): mỗi hội thoại có
mã do trình duyệt đặt (mã phiên của AIRI), mỗi tin có mã riêng và số thứ tự ``seq`` tăng dần trong hội thoại. Gửi lại
một tin đã có (cùng mã) thì sửa nội dung và cấp ``seq`` mới, nên máy khác kéo về được bản sửa. Chỉ lưu chữ của tin người
dùng và tin trả lời; công cụ, lỗi, ảnh không đồng bộ (trình duyệt cũng không gửi).

Khác AIRI ở hai chỗ, vì Peto mỗi tài khoản tách riêng: khóa chính gồm ``owner`` (mã hội thoại và mã tin của hai tài
khoản trùng nhau cũng không đụng nhau), và xóa hội thoại thì xóa luôn các tin của nó (AIRI chỉ đánh dấu xóa). Hàng hội
thoại vẫn giữ dấu xóa để máy khác biết và để mã đó không tạo lại được.
"""
from __future__ import annotations

import json
import time

import aiosqlite

from storage.connection import connect

CHAT_TYPES = ('private', 'bot', 'group', 'channel')
MEMBER_TYPES = ('character', 'bot')
# Giới hạn rộng, chỉ để chặn dùng bất thường: một người trò chuyện cả năm vẫn còn xa mới chạm.
MAX_CHATS = 1_000
MAX_MESSAGES = 100_000
MAX_CONTENT_CHARS = 1_000_000_000  # tổng chữ đã lưu của một tài khoản (khoảng 1 GB)
PULL_DEFAULT = 100
PULL_MAX = 500


class SyncError(Exception):
    """Lỗi trả cho trình duyệt: ``status`` theo HTTP, ``message`` tiếng Việt."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


async def init_tables(db: aiosqlite.Connection) -> None:
    await db.execute('''CREATE TABLE IF NOT EXISTS airi_chats (
        owner TEXT NOT NULL, id TEXT NOT NULL, type TEXT NOT NULL, title TEXT, members TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
        PRIMARY KEY(owner, id))''')
    await db.execute('''CREATE TABLE IF NOT EXISTS airi_chat_messages (
        owner TEXT NOT NULL, id TEXT NOT NULL, chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
        reply_to TEXT, seq INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(owner, id))''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_airi_chat_messages_seq ON airi_chat_messages(owner, chat_id, seq)')


def _iso(seconds: float) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(seconds)) + f'.{int(seconds * 1000) % 1000:03d}Z'


def _chat(row: aiosqlite.Row, user_id: str) -> dict:
    """Hội thoại theo dạng JSON của AIRI (ngày giờ ISO), thành viên gồm người dùng và nhân vật."""
    members = [{'id': f'{row["id"]}:user', 'chatId': row['id'], 'memberType': 'user', 'userId': user_id,
                'characterId': None}]
    for index, member in enumerate(json.loads(row['members'] or '[]')):
        members.append({'id': f'{row["id"]}:{index}', 'chatId': row['id'], 'memberType': member['type'],
                        'userId': None, 'characterId': member.get('characterId')})
    return {'id': row['id'], 'type': row['type'], 'title': row['title'], 'createdAt': _iso(row['created_at']),
            'updatedAt': _iso(row['updated_at']), 'deletedAt': None, 'members': members}


def _wire(row: aiosqlite.Row, user_id: str) -> dict:
    """Một tin theo dạng ``WireMessage`` của AIRI (ngày giờ là mili giây)."""
    return {'id': row['id'], 'chatId': row['chat_id'], 'senderId': user_id, 'role': row['role'],
            'content': row['content'], 'replyToMessageId': row['reply_to'], 'seq': row['seq'],
            'createdAt': round(row['created_at'] * 1000), 'updatedAt': round(row['updated_at'] * 1000)}


async def _live_chat(db: aiosqlite.Connection, owner: str, chat_id: str) -> aiosqlite.Row:
    row = await (await db.execute('SELECT * FROM airi_chats WHERE owner=? AND id=? AND deleted_at IS NULL',
                                  (owner, chat_id))).fetchone()
    if row is None:
        raise SyncError(404, 'Không tìm thấy cuộc trò chuyện này.')
    return row


async def create_chat(owner: str, user_id: str, chat_id: str, chat_type: str, title: str | None,
                      members: list[dict]) -> dict:
    now = time.time()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN IMMEDIATE')
        try:
            exists = await (await db.execute('SELECT 1 FROM airi_chats WHERE owner=? AND id=?',
                                             (owner, chat_id))).fetchone()
            if exists:
                raise SyncError(409, 'Cuộc trò chuyện này đã có trên máy chủ.')
            count = (await (await db.execute('SELECT COUNT(*) FROM airi_chats WHERE owner=? AND deleted_at IS NULL',
                                             (owner,))).fetchone())[0]
            if count >= MAX_CHATS:
                raise SyncError(413, f'Đã đồng bộ đủ {MAX_CHATS} cuộc trò chuyện. Xóa bớt cuộc cũ rồi thử lại nhé.')
            await db.execute('INSERT INTO airi_chats (owner, id, type, title, members, created_at, updated_at) '
                             'VALUES (?,?,?,?,?,?,?)', (owner, chat_id, chat_type, title, json.dumps(members), now, now))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
        row = await _live_chat(db, owner, chat_id)
    return _chat(row, user_id)


async def list_chats(owner: str, user_id: str) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            'SELECT * FROM airi_chats WHERE owner=? AND deleted_at IS NULL ORDER BY created_at', (owner,))).fetchall()
    return [_chat(row, user_id) for row in rows]


async def get_chat(owner: str, user_id: str, chat_id: str) -> dict:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        return _chat(await _live_chat(db, owner, chat_id), user_id)


async def update_chat(owner: str, user_id: str, chat_id: str, title: str | None) -> dict:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await _live_chat(db, owner, chat_id)
        await db.execute('UPDATE airi_chats SET title=?, updated_at=? WHERE owner=? AND id=?',
                         (title, time.time(), owner, chat_id))
        await db.commit()
        return _chat(await _live_chat(db, owner, chat_id), user_id)


async def delete_chat(owner: str, user_id: str, chat_id: str) -> dict:
    """Đánh dấu xóa hội thoại và xóa hẳn các tin của nó."""
    now = time.time()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await _live_chat(db, owner, chat_id)
        await db.execute('UPDATE airi_chats SET deleted_at=?, updated_at=? WHERE owner=? AND id=?',
                         (now, now, owner, chat_id))
        await db.execute('DELETE FROM airi_chat_messages WHERE owner=? AND chat_id=?', (owner, chat_id))
        await db.commit()
    chat = _chat(row, user_id)
    chat.update(deletedAt=_iso(now), updatedAt=_iso(now))
    return chat


async def push_messages(owner: str, user_id: str, chat_id: str, messages: list[dict]) -> dict:
    """Thêm hoặc sửa tin; mỗi tin được ``seq`` mới tiếp theo. Trả ``{seq, fromSeq, toSeq, messages}`` (các tin vừa
    ghi, dạng ``WireMessage``, để báo cho các máy khác)."""
    now = time.time()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN IMMEDIATE')
        try:
            await _live_chat(db, owner, chat_id)
            max_seq = (await (await db.execute(
                'SELECT COALESCE(MAX(seq), 0) FROM airi_chat_messages WHERE owner=? AND chat_id=?',
                (owner, chat_id))).fetchone())[0]
            ids = [message['id'] for message in messages]
            existing = {}
            if ids:
                marks = ','.join('?' * len(ids))
                for row in await (await db.execute(
                        f'SELECT id, chat_id, content FROM airi_chat_messages WHERE owner=? AND id IN ({marks})',
                        (owner, *ids))).fetchall():
                    existing[row['id']] = row
            if any(row['chat_id'] != chat_id for row in existing.values()):
                raise SyncError(409, 'Tin nhắn này đã thuộc một cuộc trò chuyện khác.')
            new_count = sum(1 for message_id in dict.fromkeys(ids) if message_id not in existing)
            if new_count:
                total, chars = await (await db.execute(
                    'SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM airi_chat_messages WHERE owner=?',
                    (owner,))).fetchone()
                added = sum(len(message['content']) for message in messages)
                if total + new_count > MAX_MESSAGES or chars + added > MAX_CONTENT_CHARS:
                    raise SyncError(413, 'Chỗ đồng bộ hội thoại của tài khoản đã đầy. Xóa bớt cuộc trò chuyện cũ '
                                         'rồi thử lại nhé.')
            seq = max_seq
            for message in messages:
                seq += 1
                if message['id'] in existing:
                    await db.execute('UPDATE airi_chat_messages SET content=?, reply_to=?, seq=?, updated_at=? '
                                     'WHERE owner=? AND id=?',
                                     (message['content'], message.get('replyToMessageId'), seq, now, owner,
                                      message['id']))
                else:
                    await db.execute('INSERT INTO airi_chat_messages (owner, id, chat_id, role, content, reply_to, '
                                     'seq, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                                     (owner, message['id'], chat_id, message['role'], message['content'],
                                      message.get('replyToMessageId'), seq, now, now))
                    existing[message['id']] = message
            await db.execute('UPDATE airi_chats SET updated_at=? WHERE owner=? AND id=?', (now, owner, chat_id))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
        rows = await (await db.execute(
            'SELECT * FROM airi_chat_messages WHERE owner=? AND chat_id=? AND seq>? ORDER BY seq',
            (owner, chat_id, max_seq))).fetchall()
    return {'seq': seq, 'fromSeq': max_seq + 1, 'toSeq': seq, 'messages': [_wire(row, user_id) for row in rows]}


async def pull_messages(owner: str, user_id: str, chat_id: str, after_seq: int, limit: int | None) -> dict:
    """Các tin có ``seq`` lớn hơn ``after_seq`` (tối đa ``limit``, mặc định 100, trần 500) và ``seq`` lớn nhất."""
    clamped = PULL_DEFAULT if not limit or limit <= 0 else min(limit, PULL_MAX)
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await _live_chat(db, owner, chat_id)
        rows = await (await db.execute(
            'SELECT * FROM airi_chat_messages WHERE owner=? AND chat_id=? AND seq>? ORDER BY seq LIMIT ?',
            (owner, chat_id, after_seq, clamped))).fetchall()
        max_seq = (await (await db.execute(
            'SELECT COALESCE(MAX(seq), 0) FROM airi_chat_messages WHERE owner=? AND chat_id=?',
            (owner, chat_id))).fetchone())[0]
    return {'messages': [_wire(row, user_id) for row in rows], 'seq': max_seq}
