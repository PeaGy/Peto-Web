"""Bản PDF (xem trước và tải về) của tài liệu Peto tạo, cùng kiểu trình bày với bản Word (docx_out.py), bằng ReportLab.

Chữ dùng Tinos, cùng bề rộng với Times New Roman của bản Word, nên ngắt dòng và số trang gần như trùng. Bìa vẽ thẳng lên
trang đầu (onFirstPage): khối trường ở trên, đề tài giữa trang, người làm ở đáy; luồng chữ bắt đầu từ trang hai.
"""
from __future__ import annotations

import unicodedata
from html import escape
from io import BytesIO

from features.documents import export as base
from features.documents.cover import DOTS, Cover
from features.documents.themes import Theme, theme_for

CM = 28.3465
PAGE_WIDTH, PAGE_HEIGHT = 595.28, 841.89
TOP, BOTTOM, LEFT, RIGHT = 2 * CM, 2 * CM, 3 * CM, 2 * CM
FRAME_WIDTH = PAGE_WIDTH - LEFT - RIGHT
# "Giãn dòng 1,5" của Word với Times New Roman 13: một dòng đơn cao 1,15 cỡ chữ.
LEADING = 13 * 1.15 * 1.5
GRAY = "#5A6B80"
FONT, BOLD, ITALIC, BOLD_ITALIC, MONO = "PetoTimes", "PetoTimes-Bold", "PetoTimes-Italic", "PetoTimes-BoldItalic", "PetoMono"


def _color(value: str):
    from reportlab.lib import colors
    return colors.HexColor("#" + value.lstrip("#"))


def render(title: str, content: str, layout: str = "classic", images: dict | None = None,
           toc_out: list | None = None) -> bytes:
    from reportlab.pdfbase import pdfmetrics

    from features.documents.math.layout import MATH_FONT, TextFonts, glyphs as math_glyphs

    base.register_fonts()
    theme = theme_for(layout)
    title = " ".join(title.split())
    body_glyphs = pdfmetrics.getFont(FONT).face.charToGlyph
    math_cmap = math_glyphs().cmap
    # Ký tự Tinos thiếu mà phông toán có (≤, ∈, →…) được vẽ bằng phông toán; thiếu cả hai mới từ chối.
    if any(not char.isspace() and ord(char) not in body_glyphs and ord(char) not in math_cmap
           and not unicodedata.combining(char) for char in title + content):
        raise ValueError("PDF chưa hỗ trợ một số ký tự trong bản nháp (chẳng hạn emoji hoặc chữ tượng hình). "
                         "Hãy bỏ các ký tự đó hoặc tải DOCX.")
    cover, blocks = base.parse_document(content)
    shown, blocks = base.body_blocks(title, blocks)
    writer = _Writer(title, theme, images or {}, TextFonts(FONT, BOLD, ITALIC), body_glyphs, math_cmap, MATH_FONT)
    writer.shown = shown
    return writer.build(cover, blocks, toc_out)


