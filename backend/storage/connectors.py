"""Kết nối và mã cấp quyền riêng theo tài khoản; khóa truy cập luôn được mã hóa."""
import time
import aiosqlite
from storage import connection


async def init_tables(db):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS connector_accounts (
            owner TEXT NOT NULL, provider TEXT NOT NULL, login TEXT NOT NULL,
            credentials TEXT NOT NULL, revision TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY(owner, provider)
        );
        CREATE TABLE IF NOT EXISTS connector_oauth_states (
            state TEXT PRIMARY KEY, owner TEXT NOT NULL, session TEXT NOT NULL,
            verifier TEXT NOT NULL, expires_at REAL NOT NULL
        );
    """)


async def get_github(owner):
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM connector_accounts WHERE owner=? AND provider='github'", (owner,))).fetchone()
        return dict(row) if row else None


async def save_github(owner, login, credentials, revision):
    async with connection.connect() as db:
        await db.execute("""INSERT INTO connector_accounts VALUES(?,'github',?,?,?,?)
            ON CONFLICT(owner,provider) DO UPDATE SET login=excluded.login, credentials=excluded.credentials,
            revision=excluded.revision, updated_at=excluded.updated_at""", (owner, login, credentials, revision, time.time()))
        await db.commit()


async def refresh_github(owner, revision, credentials):
    async with connection.connect() as db:
        result = await db.execute("UPDATE connector_accounts SET credentials=?,updated_at=? WHERE owner=? AND provider='github' AND revision=?",
                                  (credentials, time.time(), owner, revision))
        await db.commit()
        return result.rowcount == 1


async def disconnect_github(owner):
    async with connection.connect() as db:
        await db.execute("DELETE FROM connector_accounts WHERE owner=? AND provider='github'", (owner,))
        await db.execute("DELETE FROM connector_oauth_states WHERE owner=?", (owner,))
        await db.commit()


async def put_state(state, owner, session, verifier):
    async with connection.connect() as db:
        await db.execute("DELETE FROM connector_oauth_states WHERE owner=? OR expires_at<?", (owner, time.time()))
        await db.execute("INSERT INTO connector_oauth_states VALUES(?,?,?,?,?)", (state, owner, session, verifier, time.time() + 600))
        await db.commit()


async def take_state(state, owner, session):
    async with connection.connect() as db:
        row = await (await db.execute("DELETE FROM connector_oauth_states WHERE state=? AND owner=? AND session=? AND expires_at>=? RETURNING verifier",
                                     (state, owner, session, time.time()))).fetchone()
        await db.commit()
        return row[0] if row else None
