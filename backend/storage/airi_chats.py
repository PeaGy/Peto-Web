"""Hội thoại Companion bản AIRI đồng bộ giữa các máy của cùng một tài khoản (``features/companion/airi_sync.py``).

Theo đúng dịch vụ hội thoại của AIRI (``server/apps/api/src/services/domain/chats.ts`` trong bản fork): mỗi hội thoại có
mã do trình duyệt đặt (mã phiên của AIRI), mỗi tin có mã riêng và số thứ tự ``seq`` tăng dần trong hội thoại. Gửi lại
một tin đã có (cùng mã) thì sửa nội dung và cấp ``seq`` mới, nên máy khác kéo về được bản sửa. Chỉ lưu tin người dùng
và tin trả lời; công cụ, lỗi không đồng bộ (trình duyệt cũng không gửi).

Ảnh trong tin (từ 26/11/2026, theo ``services/domain/attachments.ts`` của AIRI): trình duyệt đăng ký ảnh, đẩy byte lên
một địa chỉ có chữ ký, báo xong, rồi gửi tin kèm ``mediaIds``. Ảnh nằm trong ``UPLOAD_DIR/companion/<mã người dùng>``,
bảng ``companion_attachments``. Tin chỉ được kèm ảnh đã xong của chính tài khoản; máy khác nhận ``attachments`` trong
tin và tự tải ảnh về. Không giới hạn tổng dung lượng mỗi tài khoản, như AIRI và Chat (chủ web chọn ngày 26/11/2026).

Khác AIRI ở hai chỗ, vì Peto mỗi tài khoản tách riêng: khóa chính gồm ``owner`` (mã hội thoại và mã tin của hai tài
khoản trùng nhau cũng không đụng nhau), và xóa hội thoại thì xóa luôn các tin của nó (AIRI chỉ đánh dấu xóa). Hàng hội
thoại vẫn giữ dấu xóa để máy khác biết và để mã đó không tạo lại được.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from pathlib import Path

import aiosqlite

from core import config
from storage.connection import connect

CHAT_TYPES = ('private', 'bot', 'group', 'channel')
MEMBER_TYPES = ('character', 'bot')
# Giới hạn rộng, chỉ để chặn dùng bất thường: một người trò chuyện cả năm vẫn còn xa mới chạm.
MAX_CHATS = 1_000
MAX_MESSAGES = 100_000
MAX_CONTENT_CHARS = 1_000_000_000  # tổng chữ đã lưu của một tài khoản (khoảng 1 GB)
# Kéo tin: có ``limit`` thì tối đa 500 như AIRI; không có (trình duyệt AIRI luôn kéo không kèm limit) thì trả cả đoạn,
# tới trần ``PULL_ALL_MAX``. Máy chủ AIRI trả 100 tin mà vẫn báo seq lớn nhất, nên trình duyệt nhảy con trỏ qua phần
# còn lại và không bao giờ kéo nó (chủ web gặp ngày 18/11/2026 với hội thoại 179 tin).
PULL_MAX = 500
PULL_ALL_MAX = 10_000
# Ảnh: đúng giới hạn của AIRI (``server-sdk-shared/src/chat.ts``). Trang AIRI tự thu nhỏ ảnh xuống dưới 3 MB trước khi
# gửi, nên giới hạn này không bao giờ chặn ảnh người dùng chọn.
ATTACHMENT_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
SHA256_HEX = re.compile(r'[a-f0-9]{64}')
IMAGE_MIMES = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/gif': '.gif'}
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024
MAX_MEDIA_PER_MESSAGE = 4
# Ảnh đăng ký mà không tải lên xong (đóng trang giữa chừng): dọn sau một ngày. AIRI để lại mãi.
PENDING_MAX_AGE = 24 * 3600


class SyncError(Exception):
    """Lỗi trả cho trình duyệt: ``status`` theo HTTP, ``message`` tiếng Việt."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# Tên bảng trước ngày 18/11/2026 (mang chữ airi). Đổi tên tại chỗ lúc khởi động, dữ liệu giữ nguyên.
_OLD_TABLES = (('airi_chats', 'companion_chats'), ('airi_chat_messages', 'companion_chat_messages'),
               ('airi_sync_users', 'companion_sync_users'))


