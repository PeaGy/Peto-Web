"""Một tên miền chính cho người dùng (17/11/2026).

Peto chạy ở hai tên miền (``peto.pearto.shop`` cũ và ``peto.peagy.com``). Cookie đăng nhập gắn theo tên miền, nên đăng
nhập ở tên miền này thì vào tên miền kia vẫn thấy chưa đăng nhập. Khi đặt ``PETO_CANONICAL_ORIGIN``, trình duyệt mở một
trang (GET/HEAD, ngoài ``/api/``, muốn nhận HTML) bằng tên miền khác sẽ được chuyển sang tên miền chính, giữ đường dẫn và
tham số.

Không chuyển: mọi ``/api/…`` (Peto Agent, Peto Harness, máy giọng nói và bộ cài vẫn gọi tên miền cũ), yêu cầu không xin
HTML (``irm …/install.ps1``), phương thức khác GET/HEAD, và truy cập nội bộ (localhost, 127.0.0.1) để lệnh kiểm tra
trên VPS vẫn chạy. Dùng 302 chứ không 301: trình duyệt không nhớ mãi, đổi ý thì chỉ cần bỏ biến môi trường.
"""
from __future__ import annotations

from urllib.parse import urlsplit

LOOPBACK = {'localhost', '127.0.0.1', '::1', '[::1]'}


def parse_origin(value: str) -> tuple[str, str] | None:
    """``https://peto.peagy.com`` → (``https``, ``peto.peagy.com``); giá trị hỏng thì None (bỏ qua, không chặn app)."""
    parts = urlsplit((value or '').strip())
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.path not in {'', '/'} or parts.query:
        return None
    return parts.scheme, parts.netloc.lower()


def _host(headers: list[tuple[bytes, bytes]]) -> str:
    for name, value in headers:
        if name == b'host':
            return value.decode('latin-1').strip().lower()
    return ''


def _wants_html(headers: list[tuple[bytes, bytes]]) -> bool:
    for name, value in headers:
        if name == b'accept':
            return b'text/html' in value.lower()
    return False


class CanonicalHost:
    """ASGI middleware: chuyển trang mở bằng tên miền phụ sang tên miền chính."""

    def __init__(self, app, origin: str = ''):
        self.app = app
        self.origin = parse_origin(origin)

    async def __call__(self, scope, receive, send):
        if self.origin is None or scope['type'] != 'http' or scope['method'] not in {'GET', 'HEAD'}:
            return await self.app(scope, receive, send)
        path = scope.get('path') or '/'
        headers = scope.get('headers') or []
        host = _host(headers)
        bare = host.rsplit(':', 1)[0] if not host.startswith('[') else host.split(']')[0] + ']'
        scheme, canonical = self.origin
        if (not host or host == canonical or bare in LOOPBACK or path == '/api' or path.startswith('/api/')
                or not _wants_html(headers)):
            return await self.app(scope, receive, send)
        query = scope.get('query_string') or b''
        target = f'{scheme}://{canonical}{path}' + (f'?{query.decode("latin-1")}' if query else '')
        await send({'type': 'http.response.start', 'status': 302, 'headers': [
            (b'location', target.encode('latin-1')), (b'cache-control', b'no-store'), (b'content-length', b'0')]})
        await send({'type': 'http.response.body', 'body': b''})
