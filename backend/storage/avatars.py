"""Một ảnh đại diện riêng cho mỗi tài khoản; ảnh gốc đăng nhập vẫn được giữ."""
import time
import uuid
from storage import connection


def info(user: dict) -> dict:
    version = user.get('avatar_version')
    return {'avatar_url': f'/api/profile/avatar?v={version}' if version else user.get('avatar_url', ''),
            'custom_avatar': bool(version)}


async def save(owner: str, data: bytes) -> None:
    async with connection.connect() as db:
        await db.execute('PRAGMA foreign_keys=ON')
        await db.execute('''INSERT INTO user_avatars(owner,data,version,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(owner) DO UPDATE SET data=excluded.data,version=excluded.version,updated_at=excluded.updated_at''',
                         (owner, data, uuid.uuid4().hex, time.time()))
        await db.commit()


async def get(owner: str) -> bytes | None:
    async with connection.connect() as db:
        row = await (await db.execute('SELECT data FROM user_avatars WHERE owner=?', (owner,))).fetchone()
        return row[0] if row else None


async def reset(owner: str) -> None:
    async with connection.connect() as db:
        await db.execute('DELETE FROM user_avatars WHERE owner=?', (owner,))
        await db.commit()