async def _rename_old_tables(db: aiosqlite.Connection) -> None:
    names = {row[0] for row in await (await db.execute("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    for old, new in _OLD_TABLES:
        if old in names and new not in names:
            await db.execute(f'ALTER TABLE {old} RENAME TO {new}')
    await db.execute('DROP INDEX IF EXISTS idx_airi_chat_messages_seq')


async def init_tables(db: aiosqlite.Connection) -> None:
    await _rename_old_tables(db)
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_chats (
        owner TEXT NOT NULL, id TEXT NOT NULL, type TEXT NOT NULL, title TEXT, members TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
        PRIMARY KEY(owner, id))''')
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_chat_messages (
        owner TEXT NOT NULL, id TEXT NOT NULL, chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
        reply_to TEXT, seq INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(owner, id))''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_companion_chat_messages_seq '
                     'ON companion_chat_messages(owner, chat_id, seq)')
    columns = {row[1] for row in await (await db.execute('PRAGMA table_info(companion_chat_messages)')).fetchall()}
    if 'media_ids' not in columns:
        await db.execute("ALTER TABLE companion_chat_messages ADD COLUMN media_ids TEXT NOT NULL DEFAULT '[]'")
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_attachments (
        owner TEXT NOT NULL, id TEXT NOT NULL, mime TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
        state TEXT NOT NULL, path TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(owner, id))''')
    # Mã người dùng mà trang AIRI thấy (17–18/11/2026 tính lại mỗi lần bằng HMAC với PETO_SESSION_SECRET). Trình duyệt
    # cất hội thoại theo mã này, nên mã phải giữ nguyên cả khi đổi PETO_SESSION_SECRET: lưu một lần cho mỗi tài khoản.
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_sync_users (
        owner TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE)''')
    # Mọi tài khoản đã có giữ đúng mã đang dùng. Chạy mỗi lần khởi động; hàng đã có không đổi.
    rows = await (await db.execute(
        'SELECT owner FROM users UNION SELECT owner FROM companion_chats EXCEPT SELECT owner FROM companion_sync_users')).fetchall()
    await db.executemany('INSERT OR IGNORE INTO companion_sync_users (owner, user_id) VALUES (?, ?)',
                         [(owner, derived_user_id(owner)) for (owner,) in rows])


def derived_user_id(owner: str) -> str:
    """Mã người dùng theo cách tính ban đầu: ``peto-`` + 24 hex của HMAC-SHA256(PETO_SESSION_SECRET, ``airi-sync:``
    + owner). Không đoán ngược ra owner hay ID Discord. Chỉ dùng để tạo hàng lần đầu; sau đó đọc từ bảng."""
    digest = hmac.new(config.SESSION_SECRET.encode('utf-8'), f'airi-sync:{owner}'.encode('utf-8'), hashlib.sha256)
    return 'peto-' + digest.hexdigest()[:24]


async def sync_user_id(owner: str) -> str:
    """Mã người dùng cố định của tài khoản cho đồng bộ AIRI; tạo lần đầu."""
    async with connect() as db:
        row = await (await db.execute('SELECT user_id FROM companion_sync_users WHERE owner=?', (owner,))).fetchone()
        if row:
            return row[0]
        await db.execute('INSERT OR IGNORE INTO companion_sync_users (owner, user_id) VALUES (?, ?)',
                         (owner, derived_user_id(owner)))
        await db.commit()
        return (await (await db.execute('SELECT user_id FROM companion_sync_users WHERE owner=?', (owner,))).fetchone())[0]


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


def _media_ids(row: aiosqlite.Row) -> list[str]:
    return json.loads(row['media_ids'] or '[]')


def _wire(row: aiosqlite.Row, user_id: str, attachments: dict[str, dict]) -> dict:
    """Một tin theo dạng ``WireMessage`` của AIRI (ngày giờ là mili giây). ``attachments``: ảnh đã xong theo mã; ảnh
    không còn thì bỏ, như AIRI."""
    return {'id': row['id'], 'chatId': row['chat_id'], 'senderId': user_id, 'role': row['role'],
            'content': row['content'],
            'attachments': [attachments[media_id] for media_id in _media_ids(row) if media_id in attachments],
            'replyToMessageId': row['reply_to'], 'seq': row['seq'],
            'createdAt': round(row['created_at'] * 1000), 'updatedAt': round(row['updated_at'] * 1000)}


def public_attachment(row: aiosqlite.Row | dict) -> dict:
    """Một ảnh theo dạng ``WireAttachment`` của AIRI."""
    return {'id': row['id'], 'mimeType': row['mime'], 'size': row['size']}


async def _attachments_by_id(db: aiosqlite.Connection, owner: str, ids: set[str], *,
                             ready: bool = True) -> dict[str, aiosqlite.Row]:
    found: dict[str, aiosqlite.Row] = {}
    ordered = sorted(ids)
    state = " AND state='ready'" if ready else ''
    for start in range(0, len(ordered), 500):
        part = ordered[start:start + 500]
        marks = ','.join('?' * len(part))
        for row in await (await db.execute(
                f'SELECT * FROM companion_attachments WHERE owner=?{state} AND id IN ({marks})',
                (owner, *part))).fetchall():
            found[row['id']] = row
    return found


async def _wire_messages(db: aiosqlite.Connection, owner: str, user_id: str, rows: list[aiosqlite.Row]) -> list[dict]:
    ids = {media_id for row in rows for media_id in _media_ids(row)}
    attachments = {key: public_attachment(row) for key, row in (await _attachments_by_id(db, owner, ids)).items()}
    return [_wire(row, user_id, attachments) for row in rows]


def _unlink(paths: list[str]) -> None:
    """Xóa tệp ảnh; chỉ tệp nằm trong ``UPLOAD_DIR/companion``."""
    root = (config.UPLOAD_DIR / 'companion').resolve()
    for item in paths:
        target = Path(item).resolve()
        if target != root and target.is_relative_to(root):
            target.unlink(missing_ok=True)


async def _live_chat(db: aiosqlite.Connection, owner: str, chat_id: str) -> aiosqlite.Row:
    row = await (await db.execute('SELECT * FROM companion_chats WHERE owner=? AND id=? AND deleted_at IS NULL',
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
            exists = await (await db.execute('SELECT 1 FROM companion_chats WHERE owner=? AND id=?',
                                             (owner, chat_id))).fetchone()
            if exists:
                raise SyncError(409, 'Cuộc trò chuyện này đã có trên máy chủ.')
            count = (await (await db.execute('SELECT COUNT(*) FROM companion_chats WHERE owner=? AND deleted_at IS NULL',
                                             (owner,))).fetchone())[0]
            if count >= MAX_CHATS:
                raise SyncError(413, f'Đã đồng bộ đủ {MAX_CHATS} cuộc trò chuyện. Xóa bớt cuộc cũ rồi thử lại nhé.')
            await db.execute('INSERT INTO companion_chats (owner, id, type, title, members, created_at, updated_at) '
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
            'SELECT * FROM companion_chats WHERE owner=? AND deleted_at IS NULL ORDER BY created_at', (owner,))).fetchall()
    return [_chat(row, user_id) for row in rows]


async def get_chat(owner: str, user_id: str, chat_id: str) -> dict:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        return _chat(await _live_chat(db, owner, chat_id), user_id)


async def update_chat(owner: str, user_id: str, chat_id: str, title: str | None) -> dict:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await _live_chat(db, owner, chat_id)
        await db.execute('UPDATE companion_chats SET title=?, updated_at=? WHERE owner=? AND id=?',
                         (title, time.time(), owner, chat_id))
        await db.commit()
        return _chat(await _live_chat(db, owner, chat_id), user_id)


async def delete_chat(owner: str, user_id: str, chat_id: str) -> dict:
    """Đánh dấu xóa hội thoại, xóa hẳn các tin của nó và các ảnh không còn tin nào khác dùng (AIRI giữ ảnh tới khi xóa
    tài khoản)."""
    now = time.time()
    paths: list[str] = []
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN IMMEDIATE')
        try:
            row = await _live_chat(db, owner, chat_id)
            media = {media_id for message in await (await db.execute(
                "SELECT media_ids FROM companion_chat_messages WHERE owner=? AND chat_id=? AND media_ids<>'[]'",
                (owner, chat_id))).fetchall() for media_id in _media_ids(message)}
            await db.execute('UPDATE companion_chats SET deleted_at=?, updated_at=? WHERE owner=? AND id=?',
                             (now, now, owner, chat_id))
            await db.execute('DELETE FROM companion_chat_messages WHERE owner=? AND chat_id=?', (owner, chat_id))
            if media:
                still_used = {media_id for message in await (await db.execute(
                    "SELECT media_ids FROM companion_chat_messages WHERE owner=? AND media_ids<>'[]'",
                    (owner,))).fetchall() for media_id in _media_ids(message)}
                for attachment in (await _attachments_by_id(db, owner, media - still_used, ready=False)).values():
                    paths.append(attachment['path'])
                    await db.execute('DELETE FROM companion_attachments WHERE owner=? AND id=?',
                                     (owner, attachment['id']))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    _unlink(paths)
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
            media = {media_id for message in messages for media_id in message.get('mediaIds', [])}
            if media and len(await _attachments_by_id(db, owner, media)) != len(media):
                raise SyncError(400, 'Tin chỉ kèm được ảnh đã tải lên xong của chính tài khoản này.')
            max_seq = (await (await db.execute(
                'SELECT COALESCE(MAX(seq), 0) FROM companion_chat_messages WHERE owner=? AND chat_id=?',
                (owner, chat_id))).fetchone())[0]
            ids = [message['id'] for message in messages]
            existing = {}
            if ids:
                marks = ','.join('?' * len(ids))
                for row in await (await db.execute(
                        f'SELECT id, chat_id, role, content, reply_to, media_ids FROM companion_chat_messages '
                        f'WHERE owner=? AND id IN ({marks})', (owner, *ids))).fetchall():
                    existing[row['id']] = dict(row)
            if any(row['chat_id'] != chat_id for row in existing.values()):
                raise SyncError(409, 'Tin nhắn này đã thuộc một cuộc trò chuyện khác.')
            new_count = sum(1 for message_id in dict.fromkeys(ids) if message_id not in existing)
            if new_count:
                total, chars = await (await db.execute(
                    'SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM companion_chat_messages WHERE owner=?',
                    (owner,))).fetchone()
                added = sum(len(message['content']) for message in messages)
                if total + new_count > MAX_MESSAGES or chars + added > MAX_CONTENT_CHARS:
                    raise SyncError(413, 'Chỗ đồng bộ hội thoại của tài khoản đã đầy. Xóa bớt cuộc trò chuyện cũ '
                                         'rồi thử lại nhé.')
            seq = max_seq
            for message in messages:
                stored = existing.get(message['id'])
                media_ids = json.dumps(message.get('mediaIds', []))
                if stored is not None and (stored['role'], stored['content'], stored.get('reply_to'),
                                           stored['media_ids']) == (
                        message['role'], message['content'], message.get('replyToMessageId'), media_ids):
                    # Gửi lại y hệt (trình duyệt thử lại khi mất lời đáp, hay một tab bản cũ gửi lại tin cũ): không
                    # đổi gì, giữ nguyên seq. Máy chủ AIRI cấp seq mới cả khi y hệt, nên tin cũ nhảy xuống cuối trên
                    # máy kéo về (chủ web gặp ngày 18/11/2026).
                    continue
                seq += 1
                if stored is not None:
                    await db.execute('UPDATE companion_chat_messages SET content=?, reply_to=?, media_ids=?, seq=?, '
                                     'updated_at=? WHERE owner=? AND id=?',
                                     (message['content'], message.get('replyToMessageId'), media_ids, seq, now, owner,
                                      message['id']))
                else:
                    await db.execute('INSERT INTO companion_chat_messages (owner, id, chat_id, role, content, reply_to, '
                                     'media_ids, seq, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                     (owner, message['id'], chat_id, message['role'], message['content'],
                                      message.get('replyToMessageId'), media_ids, seq, now, now))
                existing[message['id']] = {'chat_id': chat_id, 'role': message['role'], 'content': message['content'],
                                           'reply_to': message.get('replyToMessageId'), 'media_ids': media_ids}
            if seq > max_seq:
                await db.execute('UPDATE companion_chats SET updated_at=? WHERE owner=? AND id=?', (now, owner, chat_id))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
        rows = await (await db.execute(
            'SELECT * FROM companion_chat_messages WHERE owner=? AND chat_id=? AND seq>? ORDER BY seq',
            (owner, chat_id, max_seq))).fetchall()
        wire = await _wire_messages(db, owner, user_id, rows)
    return {'seq': seq, 'fromSeq': max_seq + 1, 'toSeq': seq, 'messages': wire}


async def pull_messages(owner: str, user_id: str, chat_id: str, after_seq: int, limit: int | None) -> dict:
    """Các tin có ``seq`` lớn hơn ``after_seq`` theo thứ tự, và ``seq``: seq lớn nhất của hội thoại, hoặc seq của tin
    cuối đã trả khi còn tin chưa trả (để con trỏ của trình duyệt không vượt qua phần chưa kéo)."""
    clamped = PULL_ALL_MAX if not limit or limit <= 0 else min(limit, PULL_MAX)
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await _live_chat(db, owner, chat_id)
        rows = await (await db.execute(
            'SELECT * FROM companion_chat_messages WHERE owner=? AND chat_id=? AND seq>? ORDER BY seq LIMIT ?',
            (owner, chat_id, after_seq, clamped))).fetchall()
        max_seq = (await (await db.execute(
            'SELECT COALESCE(MAX(seq), 0) FROM companion_chat_messages WHERE owner=? AND chat_id=?',
            (owner, chat_id))).fetchone())[0]
        wire = await _wire_messages(db, owner, user_id, rows)
    seq = rows[-1]['seq'] if rows and rows[-1]['seq'] < max_seq else max_seq
    return {'messages': wire, 'seq': seq}


# --- Ảnh ------------------------------------------------------------------------------------------------------------

def attachment_path(user_id: str, attachment_id: str, mime: str) -> Path:
    return config.UPLOAD_DIR / 'companion' / user_id / (attachment_id + IMAGE_MIMES[mime])


async def owner_of_user(user_id: str) -> str | None:
    """Tài khoản của một mã người dùng đồng bộ; ``None`` khi không có (hay tài khoản đã xóa)."""
    async with connect() as db:
        row = await (await db.execute('SELECT owner FROM companion_sync_users WHERE user_id=?', (user_id,))).fetchone()
    return row[0] if row else None


async def create_attachment(owner: str, user_id: str, attachment_id: str, mime: str, sha256: str,
                            size: int) -> tuple[dict, bool]:
    """Đăng ký một ảnh; gọi lại với cùng mã thì trả hàng đã có, như AIRI. Trả ``(ảnh, còn phải tải lên)``. Dọn luôn
    các ảnh của tài khoản đăng ký quá ``PENDING_MAX_AGE`` mà chưa xong."""
    now = time.time()
    path = str(attachment_path(user_id, attachment_id, mime))
    stale_where = "owner=? AND state='pending' AND created_at<? AND id<>?"
    stale_args = (owner, now - PENDING_MAX_AGE, attachment_id)
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN IMMEDIATE')
        try:
            stale = [row['path'] for row in await (await db.execute(
                f'SELECT path FROM companion_attachments WHERE {stale_where}', stale_args)).fetchall()]
            await db.execute(f'DELETE FROM companion_attachments WHERE {stale_where}', stale_args)
            await db.execute('INSERT OR IGNORE INTO companion_attachments (owner, id, mime, sha256, size, state, path, '
                             "created_at, updated_at) VALUES (?,?,?,?,?,'pending',?,?,?)",
                             (owner, attachment_id, mime, sha256, size, path, now, now))
            row = await (await db.execute('SELECT * FROM companion_attachments WHERE owner=? AND id=?',
                                          (owner, attachment_id))).fetchone()
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    _unlink(stale)
    if (row['mime'], row['sha256'], row['size']) != (mime, sha256, size):
        raise SyncError(409, 'Mã ảnh này đã dùng cho một ảnh khác.')
    return public_attachment(row), row['state'] != 'ready'


async def get_attachment(owner: str, attachment_id: str) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute('SELECT * FROM companion_attachments WHERE owner=? AND id=?',
                                      (owner, attachment_id))).fetchone()
    return dict(row) if row else None


async def mark_attachment_ready(owner: str, attachment_id: str) -> None:
    async with connect() as db:
        await db.execute("UPDATE companion_attachments SET state='ready', updated_at=? WHERE owner=? AND id=?",
                         (time.time(), owner, attachment_id))
        await db.commit()
