"""Dàn trang 7 khuôn × 3 phong cách thành các hình có tọa độ (scene.py), theo trang mẫu chủ web chọn ngày 2026-10-04.

Chữ được ngắt dòng bằng số đo của phông thật (fonts.py) và tự thu nhỏ trong một khoảng cỡ chữ. Vẫn không vừa thì báo lỗi nói
rõ slide nào, để model rút gọn hoặc tách slide, thay vì để chữ tràn khung.
"""
from __future__ import annotations

import math
import re

from features.documents.export import DocImage
from features.documents.slides import fonts
from features.documents.slides.fonts import SANS, SERIF
from features.documents.slides.scene import H, W, Bullet, Cell, Chart, Line, Para, Picture, Scene, Shape, Table, TextBox
from features.documents.slides.spec import Deck, Slide
from features.documents.slides.themes import (BOLD_META, CORAL_LIGHT, GOLD, GOLD_LIGHT, MIST, RING, THEMES, ZEBRA, Theme,
                                              series_colors)

# Đo chữ ở 97% bề rộng khung: chừa chỗ cho sai khác nhỏ khi PowerPoint tự ngắt dòng.
SLACK = 0.97
WHITE = 'FFFFFF'
_NUMERIC = re.compile(r'^[\s(+\-−~≈<>≤≥]*[$€£¥₫]?\s*\d')


class SlideOverflow(ValueError):
    """Chữ không vừa khung kể cả khi đã thu nhỏ."""


def para(text: str, family: str, size: float, color: str, *, bold=False, italic=False, align='left', spacing=0.0,
         line=1.25, after=0.0, bullet: Bullet | None = None) -> Para:
    return Para(text=text, family=family, size=size, color=color, bold=bold, italic=italic, align=align, spacing=spacing,
                line=round(size * line, 2), after=after, bullet=bullet)


def wrapped(item: Para, width: float) -> Para:
    indent = item.bullet.indent if item.bullet else 0
    item.lines = fonts.wrap(item.text, item.family, item.size, (width - indent) * SLACK, item.bold, item.italic,
                            item.spacing)
    return item


def stack_height(paras: list[Para]) -> float:
    return sum(item.height + item.after for item in paras) - (paras[-1].after if paras else 0)


def one_line(text: str, family: str, size: float, width: float, bold=False) -> str:
    """Rút gọn còn một dòng (chân trang, chú thích ngắn)."""
    if fonts.width(text, family, size, bold) <= width * SLACK:
        return text
    while text and fonts.width(text + '…', family, size, bold) > width * SLACK:
        text = text[:-1]
    return text.rstrip() + '…'


def nice_axis(low: float, high: float) -> tuple[float, float, float]:
    """Thang chia đẹp (bước 1, 2, 2,5 hay 5 × 10ⁿ, khoảng 4–5 vạch), gốc 0 khi mọi số không âm."""
    low = min(0.0, low)
    span = (high - low) or abs(high) or 1.0
    raw = span / 5
    power = 10 ** math.floor(math.log10(raw))
    step = next(multiple * power for multiple in (1, 2, 2.5, 5, 10) if multiple * power >= raw)
    return math.floor(low / step) * step, math.ceil(high / step) * step or step, step