class _Writer:
    def __init__(self, title, theme: Theme, images, text_fonts, body_glyphs, math_cmap, math_font):
        from reportlab.lib.styles import ParagraphStyle

        self.title = title
        self.shown = title
        self.theme = theme
        self.images = images
        self.text_fonts = text_fonts
        self.body_glyphs = body_glyphs
        self.math_cmap = math_cmap
        self.math_font = math_font
        self.math_slots: list = []
        self.figures = 0
        self.tables = 0
        accent = _color(theme.heading_color)
        # autoLeading "max": dòng có công thức cao (phân số trong dòng) tự giãn thay vì đè lên dòng trên.
        self.normal = ParagraphStyle("Body", fontName=FONT, fontSize=13, leading=LEADING, alignment=4,
                                   firstLineIndent=CM, spaceAfter=6, splitLongWords=True, autoLeading="max")
        spacing = [(12, 6), (10, 4), (8, 3), (6, 3)]
        self.headings = {}
        for level in range(1, 5):
            size = theme.heading_sizes[level - 1]
            italic = theme.heading_italic[level - 1]
            self.headings[level] = ParagraphStyle(
                f"Heading{level}", parent=self.normal, fontName=BOLD_ITALIC if italic else BOLD, fontSize=size,
                leading=size * 1.35, alignment=0, firstLineIndent=0, spaceBefore=spacing[level - 1][0],
                spaceAfter=spacing[level - 1][1], keepWithNext=True, textColor=accent)
        self.cell = ParagraphStyle("Cell", parent=self.normal, fontSize=12, leading=14.5, firstLineIndent=0, alignment=0,
                                   spaceAfter=0)
        self.caption_style = ParagraphStyle(
            "Caption", parent=self.normal, fontName=ITALIC if theme.name in {"classic", "essay"} else FONT,
            fontSize=11.5 if theme.caption_small_caps else 12, leading=15, firstLineIndent=0,
            alignment=0 if theme.caption_align == "left" else 1, leftIndent=CM if theme.caption_align == "left" else 0,
            spaceBefore=3, spaceAfter=10)
        self.code_style = ParagraphStyle("Code", fontName=MONO, fontSize=10.5 if theme.code == "bar" else 11,
                                         leading=13.5, alignment=0)

    # ---------- chữ ----------
    def markup(self, runs, size, upper=False) -> str:
        chunks = []
        for run in runs:
            if run.math:
                chunks.append(base.math_slot(run.text, size, self.text_fonts, self.math_slots))
                continue
            text = run.text.upper() if upper else run.text
            text = base.fallback(escape(text), self.body_glyphs, self.math_cmap, self.math_font).replace("\n", "<br/>")
            if run.code:
                text = text.replace(" ", "&#160;")
                back = ' backColor="#E9EEF5"' if self.theme.code == "bar" else ""
                text = f'<font face="{MONO}" size="{size * 0.85:.1f}"{back}>{text}</font>'
            if run.bold: text = f"<b>{text}</b>"
            if run.italic: text = f"<i>{text}</i>"
            if run.strike: text = f"<strike>{text}</strike>"
            chunks.append(text)
        return "".join(chunks) or "&#160;"

    def para(self, runs, style, upper=False, **options):
        """Paragraph có công thức trong dòng: mỗi công thức là một ô ảnh rỗng giữ chỗ, canvas vẽ công thức vào đó."""
        from reportlab.platypus import Paragraph
        start = len(self.math_slots)
        paragraph = Paragraph(self.markup(runs, style.fontSize, upper), style, **options)
        base.attach_math(paragraph, self.math_slots[start:])
        return paragraph

    def text(self, value: str, style, **overrides):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        if overrides:
            style = ParagraphStyle(f"{style.name}+", parent=style, **overrides)
        markup = base.fallback(escape(value), self.body_glyphs, self.math_cmap, self.math_font).replace("\n", "<br/>")
        return Paragraph(markup or "&#160;", style)

    def style(self, name: str, **values):
        from reportlab.lib.styles import ParagraphStyle
        return ParagraphStyle(name, **{"fontName": FONT, "fontSize": 13, "leading": 16, "alignment": 1, **values})

    # ---------- khung ----------
    def build(self, cover: Cover | None, blocks: list, toc_out: list | None) -> bytes:
        from reportlab.platypus import SimpleDocTemplate

        story = []
        if cover is not None:
            story.append(_FullPage())
        else:
            story.extend(self.title_block())
        entries = base.contents(blocks)
        self.has_contents = any(block.kind == "toc" for block in blocks) and bool(entries)
        story.extend(self.body(blocks, entries))
        pages: dict[str, tuple[int, str, int]] = {}
        writer = self
        outline_top = 1

        class Template(SimpleDocTemplate):
            def handle_keepWithNext(self, flowables):
                _keep_with_next(self, flowables)

            def afterFlowable(self, flowable):
                # Đề mục thành dấu trang trong trình xem PDF và, khi có mục lục, thành một dòng mục lục có số trang thật.
                entry = getattr(flowable, "peto_heading", None)
                if entry is None:
                    return
                level, outline, text, key = entry
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=outline, closed=False)
                pages[key] = (level, text, self.page)
                if writer.has_contents and level <= base.TOC_LEVELS:
                    shown = escape(text.upper() if level == 1 and writer.theme.name == "classic" else text)
                    self.notify("TOCEntry", (level - outline_top, shown, self.page, key))

        output = BytesIO()
        document = Template(output, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), topMargin=TOP, bottomMargin=BOTTOM,
                            leftMargin=LEFT, rightMargin=RIGHT, title=self.title, author="Peto")
        # Không bìa: trang đầu đã có tên tài liệu nên không lặp lại ở đầu trang, chỉ có số trang.
        first = ((lambda canvas, doc: self.cover_page(canvas, cover)) if cover is not None else
                 (lambda canvas, doc: self.decorate(canvas, doc, header=False)))
        build = document.multiBuild if self.has_contents else document.build
        build(story, onFirstPage=first, onLaterPages=self.decorate, canvasmaker=base.math_canvas)
        if toc_out is not None:
            toc_out.extend(pages[key] for key in sorted(pages, key=lambda item: int(item[1:])))
        return output.getvalue()

    # ---------- tên tài liệu khi không có bìa ----------
    def title_block(self) -> list:
        theme = self.theme
        if theme.title == "center":
            return [self.text(self.shown.upper(), self.style("Title", fontName=BOLD, fontSize=15, leading=20,
                                                               spaceAfter=14))]
        if theme.title == "band":
            return [self.text(self.shown, self.style("Title", fontName=BOLD, fontSize=20, leading=25, alignment=0,
                                                     textColor=_color(theme.accent), spaceAfter=4)),
                    _Rule(1.0, theme.accent, after=14)]
        if theme.title == "rule":
            return [self.text(self.shown, self.style("Title", fontSize=18, leading=23, spaceAfter=4)),
                    _Rule(0.75, "111111", after=14)]
        return [self.text(self.shown, self.style("Title", fontName=BOLD, fontSize=18, leading=24, spaceAfter=18))]

    # ---------- phần thân ----------
    def body(self, blocks: list, entries: list) -> list:
        from reportlab.platypus import PageBreak, Paragraph
        from reportlab.platypus.tableofcontents import TableOfContents

        story = []
        index = 0
        outline_level = -1
        added_contents = False
        while index < len(blocks):
            block = blocks[index]
            following = blocks[index + 1] if index + 1 < len(blocks) else None
            caption = base.table_caption(block, following)
            if caption is not None:
                story.extend(self.table(following.rows, caption))
                index += 2
                continue
            if block.kind == "code":
                end = index
                while end < len(blocks) and blocks[end].kind == "code":
                    end += 1
                story.append(self.code([item.runs for item in blocks[index:end]]))
                index = end
                continue
            if block.kind == "table" and block.rows:
                story.extend(self.table(block.rows, None))
            elif block.kind == "rule":
                story.append(_Rule(0.5, "BFBFBF", before=4, after=10))
            elif block.kind == "math":
                story.append(base.math_block(block.math, 13, self.text_fonts))
            elif block.kind == "image":
                story.extend(self.image(block))
            elif block.kind == "slot":
                story.extend(self.slot(block.caption))
            elif block.kind == "toc":
                if entries and not added_contents:
                    added_contents = True
                    story.extend([self.toc_title(), self.toc(), PageBreak()])
            elif block.kind == "heading":
                upper = block.level == 1 and self.theme.heading_caps[0]
                paragraph = self.para(block.runs, self.headings[block.level], upper=upper)
                # Mục trong khung dấu trang của trình xem PDF không được sâu hơn mục đứng trước quá một cấp.
                outline_level = min(block.level - 1, outline_level + 1)
                paragraph.peto_heading = (block.level, outline_level, base.plain(block.runs), f"h{index}")
                story.append(paragraph)
                if block.level == 1 and self.theme.heading_rule:
                    story.append(_Rule(1.0, self.theme.accent, before=-2, after=6, keep=True))
            elif block.list_info:
                from reportlab.lib.styles import ParagraphStyle
                number_x, text_x = base.list_indent(block.list_info.depth)
                style = ParagraphStyle("Item", parent=self.normal, leftIndent=text_x, firstLineIndent=0,
                                       bulletIndent=number_x, bulletFontName=FONT, bulletFontSize=13, spaceAfter=3)
                label = base.list_label(block.list_info, block.number) if block.number is not None else None
                story.append(self.para(block.runs, style, bulletText=label))
            elif block.kind == "quote":
                from reportlab.lib.styles import ParagraphStyle
                for item in block.runs:
                    item.italic = True
                style = ParagraphStyle("Quote", parent=self.normal, leftIndent=CM, firstLineIndent=0)
                paragraph = self.para(block.runs, style)
                if self.theme.name == "band":
                    story.append(self.boxed([[paragraph]], [("LINEBEFORE", (0, 0), (0, -1), 2, _color(self.theme.accent)),
                                                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
                else:
                    story.append(paragraph)
            else:
                story.append(self.para(block.runs, self.normal))
            index += 1
        return story

    def boxed(self, rows, commands, widths=None, repeat=0):
        from reportlab.platypus import LongTable, TableStyle
        table = LongTable(rows, colWidths=widths or [FRAME_WIDTH], repeatRows=repeat, splitByRow=1, splitInRow=1)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 2), *commands]))
        return table

    def code(self, lines: list):
        from reportlab.platypus import Paragraph
        rows = []
        for runs in lines:
            text = escape("".join(run.text for run in runs)).replace(" ", "&#160;")
            text = base.fallback(text, self.body_glyphs, self.math_cmap, self.math_font)
            rows.append([Paragraph(text or "&#160;", self.code_style)])
        theme = self.theme
        if theme.code == "box":
            commands = [("BOX", (0, 0), (-1, -1), 0.75, _color("BFBFBF")), ("BACKGROUND", (0, 0), (-1, -1), _color("F2F2F2"))]
        elif theme.code == "bar":
            commands = [("LINEBEFORE", (0, 0), (0, -1), 3, _color(theme.accent)),
                        ("BACKGROUND", (0, 0), (-1, -1), _color("F3F6FA"))]
        else:
            commands = [("LINEABOVE", (0, 0), (-1, 0), 0.75, _color("222222")),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.75, _color("222222"))]
        commands += [("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
                     ("TOPPADDING", (0, 1), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9)]
        table = self.boxed(rows, commands)
        table.spaceBefore, table.spaceAfter = 4, 8
        return table

    def caption(self, kind: str, number: int, text: str):
        from reportlab.platypus import Paragraph
        theme = self.theme
        label = f"{kind} {number}{theme.caption_separator}"
        if theme.caption_small_caps:
            label = f'<font size="9.5">{escape(label.upper())}</font>'
        else:
            label = escape(label)
        color = f' color="#{theme.caption_color}"' if theme.caption_color != "000000" else ""
        label = f'<font name="{BOLD}"{color}>{label}</font>'
        body = base.fallback(escape(text), self.body_glyphs, self.math_cmap, self.math_font)
        return Paragraph(label + (" " + body if text else ""), self.caption_style)

    def image(self, block) -> list:
        from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer
        image = self.images.get(block.image)
        if image is None:
            return [Paragraph(escape(base.placeholder(block)), self.normal)]
        width, height = base.fit(image, FRAME_WIDTH, (PAGE_HEIGHT - TOP - BOTTOM) * .55)
        picture = Image(BytesIO(image.data), width=width, height=height)
        picture.hAlign = "CENTER"
        parts = [Spacer(1, 4), picture]
        if block.caption:
            self.figures += 1
            parts.append(self.caption("Hình", self.figures, base.figure_caption(block.caption)))
        else:
            parts.append(Spacer(1, 12))
        return [KeepTogether(parts)]

    def slot(self, caption: str) -> list:
        from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle
        text = base.figure_caption(caption)
        note = self.text("Chỗ dán ảnh chụp màn hình" + (f":\n{text}" if text else ""),
                         self.style("Slot", fontName=ITALIC, fontSize=11, leading=14, textColor=_color("6B7480")))
        width = FRAME_WIDTH * 0.85
        box = Table([[note]], colWidths=[width], rowHeights=[5.4 * CM])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, _color("9AA3AD"), None, (3, 2)),
                                 ("BACKGROUND", (0, 0), (-1, -1), _color("FAFBFC")),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        box.hAlign = "CENTER"
        self.figures += 1
        return [KeepTogether([Spacer(1, 4), box, Spacer(1, 6), self.caption("Hình", self.figures, text)])]

    def table(self, rows: list, caption: str | None) -> list:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import KeepTogether, Spacer
        theme = self.theme
        parts = []
        if caption is not None:
            self.tables += 1
            parts.append(self.caption("Bảng", self.tables, caption))
        columns = max(len(row) for row in rows)
        rows = [row + [[] for _ in range(columns - len(row))] for row in rows]
        widths = base.column_widths(rows, FRAME_WIDTH)
        centered = base.centered_columns(rows)
        center = ParagraphStyle("CellCenter", parent=self.cell, alignment=1)
        head = ParagraphStyle("CellHead", parent=self.cell, fontName=BOLD,
                              textColor=_color("FFFFFF") if theme.table == "band" else _color("000000"))
        head_center = ParagraphStyle("CellHeadCenter", parent=head, alignment=1)
        cells = []
        for row_index, row in enumerate(rows):
            line = []
            for column, runs in enumerate(row):
                if row_index == 0:
                    style = head_center if column in centered or theme.table == "grid" else head
                else:
                    style = center if column in centered else self.cell
                line.append(self.para(runs, style))
            cells.append(line)
        commands = [("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        if theme.table == "grid":
            commands += [("GRID", (0, 0), (-1, -1), 0.75, _color("000000")),
                         ("BACKGROUND", (0, 0), (-1, 0), _color("F2F2F2"))]
        elif theme.table == "band":
            commands += [("BACKGROUND", (0, 0), (-1, 0), _color(theme.accent)),
                         ("LINEBELOW", (0, 1), (-1, -1), 0.75, _color("C9D3E0"))]
            commands += [("BACKGROUND", (0, row), (-1, row), _color("F3F6FA")) for row in range(2, len(rows), 2)]
        else:
            commands += [("LINEABOVE", (0, 0), (-1, 0), 1.5, _color("000000")),
                         ("LINEBELOW", (0, 0), (-1, 0), 0.75, _color("000000")),
                         ("LINEBELOW", (0, -1), (-1, -1), 1.5, _color("000000"))]
        table = self.boxed(cells, commands, widths, repeat=1)
        # Bảng ngắn không tách trang (bản Word giữ các hàng với hàng sau). Bảng dài tách theo hàng, lặp hàng tiêu đề, và
        # chú thích đi cùng phần đầu bảng (_KeepStart) thay vì nằm lại một mình cuối trang.
        if len(rows) <= base.SHORT_TABLE_ROWS:
            return [KeepTogether([*parts, table]), Spacer(1, 8)]
        if parts:
            parts[0].keepWithNext = True
        return [*parts, table, Spacer(1, 8)]

    def toc_title(self):
        theme = self.theme
        if theme.name == "band":
            return self.text("Mục lục", self.style("TocTitle", fontName=BOLD, fontSize=20, leading=25, alignment=0,
                                                   textColor=_color(theme.accent), spaceAfter=14))
        if theme.name == "minimal":
            return self.text("MỤC LỤC", self.style("TocTitle", fontSize=12.5, leading=18, spaceAfter=14))
        if theme.name == "classic":
            return self.text("MỤC LỤC", self.style("TocTitle", fontName=BOLD, fontSize=14, leading=20, spaceAfter=14))
        return self.text("Mục lục", self.style("TocTitle", fontName=BOLD, fontSize=16, leading=22, spaceAfter=14))

    def toc(self):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus.tableofcontents import TableOfContents
        theme = self.theme
        contents = TableOfContents(dotsMinLevel=0)
        styles = []
        for level in range(base.TOC_LEVELS):
            styles.append(ParagraphStyle(
                f"Contents{level}", fontName=BOLD if level == 0 else FONT, fontSize=13, leading=19,
                leftIndent=18 * level, firstLineIndent=0,
                textColor=_color(theme.accent) if level == 0 and theme.name == "band" else _color("000000"),
                spaceBefore=3 if level == 0 else 0))
        contents.levelStyles = styles
        return contents

    # ---------- đầu, chân trang ----------
    def decorate(self, canvas, document, header: bool = True) -> None:
        theme = self.theme
        canvas.saveState()
        page = document.page
        if not header:
            pass
        elif theme.header == "title":
            canvas.setFont(ITALIC, 10)
            canvas.setFillColor(_color("333333"))
            canvas.drawRightString(PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 1.25 * CM, base.running_title(self.title))
        elif theme.header == "split":
            left, right = self.header_texts
            y = PAGE_HEIGHT - 1.3 * CM
            color = _color(GRAY) if theme.name == "band" else _color("333333")
            canvas.setFillColor(color)
            if theme.header_small_caps:
                left, right = left.upper(), right.upper()
                canvas.setFont(FONT, 8.5)
            else:
                canvas.setFont(FONT, 10)
            canvas.drawString(LEFT, y, left)
            if right:
                canvas.drawRightString(PAGE_WIDTH - RIGHT, y, right)
            canvas.setStrokeColor(_color("C9D3E0") if theme.name == "band" else _color("555555"))
            canvas.setLineWidth(0.6)
            canvas.line(LEFT, y - 5, PAGE_WIDTH - RIGHT, y - 5)
        canvas.setFillColor(_color("000000") if theme.footer != "trang-right" else _color(GRAY))
        if theme.footer == "number":
            canvas.setFont(FONT, 12)
            canvas.drawCentredString(LEFT + FRAME_WIDTH / 2, 1.1 * CM, str(page))
        elif theme.footer == "trang":
            canvas.setFont(FONT, 11)
            canvas.drawCentredString(LEFT + FRAME_WIDTH / 2, 1.1 * CM, f"Trang {page}")
        else:
            canvas.setFont(FONT, 10.5)
            canvas.drawRightString(PAGE_WIDTH - RIGHT, 1.1 * CM, f"Trang {page}")
        canvas.restoreState()

    @property
    def header_texts(self) -> tuple[str, str]:
        cover = getattr(self, "cover", None)
        left = ""
        if cover is not None:
            left = " · ".join(part for part in (cover.course, cover.group) if part) or cover.kind
        right = base.running_title(self.title) if left else ""
        return (left or base.running_title(self.title)), right

    # ---------- bìa ----------
    def cover_page(self, canvas, cover: Cover) -> None:
        self.cover = cover
        canvas.saveState()
        getattr(self, f"cover_{self.theme.cover}")(canvas, cover)
        canvas.restoreState()

    def stack(self, canvas, flowables: list, top: float, align: str = "center", indent: float = 0.0) -> float:
        """Vẽ lần lượt từ trên xuống bắt đầu ở ``top``; trả về chỗ dưới cùng đã vẽ."""
        y = top
        for flowable in flowables:
            y -= getattr(flowable, "spaceBefore", 0) or 0
            width, height = flowable.wrapOn(canvas, FRAME_WIDTH - indent, PAGE_HEIGHT)
            y -= height
            if align == "center" and not hasattr(flowable, "style"):
                x = LEFT + (FRAME_WIDTH - width) / 2
            else:
                x = LEFT + indent
            flowable.drawOn(canvas, x, y)
            y -= getattr(flowable, "spaceAfter", 0) or 0
        return y

    def measure(self, canvas, flowables: list, indent: float = 0.0) -> float:
        total = 0.0
        for flowable in flowables:
            _, height = flowable.wrapOn(canvas, FRAME_WIDTH - indent, PAGE_HEIGHT)
            total += height + (getattr(flowable, "spaceBefore", 0) or 0) + (getattr(flowable, "spaceAfter", 0) or 0)
        return total

    def place(self, canvas, top: list, middle: list, bottom: list, align: str, indent_bottom: float = 0.0,
              middle_at: float | None = None) -> None:
        upper = PAGE_HEIGHT - TOP - 0.3 * CM
        lower = BOTTOM + 0.4 * CM
        top_end = self.stack(canvas, top, upper, align)
        bottom_height = self.measure(canvas, bottom, indent_bottom)
        bottom_start = lower + bottom_height
        middle_height = self.measure(canvas, middle)
        if middle_at is not None:
            start = min(top_end - 0.5 * CM, PAGE_HEIGHT * middle_at)
        else:
            start = top_end - max(0.0, (top_end - bottom_start - middle_height) / 2)
        self.stack(canvas, middle, start, align)
        self.stack(canvas, bottom, bottom_start, "left" if indent_bottom else align, indent_bottom)

    def members(self, cover: Cover, kind: str, indent: float = 0.0):
        from reportlab.platypus import Table, TableStyle
        has_code = any(member.code for member in cover.members)
        has_note = any(member.note for member in cover.members)
        headers = ["STT", "Họ và tên"] + (["MSSV"] if has_code else []) + (["Ghi chú"] if has_note else [])
        widths = [1.5 * CM, 6.0 * CM] + ([3.0 * CM] if has_code else []) + ([3.2 * CM] if has_note else [])
        style = self.style("Member", fontSize=12 if kind != "band" else 11.5, leading=15, alignment=0)
        head = self.style("MemberHead", fontName=BOLD, fontSize=style.fontSize, leading=15, alignment=0,
                          textColor=_color(self.theme.accent) if kind == "band" else _color("000000"))
        rows = [[self.text(value, head) for value in headers]]
        for index, member in enumerate(cover.members):
            values = [str(index + 1), member.name] + ([member.code] if has_code else []) + ([member.note] if has_note else [])
            rows.append([self.text(value, style, alignment=1 if column == 0 else 0) for column, value in enumerate(values)])
        table = Table(rows, colWidths=widths)
        commands = [("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        if kind == "grid":
            commands += [("GRID", (0, 0), (-1, -1), 0.5, _color("000000")), ("BACKGROUND", (0, 0), (-1, 0), _color("F2F2F2"))]
        elif kind == "band":
            commands += [("BACKGROUND", (0, 0), (-1, 0), _color("E9EEF5")),
                         ("LINEBELOW", (0, 1), (-1, -1), 0.75, _color("D5DDE8"))]
        else:
            commands += [("LINEABOVE", (0, 0), (-1, 0), 1.2, _color("000000")),
                         ("LINEBELOW", (0, 0), (-1, 0), 0.6, _color("000000")),
                         ("LINEBELOW", (0, -1), (-1, -1), 1.2, _color("000000"))]
        table.setStyle(TableStyle(commands))
        return table

    def logo_flowable(self, cover: Cover, align: str = "CENTER"):
        from reportlab.platypus import Image
        image = self.images.get(cover.logo) if cover.logo else None
        if image is None:
            return None
        width, height = base.fit(image, 200, 92)
        picture = Image(BytesIO(image.data), width=width, height=height)
        picture.spaceBefore, picture.spaceAfter = 4, 4
        return picture

    def info(self, cover: Cover, indent: float) -> list:
        from reportlab.platypus import Spacer
        style = self.style("Info", fontSize=13, leading=17, alignment=0)
        lines = [self.text_rich(f"<b>Giảng viên hướng dẫn:</b> {escape(cover.instructor or DOTS)}", style)]
        for label, value in (("Nhóm thực hiện:", cover.group), ("Lớp:", cover.class_name)):
            if value:
                lines.append(self.text_rich(f"<b>{label}</b> {escape(value)}", style))
        if cover.members:
            lines.append(Spacer(1, 4))
            lines.append(self.members(cover, "grid"))
        elif not cover.group:
            lines.append(self.text_rich(f"<b>Sinh viên thực hiện:</b> {DOTS}", style))
        return lines

    def text_rich(self, markup: str, style):
        from reportlab.platypus import Paragraph
        return Paragraph(base.fallback(markup, self.body_glyphs, self.math_cmap, self.math_font), style)

    def cover_frame(self, canvas, cover: Cover) -> None:
        from reportlab.platypus import Spacer
        inset = 24
        canvas.setStrokeColor(_color("1A1A1A"))
        canvas.setLineWidth(2.6)
        canvas.rect(inset, inset, PAGE_WIDTH - 2 * inset, PAGE_HEIGHT - 2 * inset)
        canvas.setLineWidth(0.8)
        canvas.rect(inset + 4, inset + 4, PAGE_WIDTH - 2 * inset - 8, PAGE_HEIGHT - 2 * inset - 8)
        centered = lambda size, bold=False, italic=False, after=0, before=0, leading=None: self.style(  # noqa: E731
            "Cover", fontName=BOLD if bold else ITALIC if italic else FONT, fontSize=size,
            leading=leading or size * 1.3, spaceAfter=after, spaceBefore=before)
        top = []
        if cover.authority:
            top.append(self.text(cover.authority.upper(), centered(13)))
        top.append(self.text((cover.school or f"Trường {DOTS}").upper(), centered(14, True, before=2)))
        top.append(self.text((cover.faculty or f"Khoa {DOTS}").upper(), centered(13, True)))
        top.append(self.text("———  ◆  ———", centered(12, before=4, after=8)))
        logo = self.logo_flowable(cover)
        if logo is not None:
            top.append(logo)
        middle = [self.text((cover.kind or "Báo cáo").upper(), centered(21, True, after=4))]
        if cover.course:
            middle.append(self.text(f"MÔN: {cover.course.upper()}", centered(15, True, after=18)))
        if cover.topic:
            middle.append(self.text_rich("<u><b>ĐỀ TÀI</b></u>", centered(13, before=6, after=4)))
        middle.append(self.text((cover.topic or self.title).upper(), centered(17, True, after=2)))
        if cover.subtitle:
            middle.append(self.text(f"({cover.subtitle})", centered(13, italic=True)))
        bottom = self.info(cover, 2 * CM) + [Spacer(1, 22), self.text(cover.when(), centered(13, True))]
        self.place_frame(canvas, top, middle, bottom)

    def place_frame(self, canvas, top, middle, bottom) -> None:
        """Bìa Khung đôi: khối thông tin canh trái lùi 2 cm, riêng dòng nơi và thời gian ở giữa."""
        upper = PAGE_HEIGHT - TOP - 0.3 * CM
        lower = BOTTOM + 0.4 * CM
        top_end = self.stack(canvas, top, upper)
        info, when = bottom[:-2], bottom[-2:]
        height = self.measure(canvas, info, 2 * CM) + self.measure(canvas, when)
        start = lower + height
        y = self.stack(canvas, info, start, "left", 2 * CM)
        self.stack(canvas, when, y)
        middle_height = self.measure(canvas, middle)
        middle_start = top_end - max(0.0, (top_end - start - middle_height) / 2)
        self.stack(canvas, middle, middle_start)

    def cover_band(self, canvas, cover: Cover) -> None:
        from reportlab.platypus import Spacer, Table, TableStyle
        accent = _color(self.theme.accent)
        canvas.setFillColor(accent)
        canvas.rect(0, 0, 40, PAGE_HEIGHT, stroke=0, fill=1)
        left = lambda size, font=FONT, color="000000", after=0, before=0, leading=None: self.style(  # noqa: E731
            "Cover", fontName=font, fontSize=size, leading=leading or size * 1.3, alignment=0,
            textColor=_color(color), spaceAfter=after, spaceBefore=before)
        top = [self.text_rich(_spaced((cover.school or f"Trường {DOTS}").upper()),
                              left(10.5, BOLD, self.theme.accent)),
               self.text_rich(_spaced((cover.faculty or f"Khoa {DOTS}").upper()), left(10.5, FONT, self.theme.accent,
                                                                                     before=3))]
        logo = self.logo_flowable(cover)
        if logo is not None:
            logo.hAlign = "LEFT"
            top.append(logo)
        middle = [self.text_rich(_spaced((cover.kind or "Báo cáo").upper()), left(12, BOLD, self.theme.accent))]
        if cover.course:
            middle.append(self.text(f"Môn {cover.course}", left(14, FONT, "44546A", before=3)))
        middle.append(self.text(cover.topic or self.title, left(30, BOLD, self.theme.accent, before=14, leading=33)))
        if cover.subtitle:
            middle.append(self.text(cover.subtitle, left(14, FONT, "44546A", before=8)))
        middle.append(_Rule(3, self.theme.accent, width=5.3 * CM, before=14, after=16))
        pairs = [("Giảng viên hướng dẫn", cover.instructor or DOTS)]
        if cover.group:
            pairs.append(("Nhóm thực hiện", cover.group))
        if cover.class_name:
            pairs.append(("Lớp", cover.class_name))
        if not cover.members and not cover.group:
            pairs.append(("Sinh viên thực hiện", DOTS))
        label, value = left(12.5, FONT, GRAY), left(12.5, BOLD)
        info = Table([[self.text(name, label), self.text(text, value)] for name, text in pairs],
                     colWidths=[5 * CM, FRAME_WIDTH - 5 * CM])
        info.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        info.hAlign = "LEFT"
        middle.append(info)
        if cover.members:
            middle.append(Spacer(1, 10))
            members = self.members(cover, "band")
            members.hAlign = "LEFT"
            middle.append(members)
        bottom = [self.text(cover.when(), left(12, FONT, GRAY))]
        self.place(canvas, top, middle, bottom, "left", middle_at=0.66)

    def cover_rules(self, canvas, cover: Cover) -> None:
        from reportlab.platypus import Spacer
        centered = lambda size, font=FONT, after=0, before=0, leading=None: self.style(  # noqa: E731
            "Cover", fontName=font, fontSize=size, leading=leading or size * 1.3, spaceAfter=after, spaceBefore=before)
        top = [self.text_rich(_spaced((cover.school or f"Trường {DOTS}").upper(), 1.2), centered(12)),
               self.text(cover.faculty or f"Khoa {DOTS}", centered(13, ITALIC, before=3))]
        logo = self.logo_flowable(cover)
        if logo is not None:
            top.append(logo)
        kind = cover.kind or "Báo cáo"
        label = f"{kind} · {cover.course}" if cover.course else kind
        middle = [_Rule(0.75, "111111", before=0, after=16),
                  self.text_rich(_spaced(label.upper(), 0.8), centered(11.5)),
                  self.text(cover.topic or self.title, centered(25, before=8, leading=30))]
        if cover.subtitle:
            middle.append(self.text(cover.subtitle, centered(13, ITALIC, before=8)))
        middle.append(_Rule(0.75, "111111", before=16, after=0))
        bottom = [self.text(f"Giảng viên hướng dẫn: {cover.instructor or DOTS}", centered(13))]
        for extra in (cover.group, cover.class_name and f"Lớp {cover.class_name}"):
            if extra:
                bottom.append(self.text(extra, centered(13)))
        if cover.members:
            bottom.append(Spacer(1, 8))
            bottom.append(self.members(cover, "booktabs"))
        elif not cover.group:
            bottom.append(self.text(f"Sinh viên thực hiện: {DOTS}", centered(13)))
        bottom.append(Spacer(1, 24))
        bottom.append(self.text_rich(_spaced(cover.when().upper(), 0.8), centered(11.5)))
        self.place(canvas, top, middle, bottom, "center")


def _spaced(text: str, gap: float = 1.4) -> str:
    """Chữ in hoa thay cho chữ nhỏ in hoa (small caps) của bản Word, vì ReportLab không có kiểu đó."""
    del gap
    return escape(text)


class _Rule:
    """Đường kẻ ngang (dưới tên tài liệu, đề mục cấp 1 kiểu Dải màu, khối tên đề tài của bìa Tối giản)."""

    def __new__(cls, thickness: float, color: str, before: float = 0, after: float = 0, width: float | None = None,
                keep: bool = False):
        from reportlab.platypus import Flowable

        class Rule(Flowable):
            def wrap(self, available_width, available_height):
                self.length = width or available_width
                return self.length, thickness

            def draw(self):
                self.canv.saveState()
                self.canv.setStrokeColor(_color(color))
                self.canv.setLineWidth(thickness)
                self.canv.line(0, thickness / 2, self.length, thickness / 2)
                self.canv.restoreState()

        rule = Rule()
        rule.spaceBefore, rule.spaceAfter = before, after
        rule.keepWithNext = keep
        return rule


def _keep_with_next(document, flowables: list) -> None:
    """Gom các khối "giữ với khối sau" (đề mục, đường kẻ dưới đề mục, chú thích bảng dài) cùng khối kế tiếp vào một
    _KeepStart. Giống handle_keepWithNext của ReportLab, trừ hai chỗ. Khối kế tiếp được phép là một KeepTogether (bảng
    ngắn, ảnh, khung chừa ảnh): bản gốc không gom nó, nên đề mục nằm lại một mình cuối trang. Và nhóm chỉ sang trang khi
    không vừa phần đầu của khối đó."""
    from reportlab.platypus.doctemplate import _ktAllow
    from reportlab.platypus.flowables import KeepTogether

    count = 0
    while count < len(flowables) and flowables[count].getKeepWithNext() and _ktAllow(flowables[count]):
        count += 1
    if not count:
        return
    if count < len(flowables) and (_ktAllow(flowables[count]) or isinstance(flowables[count], KeepTogether)):
        count += 1
    group = _KeepStart(flowables[:count])
    # Như bản gốc: tắt cờ của các khối dẫn để khi nhóm trả lại chúng thì không gom lần nữa, và ghi lại để multiBuild
    # (mục lục cần dựng nhiều lượt) bật lại ở lượt sau.
    edits = getattr(document, "_multiBuildEdits", None)
    for flowable in group._content[:-1]:
        if edits:
            if hasattr(flowable, "keepWithNext"):
                edits((setattr, flowable, "keepWithNext", flowable.keepWithNext))
            else:
                edits((delattr, flowable, "keepWithNext"))
        flowable.__dict__["keepWithNext"] = 0
    del flowables[:count]
    flowables.insert(0, group)


class _KeepStart:
    """Giữ đề mục, chú thích với phần đầu của khối ngay sau, như "giữ với đoạn sau" của Word.

    KeepTogether của ReportLab đưa cả nhóm sang trang mới khi khối sau dài hơn chỗ còn lại, nên đề mục đứng trước một đoạn
    văn hay bảng dài để trống nửa trang phía trên. Ở đây nhóm chỉ sang trang khi chỗ còn lại không đủ cho các khối dẫn
    cộng phần đầu khối sau. Phần đầu do chính khối đó tự chia: đoạn văn cần ít nhất hai dòng, bảng cần hàng tiêu đề và
    một hàng. Khối không chia được (bảng ngắn, ảnh, công thức) thì cần trọn khối."""

    def __new__(cls, flowables: list):
        from reportlab.platypus.flowables import KeepTogether

        class KeepStart(KeepTogether):
            def split(self, available_width, available_height):
                content = self._content[:]
                frame = getattr(self, "_frame", None)
                if frame is None or getattr(frame, "_atTop", False) or _start_fits(
                        getattr(self, "canv", None), content, available_width, available_height,
                        bool(getattr(frame, "_oASpace", 0))):
                    return content
                return [self.FrameBreak(), *content]

        return KeepStart(flowables)


def _start_fits(canvas, content: list, width: float, height: float, overlap: bool) -> bool:
    """Chỗ cao ``height`` có đủ cho các khối dẫn và phần đầu của khối cuối không. Khoảng cách giữa hai khối tính như
    khung chữ: khoảng sau của khối trên chồng lên khoảng trước của khối dưới (``overlap``) hoặc cộng dồn."""
    from reportlab.platypus.flowables import KeepTogether

    *leads, last = content
    used, after = 0.0, None
    for flowable in leads:
        before = flowable.getSpaceBefore() if after is not None else 0.0  # khoảng trước khối đầu khung đã trừ sẵn
        used += _gap(before, after or 0.0, overlap) + flowable.wrapOn(canvas, width, height)[1]
        after = flowable.getSpaceAfter()
    if after is not None:
        used += _gap(last.getSpaceBefore(), after, overlap)
    rest = height - used - 1  # 1 pt dư cho sai số làm tròn
    if rest <= 0:
        return False
    if isinstance(last, KeepTogether):
        last.wrapOn(canvas, width, rest)
        return last._H <= rest
    if last.wrapOn(canvas, width, rest)[1] <= rest:
        return True
    return bool(last.splitOn(canvas, width, rest))


def _gap(before: float, after: float, overlap: bool) -> float:
    return max(before, after) if overlap else before + after


class _FullPage:
    """Chiếm trọn khung chữ trang đầu để luồng chữ bắt đầu từ trang hai (trang đầu là bìa vẽ ở onFirstPage)."""

    def __new__(cls):
        from reportlab.platypus import Flowable

        class FullPage(Flowable):
            def wrap(self, available_width, available_height):
                return available_width, available_height

            def draw(self):
                pass

        return FullPage()
