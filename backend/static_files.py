"""Phục vụ frontend đã build từ chính backend.

Chỉ bật khi `frontend/dist` tồn tại. Lúc dev không có thư mục đó, nên Vite vẫn
lo phần giao diện và module này đứng ngoài.

Trên VPS, cách này giúp chỉ cần một tiến trình và một cổng cho Cloudflare
Tunnel trỏ tới, thay vì phải dựng thêm nginx.

Đường dẫn không khớp file nào sẽ nhận ``404.html`` kèm status 404. Nếu sau này
giao diện dùng router theo đường dẫn thật, chỗ đó phải đổi lại thành index.html.

Riêng trang chủ không trả nguyên file: nó được chèn ảnh xem trước link
(``og:image``) lúc phục vụ, xem ``_with_preview_image``. Ảnh đó là
``og.png`` trong bản build (ảnh banner ngang). URL tuyệt đối lấy từ chính yêu
cầu, không ghi cứng domain. Không có file, hoặc không biết địa chỉ https công
khai, thì mới dùng avatar Discord.
"""

from __future__ import annotations

import html
import logging
import struct
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse

from agent_install import public_origin
from app_identity import get_app_identity

logger = logging.getLogger("peto_web.static")

# File có hash trong tên (do Vite sinh) thì cache lâu được; các file khác thì
# không, để lần deploy sau người dùng không dính bản cũ.
_IMMUTABLE_DIRS = {"assets"}
# Ảnh banner trong frontend/public; Vite chép ra gốc bản build. Discord cần ảnh
# ngang khoảng 1.9:1 thì mới hiện khung lớn. Avatar vuông chỉ thành thumbnail.
_BANNER_NAME = "og.png"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _safe_path(static_dir: Path, relative: str) -> Path | None:
    """Chặn path traversal: kết quả phải nằm trong ``static_dir``."""
    candidate = (static_dir / relative).resolve()
    try:
        candidate.relative_to(static_dir)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _png_size(path: Path) -> tuple[int, int] | None:
    """Đọc rộng × cao từ header PNG. File lạ thì bỏ qua, không đoán."""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or not header.startswith(_PNG_SIG):
        return None
    width, height = struct.unpack(">II", header[16:24])
    if not (1 <= width <= 8192 and 1 <= height <= 8192):
        return None
    return width, height


def _with_preview_image(
    page: str,
    image_url: str | None,
    name: str,
    *,
    width: int | None = None,
    height: int | None = None,
    image_type: str | None = None,
    alt: str | None = None,
) -> str:
    """Chèn ``og:image`` vào trang chủ, để link dán vào Discord có ảnh lớn.

    Các thẻ xem trước còn lại nằm sẵn trong ``frontend/index.html``. Open Graph
    đòi URL tuyệt đối, mà domain không ghi cứng trong bản build: chèn lúc phục
    vụ. Ảnh banner là ``/og.png``; không có thì dùng avatar Discord. Không có
    ảnh nào dùng được thì trang vẫn nguyên, chỉ thiếu ảnh xem trước.
    """
    if not image_url or not image_url.startswith(("https://", "http://")):
        return page
    head_end = page.find("</head>")
    if head_end < 0:
        return page
    shown = alt or f"Ảnh đại diện của {name}"
    escaped = html.escape(image_url)
    tags = (
        f'<meta property="og:image" content="{escaped}" />'
        f'<meta property="og:image:alt" content="{html.escape(shown)}" />'
    )
    if width and height:
        tags += (
            f'<meta property="og:image:width" content="{width}" />'
            f'<meta property="og:image:height" content="{height}" />'
        )
    if image_type:
        tags += f'<meta property="og:image:type" content="{html.escape(image_type)}" />'
    tags += f'<meta name="twitter:image" content="{escaped}" />'
    return page[:head_end] + tags + page[head_end:]


def mount(app: FastAPI, static_dir: Path) -> bool:
    """Gắn phần phục vụ file tĩnh. Trả về True nếu đã bật."""
    static_dir = static_dir.resolve()
    index = static_dir / "index.html"
    not_found = static_dir / "404.html"
    if not index.is_file():
        logger.info(
            "Không thấy %s — backend chỉ phục vụ API. "
            "Chạy `npm run build` nếu muốn phục vụ cả giao diện.",
            index,
        )
        return False

    async def index_page(request: Request) -> HTMLResponse:
        # Đọc lại file mỗi lượt như FileResponse trước đây, để build lại là có
        # ngay. get_app_identity có cache và không bao giờ raise, nên Discord
        # trục trặc thì trang chủ chỉ thiếu ảnh xem trước chứ không sập.
        identity = await get_app_identity()
        name = identity["name"] or "Peto"
        page = await anyio.Path(index).read_text(encoding="utf-8")
        banner = static_dir / _BANNER_NAME
        origin = public_origin(request) if banner.is_file() else None
        if origin:
            size = _png_size(banner)
            page = _with_preview_image(
                page,
                f"{origin}/{_BANNER_NAME}",
                name,
                width=size[0] if size else None,
                height=size[1] if size else None,
                image_type="image/png",
                alt=f"{name}, trợ lý AI",
            )
        else:
            page = _with_preview_image(page, identity["avatar_url"], name)
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    # Nhận cả HEAD: công cụ giám sát uptime và `curl -I` dùng HEAD, và FastAPI
    # không tự thêm method này cho route GET.
    @app.api_route(
        "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    async def spa(full_path: str, request: Request) -> Response:
        # Route API đã được đăng ký trước nên tới được đây nghĩa là không khớp;
        # đừng trả index.html cho chúng, kẻo lỗi 404 hiện ra thành trang web.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        if full_path in ("", "index.html"):
            return await index_page(request)

        target = _safe_path(static_dir, full_path)
        if target is not None:
            top = target.relative_to(static_dir).parts[0]
            cache = (
                "public, max-age=31536000, immutable"
                if top in _IMMUTABLE_DIRS
                else "no-cache"
            )
            return FileResponse(target, headers={"Cache-Control": cache})

        # Giao diện chuyển tab bằng hash (`#imagine`), không có router theo đường
        # dẫn. Nên đường dẫn lạ là 404 thật, trả index.html kèm status 200 chỉ
        # khiến mọi lỗi gõ nhầm trông như trang chủ.
        if not_found.is_file():
            return FileResponse(
                not_found, status_code=404, headers={"Cache-Control": "no-cache"}
            )
        raise HTTPException(status_code=404, detail="Not found")

    logger.info("Phục vụ giao diện từ %s", static_dir)
    return True
