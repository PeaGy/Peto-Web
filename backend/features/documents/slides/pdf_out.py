"""Vẽ các Scene thành PDF 16:9 (bản xem trước và bản tải PDF) bằng ReportLab, cùng tọa độ với tệp PPTX.

Biểu đồ trong PPTX là biểu đồ gốc do PowerPoint tự vẽ; ở đây vẽ lại cùng số liệu, cùng thang chia và màu, nên gần giống chứ
không trùng từng điểm ảnh.
"""
from __future__ import annotations

from io import BytesIO
import math

from features.documents.slides import fonts
from features.documents.slides.fonts import SANS
from features.documents.slides.scene import H, W, Chart, Line, Para, Picture, Scene, Shape, Table, TextBox


def _color(value: str):
    from reportlab.lib.colors import HexColor
    return HexColor('#' + value)


def number(value: float) -> str:
    """Số kiểu Việt Nam: 1.234 và 12,5."""
    if abs(value - round(value)) < 1e-9:
        return f'{int(round(value)):,}'.replace(',', '.')
    text = f'{value:,.2f}'.rstrip('0').rstrip('.')
    return text.replace(',', ' ').replace('.', ',').replace(' ', '.')


def _lines(canvas, item: Para, x: float, width: float, top: float):
    """Vẽ các dòng đã ngắt của một đoạn; ``top`` tính từ mép trên slide."""
    name = fonts.font_name(item.family, item.bold, item.italic)
    drop = fonts.descent(item.family, item.size, item.bold)
    indent = item.bullet.indent if item.bullet else 0
    for index, text in enumerate(item.lines):
        baseline = H - (top + (index + 1) * item.line - drop)
        if index == 0 and item.bullet:
            mark = item.bullet
            canvas.setFillColor(_color(mark.color))
            canvas.setFont(fonts.font_name(SANS), item.size * mark.scale)
            canvas.drawString(x, baseline, mark.char)
        canvas.setFillColor(_color(item.color))
        canvas.setFont(name, item.size)
        used = fonts.width(text, item.family, item.size, item.bold, item.italic, item.spacing)
        left = x + indent
        if item.align == 'right':
            left = x + width - used
        elif item.align == 'center':
            left = x + indent + (width - indent - used) / 2
        canvas.drawString(left, baseline, text, charSpace=item.spacing)


def _text(canvas, box: TextBox):
    height = box.content_height
    top = box.y + {'top': 0, 'middle': (box.h - height) / 2, 'bottom': box.h - height}[box.anchor]
    for item in box.paras:
        _lines(canvas, item, box.x, box.w, top)
        top += item.height + item.after


def _shape(canvas, item: Shape):
    canvas.saveState()
    if item.fill:
        canvas.setFillColor(_color(item.fill))
    if item.line:
        canvas.setStrokeColor(_color(item.line))
        canvas.setLineWidth(item.line_width)
    y = H - item.y - item.h
    stroke, fill = int(bool(item.line)), int(bool(item.fill))
    if item.kind == 'rect':
        canvas.rect(item.x, y, item.w, item.h, stroke=stroke, fill=fill)
    elif item.kind == 'round':
        canvas.roundRect(item.x, y, item.w, item.h, item.radius, stroke=stroke, fill=fill)
    else:
        canvas.ellipse(item.x, y, item.x + item.w, y + item.h, stroke=stroke, fill=fill)
    canvas.restoreState()


def _line(canvas, item: Line):
    canvas.saveState()
    canvas.setStrokeColor(_color(item.color))
    canvas.setLineWidth(item.width)
    if item.dash:
        canvas.setLineCap(1)
        canvas.setDash([0.01, 2.6])
    canvas.line(item.x1, H - item.y1, item.x2, H - item.y2)
    canvas.restoreState()


def _picture(canvas, item: Picture):
    from reportlab.lib.utils import ImageReader
    canvas.drawImage(ImageReader(BytesIO(item.data)), item.x, H - item.y - item.h, item.w, item.h, mask='auto')
    if item.border:
        canvas.saveState()
        canvas.setStrokeColor(_color(item.border))
        canvas.setLineWidth(0.75)
        canvas.rect(item.x, H - item.y - item.h, item.w, item.h, stroke=1, fill=0)
        canvas.restoreState()


