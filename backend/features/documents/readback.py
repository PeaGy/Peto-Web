"""Bản đọc lại cấu trúc của tài liệu và bài thuyết trình vừa tạo, gửi kèm kết quả công cụ (trường ``check``).

Trước đây create_document và create_presentation chỉ trả thẻ tệp và số trang, nên Peto không có gì để đối chiếu đầu ra
với yêu cầu (thiếu chương, thiếu bảng, bìa còn dòng chấm) và dễ nói "đã xong" khi còn thiếu. Chủ web duyệt phần này
ngày 21/10/2026 (P2 của khảo sát công cụ). Chỉ đếm cấu trúc, không kiểm nội dung đúng hay sai; mọi danh sách có giới
hạn để kết quả công cụ không phình ngữ cảnh.
"""
from __future__ import annotations

from features.documents.export import body_blocks, parse_document, plain, visible

MAX_HEADINGS = 20
HEADING_CHARS = 60
SLIDE_TITLE_CHARS = 40
# Trường bìa mà docx_out/pdf_out để dòng chấm khi thiếu: người dùng phải tự điền.
COVER_BLANKS = (('school', 'trường'), ('faculty', 'khoa'), ('instructor', 'giảng viên'))


def _clip(text: str, limit: int) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def document_check(title: str, content: str, pages: int) -> dict:
    """Cấu trúc của tài liệu đúng như bản đã dựng: tên in ở đầu, đề mục cấp 1–2, số chữ, bảng, công thức, ảnh, khung
    ảnh, mục lục và các trường bìa còn trống."""
    cover, blocks = parse_document(content)
    shown, body = body_blocks(title, blocks)
    headings = [block for block in body if block.kind == 'heading']
    top = [[block.level, _clip(plain(block.runs), HEADING_CHARS)] for block in headings if block.level <= 2]
    cells = [cell for block in body if block.kind == 'table' for row in block.rows for cell in row]
    text_runs = [block.runs for block in body if block.kind in {'heading', 'paragraph', 'quote'}] + cells
    check = {
        'title': _clip(shown, 120),
        'pages': pages,
        # Đếm theo khoảng trắng như Word; công thức tính theo ký hiệu nhìn thấy.
        'words': sum(len(visible(runs).split()) for runs in text_runs),
        'headings': top[:MAX_HEADINGS],
        'tables': sum(block.kind == 'table' for block in body),
        'formulas': sum(block.kind == 'math' for block in body)
                    + sum(run.math for runs in text_runs for run in runs),
        'images': sum(block.kind == 'image' for block in body),
        'image_slots': sum(block.kind == 'slot' for block in body),
        'toc': any(block.kind == 'toc' for block in body) and bool(headings),
    }
    if len(top) > MAX_HEADINGS:
        check['headings_omitted'] = len(top) - MAX_HEADINGS
    if cover is not None:
        blank = [label for name, label in COVER_BLANKS if not getattr(cover, name)]
        if not cover.members:
            blank.append('thành viên')
        check['cover'] = {'blank': blank}
    return check


def deck_check(deck) -> dict:
    """Từng slide (số, bố cục, tiêu đề), slide chưa có ghi chú, số ảnh, bảng và biểu đồ."""
    slides = deck.slides
    return {
        'slides': [[index, slide.layout, _clip(slide.title, SLIDE_TITLE_CHARS)] for index, slide in enumerate(slides, 1)],
        'without_notes': [index for index, slide in enumerate(slides, 1) if not slide.notes.strip()],
        'images': sum(slide.layout == 'image_text' and bool(slide.image) for slide in slides),
        'tables': sum(slide.layout == 'table' for slide in slides),
        'charts': sum(slide.layout == 'chart' for slide in slides),
    }
