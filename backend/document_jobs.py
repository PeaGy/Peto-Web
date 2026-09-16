"""Bounded document rendering shared by chat tools and download routes."""
import asyncio
from io import BytesIO

import pypdfium2 as pdfium
from pypdf import PdfReader
from document_export import render_docx, render_pdf

render_lock = asyncio.Lock()


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


def build_files(title, content, style, format):
    pdf = render_pdf(title, content, style)
    pages = len(PdfReader(BytesIO(pdf)).pages)
    if pages > 40:
        raise ValueError('Tài liệu dài quá 40 trang. Hãy chia thành các phần nhỏ hơn.')
    docx = render_docx(title, content, style)
    preview = render_page(pdf)
    if sum(map(len, [docx, pdf, preview])) > 8 * 1024 * 1024:
        raise ValueError('Tệp xuất quá lớn. Hãy chia nhỏ tài liệu.')
    return {'docx': docx, 'pdf': pdf, 'preview': preview, 'pages': pages, 'format': format}


def document_filename(title, format):
    name = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:90]
    return f'{name or "Tai lieu Peto"}.{format}'
