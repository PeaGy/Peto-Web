"""Phục vụ bản build AIRI stage-web (bản fork của Peto) làm Companion, dưới ``/companion/`` (từ 15/11/2026).

Chỉ bật khi ``PETO_AIRI_DIR`` trỏ tới một thư mục build có ``index.html`` (build với ``--base=/companion/``); không đặt
thì không đăng ký route nào và ``/companion`` vẫn là Companion React như cũ. Bỏ biến rồi khởi động lại là quay về bản
React. Phải gắn TRƯỚC ``static_files.mount`` trong ``main.py``, vì route bắt mọi đường dẫn của trang chính nằm cuối cùng;
khi bật, ``static_files`` cũng không trả ``index.html`` của React cho ``/companion…`` nữa (xem ``active``).

Tệp có thật thì trả tệp (``assets/`` có hash trong tên nên cache lâu). Đường dẫn không phải tệp mà đoạn cuối không có
dấu chấm là một trang của router AIRI (``/companion/settings/modules``…): trả ``index.html`` để mở thẳng hay F5 vẫn
được. Đường dẫn cũ của Companion React (``/companion/settings/modules/voice``…) cũng nhận ``index.html``; AIRI tự hiện
trang "Không tìm thấy trang này" với lối về. Tài nguyên thiếu (có phần mở rộng) là 404 thật, không biến thành trang.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from core import config

logger = logging.getLogger("peto_web.airi")

PREFIX = "/companion"
# Trang báo khi bản build đang được thay (index.html tạm thời không có): không script, không tài nguyên ngoài.
UNAVAILABLE_PAGE = ("<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
                    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                    "<title>Companion đang cập nhật · Peto</title></head>"
                    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;"
                    "line-height:1.5\"><h1 style=\"font-size:1.4rem\">Companion đang cập nhật</h1>"
                    "<p>Peto đang thay bản Companion mới. Đợi chừng một phút rồi tải lại trang nhé.</p>"
                    "<p><a href=\"/companion/\">Tải lại Companion</a> · <a href=\"/\">Về Peto Web</a></p>"
                    "</body></html>")
# Kiểu MIME mà bảng của hệ điều hành có thể thiếu (Windows): WebAssembly phải đúng application/wasm thì trình duyệt mới
# biên dịch theo luồng; mô hình Live2D/VRM là nhị phân.
_TYPES = {
    ".wasm": "application/wasm",
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".webmanifest": "application/manifest+json",
    ".vrm": "application/octet-stream",
    ".vrma": "application/octet-stream",
    ".moc3": "application/octet-stream",
    ".onnx": "application/octet-stream",
}


def usable(airi_dir: Path | None) -> bool:
    """Thư mục build dùng được: có đặt và có ``index.html``."""
    return airi_dir is not None and (airi_dir / "index.html").is_file()


def active() -> bool:
    """Companion có phải là bản AIRI không (đọc ``config.AIRI_DIR`` lúc gọi). Frontend React nhận cờ này qua
    ``/api/auth/me`` (``companion_airi``) và ``static_files`` dùng nó để nhường ``/companion…``."""
    return usable(config.AIRI_DIR)


def is_companion_path(path: str) -> bool:
    """``companion`` hoặc ``companion/…`` (đường dẫn không có dấu "/" đầu, như route bắt mọi đường dẫn nhận)."""
    return path == PREFIX[1:] or path.startswith(PREFIX[1:] + "/")


def _safe_file(root: Path, relative: str) -> Path | None:
    """Chặn path traversal: tệp phải nằm trong ``root``."""
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def mount(app: FastAPI, airi_dir: Path | None) -> bool:
    """Gắn ``/companion/`` cho bản AIRI. Trả về True nếu đã bật."""
    if airi_dir is None:
        return False
    root = airi_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.warning("PETO_AIRI_DIR=%s không có index.html — Companion giữ bản React.", root)
        return False

    async def index_page() -> HTMLResponse:
        try:
            page = await anyio.Path(index).read_text(encoding="utf-8")
        except OSError:
            # index.html biến mất sau khi khởi động (đang build lại hay chép bản mới vào thư mục): báo tạm thời không
            # dùng được thay vì lỗi 500.
            logger.warning("Không đọc được index.html của Companion bản AIRI ở %s.", root)
            return HTMLResponse(UNAVAILABLE_PAGE, status_code=503,
                                headers={"Cache-Control": "no-store", "Retry-After": "30"})
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    @app.api_route(PREFIX, methods=["GET", "HEAD"], include_in_schema=False)
    async def airi_root() -> Response:
        return RedirectResponse(PREFIX + "/", status_code=308)

    @app.api_route(PREFIX + "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def airi(full_path: str) -> Response:
        if full_path in ("", "index.html"):
            return await index_page()
        target = _safe_file(root, full_path)
        if target is not None:
            immutable = target.relative_to(root).parts[0] == "assets" and len(target.relative_to(root).parts) > 1
            return FileResponse(
                target,
                media_type=_TYPES.get(target.suffix.lower()),
                headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"},
            )
        last = full_path.rstrip("/").rsplit("/", 1)[-1]
        if last and "." not in last and ".." not in full_path.split("/"):
            return await index_page()
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")

    logger.info("Companion là bản AIRI từ %s tại %s/", root, PREFIX)
    return True
