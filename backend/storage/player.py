"""Yêu thích YouTube của từng tài khoản; không lưu phiên phát hoặc URL tùy ý."""
from __future__ import annotations

import time
import aiosqlite
from storage.connection import connect

MAX_FAVORITES = 500


async def init_tables(db: aiosqlite.Connection) -> None:
    await db.execute('''CREATE TABLE IF NOT EXISTS player_favorites (
        owner TEXT NOT NULL REFERENCES users(owner) ON DELETE CASCADE,
        video_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL, PRIMARY KEY(owner, video_id))''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_player_favorites_owner ON player_favorites(owner, created_at DESC)')


async def list_favorites(owner: str) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            'SELECT video_id, title, artist FROM player_favorites WHERE owner=? ORDER BY created_at DESC, video_id',
            (owner,))).fetchall()
        return [dict(row) for row in rows]


async def save_favorite(owner: str, video_id: str, title: str, artist: str) -> bool:
    async with connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        exists = await (await db.execute('SELECT 1 FROM player_favorites WHERE owner=? AND video_id=?', (owner, video_id))).fetchone()
        count = (await (await db.execute('SELECT COUNT(*) FROM player_favorites WHERE owner=?', (owner,))).fetchone())[0]
        if not exists and count >= MAX_FAVORITES:
            await db.rollback()
            return False
        await db.execute('''INSERT INTO player_favorites(owner, video_id, title, artist, created_at) VALUES(?,?,?,?,?)
            ON CONFLICT(owner, video_id) DO UPDATE SET
            title=CASE WHEN excluded.title!='' THEN excluded.title ELSE player_favorites.title END,
            artist=CASE WHEN excluded.artist!='' THEN excluded.artist ELSE player_favorites.artist END''',
            (owner, video_id, title, artist, time.time()))
        await db.commit()
        return True


async def delete_favorite(owner: str, video_id: str) -> None:
    async with connect() as db:
        await db.execute('DELETE FROM player_favorites WHERE owner=? AND video_id=?', (owner, video_id))
        await db.commit()
