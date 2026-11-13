"""Một chỗ mở kết nối SQLite (G3.1): khóa ngoại và busy_timeout luôn bật, trừ kết nối nâng cấp schema."""
from pathlib import Path
import re
import sqlite3
import time

import pytest

from storage import connection, player
from storage.schema import init_db

BACKEND = Path(__file__).resolve().parents[1]


async def pragmas(**kwargs):
    async with connection.connect(**kwargs) as conn:
        foreign = (await (await conn.execute('PRAGMA foreign_keys')).fetchone())[0]
        busy = (await (await conn.execute('PRAGMA busy_timeout')).fetchone())[0]
    return foreign, busy


async def test_every_connection_enables_foreign_keys_and_busy_timeout(tmp_path):
    assert await pragmas() == (1, 5000)
    assert await pragmas(path=tmp_path / 'rieng.db') == (1, 5000)
    # Chỉ kết nối nâng cấp schema tắt khóa ngoại; vẫn chờ khóa ghi như mọi kết nối khác.
    assert await pragmas(foreign_keys=False) == (0, 5000)


async def test_foreign_keys_hold_inside_transactions_and_reject_orphans(client):
    # Fixture client chạy init_db của conftest, nên bảng đã có.
    # PRAGMA foreign_keys đặt sau BEGIN không có tác dụng; bật lúc mở thì giao dịch nào cũng có khóa ngoại.
    async with connection.connect() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        assert (await (await conn.execute('PRAGMA foreign_keys')).fetchone())[0] == 1
        await conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        await player.save_favorite('discord:khong-ton-tai', 'abc', 'Bài', 'Ca sĩ')


def test_no_module_opens_sqlite_or_toggles_foreign_keys_on_its_own():
    opens, toggles = [], []
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(('tests/', '.venv/')) or '/.venv/' in relative:
            continue
        text = path.read_text(encoding='utf-8')
        if relative != 'storage/connection.py' and re.search(r'aiosqlite\.connect\(', text):
            opens.append(relative)
        if relative not in {'storage/connection.py', 'ops/purge_guests.py'} and re.search(r'PRAGMA foreign_keys', text, re.I):
            toggles.append(relative)
    # Các công cụ ops/ dùng sqlite3 đồng bộ, chạy ngoài máy chủ; purge_guests tự bật khóa ngoại để xóa dây chuyền.
    assert opens == [] and toggles == []


async def test_schema_upgrade_rebuilds_users_without_cascading_child_rows(tmp_path, monkeypatch):
    path = tmp_path / 'cu.db'
    with sqlite3.connect(path) as old:
        # Bảng users trước khi có cột provider, cùng hàng con trỏ tới nó.
        old.executescript('''
            CREATE TABLE users (owner TEXT PRIMARY KEY, discord_id TEXT UNIQUE, username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '', avatar_url TEXT NOT NULL DEFAULT '',
                first_login_at REAL NOT NULL, last_login_at REAL NOT NULL);
            CREATE TABLE user_avatars (owner TEXT PRIMARY KEY REFERENCES users(owner) ON DELETE CASCADE,
                data BLOB NOT NULL, version TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE player_favorites (owner TEXT NOT NULL REFERENCES users(owner) ON DELETE CASCADE,
                video_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL, PRIMARY KEY(owner, video_id));
        ''')
        now = time.time()
        old.execute("INSERT INTO users(owner, discord_id, first_login_at, last_login_at) VALUES('discord:1','1',?,?)", (now, now))
        old.execute("INSERT INTO user_avatars VALUES('discord:1', x'00', 'v1', ?)", (now,))
        old.execute("INSERT INTO player_favorites VALUES('discord:1', 'abc', 'Bài', '', ?)", (now,))
    monkeypatch.setattr(connection, 'DB_PATH', path)
    await init_db()
    with sqlite3.connect(path) as check:
        columns = {row[1] for row in check.execute('PRAGMA table_info(users)')}
        assert 'provider' in columns
        assert check.execute('SELECT COUNT(*) FROM user_avatars').fetchone()[0] == 1
        assert check.execute('SELECT COUNT(*) FROM player_favorites').fetchone()[0] == 1
        assert check.execute('PRAGMA foreign_key_check').fetchall() == []


async def test_deleting_a_project_cascades_its_files_through_the_shared_connection(client):
    # Trước G3.1 chỉ lệnh DELETE tay dọn project_files; nay khóa ngoại cũng làm, kết quả giống hệt.
    owner = 'discord:000000000000000001'
    async with connection.connect() as conn:
        now = time.time()
        await conn.execute("INSERT INTO projects(id, owner, name, created_at, updated_at) VALUES('p-g31', ?, 'Dự án', ?, ?)",
                           (owner, now, now))
        await conn.execute("INSERT INTO project_files VALUES('f-g31', 'p-g31', ?, 'a.txt', 'text/plain', 1, x'00', '{}', ?)",
                           (owner, now))
        await conn.commit()
        await conn.execute("DELETE FROM projects WHERE id='p-g31'")
        await conn.commit()
        assert (await (await conn.execute("SELECT COUNT(*) FROM project_files WHERE id='f-g31'")).fetchone())[0] == 0
