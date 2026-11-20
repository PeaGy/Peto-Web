"""Header bảo mật cho mọi phản hồi (gói G3.4, 13/11/2026).

Bắt buộc ngay: ``X-Content-Type-Options: nosniff``, ``Referrer-Policy: strict-origin-when-cross-origin`` (YouTube nhúng
vẫn nhận được nguồn trang), và không cho trang khác nhúng Peto vào khung (``X-Frame-Options: DENY`` cùng
``Content-Security-Policy: frame-ancestors 'none'``; app không tự nhúng trang của mình, bản in mở cửa sổ riêng).

CSP đầy đủ của trang chính chặn thật từ 20/11/2026 (``PETO_CSP_ENFORCE``, mặc định bật): log chỉ báo cáo từ 15 tới 20/11
không có vi phạm nào ngoài ``/companion``. Trình duyệt vẫn gửi báo cáo về ``/api/csp-report`` (``mode=enforce``), nên
nguồn hợp lệ bị chặn nhầm hiện ra trong log; đặt ``PETO_CSP_ENFORCE=false`` rồi khởi động lại là quay về chỉ báo cáo. Danh sách
nguồn lấy từ những gì frontend đang dùng: YouTube (iframe_api, khung phát, ảnh thu nhỏ), ảnh đại diện Discord, Google,
GitHub, biểu tượng trang của Google, font Google của trang Docs, các API giọng nói khi người dùng tự nhập khóa (gọi thẳng
từ trình duyệt, kể cả địa chỉ tùy chỉnh nên ``connect-src`` cho mọi ``https:``), blob/data cho Live2D, ảnh và âm thanh.
Script nhúng sẵn trong ``index.html`` và ``404.html`` (gắn giao diện sáng/tối) được cho phép bằng mã băm SHA-256 tính từ
đúng tệp đang phục vụ, không bằng ``'unsafe-inline'``.

Companion bản AIRI ở ``/companion/`` (từ 15/11/2026, khi đặt ``PETO_AIRI_DIR``) có chính sách riêng (``airi_policy``), luôn chỉ báo
cáo: bản build còn tải từ cdn.jsdelivr.net và huggingface.co (82 báo cáo 16–20/11), phần Companion sẽ quyết,
viết theo đúng những gì bản build AIRI dùng: script nhúng và ``onclick`` của ``index.html`` AIRI theo mã băm,
WebAssembly, worker từ blob, kết nối data/blob. Không cho phép máy chủ đám mây nào của AIRI, không cho phép CDN font
(font sẽ tự phục vụ). Phần còn lại của trang giữ chính sách cũ.

Báo cáo vi phạm chỉ ghi loại vi phạm, gốc của nguồn bị chặn và đoạn đầu đường dẫn trang; không ghi đường dẫn đầy đủ,
tham số, mã hội thoại hay đoạn mã. Có trần số dòng log mỗi phút vì endpoint này không cần đăng nhập.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

logger = logging.getLogger('peto_web.csp')
router = APIRouter()

REPORT_PATH = '/api/csp-report'
MAX_REPORT_BYTES = 16_384
MAX_LOGS_PER_MINUTE = 120

ENFORCED = (
    (b'x-content-type-options', b'nosniff'),
    (b'referrer-policy', b'strict-origin-when-cross-origin'),
    (b'x-frame-options', b'DENY'),
    (b'content-security-policy', b"frame-ancestors 'none'"),
)

_SCRIPT = re.compile(r'<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
_HANDLER = re.compile(r'\son[a-z]+\s*=\s*"([^"]*)"', re.IGNORECASE)
AIRI_PREFIX = '/companion'


def inline_script_hashes(page: str) -> list[str]:
    """Mã băm CSP của từng script nhúng (không có ``src``) trong một trang HTML."""
    return [f"'sha256-{base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode()}'"
            for body in _SCRIPT.findall(page) if body.strip()]


def handler_hashes(page: str) -> list[str]:
    """Mã băm CSP của thuộc tính sự kiện nhúng (``onclick="..."``), dùng cùng ``'unsafe-hashes'``."""
    return list(dict.fromkeys(
        f"'sha256-{base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode()}'"
        for body in _HANDLER.findall(page) if body.strip()))


def _join(sources: dict) -> str:
    return '; '.join(f"{name} {' '.join(values)}" for name, values in sources.items())


def airi_policy(hashes: list[str], handlers: list[str]) -> str:
    """Chính sách chỉ báo cáo của Companion bản AIRI (``/companion/``), theo những gì bản build AIRI stage-web dùng (bản thử 15/11/2026 chạy chung
    chính sách của trang chính và gửi khoảng 360 báo cáo vi phạm mỗi lần mở)."""
    sources = {
        'default-src': ["'self'"],
        # Script nhúng của index.html AIRI (giao diện sáng/tối, màn hình khởi động) theo mã băm; nút "Thử lại" của màn
        # hình khởi động là onclick nhúng, cho phép bằng 'unsafe-hashes' kèm đúng mã băm của nó. 'wasm-unsafe-eval':
        # onnxruntime, Silero VAD chạy WebAssembly. 'unsafe-eval': bản build có new Function(...) (PixiJS của Live2D,
        # onnxruntime), như trang chính. Cloudflare tự chèn script Web Analytics như ở trang chính.
        'script-src': ["'self'", *hashes, *(["'unsafe-hashes'", *handlers] if handlers else []), "'wasm-unsafe-eval'",
                       "'unsafe-eval'", 'https://static.cloudflareinsights.com'],
        # Vue và UnoCSS gắn style nhúng. Font của AIRI sẽ tự phục vụ nên không có CDN font nào.
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", 'data:', 'blob:'],
        'font-src': ["'self'", 'data:'],
        # Bộ não AIRI chỉ gọi máy chủ Peto cùng gốc; data:/blob: là mô hình, âm thanh, ảnh nạp ngay trong trình duyệt.
        # Không có máy chủ đám mây nào của AIRI và không có https: chung như trang chính.
        'connect-src': ["'self'", 'data:', 'blob:'],
        'media-src': ["'self'", 'blob:', 'data:'],
        'worker-src': ["'self'", 'blob:'],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        'report-uri': [REPORT_PATH],
    }
    return _join(sources)


def policy(hashes: list[str]) -> str:
    sources = {
        'default-src': ["'self'"],
        # 'unsafe-eval': PixiJS 6 (Live2D của Companion) thử Function(...) lúc khởi động và báo lỗi "does not allow
        # unsafe-eval" nếu bị chặn thật (thử ngày 13/11/2026). Muốn bỏ thì phải thêm gói @pixi/unsafe-eval trước khi
        # chuyển CSP sang chế độ chặn. Script nhúng vẫn chỉ được phép bằng mã băm, không có 'unsafe-inline'.
        # static.cloudflareinsights.com: Cloudflare tự chèn script Web Analytics vào trang khi đi qua proxy (báo cáo thật
        # trên mọi trang ngày 13/11/2026); dữ liệu nó gửi về đã nằm trong connect-src https:.
        'script-src': ["'self'", *hashes, "'unsafe-eval'", 'https://www.youtube.com', 'https://s.ytimg.com',
                       'https://static.cloudflareinsights.com'],
        'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
        'img-src': ["'self'", 'data:', 'blob:', 'https://cdn.discordapp.com', 'https://*.googleusercontent.com',
                    'https://avatars.githubusercontent.com', 'https://www.google.com', 'https://*.gstatic.com',
                    'https://i.ytimg.com'],
        'font-src': ["'self'", 'data:', 'https://fonts.gstatic.com'],
        'connect-src': ["'self'", 'https:'],
        'media-src': ["'self'", 'blob:', 'data:'],
        'worker-src': ["'self'", 'blob:'],
        'frame-src': ['https://www.youtube.com', 'https://www.youtube-nocookie.com'],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        # Như header frame-ancestors riêng (ENFORCED): khi chính sách này chặn thật thì nó cũng nói điều đó.
        'frame-ancestors': ["'none'"],
        'report-uri': [REPORT_PATH],
    }
    return _join(sources)


class _Pages:
    """Mã băm script nhúng của các trang HTML đang phục vụ; đọc lại khi tệp đổi (deploy mới)."""

    def __init__(self, static_dir: Path):
        self.files = [static_dir / 'index.html', static_dir / '404.html']
        self.stamp: tuple | None = None
        self.value = policy([])

    def current(self) -> str:
        stamp = tuple((path.stat().st_mtime_ns, path.stat().st_size) if path.is_file() else None for path in self.files)
        if stamp != self.stamp:
            hashes: list[str] = []
            for path in self.files:
                if path.is_file():
                    for value in inline_script_hashes(path.read_text(encoding='utf-8')):
                        if value not in hashes:
                            hashes.append(value)
            self.value, self.stamp = policy(hashes), stamp
        return self.value


class _AiriPage:
    """Như ``_Pages``, cho ``index.html`` của bản build AIRI; đọc lại khi bản build đổi. ``PETO_AIRI_DIR`` có thể là
    symlink ``current`` mà ``deploy/update-companion.sh`` đổi sang bản khác: dấu nhận biết gồm cả đường dẫn thật của
    tệp, nên hai bản build trùng giờ sửa và cỡ tệp vẫn được đọc lại."""

    def __init__(self, airi_dir: Path):
        self.file = airi_dir / 'index.html'
        self.stamp: tuple | None = None
        self.value = airi_policy([], [])

    def current(self) -> str:
        real = self.file.resolve()
        if real.is_file():
            info = real.stat()
            stamp = (str(real), info.st_mtime_ns, info.st_size)
        else:
            stamp = None
        if stamp != self.stamp:
            # Đọc đúng tệp vừa lấy dấu, không đi lại qua symlink (có thể vừa bị đổi lần nữa).
            page = real.read_text(encoding='utf-8') if stamp is not None else ''
            self.value, self.stamp = airi_policy(inline_script_hashes(page), handler_hashes(page)), stamp
        return self.value


def _is_airi(path: str) -> bool:
    return path == AIRI_PREFIX or path.startswith(AIRI_PREFIX + '/')


class SecurityHeaders:
    """Middleware ASGI thuần: chỉ thêm header vào ``http.response.start``, không đọc hay giữ thân phản hồi (SSE vẫn
    chảy từng mảnh). Header mà route đã tự đặt thì giữ nguyên."""

    def __init__(self, app, static_dir: Path, airi_dir: Path | None = None, enforce: bool = False):
        self.app = app
        # Trang chính: ``Content-Security-Policy`` (chặn thật) khi ``enforce``, không thì ``…-Report-Only``. AIRI luôn
        # chỉ báo cáo.
        self.enforce = enforce
        self.pages = _Pages(static_dir)
        # Chỉ khi Companion là bản AIRI (PETO_AIRI_DIR có index.html); không thì /companion… (Companion React) vẫn theo
        # chính sách của trang chính, vì nó cần YouTube và các nguồn khác của trang chính.
        self.airi = _AiriPage(airi_dir) if airi_dir is not None and (airi_dir / 'index.html').is_file() else None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers') or [])
                present = {name.lower() for name, _ in headers}
                airi = self.airi is not None and _is_airi(scope.get('path', ''))
                # Trang chính khi chặn thật: một header CSP đầy đủ (đã gồm frame-ancestors 'none') thay cho header
                # frame-ancestors riêng. Route tự đặt CSP của nó thì giữ nguyên.
                enforce = self.enforce and not airi and b'content-security-policy' not in present
                for name, value in ENFORCED:
                    if name not in present and not (enforce and name == b'content-security-policy'):
                        headers.append((name, value))
                if enforce or b'content-security-policy-report-only' not in present:
                    try:
                        value = self.airi.current() if airi else self.pages.current()
                    except OSError:
                        value = airi_policy([], []) if airi else policy([])
                    name = b'content-security-policy' if enforce else b'content-security-policy-report-only'
                    headers.append((name, value.encode('latin-1')))
                message = {**message, 'headers': headers}
            await send(message)

        return await self.app(scope, receive, wrapped)


_window = {'start': 0.0, 'count': 0, 'dropped': 0}


def _origin(value: object) -> str:
    """Gốc của nguồn bị chặn (``https://host``) hoặc từ khóa (inline, eval, data, blob…); không bao giờ cả đường dẫn."""
    text = str(value or '').strip()
    if not text:
        return 'none'
    if '://' not in text:
        word = text.split(':', 1)[0].lower()
        return word if re.fullmatch(r'[a-z-]{1,24}', word) else 'other'
    parts = urlsplit(text)
    host = (parts.hostname or '').lower()
    return f'{parts.scheme.lower()}://{host}' if re.fullmatch(r'[a-z0-9.-]{1,253}', host) else 'other'


def _page(value: object) -> str:
    """Chỉ đoạn đầu đường dẫn trang (``/chat``, ``/docs``…): phần sau có thể là mã hội thoại."""
    path = urlsplit(str(value or '')).path
    first = path.strip('/').split('/', 1)[0]
    return '/' + first if re.fullmatch(r'[a-z0-9-]{0,32}', first) else '/other'


def _directive(value: object) -> str:
    text = str(value or '').split(' ', 1)[0].lower()
    return text if re.fullmatch(r'[a-z-]{1,40}', text) else 'other'


def summaries(payload: object) -> list[dict]:
    """Đổi báo cáo kiểu ``report-uri`` hay Reporting API thành bản tóm tắt không chứa nội dung."""
    reports = []
    if isinstance(payload, dict) and isinstance(payload.get('csp-report'), dict):
        body = payload['csp-report']
        reports.append((body.get('effective-directive') or body.get('violated-directive'), body.get('blocked-uri'),
                        body.get('document-uri'), body.get('disposition')))
    elif isinstance(payload, list):
        for item in payload[:20]:
            body = item.get('body') if isinstance(item, dict) else None
            if isinstance(body, dict) and item.get('type') == 'csp-violation':
                reports.append((body.get('effectiveDirective'), body.get('blockedURL'), body.get('documentURL'),
                                body.get('disposition')))
    return [{'directive': _directive(directive), 'blocked': _origin(blocked), 'page': _page(page),
             'mode': 'report' if str(mode or 'report') == 'report' else 'enforce'}
            for directive, blocked, page, mode in reports]


@router.post(REPORT_PATH, include_in_schema=False)
async def csp_report(request: Request) -> Response:
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_REPORT_BYTES:
            return Response(status_code=413)
    try:
        items = summaries(json.loads(body or b'null'))
    except (ValueError, UnicodeDecodeError):
        return Response(status_code=400)
    now = time.monotonic()
    if now - _window['start'] >= 60:
        if _window['dropped']:
            logger.warning('csp_violation_dropped count=%d', _window['dropped'])
        _window.update(start=now, count=0, dropped=0)
    for item in items:
        if _window['count'] >= MAX_LOGS_PER_MINUTE:
            _window['dropped'] += 1
            continue
        _window['count'] += 1
        logger.warning('csp_violation directive=%s blocked=%s page=%s mode=%s',
                       item['directive'], item['blocked'], item['page'], item['mode'])
    return Response(status_code=204)