def _table(canvas, item: Table):
    y = item.y
    right = item.x + sum(item.widths)
    for r, row in enumerate(item.cells):
        height = item.heights[r]
        x = item.x
        for c, cell in enumerate(row):
            width = item.widths[c]
            if cell.fill:
                canvas.setFillColor(_color(cell.fill))
                canvas.rect(x, H - y - height, width, height, stroke=0, fill=1)
            _lines(canvas, cell.para, x + item.pad_x, width - 2 * item.pad_x, y + (height - cell.para.height) / 2)
            x += width
        rule = item.header_rule if r == 0 and item.header_rule else item.row_rule
        if rule:
            _line(canvas, Line(item.x, y + height, right, y + height, rule[0], rule[1]))
        y += height


def _label(canvas, text: str, x: float, y: float, size: float, color: str, align: str = 'center', bold=False):
    canvas.setFillColor(_color(color))
    canvas.setFont(fonts.font_name(SANS, bold), size)
    used = fonts.width(text, SANS, size, bold)
    left = x - used / 2 if align == 'center' else (x - used if align == 'right' else x)
    canvas.drawString(left, y, text)


def _fit_label(text: str, width: float, size: float) -> str:
    if fonts.width(text, SANS, size) <= width:
        return text
    while text and fonts.width(text + '…', SANS, size) > width:
        text = text[:-1]
    return text + '…'


def _legend(canvas, item: Chart, top: float) -> float:
    """Chú giải phía trên, căn giữa như PowerPoint; trả chiều cao đã dùng."""
    if len(item.series) < 2:
        return 0.0
    entries = [(name, item.colors[index]) for index, (name, _) in enumerate(item.series)]
    widths = [13 + fonts.width(name, SANS, 12) for name, _ in entries]
    total = sum(widths) + 18 * (len(entries) - 1)
    x = item.x + (item.w - total) / 2
    baseline = H - (top + 13)
    for (name, color), width in zip(entries, widths):
        canvas.setFillColor(_color(color))
        canvas.rect(x, baseline - 0.5, 8.5, 8.5, stroke=0, fill=1)
        _label(canvas, name, x + 13, baseline, 12, item.text, align='left')
        x += width + 18
    return 24.0


def _axis_chart(canvas, item: Chart):
    top = item.y + 4 + _legend(canvas, item, item.y)
    span = item.maximum - item.minimum or 1.0
    ticks = [item.minimum + index * item.step for index in range(int(round(span / item.step)) + 1)]
    horizontal = item.kind == 'bar'
    count = len(item.categories)
    if horizontal:
        label_width = min(item.w * 0.3, max(fonts.width(text, SANS, 12) for text in item.categories) + 10)
        left, right, bottom = item.x + label_width, item.x + item.w - 10, item.y + item.h - 20
        plot_top = top + 6
        scale = (right - left) / span
        for tick in ticks:
            x = left + (tick - item.minimum) * scale
            _line(canvas, Line(x, plot_top, x, bottom, item.grid, 0.75))
            _label(canvas, number(tick), x, H - (bottom + 15), 12, item.text)
        group = (bottom - plot_top) / count
        series = len(item.series)
        bar = group / (series + 0.7 + 0.12 * (series - 1))
        for index, category in enumerate(item.categories):
            start = plot_top + group * index + bar * 0.35
            _label(canvas, _fit_label(category, label_width - 10, 12), left - 8, H - (plot_top + group * (index + 0.5) + 4), 12,
                   item.text, align='right')
            for number_index, (_, values) in enumerate(item.series):
                value = values[index]
                y0 = start + number_index * bar * 1.12
                width = (value - item.minimum) * scale
                canvas.setFillColor(_color(item.colors[number_index]))
                canvas.rect(left, H - y0 - bar, width, bar, stroke=0, fill=1)
                if item.labels:
                    _label(canvas, number(value), left + width + 5, H - (y0 + bar / 2 + 4), 12, item.text, align='left')
        _line(canvas, Line(left, plot_top, left, bottom, item.grid, 0.75))
        return
    label_width = max(fonts.width(number(tick), SANS, 12) for tick in ticks) + 10
    left, right, bottom = item.x + label_width, item.x + item.w - 6, item.y + item.h - 22
    plot_top = top + (18 if item.labels else 8)
    scale = (bottom - plot_top) / span
    for tick in ticks:
        y = bottom - (tick - item.minimum) * scale
        _line(canvas, Line(left, y, right, y, item.grid, 0.75))
        _label(canvas, number(tick), left - 7, H - (y + 4), 12, item.text, align='right')
    group = (right - left) / count
    zero = bottom - (max(0.0, item.minimum) - item.minimum) * scale
    for index, category in enumerate(item.categories):
        _label(canvas, _fit_label(category, group - 4, 12), left + group * (index + 0.5), H - (bottom + 16), 12, item.text)
    if item.kind == 'column':
        series = len(item.series)
        bar = group / (series + 0.7 + 0.12 * (series - 1))
        for index in range(count):
            start = left + group * index + bar * 0.35
            for number_index, (_, values) in enumerate(item.series):
                value = values[index]
                x0 = start + number_index * bar * 1.12
                y = bottom - (value - item.minimum) * scale
                canvas.setFillColor(_color(item.colors[number_index]))
                canvas.rect(x0, H - zero, bar, zero - y, stroke=0, fill=1)
                if item.labels:
                    _label(canvas, number(value), x0 + bar / 2, H - (y - 6), 12, item.text)
        return
    for number_index, (_, values) in enumerate(item.series):
        points = [(left + group * (index + 0.5), bottom - (value - item.minimum) * scale) for index, value in enumerate(values)]
        canvas.saveState()
        canvas.setStrokeColor(_color(item.colors[number_index]))
        canvas.setFillColor(_color(item.colors[number_index]))
        canvas.setLineWidth(2.5)
        canvas.setLineJoin(1)
        path = canvas.beginPath()
        path.moveTo(points[0][0], H - points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, H - y)
        canvas.drawPath(path, stroke=1, fill=0)
        for x, y in points:
            canvas.circle(x, H - y, 3.5, stroke=0, fill=1)
        canvas.restoreState()


