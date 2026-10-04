"""Bounded document rendering shared by chat tools and download routes."""
import asyncio
from contextlib import asynccontextmanager
from io import BytesIO

import pypdfium2 as pdfium
from pypdf import PdfReader
from features.documents.export import render_docx, render_pdf
from features.documents.images import prepare_all

# Thời gian chờ tối đa (giây) trong hàng dựng tài liệu. Lượt tạo tệp trong chat chờ lâu nhất vì model đang đợi kết quả.
TOOL_WAIT, EXPORT_WAIT, PREVIEW_WAIT = 30.0, 15.0, 10.0


class RenderBusy(Exception):
    """Hàng chờ dựng tài liệu đã đầy, hoặc chờ quá lâu."""


class RenderQueue:
    """Mỗi tiến trình dựng một tài liệu một lúc để VPS nhỏ không quá tải; việc đến sau chờ trong một hàng ngắn.

    Trước đây việc đến sau bị từ chối ngay: hai người tạo tệp cùng lúc, hoặc một người đang lật trang xem trước, là người
    kia nhận "Peto đang xuất tài liệu khác".
    """

    def __init__(self, max_waiting: int = 4):
        self.max_waiting = max_waiting
        self._lock: asyncio.Lock | None = None
        self._loop = None
        self._waiting = 0

    def _current(self) -> asyncio.Lock:
        # asyncio.Lock gắn với vòng lặp sự kiện đầu tiên phải chờ nó; test chạy mỗi test một vòng lặp riêng.
        loop = asyncio.get_running_loop()
        if self._lock is None or (self._loop is not loop and not self._lock.locked()):
            self._lock, self._loop = asyncio.Lock(), loop
        return self._lock

    def busy(self) -> bool:
        return bool(self._lock and self._lock.locked())

    @asynccontextmanager
    async def slot(self, wait: float):
        lock = self._current()
        if lock.locked() and self._waiting >= self.max_waiting:
            raise RenderBusy
        self._waiting += 1
        try:
            async with asyncio.timeout(wait):
                await lock.acquire()
        except TimeoutError:
            raise RenderBusy from None
        finally:
            self._waiting -= 1
        try:
            yield
        finally:
            lock.release()


render_queue = RenderQueue()


def render_page(data: bytes, page_number: int = 1) -> bytes:
    pdf = pdfium.PdfDocument(data)
    try:
        if not 1 <= page_number <= len(pdf):
            raise ValueError('Không tìm thấy trang này.')
        page = pdf[page_number - 1]
        try:
            bitmap = page.render(scale=min(1.7, 1050 / page.get_width()))
            try:
                picture = bitmap.to_pil()
                try:
                    output = BytesIO()
                    picture.save(output, format='PNG')
                    return output.getvalue()
                finally: picture.close()
            finally: bitmap.close()
        finally: page.close()
    finally: pdf.close()


def build_files(title, content, style, format, raw_images=None):
    """Dựng PDF (xem trước, đếm trang) và DOCX. ``raw_images``: ảnh của hội thoại theo số (document_images.load)."""
    images = prepare_all(raw_images or {}, strict=True)
    pdf = render_pdf(title, content, style, images)
    pages = len(PdfReader(BytesIO(pdf)).pages)
    if pages > 40:
        raise ValueError('Tài liệu dài quá 40 trang. Hãy chia thành các phần nhỏ hơn.')
    docx = render_docx(title, content, style, images)
    preview = render_page(pdf)
    if sum(map(len, [docx, pdf, preview])) > 8 * 1024 * 1024:
        raise ValueError('Tệp xuất quá lớn. Hãy bớt ảnh hoặc chia nhỏ tài liệu.' if images else 'Tệp xuất quá lớn. Hãy chia nhỏ tài liệu.')
    return {'docx': docx, 'pdf': pdf, 'preview': preview, 'pages': pages, 'format': format}


def build_presentation(content: str, raw_images=None):
    """Dựng bài thuyết trình (JSON của slides.spec.Deck) thành PPTX, PDF cùng bố cục và ảnh slide đầu."""
    from features.documents.slides import layout, pdf_out, pptx_out
    from features.documents.slides.spec import load
    from features.documents.slides.themes import THEMES
    deck = load(content)
    images = prepare_all(raw_images or {}, strict=True)
    scenes = layout.build(deck, images)
    pptx = pptx_out.render(scenes, deck.title, THEMES[deck.theme])
    pdf = pdf_out.render(scenes, deck.title)
    preview = render_page(pdf)
    if sum(map(len, [pptx, pdf, preview])) > 12 * 1024 * 1024:
        raise ValueError('Tệp xuất quá lớn. Hãy bớt ảnh hoặc chia nhỏ bài thuyết trình.')
    return {'docx': b'', 'pptx': pptx, 'pdf': pdf, 'preview': preview, 'pages': len(scenes), 'format': 'pptx'}


def export_file(format, title, content, style, raw_images=None):
    """Dựng một định dạng cho bản người dùng tự sửa. Ảnh không dùng được thì chỗ đó hiện thành chữ thay vì báo lỗi."""
    images = prepare_all(raw_images or {}, strict=False)
    return (render_pdf if format == 'pdf' else render_docx)(title, content, style, images)


def document_filename(title, format):
    name = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:90]
    return f'{name or "Tai lieu Peto"}.{format}'
