"""Header bảo mật cho mọi phản hồi (gói G3.4, 13/11/2026).

Bắt buộc ngay: ``X-Content-Type-Options: nosniff``, ``Referrer-Policy: strict-origin-when-cross-origin`` (YouTube nhúng
vẫn nhận được nguồn trang), và không cho trang khác nhúng Peto vào khung (``X-Frame-Options: DENY`` cùng
``Content-Security-Policy: frame-ancestors 'none'``; app không tự nhúng trang của mình, bản in mở cửa sổ riêng).

CSP đầy đủ mới ở chế độ ``Report-Only``: trình duyệt không chặn gì, chỉ gửi báo cáo về ``/api/csp-report``. Danh sách
nguồn lấy từ những gì frontend đang dùng: YouTube (iframe_api, khung phát, ảnh thu nhỏ), ảnh đại diện Discord, Google,
GitHub, biểu tượng trang của Google, font Google của trang Docs, các API giọng nói khi người dùng tự nhập khóa (gọi thẳng
từ trình duyệt, kể cả địa chỉ tùy chỉnh nên ``connect-src`` cho mọi ``https:``), blob/data cho Live2D, ảnh và âm thanh.
Script nhúng sẵn trong ``index.html`` và ``404.html`` (gắn giao diện sáng/tối) được cho phép bằng mã băm SHA-256 tính từ
đúng tệp đang phục vụ, không bằng ``'unsafe-inline'``.

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


def inline_script_hashes(page: str) -> list[str]:
    """Mã băm CSP của từng script nhúng (không có ``src``) trong một trang HTML."""
    return [f"'sha256-{base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode()}'"
            for body in _SCRIPT.findall(page) if body.strip()]


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
        'report-uri': [REPORT_PATH],
    }
    return '; '.join(f"{name} {' '.join(values)}" for name, values in sources.items())


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


class SecurityHeaders:
    """Middleware ASGI thuần: chỉ thêm header vào ``http.response.start``, không đọc hay giữ thân phản hồi (SSE vẫn
    chảy từng mảnh). Header mà route đã tự đặt thì giữ nguyên."""

    def __init__(self, app, static_dir: Path):
        self.app = app
        self.pages = _Pages(static_dir)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers') or [])
                present = {name.lower() for name, _ in headers}
                for name, value in ENFORCED:
                    if name not in present:
                        headers.append((name, value))
                if b'content-security-policy-report-only' not in present:
                    try:
                        report_only = self.pages.current()
                    except OSError:
                        report_only = policy([])
                    headers.append((b'content-security-policy-report-only', report_only.encode('latin-1')))
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
