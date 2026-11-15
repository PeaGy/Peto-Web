"""Phục vụ bản build AIRI stage-web dưới ``/airi/`` (thử nghiệm, 15/11/2026).

Chỉ bật khi ``PETO_AIRI_DIR`` trỏ tới một thư mục build có ``index.html``; không đặt thì không đăng ký route nào.
Phải gắn TRƯỚC ``static_files.mount`` trong ``main.py``, vì route bắt mọi đường dẫn của trang chính nằm cuối cùng.

Tệp có thật thì trả tệp (``assets/`` có hash trong tên nên cache lâu). Đường dẫn không phải tệp mà đoạn cuối không có
dấu chấm là một trang của router AIRI (``/airi/settings/modules``…): trả ``index.html`` để mở thẳng hay F5 vẫn được.
Tài nguyên thiếu (có phần mở rộng) là 404 thật, không biến thành trang.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

logger = logging.getLogger("peto_web.airi")

PREFIX = "/airi"
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


def _safe_file(root: Path, relative: str) -> Path | None:
    """Chặn path traversal: tệp phải nằm trong ``root``."""
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def mount(app: FastAPI, airi_dir: Path | None) -> bool:
    """Gắn ``/airi/``. Trả về True nếu đã bật."""
    if airi_dir is None:
        return False
    root = airi_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.warning("PETO_AIRI_DIR=%s không có index.html — bỏ qua /airi/.", root)
        return False

    async def index_page() -> HTMLResponse:
        page = await anyio.Path(index).read_text(encoding="utf-8")
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

    logger.info("Phục vụ AIRI từ %s tại %s/", root, PREFIX)
    return True
