"""Dự án riêng của từng tài khoản, gồm hướng dẫn và tài liệu dùng chung."""
import json
import time
import uuid
import aiosqlite
from fastapi import HTTPException
from storage import connection

MAX_PROJECTS, MAX_FILES, MAX_BYTES = 50, 20, 64 * 1024 * 1024

async def init_tables(db):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
            instructions TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner, updated_at DESC);
        CREATE TABLE IF NOT EXISTS project_files (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
            data BLOB NOT NULL, document TEXT NOT NULL, created_at REAL NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_project_files ON project_files(owner, project_id);
    """)
    columns = {row[1] for row in await (await db.execute('PRAGMA table_info(conversations)')).fetchall()}
    if 'project_id' not in columns:
        await db.execute('ALTER TABLE conversations ADD COLUMN project_id TEXT DEFAULT NULL')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_conversation_project ON conversations(owner, project_id)')

async def get_project(owner, project_id):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute('SELECT id,name,instructions,created_at,updated_at FROM projects WHERE owner=? AND id=?', (owner, project_id))).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy dự án')
        return dict(row)

async def list_projects(owner):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("""SELECT p.id, p.name, p.created_at, p.updated_at,
            (SELECT COUNT(*) FROM conversations c WHERE c.owner=p.owner AND c.project_id=p.id AND c.mode='chat' AND c.archived=0) AS conversation_count,
            (SELECT COUNT(*) FROM project_files f WHERE f.owner=p.owner AND f.project_id=p.id) AS file_count
            FROM projects p WHERE p.owner=? ORDER BY p.updated_at DESC, p.id DESC""", (owner,))).fetchall()
        return [dict(row) for row in rows]

async def create_project(owner, name):
    name = ' '.join(name.split())
    if not name:
        raise HTTPException(400, 'Tên dự án không được để trống')
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        count = (await (await db.execute('SELECT COUNT(*) FROM projects WHERE owner=?', (owner,))).fetchone())[0]
        if count >= MAX_PROJECTS:
            raise HTTPException(400, 'Mỗi tài khoản có tối đa 50 dự án')
        project_id, now = uuid.uuid4().hex, time.time()
        await db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)', (project_id, owner, name, '', now, now))
        await db.commit()
    return await get_project(owner, project_id)

async def update_project(owner, project_id, name=None, instructions=None):
    fields, values = [], []
    if name is not None:
        name = ' '.join(name.split())
        if not name:
            raise HTTPException(400, 'Tên dự án không được để trống')
        fields.append('name=?')
        values.append(name)
    if instructions is not None:
        fields.append('instructions=?')
        values.append(instructions.strip())
    if not fields:
        raise HTTPException(400, 'Chưa có thay đổi')
    async with connection.connect() as db:
        cursor = await db.execute(f"UPDATE projects SET {','.join(fields)},updated_at=? WHERE owner=? AND id=?", (*values, time.time(), owner, project_id))
        if not cursor.rowcount:
            raise HTTPException(404, 'Không tìm thấy dự án')
        await db.commit()

async def delete_project(owner, project_id):
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        cursor = await db.execute('DELETE FROM projects WHERE owner=? AND id=?', (owner, project_id))
        if not cursor.rowcount:
            raise HTTPException(404, 'Không tìm thấy dự án')
        await db.execute('DELETE FROM project_files WHERE owner=? AND project_id=?', (owner, project_id))
        await db.execute('UPDATE conversations SET project_id=NULL WHERE owner=? AND project_id=?', (owner, project_id))
        await db.commit()

async def move_conversation(owner, conversation_id, project_id):
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        if project_id is not None and not await (await db.execute('SELECT 1 FROM projects WHERE owner=? AND id=?', (owner, project_id))).fetchone():
            raise HTTPException(404, 'Không tìm thấy dự án')
        cursor = await db.execute("UPDATE conversations SET project_id=? WHERE owner=? AND id=? AND mode='chat'", (project_id, owner, conversation_id))
        if not cursor.rowcount:
            raise HTTPException(404, 'Không tìm thấy hội thoại')
        await db.commit()

async def add_file(owner, project_id, file, document):
    async with connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        if not await (await db.execute('SELECT 1 FROM projects WHERE owner=? AND id=?', (owner, project_id))).fetchone():
            raise HTTPException(404, 'Không tìm thấy dự án')
        count, size = await (await db.execute('SELECT COUNT(*), COALESCE(SUM(size),0) FROM project_files WHERE owner=? AND project_id=?', (owner, project_id))).fetchone()
        if count >= MAX_FILES or size + len(file.data) > MAX_BYTES:
            raise HTTPException(400, 'Dự án chỉ giữ tối đa 20 tài liệu và tổng 64 MB')
        file_id = uuid.uuid4().hex
        await db.execute('INSERT INTO project_files VALUES(?,?,?,?,?,?,?,?,?)', (file_id, project_id, owner, file.name, file.mime, len(file.data), file.data, json.dumps(document, ensure_ascii=False), time.time()))
        await db.commit()
        return file_id

async def check_file_capacity(owner, project_id, incoming_size):
    """Báo đầy trước khi đọc tài liệu; lúc ghi vẫn kiểm tra trong giao dịch."""
    await get_project(owner, project_id)
    async with connection.connect() as db:
        count, size = await (await db.execute('SELECT COUNT(*), COALESCE(SUM(size),0) FROM project_files WHERE owner=? AND project_id=?', (owner, project_id))).fetchone()
        if count >= MAX_FILES or size + incoming_size > MAX_BYTES:
            raise HTTPException(400, 'Dự án chỉ giữ tối đa 20 tài liệu và tổng 64 MB')

async def list_files(owner, project_id):
    await get_project(owner, project_id)
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute('SELECT id,name,mime,size,document,created_at FROM project_files WHERE owner=? AND project_id=? ORDER BY created_at,id', (owner, project_id))).fetchall()
        return [dict(row) for row in rows]

async def get_file(owner, project_id, file_id, *, data=False):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        columns = 'f.*' if data else 'f.id,f.name,f.mime,f.size,f.document'
        row = await (await db.execute(f'SELECT {columns} FROM project_files f JOIN projects p ON p.id=f.project_id AND p.owner=f.owner WHERE f.owner=? AND f.project_id=? AND f.id=?', (owner, project_id, file_id))).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy tài liệu dự án')
        return dict(row)

async def delete_file(owner, project_id, file_id):
    async with connection.connect() as db:
        cursor = await db.execute('DELETE FROM project_files WHERE owner=? AND project_id=? AND id=?', (owner, project_id, file_id))
        if not cursor.rowcount:
            raise HTTPException(404, 'Không tìm thấy tài liệu dự án')
        await db.commit()