class Builder:
    def __init__(self, deck: Deck, images: dict[int, DocImage]):
        self.deck = deck
        self.theme: Theme = THEMES[deck.theme]
        self.images = images
        self.figures = 0
        self.tables = 0
        self.index = 0
        self.slide: Slide | None = None

    # ---------- chung ----------
    def fail(self, what: str = 'Chữ'):
        raise SlideOverflow(f'Slide {self.index} ({self.slide.layout}): {what} quá dài so với khung, kể cả khi đã thu nhỏ. '
                            'Rút gọn hoặc tách thành hai slide rồi gọi lại.')

    def fit(self, make, width: float, height: float, sizes, max_lines: int | None = None) -> list[Para]:
        """``make(size)`` trả các đoạn chưa ngắt; dùng cỡ lớn nhất vừa khung."""
        for size in sizes:
            paras = [wrapped(item, width) for item in make(size)]
            if stack_height(paras) <= height + 0.5 and (max_lines is None or sum(len(p.lines) for p in paras) <= max_lines):
                return paras
        self.fail()

    def bullet_paras(self, items: list[str], size: float, color: str, after: float) -> list[Para]:
        theme = self.theme
        mark = {'clean': Bullet('■', theme.accent, 0.6, round(size * 1.15, 1)),
                'academic': Bullet('–', theme.accent, 1.0, round(size * 1.1, 1)),
                'bold': Bullet('●', theme.accent, 0.7, round(size * 1.15, 1))}[theme.name]
        return [para(text, SANS, size, color, line=1.3, after=after, bullet=mark) for text in items]

    def bullets(self, items: list[str], x: float, y: float, width: float, height: float, base: float, color: str | None = None,
                after_ratio: float = 0.55) -> TextBox:
        paras = self.fit(lambda size: self.bullet_paras(items, size, color or self.theme.ink, round(size * after_ratio, 1)),
                         width, height, range(int(base), int(base) - 6, -1))
        return TextBox(x, y, width, stack_height(paras), paras)

    def number_box(self, x: float, y: float, w: float, size: float, color: str, align='right', bold=False) -> TextBox:
        item = para(str(self.index), SANS, size, color, bold=bold, align=align, line=1.2)
        item.lines = [item.text]
        return TextBox(x, y, w, item.height, [item], slide_number=True)

    def caption(self, text: str, x: float, y: float, width: float, *, italic=False, size=12.0, lines=2) -> TextBox:
        item = wrapped(para(text, SANS, size, self.theme.muted, italic=italic, line=1.3), width)
        item.lines = item.lines[:lines]
        return TextBox(x, y, width, item.height, [item])

    # ---------- tiêu đề ----------
    def heading(self, items: list) -> tuple[float, float, float, float]:
        """Vẽ tiêu đề theo phong cách; trả vùng nội dung còn lại (x, y, rộng, đáy)."""
        theme, slide = self.theme, self.slide
        if theme.name == 'clean':
            x, top, width = 62.0, 50.0, W - 124
            paras = self.fit(lambda size: [para(slide.title, SANS, size, theme.ink, bold=True, line=1.12)],
                             width - 40, 90, range(34, 25, -1), max_lines=2)
            box = TextBox(x, top, width - 40, stack_height(paras), paras, title=True)
            rule = top + box.h + 12
            items += [box, Shape('rect', x, rule, 38, 4, fill=theme.accent),
                      self.number_box(W - 31 - 80, H - 25 - 13, 80, 11, theme.muted)]
            return x, rule + 28, width, H - 48
        if theme.name == 'academic':
            x, y, width = 58.0, 44.0, W - 116
            if slide.section:
                label = para(one_line(slide.section.upper(), SANS, 12.5, width, True), SANS, 12.5, GOLD, bold=True,
                             spacing=1.0, line=1.25)
                label.lines = [label.text]
                items.append(TextBox(x, y, width, label.height, [label]))
                y += label.height + 5
            paras = self.fit(lambda size: [para(slide.title, SERIF, size, theme.accent, bold=True, line=1.15)],
                             width, 80, range(31, 23, -1), max_lines=2)
            box = TextBox(x, y, width, stack_height(paras), paras, title=True)
            items.append(box)
            footer = H - 38
            title = para(one_line(self.deck.title, SANS, 10.5, width * 0.7), SANS, 10.5, theme.muted, line=1.2)
            title.lines = [title.text]
            items += [Line(x, footer, x + width, footer, theme.accent, 0.75),
                      TextBox(x, footer + 6, width * 0.7, title.height, [title]),
                      self.number_box(x + width - 80, footer + 6, 80, 10.5, theme.muted)]
            return x, y + box.h + 20, width, footer - 14
        # bold: dải tiêu đề tối
        band = 96.0
        items.append(Shape('rect', 0, 0, W, band, fill=theme.ink))
        paras = self.fit(lambda size: [para(slide.title, SANS, size, WHITE, bold=True, line=1.1)],
                         W - 124 - 70, band - 30, range(31, 21, -1), max_lines=2)
        height = stack_height(paras)
        items += [TextBox(62, (band - height) / 2, W - 124 - 70, height, paras, title=True),
                  self.number_box(W - 62 - 60, (band - 20.4) / 2, 60, 17, theme.accent, bold=True)]
        return 62.0, band + 34, W - 124, H - 40

    # ---------- khuôn ----------
    def cover(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        kicker = slide.subtitle.upper()
        if theme.name == 'clean':
            x, width = 72.0, (W - 72 - 62) * 0.8
            items.append(Shape('rect', 0, 0, 10.5, H, fill=theme.accent))
            blocks = []
            if kicker:
                label = wrapped(para(kicker, SANS, 13.5, theme.accent, bold=True, spacing=1.6, line=1.3), width)
                blocks.append((label, 10))
            title = self.fit(lambda size: [para(slide.title, SANS, size, theme.ink, bold=True, line=1.08)],
                             width, 4 * 58, range(54, 37, -2), max_lines=3)[0]
            narrow = fonts.balanced(slide.title, SANS, title.size, width * SLACK, True) / SLACK
            wrapped(title, narrow)
            blocks.append((title, 14))
            meta = [wrapped(para(line, SANS, 16, theme.muted, line=1.35), width) for line in slide.meta.split('\n') if line]
            total = sum(item.height + gap for item, gap in blocks) + 5 + 26 + sum(item.height for item in meta)
            y = (H - total) / 2
            for item, gap in blocks:
                items.append(TextBox(x, y, narrow if item is title else width, item.height, [item], title=item is title))
                y += item.height + gap
            items.append(Shape('rect', x, y, 67, 5, fill=theme.accent))
            y += 5 + 26
            if meta:
                items.append(TextBox(x, y, width, stack_height(meta), meta))
            return
        if theme.name == 'academic':
            band, x, width = 324.0, 58.0, W - 116
            items += [Shape('rect', 0, 0, W, band, fill=theme.accent), Shape('rect', 0, band, W, 4.3, fill=GOLD)]
            title = self.fit(lambda size: [para(slide.title, SERIF, size, WHITE, bold=True, line=1.12)],
                             width, 3 * 52, range(46, 33, -2), max_lines=3)[0]
            narrow = fonts.balanced(slide.title, SERIF, title.size, width * SLACK, True) / SLACK
            wrapped(title, narrow)
            bottom = band - 33
            items.append(TextBox(x, bottom - title.height, narrow, title.height, [title], title=True))
            if kicker:
                label = wrapped(para(kicker, SANS, 13.5, GOLD_LIGHT, spacing=1.0, line=1.3), width)
                items.append(TextBox(x, bottom - title.height - 8 - label.height, width, label.height, [label]))
            lines = [line for line in slide.meta.split('\n') if line]
            meta = [wrapped(para(lines[0], SANS, 17.5, theme.ink, bold=True, line=1.35), width)] if lines else []
            meta += [wrapped(para(line, SANS, 15.5, theme.muted, line=1.4), width) for line in lines[1:]]
            if meta:
                height = stack_height(meta)
                items.append(TextBox(x, band + 4.3 + (H - band - 4.3 - height) / 2, width, height, meta))
            return
        # bold: nền tối, hình tròn cam
        scene.background = theme.ink
        items += [Shape('ellipse', W - 442 + 115, -96, 442, 442, fill=theme.accent),
                  Shape('ellipse', W - 211 - 173, H + 86 - 173, 173, 173, line=RING, line_width=11.5)]
        x, width, y = 62.0, W * 0.62, 58.0
        if kicker:
            label = wrapped(para(kicker, SANS, 14.5, CORAL_LIGHT, bold=True, spacing=1.5, line=1.3), width)
            items.append(TextBox(x, y, width, label.height, [label]))
            y += label.height + 10
        title = self.fit(lambda size: [para(slide.title, SANS, size, WHITE, bold=True, line=1.04)],
                         width, 4 * 61, range(58, 39, -2), max_lines=3)[0]
        narrow = fonts.balanced(slide.title, SANS, title.size, width * SLACK, True) / SLACK
        wrapped(title, narrow)
        items.append(TextBox(x, y, narrow, title.height, [title], title=True))
        meta = [wrapped(para(line, SANS, 16, BOLD_META, line=1.35), width) for line in slide.meta.split('\n') if line]
        if meta:
            height = stack_height(meta)
            items.append(TextBox(x, H - 48 - height, width, height, meta))

    def agenda(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        if theme.name == 'bold':
            panel = W * 0.36
            items.append(Shape('rect', 0, 0, panel, H, fill=theme.ink))
            title = self.fit(lambda size: [para(slide.title, SANS, size, WHITE, bold=True, line=1.1)],
                             panel - 86, 200, range(38, 25, -2), max_lines=4)
            items += [TextBox(43, 58, panel - 86, stack_height(title), title, title=True),
                      self.number_box(43, H - 58 - 20.4, 80, 17, theme.accent, align='left', bold=True)]
            x, width = panel + 48, W - panel - 96
            for size in range(21, 15, -1):
                rows = [wrapped(para(text, SANS, size, theme.ink, bold=True, line=1.3), width - 44) for text in slide.bullets]
                gap = round(size * 0.72, 1)
                total = sum(row.height for row in rows) + gap * (len(rows) - 1)
                if total <= H - 110:
                    break
            else:
                self.fail()
            y = (H - total) / 2
            for number, row in enumerate(rows, start=1):
                mark = para(str(number), SANS, round(size * 1.3, 1), theme.accent, bold=True, line=1.0)
                mark.lines = [mark.text]
                items += [TextBox(x, y + (row.line - mark.height) / 2, 40, mark.height, [mark]),
                          TextBox(x + 44, y, width - 44, row.height, [row])]
                y += row.height + gap
            return
        x, top, width, bottom = self.heading(items)
        academic = theme.name == 'academic'
        if academic:
            width *= 0.78
        lead = 36 if academic else 50
        pad = 8 if academic else 10.5
        for size in range(21, 15, -1):
            rows = [wrapped(para(text, SANS, size, theme.ink, line=1.3), width - lead) for text in slide.bullets]
            total = sum(row.height + 2 * pad for row in rows)
            if total <= bottom - top + 8:
                break
        else:
            self.fail()
        y = top - pad
        for number, row in enumerate(rows, start=1):
            label = f'{number}.' if academic else f'{number:02d}'
            mark = para(label, SERIF if academic else SANS, row.size, GOLD if academic else theme.accent, bold=True, line=1.3)
            mark.lines = [label]
            items += [TextBox(x, y + pad, lead, mark.height, [mark]), TextBox(x + lead, y + pad, width - lead, row.height, [row])]
            y += row.height + 2 * pad
            items.append(Line(x, y, x + width, y, theme.hair, 0.75, dash=academic))

    def bullets_slide(self, scene: Scene):
        x, top, width, bottom = self.heading(scene.items)
        base = 21 if self.theme.name == 'bold' else 20
        scene.items.append(self.bullets(self.slide.bullets, x, top, width, bottom - top, base,
                                        after_ratio=0.62 if self.theme.name == 'bold' else 0.55))

    def two_columns(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        x, top, width, bottom = self.heading(items)
        sides = ((slide.left_title, slide.left_bullets), (slide.right_title, slide.right_bullets))
        if theme.name == 'bold':
            gap, pad_x, pad_y = 23.0, 27.0, 25.0
            card = (width - gap) / 2
            inner = card - 2 * pad_x
            titles = [wrapped(para(name.upper(), SANS, 15, theme.accent, bold=True, spacing=1.2, line=1.3), inner) for name, _ in sides]
            room = bottom - top - 2 * pad_y - max(t.height for t in titles) - 10
            size = next((size for size in range(20, 14, -1) if all(
                stack_height([wrapped(p, inner) for p in self.bullet_paras(points, size, theme.ink, round(size * 0.55, 1))]) <= room
                for _, points in sides)), None)
            if size is None:
                self.fail()
            columns = [[wrapped(p, inner) for p in self.bullet_paras(points, size, theme.ink if i == 0 else WHITE, round(size * 0.55, 1))]
                       for i, (_, points) in enumerate(sides)]
            height = max(t.height + 10 + stack_height(c) for t, c in zip(titles, columns)) + 2 * pad_y
            for i, (label, column) in enumerate(zip(titles, columns)):
                left = x + i * (card + gap)
                items += [Shape('round', left, top, card, height, fill=MIST if i == 0 else theme.ink, radius=11.5),
                          TextBox(left + pad_x, top + pad_y, inner, label.height, [label]),
                          TextBox(left + pad_x, top + pad_y + label.height + 10, inner, stack_height(column), column)]
            return
        academic = theme.name == 'academic'
        gap = 35.0 if academic else 33.0
        column_width = (width - gap - (0 if academic else gap + 1)) / 2 if not academic else (width - gap) / 2
        if academic:
            titles = [wrapped(para(name, SERIF, 18, theme.accent, bold=True, line=1.25), column_width) for name, _ in sides]
            lead = 3.4 + 7
        else:
            titles = [wrapped(para(name.upper(), SANS, 14, theme.accent, bold=True, spacing=1.4, line=1.3), column_width)
                      for name, _ in sides]
            lead = 0.0
        head = lead + max(t.height for t in titles) + 12
        room = bottom - top - head
        size = next((size for size in range(20, 14, -1) if all(
            stack_height([wrapped(p, column_width) for p in self.bullet_paras(points, size, theme.ink, round(size * 0.55, 1))]) <= room
            for _, points in sides)), None)
        if size is None:
            self.fail()
        heights = []
        for i, ((_, points), label) in enumerate(zip(sides, titles)):
            left = x + i * (column_width + (gap if academic else 2 * gap + 1))
            column = [wrapped(p, column_width) for p in self.bullet_paras(points, size, theme.ink, round(size * 0.55, 1))]
            if academic:
                items.append(Shape('rect', left, top, column_width, 3.4, fill=theme.accent))
            items += [TextBox(left, top + lead, column_width, label.height, [label]),
                      TextBox(left, top + head, column_width, stack_height(column), column)]
            heights.append(head + stack_height(column))
        if not academic:
            middle = x + column_width + gap
            items.append(Line(middle, top, middle, top + max(heights), theme.hair, 0.75))

    def picture(self, number: int, x: float, y: float, width: float, height: float, *, border: str | None) -> Picture:
        image = self.images.get(number)
        if not image:
            raise ValueError(f'Slide {self.index}: không dùng được Ảnh {number}.')
        scale = min(width / image.width, height / image.height)
        return Picture(x, y, image.width * scale, image.height * scale, image.data, border)

    def image_text(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        if theme.name == 'bold':
            half = W / 2
            items.append(Shape('rect', 0, 0, half, H, fill=MIST))
            caption = self.caption(slide.caption, 29, 0, half - 58) if slide.caption else None
            room = H - 58 - ((caption.h + 8) if caption else 0)
            image = self.picture(slide.image, 29, 29, half - 58, room, border=None)
            block = image.h + ((caption.h + 8) if caption else 0)
            image.y = (H - block) / 2
            image.x = 29 + (half - 58 - image.w) / 2
            items.append(image)
            if caption:
                caption.x, caption.y, caption.w = image.x, image.y + image.h + 8, image.w
                items.append(caption)
            x, width = half + 44, half - 88
            items.append(self.number_box(x, 48, 80, 15, theme.accent, align='left', bold=True))
            title = self.fit(lambda size: [para(slide.title, SANS, size, theme.ink, bold=True, line=1.1)],
                             width, 130, range(31, 21, -1), max_lines=3)
            height = stack_height(title)
            items.append(TextBox(x, 48 + 26, width, height, title, title=True))
            top = 48 + 26 + height + 22
            items.append(self.bullets(slide.bullets, x, top, width, H - 40 - top, 21))
            return
        x, top, width, bottom = self.heading(items)
        academic = theme.name == 'academic'
        gap = 34.0
        image_width = width * (0.52 if academic else 0.54)
        text_width = width - image_width - gap
        image_x = x + text_width + gap if academic else x
        text_x = x if academic else x + image_width + gap
        if academic:
            self.figures += 1
            label = f'Hình {self.figures}. {slide.caption}' if slide.caption else f'Hình {self.figures}.'
        else:
            label = slide.caption
        caption = self.caption(label, image_x, 0, image_width, italic=academic, size=12.5 if academic else 12) if label else None
        room = bottom - top - ((caption.h + 8) if caption else 0)
        image = self.picture(slide.image, image_x, top, image_width, room, border=theme.hair)
        items.append(image)
        if caption:
            caption.y, caption.w = top + image.h + 8, max(image.w, 120)
            items.append(caption)
        items.append(self.bullets(slide.bullets, text_x, top, text_width, bottom - top, 20))

    def table(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        x, top, width, bottom = self.heading(items)
        academic, bold = theme.name == 'academic', theme.name == 'bold'
        caption_top = None
        if academic:
            self.tables += 1
            text = f'Bảng {self.tables}. {slide.caption}' if slide.caption else ''
            if text:
                caption_top = self.caption(text, x, top, width, italic=True, size=12.5, lines=1)
                items.append(caption_top)
                top += caption_top.h + 8
        caption_below = self.caption(slide.caption, x, 0, width) if slide.caption and not academic else None
        room = bottom - top - ((caption_below.h + 10) if caption_below else 0)
        numeric = [all(_NUMERIC.match(row[i]) and len(row[i]) <= 24 for row in slide.rows) for i in range(len(slide.columns))]
        pad_x, pad_y = 10.0, 6.0 if academic else 7.0
        header_color = theme.accent if theme.name == 'clean' else WHITE
        for size in range(18, 12, -1):
            head_size = 13.0 if theme.name == 'clean' else min(15.0, size - 2)

            def head(text, i):
                label = text.upper() if theme.name == 'clean' else text
                return para(label, SANS, head_size, header_color, bold=True, spacing=0.6 if theme.name == 'clean' else 0,
                            align='right' if numeric[i] else 'left', line=1.25)

            def body(text, i):
                hot = bold and i == len(slide.columns) - 1 and numeric[i]
                return para(text, SANS, size, theme.accent if hot else theme.ink, bold=hot,
                            align='right' if numeric[i] else 'left', line=1.25)

            grid = [[head(text, i) for i, text in enumerate(slide.columns)]] + \
                   [[body(text, i) for i, text in enumerate(row)] for row in slide.rows]
            natural = [max(fonts.width(row[i].text, SANS, row[i].size, row[i].bold, spacing=row[i].spacing) for row in grid)
                       / SLACK + 2 * pad_x + 2 for i in range(len(slide.columns))]
            total = sum(natural)
            if total <= width:
                widths = [value + (width - total) * value / total for value in natural]
            else:
                widths = [max(70.0, value * width / total) for value in natural]
                widths = [value * width / sum(widths) for value in widths]
            heights = []
            for row in grid:
                for i, cell in enumerate(row):
                    wrapped(cell, widths[i] - 2 * pad_x)
                heights.append(max(cell.height for cell in row) + 2 * pad_y)
            if sum(heights) <= room:
                break
        else:
            self.fail('Bảng')
        cells = []
        for r, row in enumerate(grid):
            fill = None
            if r == 0 and theme.name != 'clean':
                fill = theme.accent if academic else theme.ink
            elif academic and r % 2 == 0:
                fill = ZEBRA
            cells.append([Cell(cell, fill) for cell in row])
        items.append(Table(x, top, widths, heights, cells, pad_x, pad_y,
                           header_rule=(theme.accent, 3.0) if theme.name == 'clean' else None,
                           row_rule=(theme.hair, 0.75)))
        if caption_below:
            caption_below.y = top + sum(heights) + 10
            items.append(caption_below)

    def chart(self, scene: Scene):
        theme, slide, items = self.theme, self.slide, scene.items
        x, top, width, bottom = self.heading(items)
        academic = theme.name == 'academic'
        if academic:
            self.figures += 1
            label = f'Hình {self.figures}. {slide.caption}' if slide.caption else ''
        else:
            label = slide.caption
        caption = self.caption(label, x, 0, width, italic=academic, size=12.5 if academic else 12, lines=1) if label else None
        if slide.unit:
            unit = para(f'Đơn vị: {slide.unit}', SANS, 11.5, theme.muted, line=1.2)
            unit.lines = [unit.text]
            items.append(TextBox(x, top - 4, width / 2, unit.height, [unit]))
            top += unit.height
        height = bottom - top - ((caption.h + 8) if caption else 0)
        if height < 150:
            self.fail('Biểu đồ')
        series = [(item.name, item.values) for item in slide.series]
        values = [value for _, data in series for value in data]
        if slide.chart_type == 'pie':
            colors = [theme.pie[i % len(theme.pie)] for i in range(len(slide.categories))]
            minimum = maximum = step = 0.0
        else:
            colors = series_colors(theme, len(series))
            minimum, maximum, step = nice_axis(min(values), max(values))
        items.append(Chart(x, top, width, height, slide.chart_type, slide.categories, series, colors, SANS, theme.muted,
                           theme.grid, minimum, maximum, step, labels=len(series) == 1 and slide.chart_type in ('column', 'bar')))
        if caption:
            caption.y = top + height + 8
            items.append(caption)

    def build(self) -> list[Scene]:
        scenes = []
        for index, slide in enumerate(self.deck.slides, start=1):
            self.index, self.slide = index, slide
            scene = Scene(background=WHITE, notes=slide.notes)
            {'cover': self.cover, 'agenda': self.agenda, 'bullets': self.bullets_slide, 'two_columns': self.two_columns,
             'image_text': self.image_text, 'table': self.table, 'chart': self.chart}[slide.layout](scene)
            scenes.append(scene)
        return scenes


def build(deck: Deck, images: dict[int, DocImage] | None = None) -> list[Scene]:
    return Builder(deck, images or {}).build()
