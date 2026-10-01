"""Render bounded Markdown to DOCX/PDF without executing HTML or fetching assets."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from io import BytesIO
from core.config import BASE_DIR
import re
import threading
import unicodedata
from urllib.parse import unquote

from markdown_it import MarkdownIt

MAX_CONTENT = 60000
# Ảnh trong một tài liệu: chỉ ảnh người dùng đã gửi trong hội thoại (document_images.py), không bao giờ ảnh từ web.
MAX_IMAGES = 12
FONT_DIR = BASE_DIR / "assets" / "fonts"
_font_lock = threading.Lock()
# ![chú thích](anh-2) là Ảnh 2 của hội thoại, đúng số trong nhãn "[Ảnh 2: …]" model thấy cạnh ảnh.
IMAGE_REF = re.compile(r"#?(?:anh|ảnh)[-_: ]?(\d{1,3})", re.IGNORECASE)
# Một dòng riêng "[TOC]" hoặc "[Mục lục]" là chỗ đặt mục lục, gồm các đề mục cấp 1–3.
TOC_MARKERS = {"[toc]", "[mục lục]"}
TOC_LEVELS = 3
# Danh sách lồng nhau: số 1. → a. → i., dấu đầu dòng • → –. Word và PDF dùng chung để hai bản giống nhau.
ORDERED_STYLES = ("decimal", "lowerLetter", "lowerRoman")
BULLETS = ("•", "–")


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False


@dataclass
class ListInfo:
    """Một danh sách Markdown. Mỗi danh sách, kể cả danh sách lồng, là một danh sách riêng trong Word nên tự đánh số từ đầu."""
    id: int
    ordered: bool
    depth: int
    style: str
    marker: str
    start: int


@dataclass
class Block:
    kind: str
    runs: list[Run] = field(default_factory=list)
    level: int = 0
    rows: list[list[list[Run]]] = field(default_factory=list)
    # Đoạn thuộc một mục danh sách: ``number`` là số của mục ở đoạn đầu tiên, None ở các đoạn sau của cùng mục.
    list_info: ListInfo | None = None
    number: int | None = None
    image: int = 0
    caption: str = ""


@dataclass
class DocImage:
    """Ảnh đã thu nhỏ để nhúng (document_images.prepare); kích thước tính bằng điểm ảnh."""
    data: bytes
    width: int
    height: int


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]", "", value).strip()


def _image_number(token) -> int:
    """Số ảnh của hội thoại khi ``src`` là anh-N, ngược lại 0: ảnh ở địa chỉ khác chỉ hiện thành chữ, không được tải."""
    source = unicodedata.normalize("NFC", unquote(token.attrGet("src") or "")).strip()
    match = IMAGE_REF.fullmatch(source)
    return int(match.group(1)) if match and int(match.group(1)) > 0 else 0


def _alt(token) -> str:
    return " ".join((token.content or "").split())


def inline_runs(tokens) -> list[Run]:
    runs, bold, italic, strike = [], 0, 0, 0
    links = []
    for token in tokens or []:
        if token.type == "strong_open": bold += 1
        elif token.type == "strong_close": bold -= 1
        elif token.type == "em_open": italic += 1
        elif token.type == "em_close": italic -= 1
        elif token.type == "s_open": strike += 1
        elif token.type == "s_close": strike -= 1
        elif token.type in {"text", "code_inline", "softbreak", "hardbreak", "image"}:
            text = token.content
            if token.type in {"softbreak", "hardbreak"}: text = "\n"
            if token.type == "image":
                number = _image_number(token)
                text = f"[Ảnh {number}: {_alt(token) or 'không có mô tả'}]" if number else f"[Ảnh: {token.content or 'không có mô tả'}]"
            runs.append(Run(text, bool(bold), bool(italic), bool(strike), token.type == "code_inline"))
        elif token.type == "link_close":
            if links:
                url, start = links.pop()
                label = ''.join(run.text for run in runs[start:])
                if url and url != label:
                    runs.append(Run(f' ({url})'))
        elif token.type == "link_open":
            # Keep the source address in downloads without fetching or executing it.
            links.append((token.attrGet('href'), len(runs)))
    return runs


def _trim(runs: list[Run]) -> list[Run]:
    """Bỏ phần chỉ có khoảng trắng hoặc xuống dòng ở hai đầu, còn lại khi một ảnh tách đoạn văn làm đôi."""
    while runs and not runs[0].text.strip(): runs.pop(0)
    while runs and not runs[-1].text.strip(): runs.pop()
    if runs:
        runs[0].text = runs[0].text.lstrip()
        runs[-1].text = runs[-1].text.rstrip()
    return runs


def inline_parts(tokens) -> list[list[Run] | tuple[int, str]]:
    """Như inline_runs, nhưng ảnh của hội thoại (anh-N) thành phần riêng ``(số, chú thích)`` để dựng thành khối ảnh."""
    parts, segment = [], []
    for token in tokens or []:
        number = _image_number(token) if token.type == "image" else 0
        if number:
            parts.extend([_trim(inline_runs(segment)), (number, _alt(token))])
            segment = []
        else:
            segment.append(token)
    parts.append(_trim(inline_runs(segment)))
    return parts


def parse_blocks(content: str) -> list[Block]:
    if not content.strip() or len(content) > MAX_CONTENT:
        raise ValueError("Nội dung cần có từ 1 đến 60.000 ký tự.")
    tokens = MarkdownIt("commonmark", {"html": False, "maxNesting": 20}).enable(["table", "strikethrough"]).parse(content)
    if len(tokens) > 12000:
        raise ValueError("Tài liệu có quá nhiều mục. Hãy chia thành các tài liệu nhỏ hơn.")
    blocks: list[Block] = []
    lists: list[ListInfo] = []
    counters: list[int] = []
    items: list[list] = []  # [danh sách, số của mục, đã gắn số vào đoạn nào chưa]
    index, quote_depth, list_count, has_toc = 0, 0, 0, False
    while index < len(tokens):
        token = tokens[index]
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            ordered = token.type == "ordered_list_open"
            same = sum(item.ordered == ordered for item in lists)
            start = min(max(int(token.attrGet("start") or 1), 0), 99999) if ordered else 1
            list_count += 1
            lists.append(ListInfo(list_count, ordered, min(len(lists), 8), ORDERED_STYLES[same % 3] if ordered else "bullet",
                                  "" if ordered else BULLETS[same % 2], start))
            counters.append(start)
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop(); counters.pop()
        elif token.type == "list_item_open":
            items.append([lists[-1], counters[-1], False])
            counters[-1] += 1
        elif token.type == "list_item_close": items.pop()
        elif token.type == "blockquote_open": quote_depth += 1
        elif token.type == "blockquote_close": quote_depth -= 1
        elif token.type == "heading_open":
            blocks.append(Block("heading", inline_runs(tokens[index + 1].children), int(token.tag[1:])))
        elif token.type == "paragraph_open":
            parts = inline_parts(tokens[index + 1].children)
            marker = len(parts) == 1 and "".join(run.text for run in parts[0]).strip().casefold() in TOC_MARKERS
            if marker and not items and not quote_depth:
                if not has_toc: blocks.append(Block("toc"))
                has_toc = True
            else:
                for part in parts:
                    if isinstance(part, tuple):
                        blocks.append(Block("image", image=part[0], caption=part[1]))
                    elif part:
                        block = Block("quote" if quote_depth else "paragraph", part, min(len(lists), 6))
                        if items and not quote_depth:
                            item = items[-1]
                            block.list_info = item[0]
                            if not item[2]: block.number, item[2] = item[1], True
                        blocks.append(block)
        elif token.type in {"fence", "code_block"}:
            for line in token.content.rstrip("\n").split("\n"):
                blocks.append(Block("code", [Run(line or " ", code=True)]))
        elif token.type == "hr": blocks.append(Block("rule"))
        elif token.type == "table_open":
            rows, row = [], []
            index += 1
            while index < len(tokens) and tokens[index].type != "table_close":
                cell = tokens[index]
                if cell.type == "tr_open": row = []
                elif cell.type == "inline": row.append(inline_runs(cell.children))
                elif cell.type == "tr_close": rows.append(row)
                index += 1
            if len(rows) > 100 or any(len(row) > 8 for row in rows):
                raise ValueError("Mỗi bảng hỗ trợ tối đa 100 dòng và 8 cột. Hãy chia bảng lớn trước khi xuất.")
            blocks.append(Block("table", rows=rows))
        index += 1
    if sum(block.kind == "image" for block in blocks) > MAX_IMAGES:
        raise ValueError(f"Mỗi tài liệu chèn tối đa {MAX_IMAGES} ảnh. Hãy bớt ảnh hoặc chia thành nhiều tài liệu.")
    if len(blocks) > 1200:
        raise ValueError("Tài liệu có quá nhiều đoạn. Hãy chia nhỏ trước khi xuất.")
    return blocks


def image_numbers(blocks: list[Block]) -> set[int]:
    """Các số ảnh (Ảnh N của hội thoại) tài liệu chèn."""
    return {block.image for block in blocks if block.kind == "image"}


def list_indent(depth: int) -> tuple[int, int]:
    """Chỗ đặt số hoặc dấu đầu dòng và chỗ bắt đầu chữ (point), thụt treo như Word; mỗi cấp lồng thụt thêm 18 pt."""
    return 18 + 18 * depth, 36 + 18 * depth


def list_label(info: ListInfo, number: int) -> str:
    """Nhãn của một mục trong bản PDF, cùng kiểu Word dựng từ định nghĩa đánh số (_numbering_level)."""
    if not info.ordered:
        return info.marker
    if info.style == "lowerLetter":  # như Word: y, z, aa, bb
        return chr(ord("a") + (max(number, 1) - 1) % 26) * ((max(number, 1) - 1) // 26 + 1) + "."
    if info.style == "lowerRoman":
        return _roman(max(number, 1)) + "."
    return f"{number}."


def _roman(number: int) -> str:
    result = ""
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
                           (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        count, number = divmod(number, value)
        result += letters * count
    return result


def _numbering_level(level: int, info: ListInfo) -> str:
    """Một cấp trong định nghĩa đánh số của Word (numbering.xml), cùng nhãn và vị trí với bản PDF."""
    number_x, text_x = list_indent(level)
    kind, text = (info.style, f"%{level + 1}.") if info.ordered else ("bullet", info.marker)
    return (f'<w:lvl w:ilvl="{level}"><w:start w:val="{info.start}"/><w:numFmt w:val="{kind}"/>'
            f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
            f'<w:pPr><w:ind w:left="{text_x * 20}" w:hanging="{(text_x - number_x) * 20}"/></w:pPr></w:lvl>')


def _fit(image: DocImage, width: float, height: float) -> tuple[float, float]:
    """Kích thước (point) để ảnh vừa khổ chữ: ảnh tính 96 dpi, không phóng to ảnh nhỏ, không cao quá ``height``."""
    natural_width, natural_height = image.width * .75, image.height * .75
    scale = min(1, width / natural_width, height / natural_height)
    return natural_width * scale, natural_height * scale


def _placeholder(block: Block) -> str:
    return f"[Ảnh {block.image}: {block.caption}]" if block.caption else f"[Ảnh {block.image}]"


def _plain(runs: list[Run]) -> str:
    return " ".join("".join(run.text for run in runs).split())


def _contents(blocks: list[Block]) -> tuple[list[Block], int]:
    """Đề mục vào mục lục (cấp 1–3) và cấp cao nhất trong số đó, để thụt các cấp dưới so với nó."""
    entries = [block for block in blocks if block.kind == "heading" and block.level <= TOC_LEVELS]
    return entries, min((block.level for block in entries), default=1)


def _body(title, content):
    blocks = parse_blocks(content)
    if blocks and blocks[0].kind == "heading" and "".join(run.text for run in blocks[0].runs).strip() == title.strip():
        blocks.pop(0)
    return blocks


def render_docx(title: str, content: str, layout: str = 'report', images: dict[int, DocImage] | None = None) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Cm, Inches, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    essay = layout == 'essay'
    font = 'Times New Roman' if essay else 'Arial'
    section.page_width, section.page_height = (Cm(21), Cm(29.7)) if essay else (Inches(8.5), Inches(11))
    section.top_margin = section.bottom_margin = Inches(.75)
    section.left_margin = section.right_margin = Inches(.75)
    text_width, text_height = section.page_width.pt - 108, section.page_height.pt - 108
    for name in ['Normal', 'Title', 'Caption', 'TOC Heading', *[f'Heading {n}' for n in range(1, 7)]]:
        style = document.styles[name]
        style.font.name = font
        style.font.color.rgb = RGBColor(0, 0, 0)
        # Mẫu của python-docx đặt font theo theme cho tiêu đề và đề mục, và font theme thắng tên font vừa đặt: Word hiện
        # Calibri thay cho Times New Roman/Arial như bản PDF xem trước.
        for attribute in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
            style.element.rPr.rFonts.attrib.pop(qn(attribute), None)
    normal = document.styles['Normal']
    normal.font.size = Pt(13 if essay else 11)
    normal.paragraph_format.line_spacing = 1.5 if essay else 1.25
    if essay:
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        normal.paragraph_format.first_line_indent = Cm(.75)
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        header.add_run('Nghị luận xã hội').italic = True
    normal.paragraph_format.space_after = Pt(7)
    # Cỡ chữ và khoảng cách theo bản PDF xem trước. Mẫu gốc còn kẻ một đường xanh dưới tiêu đề mà bản PDF không có.
    title_style = document.styles['Title']
    title_style.font.size, title_style.font.bold = Pt(21 if essay else 24), True
    title_style.paragraph_format.space_after = Pt(26 if essay else 18)
    border = title_style.element.pPr.find(qn('w:pBdr'))
    if border is not None: title_style.element.pPr.remove(border)
    for level in range(1, 7):
        heading = document.styles[f'Heading {level}']
        heading.font.size, heading.font.bold, heading.font.italic = Pt(max(11, 20 - 2 * level)), True, False
        heading.paragraph_format.space_before, heading.paragraph_format.space_after = Pt(12), Pt(6)
    caption = document.styles['Caption']
    caption.font.size, caption.font.bold, caption.font.italic = Pt(11 if essay else 10), False, True
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = 0
    caption.paragraph_format.space_after = Pt(12)
    document.core_properties.title, document.core_properties.author = title, 'Peto'
    title_paragraph = document.add_paragraph(title, 'Title')
    title_paragraph.paragraph_format.first_line_indent = 0
    if essay: title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def write(paragraph, runs):
        for item in runs:
            run = paragraph.add_run(item.text)
            run.bold = item.bold or None
            run.italic, run.font.strike = item.italic or None, item.strike or None
            if item.code: run.font.name, run.font.size = 'Consolas', Pt(10)

    def field(paragraph, kind, dirty=False):
        char = OxmlElement('w:fldChar')
        char.set(qn('w:fldCharType'), kind)
        if dirty: char.set(qn('w:dirty'), 'true')
        paragraph.add_run()._r.append(char)

    # Mỗi danh sách một định nghĩa đánh số riêng: số tự bắt đầu lại, và Word đánh lại số khi người dùng thêm bớt mục.
    numbering = document.part.numbering_part.element
    next_abstract = max((int(item.get(qn('w:abstractNumId'))) for item in numbering.findall(qn('w:abstractNum'))), default=0) + 1
    num_ids: dict[int, int] = {}

    def num_id(info):
        nonlocal next_abstract
        if info.id not in num_ids:
            levels = ''.join(_numbering_level(level, info) for level in range(9))
            abstract = parse_xml(f'<w:abstractNum {nsdecls("w")} w:abstractNumId="{next_abstract}">'
                                 f'<w:multiLevelType w:val="hybridMultilevel"/>{levels}</w:abstractNum>')
            first = numbering.find(qn('w:num'))
            if first is None: numbering.append(abstract)
            else: first.addprevious(abstract)
            num_ids[info.id] = numbering.add_num(next_abstract).numId
            next_abstract += 1
        return num_ids[info.id]

    blocks = _body(title, content)
    entries, top = _contents(blocks)
    for block in blocks:
        if block.kind == 'table' and block.rows:
            table = document.add_table(rows=0, cols=len(block.rows[0]))
            table.style = 'Table Grid'
            for row_index, row in enumerate(block.rows):
                cells = table.add_row().cells
                for cell, runs in zip(cells, row):
                    write(cell.paragraphs[0], runs)
                    if row_index == 0:
                        for run in cell.paragraphs[0].runs: run.bold = True
                        shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), 'EDF0F4'); cell._tc.get_or_add_tcPr().append(shade)
                if row_index == 0:
                    repeat = OxmlElement('w:tblHeader'); table.rows[0]._tr.get_or_add_trPr().append(repeat)
            document.add_paragraph().paragraph_format.space_after = Pt(3)
        elif block.kind == 'rule': document.add_paragraph()
        elif block.kind == 'image':
            image = (images or {}).get(block.image)
            if image is None:
                write(document.add_paragraph(), [Run(_placeholder(block))])
                continue
            width, _ = _fit(image, text_width, text_height * .55)
            picture = document.add_paragraph()
            picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
            picture.paragraph_format.first_line_indent = 0
            picture.paragraph_format.line_spacing = 1
            picture.paragraph_format.keep_with_next = bool(block.caption)
            picture.add_run().add_picture(BytesIO(image.data), width=Pt(width))
            if block.caption: document.add_paragraph(block.caption, style='Caption')
        elif block.kind == 'toc':
            if not entries: continue
            document.add_paragraph('Mục lục', style='TOC Heading').alignment = WD_ALIGN_PARAGRAPH.CENTER
            for position, entry in enumerate(entries):
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.left_indent = Pt(18 * (entry.level - top))
                paragraph.paragraph_format.first_line_indent = 0
                paragraph.paragraph_format.space_after = Pt(2)
                if position == 0:
                    # Trường mục lục đánh dấu cần cập nhật: Word hỏi cập nhật khi mở rồi dựng lại có số trang. Trình xem
                    # khác (điện thoại, Google Docs) hiện danh sách đề mục viết sẵn bên dưới.
                    field(paragraph, 'begin', dirty=True)
                    instruction = OxmlElement('w:instrText')
                    instruction.set(qn('xml:space'), 'preserve')
                    instruction.text = f' TOC \\o "1-{TOC_LEVELS}" \\h \\z \\u '
                    paragraph.add_run()._r.append(instruction)
                    field(paragraph, 'separate')
                paragraph.add_run(_plain(entry.runs))
            field(paragraph, 'end')
            document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        else:
            style = f'Heading {block.level}' if block.kind == 'heading' else 'Normal'
            paragraph = document.add_paragraph(style=style)
            layout_format = paragraph.paragraph_format
            if block.kind == 'heading':
                layout_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
                layout_format.first_line_indent = 0
            elif block.list_info:
                number_x, text_x = list_indent(block.list_info.depth)
                layout_format.left_indent = Pt(text_x)
                layout_format.first_line_indent = Pt(number_x - text_x) if block.number is not None else 0
                if block.number is not None:
                    properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
                    properties.get_or_add_ilvl().val = block.list_info.depth
                    properties.get_or_add_numId().val = num_id(block.list_info)
            if block.kind == 'quote': layout_format.left_indent = Inches(.25)
            if block.kind == 'code': layout_format.space_after = Pt(0)
            write(paragraph, block.runs)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run('Trang ').font.size = Pt(9)
    page = OxmlElement('w:fldSimple'); page.set(qn('w:instr'), 'PAGE'); footer._p.append(page)
    output = BytesIO(); document.save(output)
    return output.getvalue()


def _register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _font_lock:
        if 'PetoSans' not in pdfmetrics.getRegisteredFontNames():
            for suffix, style in [('', 'Regular'), ('-Bold', 'Bold'), ('-Italic', 'Italic'), ('-BoldItalic', 'BoldItalic')]:
                pdfmetrics.registerFont(TTFont('PetoSans' + suffix, str(FONT_DIR / f'NotoSans-{style}.ttf')))
            pdfmetrics.registerFontFamily('PetoSans', normal='PetoSans', bold='PetoSans-Bold', italic='PetoSans-Italic', boldItalic='PetoSans-BoldItalic')
        if 'PetoSerif' not in pdfmetrics.getRegisteredFontNames():
            for suffix, style in [('', 'Regular'), ('-Bold', 'Bold'), ('-Italic', 'Italic'), ('-BoldItalic', 'BoldItalic')]:
                pdfmetrics.registerFont(TTFont('PetoSerif' + suffix, str(FONT_DIR / f'NotoSerif-{style}.ttf')))
            pdfmetrics.registerFontFamily('PetoSerif', normal='PetoSerif', bold='PetoSerif-Bold', italic='PetoSerif-Italic', boldItalic='PetoSerif-BoldItalic')


def render_pdf(title: str, content: str, layout: str = 'report', images: dict[int, DocImage] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (HRFlowable, Image, KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, TableStyle)
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.pdfbase import pdfmetrics

    _register_fonts()
    essay = layout == 'essay'
    font = 'PetoSerif' if essay else 'PetoSans'
    page_size = A4 if essay else letter
    if any(not char.isspace() and ord(char) not in pdfmetrics.getFont(font).face.charToGlyph for char in title + content):
        raise ValueError('PDF chưa hỗ trợ một số ký tự trong bản nháp (chẳng hạn emoji hoặc chữ tượng hình). Hãy bỏ các ký tự đó hoặc tải DOCX.')
    body = ParagraphStyle('Body', fontName='PetoSans', fontSize=11, leading=16, spaceAfter=8, splitLongWords=True)
    heading = {n: ParagraphStyle(f'Heading{n}', parent=body, fontName='PetoSans-Bold', fontSize=max(11, 20-2*n), leading=max(16, 25-2*n), spaceBefore=12, keepWithNext=True) for n in range(1, 7)}
    title_style = ParagraphStyle('Title', parent=body, fontName='PetoSans-Bold', fontSize=24, leading=31, spaceAfter=18)
    if essay:
        body.fontName, body.fontSize, body.leading = font, 13, 20
        body.alignment, body.firstLineIndent = 4, 21
        for style in heading.values(): style.fontName = font + '-Bold'
        title_style.fontName, title_style.fontSize, title_style.leading = font + '-Bold', 21, 29
        title_style.alignment, title_style.spaceAfter = 1, 26
    caption_style = ParagraphStyle('Caption', parent=body, fontName=font + '-Italic', fontSize=11 if essay else 10,
                                   leading=15 if essay else 14, alignment=1, firstLineIndent=0, spaceBefore=4, spaceAfter=12)
    contents_title = ParagraphStyle('ContentsTitle', parent=heading[1], alignment=1, spaceBefore=6, spaceAfter=12, keepWithNext=False)
    top_margin = 62 if essay else 54
    frame_width, frame_height = page_size[0] - 108, page_size[1] - top_margin - 54

    def markup(runs):
        chunks = []
        for run in runs:
            text = escape(run.text).replace('\n', '<br/>')
            if run.code: text = text.replace(' ', '&#160;')
            if run.bold: text = f'<b>{text}</b>'
            if run.italic: text = f'<i>{text}</i>'
            if run.strike: text = f'<strike>{text}</strike>'
            chunks.append(text)
        return ''.join(chunks) or '&#160;'

    blocks = _body(title, content)
    entries, top = _contents(blocks)
    outline_top = min((block.level for block in blocks if block.kind == 'heading'), default=1)
    outline_level, has_contents = -1, False
    story = [Paragraph(escape(title), title_style)]
    for position, block in enumerate(blocks):
        if block.kind == 'table' and block.rows:
            cell_style = ParagraphStyle('Cell', parent=body, fontSize=10, leading=14, spaceAfter=0)
            head_style = ParagraphStyle('CellHead', parent=cell_style, fontName=font + '-Bold')
            rows = [[Paragraph(markup(cell), head_style if i == 0 else cell_style) for cell in row] for i, row in enumerate(block.rows)]
            table = LongTable(rows, colWidths=[(page_size[0] - 108) / len(rows[0])] * len(rows[0]), repeatRows=1, splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EDF0F4')),
                ('GRID', (0,0), (-1,-1), .5, colors.HexColor('#BDC5CE')),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 7), ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ]))
            story.extend([table, Spacer(1, 10)])
        elif block.kind == 'rule': story.append(HRFlowable(width='100%', thickness=.5, color=colors.HexColor('#BDC5CE'), spaceAfter=10))
        elif block.kind == 'image':
            image = (images or {}).get(block.image)
            if image is None:
                story.append(Paragraph(escape(_placeholder(block)), body))
                continue
            width, height = _fit(image, frame_width, frame_height * .55)
            picture = Image(BytesIO(image.data), width=width, height=height)
            picture.hAlign = 'CENTER'
            ending = Paragraph(escape(block.caption), caption_style) if block.caption else Spacer(1, 12)
            story.append(KeepTogether([Spacer(1, 4), picture, ending]))
        elif block.kind == 'toc':
            if not entries or has_contents: continue
            has_contents = True
            contents = TableOfContents(dotsMinLevel=0)
            contents.levelStyles = [ParagraphStyle(f'Contents{level}', fontName=font, fontSize=12 if essay else 11,
                                                   leading=18 if essay else 16, leftIndent=18 * level, firstLineIndent=0)
                                    for level in range(TOC_LEVELS)]
            story.extend([Paragraph('Mục lục', contents_title), contents, PageBreak()])
        elif block.kind == 'heading':
            paragraph = Paragraph(markup(block.runs), heading[block.level])
            # Mục trong khung dấu trang của trình xem PDF không được sâu hơn mục đứng trước quá một cấp.
            outline_level = min(block.level - outline_top, outline_level + 1)
            paragraph.peto_heading = (block.level, outline_level, _plain(block.runs), f'h{position}')
            story.append(paragraph)
        elif block.list_info:
            number_x, text_x = list_indent(block.list_info.depth)
            style = ParagraphStyle('Item', parent=body, leftIndent=text_x, firstLineIndent=0, bulletIndent=number_x,
                                   bulletFontName=body.fontName, bulletFontSize=body.fontSize)
            label = list_label(block.list_info, block.number) if block.number is not None else None
            story.append(Paragraph(markup(block.runs), style, bulletText=label))
        else:
            style = ParagraphStyle('Item', parent=body, leftIndent=14 * block.level)
            if block.kind == 'quote': style.leftIndent = 18
            if block.kind == 'code': style.fontSize, style.leading, style.spaceAfter = 10, 14, 0
            story.append(Paragraph(markup(block.runs), style))

    def page_footer(canvas, document):
        canvas.saveState(); canvas.setFont(font, 9)
        canvas.drawCentredString(page_size[0] / 2, 30, f'Trang {document.page}')
        if essay:
            canvas.setFont(font + '-Italic', 9)
            canvas.setFillColor(colors.HexColor('#506279'))
            canvas.drawRightString(page_size[0] - 54, page_size[1] - 34, 'Nghị luận xã hội')
        canvas.restoreState()

    class Template(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            # Đề mục thành dấu trang trong trình xem PDF và, khi có mục lục, thành một dòng mục lục có số trang thật.
            entry = getattr(flowable, 'peto_heading', None)
            if entry is None: return
            level, outline, text, key = entry
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=outline, closed=False)
            if has_contents and level <= TOC_LEVELS:
                self.notify('TOCEntry', (level - top, escape(text), self.page, key))

    output = BytesIO()
    document = Template(output, pagesize=page_size, topMargin=top_margin, bottomMargin=54, leftMargin=54, rightMargin=54, title=title, author='Peto')
    # Mục lục cần số trang của đề mục nên phải dàn trang vài lượt.
    (document.multiBuild if has_contents else document.build)(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()
