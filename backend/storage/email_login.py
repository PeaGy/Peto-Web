"""Bảng của đăng nhập bằng email và của việc gộp tài khoản theo email đã xác minh.

Không lưu địa chỉ email đầy đủ: chỉ ``email_hash`` (SHA-256 của email đã chuẩn hóa, xem
``features.accounts.email_login.email_hash``) và tên hiển thị là phần trước @ (cột ``masked`` giữ tên cũ của nó). Token của đường dẫn trong
thư và mã của yêu cầu (cookie của trình duyệt đã gõ email) cũng chỉ lưu dạng băm.

- ``email_accounts``: email nào thuộc owner nào. Tài khoản đầu tiên có email đó (đăng nhập email, Google hay GitHub với
  email đã xác minh) nhận nó; lối đăng nhập mới tinh về sau có cùng email thì vào chính owner đó. Owner Discord không bao
  giờ có mặt ở đây.
- ``account_identities``: mỗi danh tính Google/GitHub đã đăng nhập thuộc owner nào (để đổi email bên Google sau này
  không tách ra tài khoản mới).
- ``email_login_links``: mỗi thư đăng nhập một dòng, đi qua ``pending`` → ``approved`` (đã bấm/xác nhận, có owner) →
  ``claimed`` (tab đang chờ đã nhận phiên); hoặc ``denied`` (người nhận thư bấm "Không phải mình"), ``replaced`` (có
  thư mới hơn).
"""

from __future__ import annotations

import secrets
import time

from storage import connection as db_connection


