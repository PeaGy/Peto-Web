"""API của trang Quản trị. Chỉ tài khoản trong PETO_OWNER_ACCOUNTS đọc được; người khác nhận 404 như thể không có."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core import config
from features.accounts import auth

from . import stats

router = APIRouter(prefix="/api/admin")


def is_owner(owner: str | None) -> bool:
    # Đọc lại config mỗi lần (không import tên) để test và cấu hình đổi lúc chạy đều thấy giá trị mới.
    return bool(owner) and owner in config.OWNER_ACCOUNTS


def owner_only(request: Request) -> str:
    """404 chứ không 401/403: người không phải chủ web không biết trang này tồn tại."""
    owner = auth.session_owner(request.cookies.get(auth.SESSION_COOKIE))
    if not is_owner(owner):
        raise HTTPException(status_code=404, detail="Not Found")
    return owner


@router.get("/overview")
async def overview(response: Response, range: str = "7d", _owner: str = Depends(owner_only)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    if range not in stats.RANGES:
        raise HTTPException(status_code=400, detail="Khoảng thời gian không hợp lệ.")
    return await stats.overview(range)
