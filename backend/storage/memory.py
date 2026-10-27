"""Truy vấn trí nhớ chia mục và tóm tắt hội thoại Companion."""

from __future__ import annotations
import json
import time
import aiosqlite
from storage import connection as db_connection


def _entry(row: aiosqlite.Row) -> dict:
    item = dict(row)
    try:
        details = json.loads(item.get("details") or "[]")
    except ValueError:
        details = []
    item["details"] = [text for text in details if isinstance(text, str)] if isinstance(details, list) else []
    return item


ENTRY_COLUMNS = "id, section, slot, title, summary, details, created_at, updated_at"


async def list_memories(owner: str) -> list[dict]:
    """Các mục trí nhớ của ``owner``, mỗi mục có ``details`` là danh sách câu."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {ENTRY_COLUMNS} FROM companion_memory_entries WHERE owner = ? ORDER BY id", (owner,)
        )
        return [_entry(row) for row in await cursor.fetchall()]


async def memory_state(owner: str) -> dict | None:
    """Bật/tắt, vị trí đã đọc và mốc tóm tắt; None khi người dùng chưa từng có (mặc định là bật)."""
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "SELECT enabled, cursor, since, revision FROM companion_memory_state WHERE owner = ?", (owner,)
        )
        row = await cursor.fetchone()
    return {"enabled": bool(row[0]), "cursor": row[1], "since": row[2], 'revision': row[3]} if row else None


async def ensure_memory_state(owner: str) -> dict:
    """Lần đầu ghi nhớ thì bắt đầu từ tin người dùng mới nhất: lịch sử có từ trước khi có trí nhớ không bị lục lại,
    cả để ghi nhớ lẫn để tóm tắt."""
    async with db_connection.connect() as db:
        start = max(await _last_memory_message_id(db, owner, "user") - 1, 0)
        await db.execute(
            "INSERT OR IGNORE INTO companion_memory_state (owner, enabled, cursor, since, updated_at) "
            "VALUES (?, 1, ?, ?, ?)",
            (owner, start, start, time.time()),
        )
        await db.commit()
    return await memory_state(owner) or {"enabled": True, "cursor": start, "since": start, 'revision': 0}


# Tin nào được đọc để ghi nhớ: Companion và Chat thường. Chat nhập vai thì không (chủ web chốt 11/10/2026): lời thoại
# nhân vật và nội dung 18+ không được lẫn vào trí nhớ của trợ lý. Tin của lượt Companion dùng khóa riêng (cột provider)
# cũng không (13/10/2026); hai truy vấn đọc tin bên dưới lọc thêm ``m.provider = ''``.
# Companion chỉ tính mạch của thẻ Peto mặc định: thẻ nhân vật người dùng tự viết chưa đọc, chưa ghi trí nhớ chung
# (25/10/2026), để chuyện của một nhân vật nhập vai không lọt sang tab Trò chuyện.
MEMORY_SOURCE = "((c.mode = 'companion' AND COALESCE(c.card_id, 'peto') = 'peto') OR (c.mode = 'chat' AND c.persona = 'assistant'))"
SOURCE_COLUMNS = '''m.id,m.role,m.content,m.conversation_id,m.status,m.provider,c.mode,c.persona,c.project_id,c.archived,
    COALESCE((SELECT state FROM chat_turns WHERE owner=c.owner AND
    (user_message_id=m.id OR assistant_message_id=m.id) ORDER BY id DESC LIMIT 1),'') AS turn_state'''


async def _valid_snapshot(db, owner, revision, rows):
    """Kiểm quyền, cờ bật và nguồn gốc dưới cùng write lock với lần ghi; không phục hồi nội dung đã xóa."""
    state = await (await db.execute('SELECT enabled,revision FROM companion_memory_state WHERE owner=?', (owner,))).fetchone()
    if not state or not state[0] or state[1] != revision:
        return False
    for expected in rows:
        row = await (await db.execute(f'''SELECT {SOURCE_COLUMNS} FROM messages m JOIN conversations c ON c.id=m.conversation_id
            WHERE m.id=? AND c.owner=? AND {MEMORY_SOURCE} AND m.provider='' ''', (expected['id'], owner))).fetchone()
        if row is None:
            return False
        names = ('id', 'role', 'content', 'conversation_id', 'status', 'provider', 'mode', 'persona', 'project_id', 'archived', 'turn_state')
        current = dict(zip(names, row))
        if any(current.get(key) != value for key, value in expected.items() if key in current):
            return False
        if current['mode'] == 'chat' and (current['status'] != 'complete' or current['turn_state'] not in {'', 'complete'}):
            return False
    return True


async def _last_memory_message_id(db: aiosqlite.Connection, owner: str, role: str | None = None) -> int:
    query = (
        "SELECT MAX(m.id) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
        f"WHERE c.owner = ? AND {MEMORY_SOURCE}"
    )
    params: tuple = (owner,)
    if role:
        query += " AND m.role = ?"
        params += (role,)
    row = await (await db.execute(query, params)).fetchone()
    return row[0] or 0


async def set_memory_enabled(owner: str, enabled: bool) -> None:
    """Bật lại thì bắt đầu đọc từ tin mới nhất: điều người dùng nói lúc đang tắt không bị ghi nhớ hay tóm tắt về sau."""
    async with db_connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        latest = await _last_memory_message_id(db, owner)
        await db.execute(
            """
            INSERT INTO companion_memory_state (owner, enabled, cursor, since, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner) DO UPDATE SET
                enabled = excluded.enabled,
                cursor = CASE WHEN excluded.enabled = 1 AND companion_memory_state.enabled = 0
                              THEN excluded.cursor ELSE companion_memory_state.cursor END,
                since = CASE WHEN excluded.enabled = 1 AND companion_memory_state.enabled = 0
                             THEN excluded.since ELSE companion_memory_state.since END,
                updated_at = excluded.updated_at, revision = companion_memory_state.revision + 1
            """,
            (owner, int(enabled), latest, latest, time.time()),
        )
        await db.commit()


async def memory_messages_after(owner: str, after_id: int, limit: int) -> list[dict]:
    """Tin Companion và Chat thường mới hơn ``after_id``, lấy ``limit`` tin gần nhất, xếp cũ trước mới sau. Mỗi tin có
    ``conversation_id`` và ``mode`` để đoạn gửi model phụ tách được từng cuộc trò chuyện.

    Người dùng chưa từng có vị trí đã đọc (``after_id`` âm) thì chỉ đọc từ tin người dùng mới nhất: lịch sử có từ
    trước khi có trí nhớ không bị lục lại.
    """
    async with db_connection.connect() as db:
        if after_id < 0:
            after_id = max(await _last_memory_message_id(db, owner, "user") - 1, 0)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {SOURCE_COLUMNS} FROM messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            f"WHERE c.owner = ? AND {MEMORY_SOURCE} AND m.id > ? AND m.role IN ('user', 'assistant') AND m.provider = '' "
            "AND (c.mode!='chat' OR (m.status='complete' AND COALESCE((SELECT state FROM chat_turns WHERE owner=c.owner "
            "AND (user_message_id=m.id OR assistant_message_id=m.id) ORDER BY id DESC LIMIT 1),'complete')='complete')) "
            # Không dời cursor qua một lượt khác đang chạy: checkpoint có ID cũ nhưng chưa đủ nội dung để ghi nhớ.
            "AND m.id < COALESCE((SELECT MIN(t.user_message_id) FROM chat_turns t WHERE t.owner=? AND t.state='running'),9223372036854775807) "
            "ORDER BY m.id DESC LIMIT ?",
            (owner, after_id, owner, limit),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
    return rows[::-1]


async def memory_context_before(owner: str, rows: list[dict], *, since: int, limit: int = 4) -> list[dict]:
    """A few preceding messages in each represented thread resolve referents, without authorizing new memories.

    Never read across an off/delete boundary. Read at most 4 preceding rows per thread, return at most 12 in total.
    Returned snapshots are revalidated under the write lock along with new rows.
    """
    before = {}
    for row in rows:
        cid = row.get('conversation_id')
        if cid:
            before[cid] = min(before.get(cid, row['id']), row['id'])
    context = []
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        for cid, first in list(before.items())[:12]:
            found = await (await db.execute(f'''SELECT {SOURCE_COLUMNS} FROM messages m
                JOIN conversations c ON c.id=m.conversation_id
                WHERE c.owner=? AND c.id=? AND {MEMORY_SOURCE} AND m.provider=''
                    AND m.id>? AND m.id<? AND m.role IN ('user','assistant')
                    AND (c.mode!='chat' OR (m.status='complete' AND COALESCE((SELECT state FROM chat_turns
                        WHERE owner=c.owner AND (user_message_id=m.id OR assistant_message_id=m.id)
                        ORDER BY id DESC LIMIT 1),'complete')='complete'))
                ORDER BY m.id DESC LIMIT ?''', (owner, cid, since, first, min(4, max(0, limit))))).fetchall()
            context.extend(dict(row) for row in found)
    return sorted(context, key=lambda row: row['id'])[-12:]


async def apply_memory_changes(
    owner: str, *, upserts: list[dict], remove: list[int], cursor: int | None = None, limit: int,
    expected_revision: int | None = None, source_rows: list[dict] = (),
    invalidate_summaries: bool = False, remove_seen: dict | None = None,
) -> list[dict]:
    """Ghi các thay đổi trong một giao dịch; trả về các mục vừa thêm hay vừa sửa (sau khi đổi).

    Mỗi phần tử ``upserts`` có ``id`` là sửa mục đó (chỉ các trường có mặt: ``title``, ``summary``, ``details``; còn
    ``details`` rỗng là xóa cả mục), không có ``id`` là thêm mục mới (``section``, ``slot``, ``title``, ``summary``,
    ``details``). ``_seen`` là ``updated_at`` lúc đọc: mục đã đổi sau lúc đó (người dùng vừa sửa tay) thì bỏ qua thay
    đổi này. Chỉ đụng tới dòng của đúng ``owner``; thêm quá ``limit`` mục thì bỏ phần thừa; mỗi người chỉ một mục cho
    mỗi ``slot``. ``cursor`` (nếu có) là vị trí đã đọc mới cho lượt ghi nhớ nền.
    """
    now = time.time()
    changed: list[int] = []
    dropped = False
    async with db_connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        if expected_revision is not None and not await _valid_snapshot(db, owner, expected_revision, source_rows):
            return []
        for memory_id in remove:
            guard, params = ("", ()) if remove_seen is None else (" AND updated_at=?", (remove_seen.get(memory_id),))
            result = await db.execute(f"DELETE FROM companion_memory_entries WHERE id = ? AND owner = ?{guard}", (memory_id, owner, *params))
            dropped = dropped or result.rowcount > 0
        for patch in upserts:
            if "id" not in patch:
                continue
            guard, params = ("", ()) if patch.get("_seen") is None else (" AND updated_at = ?", (patch["_seen"],))
            if "details" in patch and not patch["details"]:
                result = await db.execute(
                    f"DELETE FROM companion_memory_entries WHERE id = ? AND owner = ?{guard}", (patch["id"], owner, *params)
                )
                dropped = dropped or result.rowcount > 0
                continue
            fields = {key: patch[key] for key in ("title", "summary") if patch.get(key)}
            if "details" in patch:
                fields["details"] = json.dumps(patch["details"], ensure_ascii=False)
            if not fields:
                continue
            sets = ", ".join(f"{key} = ?" for key in fields)
            differs = " OR ".join(f"{key} != ?" for key in fields)
            previous = None
            if invalidate_summaries and 'details' in patch:
                previous = await (await db.execute('SELECT details FROM companion_memory_entries WHERE id=? AND owner=?',
                                                   (patch['id'], owner))).fetchone()
            result = await db.execute(
                f"UPDATE companion_memory_entries SET {sets}, updated_at = ? "
                f"WHERE id = ? AND owner = ?{guard} AND ({differs})",
                (*fields.values(), now, patch["id"], owner, *params, *fields.values()),
            )
            if result.rowcount:
                changed.append(patch["id"])
                if previous:
                    dropped = dropped or bool(set(json.loads(previous[0])) - set(patch['details']))
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM companion_memory_entries WHERE owner = ?", (owner,)
        )).fetchone())[0]
        for patch in upserts:
            if "id" in patch or not patch.get("details") or count >= limit:
                continue
            result = await db.execute(
                "INSERT OR IGNORE INTO companion_memory_entries "
                "(owner, section, slot, title, summary, details, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (owner, patch["section"], patch.get("slot", ""), patch["title"], patch.get("summary", ""),
                 json.dumps(patch["details"], ensure_ascii=False), now, now),
            )
            if result.rowcount:
                changed.append(result.lastrowid)
                count += 1
        if invalidate_summaries and dropped:
            # Same transaction as the accepted correction: a stale/rejected proposal cannot wipe summaries or cursors.
            await _forget_summaries(db, owner)
        if cursor is not None:
            await db.execute(
                """
                INSERT INTO companion_memory_state (owner, enabled, cursor, since, updated_at) VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(owner) DO UPDATE SET cursor = MAX(companion_memory_state.cursor, excluded.cursor),
                                                 updated_at = excluded.updated_at
                """,
                (owner, cursor, cursor, now),
            )
        await db.commit()
        if not changed:
            return []
        db.row_factory = aiosqlite.Row
        marks = ",".join("?" * len(changed))
        rows = await (await db.execute(
            f"SELECT {ENTRY_COLUMNS} FROM companion_memory_entries WHERE owner = ? AND id IN ({marks}) ORDER BY id",
            (owner, *changed),
        )).fetchall()
    return [_entry(row) for row in rows]


async def delete_memory(owner: str, memory_id: int) -> bool:
    """Xóa một mục, và bỏ luôn bản tóm tắt: điều vừa xóa có thể nằm trong đó, mà không gỡ riêng ra được."""
    async with db_connection.connect() as db:
        result = await db.execute(
            "DELETE FROM companion_memory_entries WHERE id = ? AND owner = ?", (memory_id, owner)
        )
        if result.rowcount:
            await _forget_summaries(db, owner)
        await db.commit()
    return result.rowcount > 0


async def clear_memories(owner: str) -> int:
    async with db_connection.connect() as db:
        result = await db.execute("DELETE FROM companion_memory_entries WHERE owner = ?", (owner,))
        await db.execute("DELETE FROM companion_memories WHERE owner = ?", (owner,))
        await _forget_summaries(db, owner)
        await db.commit()
    return result.rowcount


async def forget_summaries(owner: str) -> None:
    """Người dùng vừa bỏ một ý (sửa tay hay bảo Peto quên): bỏ luôn bản tóm tắt Companion, như khi xóa cả mục."""
    async with db_connection.connect() as db:
        await _forget_summaries(db, owner)
        await db.commit()


async def _forget_summaries(db: aiosqlite.Connection, owner: str) -> None:
    """Xóa trắng bản tóm tắt của mọi mạch Companion và bỏ qua mọi tin đang có: tóm tắt về sau chỉ từ tin mới hơn."""
    # Lượt trích đang chờ bị hủy; lần sau cũng không được đọc lại cùng nguồn rồi học lại điều vừa quên.
    latest = await _last_memory_message_id(db, owner)
    await db.execute('''INSERT INTO companion_memory_state(owner,enabled,cursor,since,updated_at,revision)
        VALUES(?,1,?,?,?,1) ON CONFLICT(owner) DO UPDATE SET
        cursor=MAX(companion_memory_state.cursor,excluded.cursor),revision=companion_memory_state.revision+1,
        since=MAX(companion_memory_state.since,excluded.since),updated_at=excluded.updated_at''', (owner, latest, latest, time.time()))
    await db.execute(
        """
        INSERT INTO companion_summaries (conversation_id, owner, text, upto, updated_at)
        SELECT c.id, c.owner, '', COALESCE((SELECT MAX(m.id) FROM messages m WHERE m.conversation_id = c.id), 0), ?
          FROM conversations c
         WHERE c.owner = ? AND c.mode = 'companion'
        ON CONFLICT(conversation_id) DO UPDATE SET text = '', upto = excluded.upto, updated_at = excluded.updated_at
        """,
        (time.time(), owner),
    )


async def companion_summary(owner: str, conversation_id: str) -> dict | None:
    async with db_connection.connect() as db:
        row = await (await db.execute(
            "SELECT text, upto FROM companion_summaries WHERE conversation_id = ? AND owner = ?",
            (conversation_id, owner),
        )).fetchone()
    return {"text": row[0], "upto": row[1]} if row else None


async def messages_before_window(
    owner: str, conversation_id: str, *, after_id: int, window: int, limit: int
) -> list[dict]:
    """Tin cũ hơn ``window`` tin gần nhất (tức không còn được gửi kèm lượt Companion) và mới hơn ``after_id``: lấy tối
    đa ``limit`` tin cũ nhất, xếp cũ trước mới sau."""
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT m.id, m.role, m.content, m.conversation_id, c.mode, c.project_id FROM messages m JOIN conversations c ON c.id = m.conversation_id
             WHERE c.id = ? AND c.owner = ? AND m.id > ? AND m.role IN ('user', 'assistant') AND m.provider = ''
               AND m.id < (SELECT MIN(id) FROM (
                     SELECT id FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?))
             ORDER BY m.id
             LIMIT ?
            """,
            (conversation_id, owner, after_id, conversation_id, window, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def save_companion_summary(
    owner: str, conversation_id: str, *, text: str, upto: int, expected_upto: int | None,
    expected_revision: int | None = None, source_rows: list[dict] = ()
) -> bool:
    """Lưu bản tóm tắt mới nếu không ai đổi nó trong lúc model đang viết (``expected_upto`` là ``upto`` lúc đọc, None
    khi chưa có). Người dùng xóa ghi nhớ giữa chừng thì ``upto`` đã đổi: bỏ kết quả, không đem điều vừa xóa quay lại."""
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute('BEGIN IMMEDIATE')
        if expected_revision is not None and not await _valid_snapshot(db, owner, expected_revision, source_rows):
            return False
        if expected_upto is None:
            result = await db.execute(
                "INSERT INTO companion_summaries (conversation_id, owner, text, upto, updated_at) "
                "SELECT id, owner, ?, ?, ? FROM conversations WHERE id = ? AND owner = ? "
                "ON CONFLICT(conversation_id) DO NOTHING",
                (text, upto, now, conversation_id, owner),
            )
        else:
            result = await db.execute(
                "UPDATE companion_summaries SET text = ?, upto = ?, updated_at = ? "
                "WHERE conversation_id = ? AND owner = ? AND upto = ?",
                (text, upto, now, conversation_id, owner, expected_upto),
            )
        await db.commit()
    return result.rowcount > 0