async def init_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS email_accounts (
            email_hash TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    # Bản đầu của nhánh (chưa từng deploy) đặt UNIQUE trên owner; gộp tài khoản cần nhiều email cho một owner.
    indexes = await (await db.execute("PRAGMA index_list(email_accounts)")).fetchall()
    if any(row[2] and str(row[1]).startswith("sqlite_autoindex_email_accounts_2") for row in indexes):
        await db.execute("ALTER TABLE email_accounts RENAME TO email_accounts_old")
        await db.execute(
            "CREATE TABLE email_accounts (email_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        await db.execute("INSERT INTO email_accounts SELECT email_hash, owner, created_at FROM email_accounts_old")
        await db.execute("DROP TABLE email_accounts_old")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_email_accounts_owner ON email_accounts(owner)")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS account_identities (
            identity TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS email_login_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT NOT NULL,
            masked TEXT NOT NULL,
            link_hash TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            device TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            owner TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_email_login_links_email ON email_login_links(email_hash, created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_email_login_links_link ON email_login_links(link_hash)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_email_login_links_request ON email_login_links(request_hash)")
    # Bảng mã 6 số của bản đầu (chưa từng deploy): luồng mã đã bỏ.
    await db.execute("DROP TABLE IF EXISTS email_login_codes")


# --- Thư đăng nhập ---------------------------------------------------------------------------------------------------


async def recent_sends(email_hash: str, since: float) -> list[float]:
    """Thời điểm các lần gửi thư cho email này từ ``since`` tới giờ, mới nhất trước."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT created_at FROM email_login_links WHERE email_hash = ? AND created_at >= ? ORDER BY created_at DESC",
            (email_hash, since),
        )
        return [row[0] for row in await cursor.fetchall()]


async def add_link(*, email_hash: str, masked: str, link_hash: str, request_hash: str, device: str, ttl: float,
                   keep_for: float) -> int:
    """Ghi thư mới; thư cũ chưa dùng của email đó thành ``replaced`` (chỉ thư sau cùng còn dùng được)."""
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute("DELETE FROM email_login_links WHERE created_at < ?", (now - keep_for,))
        await db.execute("UPDATE email_login_links SET state = 'replaced' WHERE email_hash = ? AND state = 'pending'",
                         (email_hash,))
        cursor = await db.execute(
            "INSERT INTO email_login_links (email_hash, masked, link_hash, request_hash, device, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email_hash, masked, link_hash, request_hash, device, now, now + ttl),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def drop_link(link_id: int) -> None:
    """Bỏ thư không gửi được."""
    async with db_connection.connect() as db:
        await db.execute("UPDATE email_login_links SET state = 'replaced' WHERE id = ?", (link_id,))
        await db.commit()


async def pending_link(link_hash: str) -> dict | None:
    """Thư còn dùng được ứng với token này, hoặc None."""
    if not link_hash:
        return None
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT id, email_hash, masked, request_hash, device, created_at FROM email_login_links "
            "WHERE link_hash = ? AND state = 'pending' AND expires_at > ?",
            (link_hash, time.time()),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    keys = ("id", "email_hash", "masked", "request_hash", "device", "created_at")
    return dict(zip(keys, row))


async def approve_link(link_id: int, owner: str) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "UPDATE email_login_links SET state = 'approved', owner = ? WHERE id = ? AND state = 'pending'",
            (owner, link_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def deny_link(link_id: int) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "UPDATE email_login_links SET state = 'denied' WHERE id = ? AND state = 'pending'", (link_id,))
        await db.commit()
        return cursor.rowcount == 1


async def request_state(request_hash: str, claim_window: float) -> tuple[str, str]:
    """Trạng thái thư mới nhất của trình duyệt đã gõ email: (``waiting`` | ``signed_in`` | ``denied`` | ``expired``,
    owner). ``signed_in`` chỉ trả về một lần: dòng chuyển sang ``claimed`` ngay trong câu lệnh đó."""
    if not request_hash:
        return "expired", ""
    now = time.time()
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT id, state, owner, expires_at FROM email_login_links WHERE request_hash = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (request_hash,),
        )
        row = await cursor.fetchone()
        if not row:
            return "expired", ""
        link_id, state, owner, expires_at = row
        if state == "pending":
            return ("waiting", "") if expires_at > now else ("expired", "")
        if state == "approved" and now < expires_at + claim_window:
            cursor = await db.execute(
                "UPDATE email_login_links SET state = 'claimed' WHERE id = ? AND state = 'approved'", (link_id,))
            await db.commit()
            return ("signed_in", owner) if cursor.rowcount == 1 else ("expired", "")
        return ("denied", "") if state == "denied" else ("expired", "")


# --- Owner theo email và theo danh tính ------------------------------------------------------------------------------


async def owner_for_email(email_hash: str) -> str | None:
    async with db_connection.connect() as db:
        cursor = await db.execute("SELECT owner FROM email_accounts WHERE email_hash = ?", (email_hash,))
        row = await cursor.fetchone()
    return str(row[0]) if row else None


async def claim_email(email_hash: str, owner: str) -> None:
    """Gắn email cho owner nếu chưa ai nhận. Không bao giờ chuyển email đã có chủ, không bao giờ gắn cho owner Discord."""
    if owner.startswith("discord:"):
        raise ValueError("owner Discord không được gắn email")
    async with db_connection.connect() as db:
        await db.execute("INSERT OR IGNORE INTO email_accounts (email_hash, owner, created_at) VALUES (?, ?, ?)",
                         (email_hash, owner, time.time()))
        await db.commit()


async def email_owner(email_hash: str) -> str:
    """Owner của email; chưa có thì tạo tài khoản email mới (``email:<32 ký tự hex>``)."""
    await claim_email(email_hash, f"email:{secrets.token_hex(16)}")
    owner = await owner_for_email(email_hash)
    assert owner is not None
    return owner


async def move_email_account(source: str, target: str) -> None:
    """Nhập tài khoản email ``source`` vào tài khoản ``target`` (Google/GitHub cùng email đã xác minh): mọi dòng có cột
    ``owner`` chuyển sang ``target``, email và danh tính của ``source`` trỏ về ``target``, rồi ``source`` không còn.

    Dòng nào đụng ràng buộc duy nhất của ``target`` (hồ sơ, ảnh đại diện, mục "Bạn" của trí nhớ, cài đặt…) thì giữ bản
    của ``target`` và bỏ bản của ``source``. Bảng ``users`` đi sau cùng: ảnh đại diện và bài hát yêu thích tham chiếu
    tới nó với ON DELETE CASCADE. Chỉ nhận ``source`` là tài khoản email: không bao giờ gộp hai tài khoản OAuth hay
    tài khoản Discord."""
    if not source.startswith("email:") or source == target or target.startswith("discord:"):
        raise ValueError("chỉ nhập được tài khoản email vào một tài khoản khác không phải Discord")
    async with db_connection.connect() as db:
        names = [row[0] for row in await (await db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")).fetchall()]
        tables = []
        for name in names:
            columns = await (await db.execute(f'PRAGMA table_info("{name}")')).fetchall()
            if any(column[1] == "owner" for column in columns):
                tables.append(name)
        tables.sort(key=lambda name: name == "users")
        try:
            for name in tables:
                await db.execute(f'UPDATE OR IGNORE "{name}" SET owner = ? WHERE owner = ?', (target, source))
                await db.execute(f'DELETE FROM "{name}" WHERE owner = ?', (source,))
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def identity_owner(identity: str) -> str | None:
    async with db_connection.connect() as db:
        cursor = await db.execute("SELECT owner FROM account_identities WHERE identity = ?", (identity,))
        row = await cursor.fetchone()
    return str(row[0]) if row else None


async def link_identity(identity: str, owner: str) -> None:
    async with db_connection.connect() as db:
        await db.execute("INSERT OR IGNORE INTO account_identities (identity, owner, created_at) VALUES (?, ?, ?)",
                         (identity, owner, time.time()))
        await db.commit()
