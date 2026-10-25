"""Thẻ nhân vật Companion của từng tài khoản (theo thẻ AIRI, chuẩn Character Card v3) và mạch trò chuyện của mỗi thẻ.

Thẻ mặc định có id ``peto``: cột nào còn NULL là dùng giá trị gốc của máy chủ (persona Companion), nên bản gốc sửa ở máy
chủ thì người chưa đụng tới vẫn nhận được. Thẻ người dùng tạo có id 32 ký tự hex.
"""
from __future__ import annotations

import json
import time
import uuid

import aiosqlite

from storage.connection import connect

DEFAULT_CARD = 'peto'
TEXT_FIELDS = ('name', 'nickname', 'version', 'description', 'notes', 'personality', 'scenario',
               'system_prompt', 'post_history', 'display_model')
JSON_FIELDS = ('greetings', 'modules')
FIELDS = TEXT_FIELDS + JSON_FIELDS


async def init_tables(db: aiosqlite.Connection) -> None:
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_cards (
        owner TEXT NOT NULL, id TEXT NOT NULL,
        name TEXT, nickname TEXT, version TEXT, description TEXT, notes TEXT, personality TEXT, scenario TEXT,
        system_prompt TEXT, post_history TEXT, display_model TEXT, greetings TEXT, modules TEXT,
        active_conversation TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(owner, id))''')
    await db.execute('''CREATE TABLE IF NOT EXISTS companion_card_state (
        owner TEXT PRIMARY KEY, active_card TEXT NOT NULL DEFAULT 'peto')''')
    columns = {row[1] for row in await (await db.execute('PRAGMA table_info(conversations)')).fetchall()}
    if 'card_id' not in columns:
        # Mạch Companion có từ trước thẻ nhân vật (25/10/2026) đều là của thẻ Peto mặc định.
        await db.execute('ALTER TABLE conversations ADD COLUMN card_id TEXT')
    await db.execute(f"UPDATE conversations SET card_id='{DEFAULT_CARD}' WHERE mode='companion' AND card_id IS NULL")


def _row(row: aiosqlite.Row) -> dict:
    card = {'id': row['id'], 'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'active_conversation': row['active_conversation']}
    for name in TEXT_FIELDS:
        card[name] = row[name]
    for name in JSON_FIELDS:
        card[name] = json.loads(row[name]) if row[name] else None
    return card


async def _ensure_default(db: aiosqlite.Connection, owner: str) -> None:
    now = time.time()
    await db.execute('INSERT OR IGNORE INTO companion_cards (owner, id, created_at, updated_at) VALUES (?,?,?,?)',
                     (owner, DEFAULT_CARD, now, now))
    await db.execute('INSERT OR IGNORE INTO companion_card_state (owner) VALUES (?)', (owner,))


async def list_cards(owner: str) -> tuple[str, list[dict]]:
    """(thẻ đang dùng, mọi thẻ còn giá trị NULL thô). Thẻ đang dùng bị xóa thì trả về thẻ mặc định."""
    async with connect() as db:
        await _ensure_default(db, owner)
        await db.commit()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute('SELECT * FROM companion_cards WHERE owner=? ORDER BY created_at, id',
                                       (owner,))).fetchall()
        active = (await (await db.execute('SELECT active_card FROM companion_card_state WHERE owner=?',
                                          (owner,))).fetchone())[0]
    cards = [_row(row) for row in rows]
    if not any(card['id'] == active for card in cards):
        active = DEFAULT_CARD
    return active, cards


async def get_card(owner: str, card_id: str) -> dict | None:
    async with connect() as db:
        if card_id == DEFAULT_CARD:
            await _ensure_default(db, owner)
            await db.commit()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute('SELECT * FROM companion_cards WHERE owner=? AND id=?',
                                      (owner, card_id))).fetchone()
    return _row(row) if row else None


def _values(fields: dict) -> dict:
    return {name: json.dumps(value, ensure_ascii=False) if name in JSON_FIELDS and value is not None else value
            for name, value in fields.items() if name in FIELDS}


async def create_card(owner: str, fields: dict, limit: int) -> str | None:
    """None khi đã đủ ``limit`` thẻ tự tạo."""
    card_id = uuid.uuid4().hex
    now = time.time()
    values = _values(fields)
    async with connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        count = (await (await db.execute('SELECT COUNT(*) FROM companion_cards WHERE owner=? AND id!=?',
                                         (owner, DEFAULT_CARD))).fetchone())[0]
        if count >= limit:
            await db.rollback()
            return None
        names = ', '.join(values)
        marks = ', '.join('?' for _ in values)
        await db.execute(f'INSERT INTO companion_cards (owner, id, created_at, updated_at, {names}) '
                         f'VALUES (?, ?, ?, ?, {marks})', (owner, card_id, now, now, *values.values()))
        await db.commit()
    return card_id


async def update_card(owner: str, card_id: str, fields: dict) -> bool:
    values = _values(fields)
    if not values:
        return await get_card(owner, card_id) is not None
    sets = ', '.join(f'{name}=?' for name in values)
    async with connect() as db:
        if card_id == DEFAULT_CARD:
            await _ensure_default(db, owner)
        result = await db.execute(f'UPDATE companion_cards SET {sets}, updated_at=? WHERE owner=? AND id=?',
                                  (*values.values(), time.time(), owner, card_id))
        await db.commit()
        return result.rowcount > 0


async def card_conversations(owner: str, card_id: str) -> list[str]:
    async with connect() as db:
        rows = await (await db.execute("SELECT id FROM conversations WHERE owner=? AND mode='companion' AND card_id=?",
                                       (owner, card_id))).fetchall()
    return [row[0] for row in rows]


async def delete_card(owner: str, card_id: str) -> bool:
    """Xóa thẻ tự tạo; mạch trò chuyện của thẻ do API xóa trước (kèm tệp). Thẻ đang dùng thì quay về thẻ mặc định."""
    async with connect() as db:
        result = await db.execute('DELETE FROM companion_cards WHERE owner=? AND id=? AND id!=?',
                                  (owner, card_id, DEFAULT_CARD))
        await db.execute('UPDATE companion_card_state SET active_card=? WHERE owner=? AND active_card=?',
                         (DEFAULT_CARD, owner, card_id))
        await db.commit()
        return result.rowcount > 0


async def set_active_card(owner: str, card_id: str, conversation_id: str | None = None) -> None:
    async with connect() as db:
        await _ensure_default(db, owner)
        await db.execute('UPDATE companion_card_state SET active_card=? WHERE owner=?', (card_id, owner))
        if conversation_id:
            await db.execute('UPDATE companion_cards SET active_conversation=? WHERE owner=? AND id=?',
                             (conversation_id, owner, card_id))
        await db.commit()


async def active_conversation(owner: str, card_id: str) -> str | None:
    """Mạch đang mở của thẻ, hoặc mạch mới nhất của thẻ khi mạch đó đã bị xóa (như AIRI: mỗi thẻ nhớ phiên của mình)."""
    async with connect() as db:
        row = await (await db.execute(
            "SELECT c.id FROM companion_cards k JOIN conversations c ON c.id=k.active_conversation AND c.owner=k.owner "
            "AND c.mode='companion' AND c.card_id=k.id WHERE k.owner=? AND k.id=?", (owner, card_id))).fetchone()
    return row[0] if row else await latest_card_conversation(owner, card_id)


async def latest_card_conversation(owner: str, card_id: str) -> str | None:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT id FROM conversations WHERE owner=? AND mode='companion' AND card_id=? "
            "ORDER BY updated_at DESC, id DESC LIMIT 1", (owner, card_id))).fetchone()
    return row[0] if row else None


async def companion_conversation(owner: str, conversation_id: str) -> dict | None:
    async with connect() as db:
        row = await (await db.execute("SELECT id, card_id, title FROM conversations WHERE id=? AND owner=? AND mode='companion'",
                                      (conversation_id, owner))).fetchone()
    return {'id': row[0], 'card_id': row[1] or DEFAULT_CARD, 'title': row[2]} if row else None


async def list_companion_conversations(owner: str, limit: int = 100) -> list[dict]:
    """Mọi mạch Companion của tài khoản, hoạt động gần nhất trước, kèm tin người dùng đầu tiên làm dòng xem trước."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT c.id, c.title, c.card_id, c.created_at, c.updated_at,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count,
                      (SELECT content FROM messages m WHERE m.conversation_id=c.id AND m.role='user'
                        ORDER BY m.id LIMIT 1) AS first_user
                 FROM conversations c WHERE c.owner=? AND c.mode='companion'
                ORDER BY c.updated_at DESC, c.id DESC LIMIT ?""", (owner, limit))).fetchall()
    return [dict(row) for row in rows]
