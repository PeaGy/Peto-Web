"""Xóa tài khoản (G5, chủ web chọn ngày 20/11/2026): người dùng tự xóa trong Cài đặt → Tài khoản.

Xóa ngay, không có thời gian chờ khôi phục: mọi hàng có cột ``owner`` của tài khoản ở mọi bảng (bảng con như tin nhắn,
phiên bản tài liệu, tệp xuất đi theo bằng khóa ngoại ON DELETE CASCADE), cả danh tính Google/GitHub/email đã gộp và mật
khẩu, rồi tệp tải lên và ảnh tạo trong thư mục tải lên. Số liệu ``usage_events`` cố ý không có owner nên ở lại.
Trí nhớ của bot Discord nằm ở kho khác, web chỉ đọc nên không đụng tới.

Tài khoản quản trị (``PETO_OWNER_ACCOUNTS``) bị chặn để chủ web không lỡ tay xóa chính mình. Phải gõ đúng chữ "XÓA".
Đăng nhập lại sau đó bằng cùng Google/GitHub/email là một tài khoản mới tinh.
"""
from __future__ import annotations

import logging
import shutil
import time
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core import config
from core.config import UPLOAD_DIR
from features.accounts.auth import SESSION_COOKIE, current_owner
from storage import connection, deleted_accounts

log = logging.getLogger(__name__)
router = APIRouter(tags=["account"])

CONFIRM_WORD = "XÓA"
# Lượt chat ghi "running" mà quá lâu không cập nhật là lượt mồ côi (máy chủ tắt giữa chừng), không chặn việc xóa.
ACTIVE_TURN_SECONDS = 600


class DeleteRequest(BaseModel):
    confirm: str = Field(default="", max_length=20)


def confirmed(text: str) -> bool:
    """Chữ người dùng gõ có đúng "XÓA" không: không phân biệt hoa thường, chấp nhận dấu tổ hợp lẫn dựng sẵn."""
    return unicodedata.normalize("NFC", text.strip()).upper() == CONFIRM_WORD


def blocked_reason(owner: str) -> str | None:
    if owner in config.OWNER_ACCOUNTS:
        return "Tài khoản quản trị không xóa được ở đây."
    return None


async def _owner_tables(db) -> list[str]:
    rows = await (await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")).fetchall()
    tables = []
    for (name,) in rows:
        columns = await (await db.execute(f'PRAGMA table_info("{name}")')).fetchall()
        if any(column[1] == "owner" for column in columns):
            tables.append(name)
    return tables


def _inside_uploads(path: Path) -> Path | None:
    root = UPLOAD_DIR.resolve()
    target = path.resolve()
    if target == root:
        return None
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _remove_files(files: list[str], folders: list[Path]) -> None:
    for item in files:
        target = _inside_uploads(Path(item))
        if target is not None:
            target.unlink(missing_ok=True)
    for folder in folders:
        target = _inside_uploads(folder)
        if target is not None and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


async def delete_account(owner: str) -> dict[str, int]:
    """Xóa mọi dữ liệu của ``owner``. Trả về số hàng đã xóa theo bảng (không tính hàng con theo khóa ngoại)."""
    async with connection.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            tables = await _owner_tables(db)
            files: list[str] = []
            folders: list[Path] = []
            if "attachments" in tables:
                files += [row[0] for row in await (await db.execute(
                    "SELECT path FROM attachments WHERE owner=?", (owner,))).fetchall() if row[0]]
            if "imagine_images" in tables:
                files += [row[0] for row in await (await db.execute(
                    "SELECT path FROM imagine_images WHERE owner=?", (owner,))).fetchall() if row[0]]
            if "conversations" in tables:
                folders += [UPLOAD_DIR / row[0] for row in await (await db.execute(
                    "SELECT id FROM conversations WHERE owner=?", (owner,))).fetchall()]
            if "imagine_jobs" in tables:
                folders += [UPLOAD_DIR / "imagine" / row[0] for row in await (await db.execute(
                    "SELECT id FROM imagine_jobs WHERE owner=?", (owner,))).fetchall()]
            # Mốc xóa để thu hồi cookie và mã đồng bộ Companion còn hạn ở máy khác (storage.deleted_accounts).
            now = time.time()
            from features.companion.airi_sync import TOKEN_MAX_AGE
            await deleted_accounts.mark_deleted(db, owner, now,
                                                forget_before=now - max(config.SESSION_MAX_AGE, TOKEN_MAX_AGE))
            counts = {}
            for name in tables:
                cursor = await db.execute(f'DELETE FROM "{name}" WHERE owner=?', (owner,))
                if cursor.rowcount:
                    counts[name] = cursor.rowcount
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    _remove_files(files, folders)
    return counts


async def _has_active_turn(owner: str) -> bool:
    async with connection.connect() as db:
        row = await (await db.execute(
            "SELECT 1 FROM chat_turns WHERE owner=? AND state='running' AND MAX(created_at, updated_at)>? LIMIT 1",
            (owner, time.time() - ACTIVE_TURN_SECONDS))).fetchone()
    return row is not None


@router.post("/api/account/delete")
async def delete(body: DeleteRequest, response: Response, owner: str = Depends(current_owner)) -> dict:
    reason = blocked_reason(owner)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    if not confirmed(body.confirm):
        raise HTTPException(status_code=400, detail=f'Gõ "{CONFIRM_WORD}" để xác nhận xóa tài khoản.')
    if await _has_active_turn(owner):
        raise HTTPException(status_code=409, detail="Peto đang trả lời. Dừng lượt đó rồi xóa tài khoản.")
    counts = await delete_account(owner)
    # Không ghi owner vào log: chỉ cần biết đã có một lần xóa và quy mô của nó.
    log.info("Đã xóa một tài khoản theo yêu cầu: %d hàng ở %d bảng", sum(counts.values()), len(counts))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"deleted": True}
