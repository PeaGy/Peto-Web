"""Bản chữ của trang /docs cho máy đọc không chạy JavaScript (công cụ tra web, Google), đặt trong <noscript>.

Trang docs vẽ bài bằng React từ /api/docs, nên HTML máy chủ trả về chỉ có tiêu đề: ngày 6/10/2026 Peto tra web về docs của
chính nó và chỉ thấy trang trống. Trình duyệt chạy JavaScript bỏ qua <noscript>, nên giao diện không đổi.

Chỉ đổi một phần Markdown mà các bài dùng (tiêu đề ##, gạch đầu dòng, trích dẫn, khối mã, bảng, liên kết, in đậm, mã).
Mọi chữ đều được thoát HTML; liên kết chỉ giữ đường dẫn trong trang (/…) và https.
"""
from __future__ import annotations

import html
import re

_LINK = re.compile(r'!?\[([^\]]*)\]\(([^)\s]+)\)')
_BOLD = re.compile(r'\*\*(.+?)\*\*')
_CODE = re.compile(r'`([^`]+)`')


def _inline(text: str) -> str:
    out, last = [], 0
    for match in _LINK.finditer(text):
        out.append(_plain(text[last:match.start()]))
        label, url = match.group(1), match.group(2)
        if match.group(0).startswith('!') or not (url.startswith('/') and not url.startswith('//') or url.startswith('https://')):
            out.append(_plain(label))      # ảnh và liên kết lạ chỉ giữ chữ
        else:
            out.append(f'<a href="{html.escape(url, quote=True)}">{_plain(label)}</a>')
        last = match.end()
    out.append(_plain(text[last:]))
    return ''.join(out)


def _plain(text: str) -> str:
    text = html.escape(text, quote=False)
    text = _CODE.sub(lambda m: f'<code>{m.group(1)}</code>', text)
    return _BOLD.sub(lambda m: f'<strong>{m.group(1)}</strong>', text)


def markdown_html(body: str) -> str:
    out: list[str] = []
    items: list[str] = []
    fence: list[str] | None = None

    def flush():
        if items:
            out.append('<ul>' + ''.join(f'<li>{item}</li>' for item in items) + '</ul>')
            items.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith('```'):
                out.append('<pre><code>' + html.escape('\n'.join(fence), quote=False) + '</code></pre>')
                fence = None
            else:
                fence.append(line)
            continue
        if stripped.startswith('```'):
            flush()
            fence = []
        elif not stripped or stripped == '---':
            flush()
        elif stripped.startswith('#'):
            flush()
            level = min(len(stripped) - len(stripped.lstrip('#')) , 4)
            out.append(f'<h{level}>{_inline(stripped.lstrip("#").strip())}</h{level}>')
        elif stripped.startswith(('- ', '* ')):
            items.append(_inline(stripped[2:]))
        elif stripped.startswith('>'):
            flush()
            out.append(f'<blockquote>{_inline(stripped.lstrip("> ").strip())}</blockquote>')
        elif stripped.startswith('|'):
            flush()
            cells = [cell.strip() for cell in stripped.strip('|').split('|')]
            if not all(re.fullmatch(r':?-{2,}:?', cell) for cell in cells):     # bỏ hàng kẻ |---|
                out.append('<p>' + ' · '.join(_inline(cell) for cell in cells) + '</p>')
        else:
            flush()
            out.append(f'<p>{_inline(stripped)}</p>')
    if fence is not None:
        out.append('<pre><code>' + html.escape('\n'.join(fence), quote=False) + '</code></pre>')
    flush()
    return '\n'.join(out)


def noscript(page: dict | None, pages: list[dict]) -> str:
    """Bài ``page`` (None là trang mục lục /docs/), kèm danh sách mọi bài để máy đọc đi tiếp được."""
    listing = '<ul>' + ''.join(
        f'<li><a href="/docs/{html.escape(item["slug"], quote=True)}/">{html.escape(item["title"])}</a>: '
        f'{html.escape(item["description"])}</li>' for item in pages) + '</ul>'
    if page is None:
        main = '<h1>Peto Docs</h1>\n<p>Hướng dẫn tiếng Việt cho Peto Web, Companion và Agent CLI.</p>'
    else:
        main = (f'<h1>{html.escape(page["title"])}</h1>\n<p>{html.escape(page["description"])}</p>\n'
                + markdown_html(page['body']))
    return f'<noscript><article>{main}</article><nav><h2>Các bài hướng dẫn</h2>{listing}</nav></noscript>'