def _pie(canvas, item: Chart):
    values = item.series[0][1]
    total = sum(values) or 1.0
    legend_width = min(item.w * 0.35, max(fonts.width(text, SANS, 12) for text in item.categories) + 26)
    radius = min((item.w - legend_width - 30) / 2, item.h / 2 - 6)
    cx = item.x + (item.w - legend_width - 10) / 2
    cy = item.y + item.h / 2
    angle = 90.0
    canvas.saveState()
    canvas.setStrokeColor(_color('FFFFFF'))
    canvas.setLineWidth(1)
    for index, value in enumerate(values):
        extent = 360.0 * value / total
        canvas.setFillColor(_color(item.colors[index]))
        canvas.wedge(cx - radius, H - cy - radius, cx + radius, H - cy + radius, angle - extent, extent, stroke=1, fill=1)
        if value / total >= 0.04:
            middle = math.radians(angle - extent / 2)
            _label(canvas, f'{round(100 * value / total)}%', cx + math.cos(middle) * radius * 0.62,
                   H - (cy - math.sin(middle) * radius * 0.62) - 4, 12, 'FFFFFF', bold=True)
        angle -= extent
    canvas.restoreState()
    x = item.x + item.w - legend_width
    y = cy - (len(values) * 22) / 2
    for index, category in enumerate(item.categories):
        canvas.setFillColor(_color(item.colors[index]))
        canvas.rect(x, H - (y + 13), 9, 9, stroke=0, fill=1)
        _label(canvas, _fit_label(category, legend_width - 16, 12), x + 14, H - (y + 13), 12, item.text, align='left')
        y += 22


def _chart(canvas, item: Chart):
    if item.kind == 'pie':
        _pie(canvas, item)
    else:
        _axis_chart(canvas, item)


def render(scenes: list[Scene], title: str) -> bytes:
    from reportlab.pdfgen.canvas import Canvas
    fonts.register()
    output = BytesIO()
    canvas = Canvas(output, pagesize=(W, H), pageCompression=1)
    canvas.setTitle(title)
    canvas.setCreator('Peto')
    draw = {TextBox: _text, Shape: _shape, Line: _line, Picture: _picture, Table: _table, Chart: _chart}
    for scene in scenes:
        canvas.setFillColor(_color(scene.background))
        canvas.rect(0, 0, W, H, stroke=0, fill=1)
        for item in scene.items:
            draw[type(item)](canvas, item)
        canvas.showPage()
    canvas.save()
    return output.getvalue()
