"""Phục vụ frontend đã build từ chính backend.

Chỉ bật khi `frontend/dist` tồn tại. Lúc dev không có thư mục đó, nên Vite vẫn
lo phần giao diện và module này đứng ngoài.

Trên VPS, cách này giúp chỉ cần một tiến trình và một cổng cho Cloudflare
Tunnel trỏ tới, thay vì phải dựng thêm nginx.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("peto_web.static")

# File có hash trong tên (do Vite sinh) thì cache lâu được; các file khác thì
# không, để lần deploy sau người dùng không dính bản cũ.
_IMMUTABLE_DIRS = {"assets"}


def _safe_path(static_dir: Path, relative: str) -> Path | None:
    """Chặn path traversal: kết quả phải nằm trong ``static_dir``."""
    candidate = (static_dir / relative).resolve()
    try:
        candidate.relative_to(static_dir)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def mount(app: FastAPI, static_dir: Path) -> bool:
    """Gắn phần phục vụ file tĩnh. Trả về True nếu đã bật."""
    static_dir = static_dir.resolve()
    index = static_dir / "index.html"
    if not index.is_file():
        logger.info(
            "Không thấy %s — backend chỉ phục vụ API. "
            "Chạy `npm run build` nếu muốn phục vụ cả giao diện.",
            index,
        )
        return False

    # Nhận cả HEAD: công cụ giám sát uptime và `curl -I` dùng HEAD, và FastAPI
    # không tự thêm method này cho route GET.
    @app.api_route(
        "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    async def spa(full_path: str) -> FileResponse:
        # Route API đã được đăng ký trước nên tới được đây nghĩa là không khớp;
        # đừng trả index.html cho chúng, kẻo lỗi 404 hiện ra thành trang web.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        target = _safe_path(static_dir, full_path) if full_path else None
        if target is not None:
            top = target.relative_to(static_dir).parts[0]
            cache = (
                "public, max-age=31536000, immutable"
                if top in _IMMUTABLE_DIRS
                else "no-cache"
            )
            return FileResponse(target, headers={"Cache-Control": cache})

        # Mọi đường dẫn khác trả về app: router phía client tự xử lý.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    logger.info("Phục vụ giao diện từ %s", static_dir)
    return True
