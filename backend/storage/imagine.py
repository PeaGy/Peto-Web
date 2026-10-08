"""Truy vấn thư viện ảnh và các lượt tạo ảnh."""

from __future__ import annotations
import time
import uuid
import aiosqlite
from storage import connection as db_connection


async def create_imagine_job(
    *,
    owner: str,
    prompt: str,
    quality: str,
    resolution: str,
    aspect_ratio: str,
    status: str = "complete",
    n: int = 1,
    request_id: str | None = None,
    fingerprint: str | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    async with db_connection.connect() as db:
        if status == "queued":
            from core.config import MAX_CONCURRENT, MAX_QUEUE
            await db.execute("BEGIN IMMEDIATE")
            rows = await (await db.execute("SELECT owner FROM imagine_jobs WHERE status IN ('queued', 'running')")).fetchall()
            if any(row[0] == owner for row in rows) or len(rows) >= MAX_CONCURRENT + MAX_QUEUE:
                raise ValueError("Hàng đợi tạo ảnh đã đầy")
        await db.execute(
            """
            INSERT INTO imagine_jobs (
                id, owner, prompt, quality, resolution, aspect_ratio, created_at, status, n, updated_at, request_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, owner, prompt, quality, resolution, aspect_ratio, now, status, n, now, request_id),
        )
        if request_id:
            await db.execute("INSERT INTO imagine_requests VALUES (?, ?, ?, ?)", (owner, request_id, fingerprint, job_id))
        await db.commit()
    return job_id


async def add_imagine_image(
    *,
    image_id: str,
    job_id: str,
    owner: str,
    mime: str,
    path: str,
    kind: str = "output",
    position: int = 0,
    parent_image_id: str | None = None,
    parent_job_id: str | None = None,
) -> None:
    now = time.time()
    async with db_connection.connect() as db:
        await db.execute(
            """
            INSERT INTO imagine_images (id, job_id, owner, mime, path, created_at, kind, position, parent_image_id, parent_job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (image_id, job_id, owner, mime, path, now, kind, position, parent_image_id, parent_job_id),
        )
        await db.commit()


async def list_imagine_jobs(owner: str, limit: int = 40, before: str | None = None, job_id: str | None = None) -> list[dict]:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        conditions = ["owner = ?"]
        params: list = [owner]
        if job_id:
            conditions.append("id = ?")
            params.append(job_id)
        if before:
            anchor = await (await db.execute("SELECT created_at, id FROM imagine_jobs WHERE owner = ? AND id = ?", (owner, before))).fetchone()
            if not anchor:
                return []
            conditions.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params += [anchor["created_at"], anchor["created_at"], anchor["id"]]
        cursor = await db.execute(
            "SELECT id, prompt, quality, resolution, aspect_ratio, created_at, status, error, n, updated_at, request_id FROM imagine_jobs WHERE "
            + " AND ".join(conditions) + " ORDER BY created_at DESC, id DESC LIMIT ?", [*params, limit],
        )
        jobs = [dict(row) for row in await cursor.fetchall()]
        if not jobs:
            return []
        ids = [job["id"] for job in jobs]
        placeholders = ",".join("?" * len(ids))
        cursor = await db.execute(
            f"""
            SELECT id, job_id, mime, created_at, kind, liked, position, parent_image_id, parent_job_id
              FROM imagine_images
             WHERE owner = ? AND job_id IN ({placeholders})
             ORDER BY position, created_at, id
            """,
            [owner, *ids],
        )
        grouped: dict[str, list[dict]] = {job_id: [] for job_id in ids}
        for row in await cursor.fetchall():
            grouped[row["job_id"]].append(dict(row))
        for job in jobs:
            job["images"] = grouped.get(job["id"], [])
        return jobs


async def get_imagine_image(owner: str, image_id: str) -> dict | None:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, job_id, mime, path, created_at, kind
              FROM imagine_images
             WHERE id = ? AND owner = ?
            """,
            (image_id, owner),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_imagine_job(owner: str, job_id: str) -> bool:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT path FROM imagine_images WHERE job_id = ? AND owner = ?",
            (job_id, owner),
        )
        paths = [str(row["path"]) for row in await cursor.fetchall()]
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "DELETE FROM imagine_jobs WHERE id = ? AND owner = ?",
            (job_id, owner),
        )
        deleted = cursor.rowcount > 0
        if deleted:
            await db.execute("DELETE FROM imagine_images WHERE job_id = ?", (job_id,))
        await db.commit()
    if deleted:
        from shared.attachments import delete_files

        delete_files(paths)
    return deleted


async def delete_imagine_image(owner: str, image_id: str) -> str | None:
    """Xóa một ảnh kết quả trong thư viện.

    Trả "image" khi lượt còn ảnh khác, "job" khi đó là ảnh cuối nên cả lượt (kèm ảnh gốc) bị xóa theo,
    và None khi không thấy ảnh kết quả nào của owner này. Ảnh gốc của lượt sửa không xóa riêng được.
    """
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT job_id, path FROM imagine_images WHERE id = ? AND owner = ? AND kind = 'output'",
            (image_id, owner),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        job_id = row["job_id"]
        paths = [str(row["path"])]
        # DELETE mở giao dịch ghi trước, nên lần đếm ngay sau đó không bị một lượt xóa song song làm lệch.
        cursor = await db.execute(
            "DELETE FROM imagine_images WHERE id = ? AND owner = ? AND kind = 'output'",
            (image_id, owner),
        )
        if cursor.rowcount == 0:
            await db.commit()
            return None
        cursor = await db.execute(
            "SELECT COUNT(*) FROM imagine_images WHERE job_id = ? AND kind = 'output'",
            (job_id,),
        )
        (remaining,) = await cursor.fetchone()
        result = "image"
        if remaining == 0:
            cursor = await db.execute("SELECT path FROM imagine_images WHERE job_id = ?", (job_id,))
            paths += [str(item["path"]) for item in await cursor.fetchall()]
            await db.execute("DELETE FROM imagine_images WHERE job_id = ?", (job_id,))
            await db.execute("DELETE FROM imagine_jobs WHERE id = ? AND owner = ?", (job_id, owner))
            result = "job"
        await db.commit()
    from shared.attachments import delete_files

    delete_files(paths)
    return result


async def set_imagine_image_liked(owner: str, image_id: str, liked: bool) -> bool:
    async with db_connection.connect() as db:
        cursor = await db.execute(
            "UPDATE imagine_images SET liked = ? WHERE id = ? AND owner = ? AND kind = 'output'",
            (1 if liked else 0, image_id, owner),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_imagine_job(owner: str, job_id: str) -> dict | None:
    rows = await list_imagine_jobs(owner, job_id=job_id)
    return rows[0] if rows else None


async def get_imagine_request(owner: str, request_id: str) -> dict | None:
    async with db_connection.connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM imagine_requests WHERE owner = ? AND request_id = ?", (owner, request_id))).fetchone()
        return dict(row) if row else None


async def update_imagine_job(owner: str, job_id: str, status: str, error: str | None = None) -> None:
    async with db_connection.connect() as db:
        await db.execute("UPDATE imagine_jobs SET status = ?, error = ?, updated_at = ? WHERE owner = ? AND id = ?", (status, error, time.time(), owner, job_id))
        await db.commit()


async def interrupt_imagine_jobs() -> None:
    """Không tự gửi lại yêu cầu có thể đã được nhà cung cấp tính phí."""
    async with db_connection.connect() as db:
        await db.execute("UPDATE imagine_jobs SET status = 'unknown', error = ?, updated_at = ? WHERE status IN ('queued', 'running')", ("Máy chủ đã khởi động lại. Chưa xác nhận được kết quả; lượt này không được tự gửi lại.", time.time()))
        await db.commit()


async def discard_imagine_outputs(owner: str, job_id: str) -> None:
    """Dọn kết quả lưu dở, giữ ảnh tham chiếu và mô tả để người dùng xem lỗi."""
    async with db_connection.connect() as db:
        paths = [row[0] for row in await (await db.execute("SELECT path FROM imagine_images WHERE owner = ? AND job_id = ? AND kind = 'output'", (owner, job_id))).fetchall()]
        await db.execute("DELETE FROM imagine_images WHERE owner = ? AND job_id = ? AND kind = 'output'", (owner, job_id))
        await db.commit()
    from shared.attachments import delete_files
    delete_files(paths)
