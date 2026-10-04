"""Cách bảng tính hiện ra, dùng chung cho tệp XLSX và lưới xem trong chat: định dạng số kiểu Việt Nam, mã định dạng Excel,
độ rộng cột, vị trí và số liệu biểu đồ.

Tệp XLSX ghi mã định dạng (#,##0 "₫"); Excel trên máy cài tiếng Việt hiện 1.500.000 ₫, máy cài tiếng Anh hiện
1,500,000 ₫. Lưới xem luôn hiện kiểu Việt Nam.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from features.documents.sheets import engine
from features.documents.sheets.formula import address, column_index
from features.documents.sheets.spec import Column, Prepared

CHART_WIDTH, CHART_HEIGHT = 480, 288      # cỡ mặc định của biểu đồ Excel, điểm ảnh
CHART_ROWS = 16                            # số hàng một biểu đồ chiếm (cao 288 px, hàng 20 px) cộng một hàng cách
MAX_WIDTH, MIN_WIDTH, HEADER_WIDTH = 50.0, 6.0, 18.0
ACCENT = '0F766E'
SERIES = ('0F766E', 'E09F3E', '4F86C6', '9A6FB0')
PIE = (('0F766E', 'FFFFFF'), ('2A9D8F', 'FFFFFF'), ('5FA8A0', 'FFFFFF'), ('9CC9C2', '1F2D33'), ('C9D3DA', '1F2D33'),
       ('E09F3E', '1F2D33'), ('F2C14E', '1F2D33'), ('4F86C6', 'FFFFFF'), ('9A6FB0', 'FFFFFF'), ('D1495B', 'FFFFFF'))


def group(digits: str) -> str:
    out = []
    while len(digits) > 3:
        out.insert(0, digits[-3:])
        digits = digits[:-3]
    out.insert(0, digits)
    return '.'.join(out)


def format_number(value: float, decimals: int, grouping: bool = True) -> str:
    """Số kiểu Việt Nam: 1.234.567,5. Làm tròn nửa lên ở 15 chữ số có nghĩa, như Excel hiển thị."""
    number = Decimal(f'{value:.15g}').quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    sign = '-' if number < 0 else ''
    whole, _, fraction = f'{abs(number):f}'.partition('.')
    whole = group(whole) if grouping else whole
    return sign + whole + (',' + fraction if decimals > 0 else '')


def general(value: float) -> str:
    return engine.general(value).replace('.', ',')


def number_format(column: Column, decimals: int) -> str | None:
    fraction = ('.' + '0' * decimals) if decimals else ''
    return {
        'number': f'#,##0{fraction}', 'percent': f'0{fraction}%', 'vnd': f'#,##0{fraction} "₫"',
        'usd': f'"$"#,##0{fraction}', 'date': 'dd/mm/yyyy', 'text': None,
    }[column.format]


@dataclass
class ColumnView:
    header: str
    format: str
    decimals: int
    code: str | None
    width: float = MIN_WIDTH       # đơn vị của Excel: bề rộng một chữ số 0
    wrap: bool = False

    @property
    def pixels(self) -> int:
        return round(self.width * 7 + 5)


def display(value, view: ColumnView) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, str):
        return value
    if isinstance(value, engine.XLError):
        return value.code
    kind = view.format
    if kind == 'number':
        return format_number(value, view.decimals)
    if kind == 'percent':
        return format_number(value * 100, view.decimals) + '%'
    if kind == 'vnd':
        return format_number(value, view.decimals) + ' ₫'
    if kind == 'usd':
        text = format_number(abs(value), view.decimals)
        return ('-$' if value < 0 and text.strip('0,.') else '$') + text
    if kind == 'date' and engine.MIN_SERIAL <= value <= engine.MAX_SERIAL:
        day = engine.EPOCH + timedelta(days=int(value))
        return f'{day.day:02d}/{day.month:02d}/{day.year}'
    return general(value)


def _needed(value: float) -> int:
    for decimals in range(3):
        if abs(round(value, decimals) - value) <= 1e-9 * max(1.0, abs(value)):
            return decimals
    return 2


def _decimals(column: Column, numbers: list[float]) -> int:
    if column.decimals is not None:
        return column.decimals
    if column.format in ('vnd', 'date', 'text'):
        return 0
    if column.format == 'usd':
        return 2
    scale = 100 if column.format == 'percent' else 1
    return max((_needed(engine.round15(value * scale)) for value in numbers), default=0)


def column_views(prepared: Prepared, s: int) -> list[ColumnView]:
    sheet = prepared.book.sheets[s]
    rows = prepared.rows(s)
    views = []
    for c, column in enumerate(sheet.columns):
        values = [prepared.value(s, r, c) for r in range(1, rows)]
        numbers = [value for value in values if engine.is_number(value)]
        decimals = _decimals(column, numbers)
        view = ColumnView(column.header, column.format, decimals, number_format(column, decimals))
        content = max((len(display(value, view)) for value in values), default=0) + 2
        # Tên cột in đậm cộng chỗ cho nút lọc (khoảng hai chữ số).
        header = min(len(column.header) * 1.15 + 4.5, HEADER_WIDTH)
        width = max(MIN_WIDTH, content, header)
        if width > MAX_WIDTH:
            width, view.wrap = MAX_WIDTH, True
        view.width = round(width, 1)
        views.append(view)
    return views


@dataclass
class ChartView:
    type: str
    title: str
    row: int
    col: int
    category_col: int
    value_cols: list[int]
    categories: list[str]
    series: list[tuple[str, list[float | None], list[str]]]
    axis: tuple[float, float, float] | None
    code: str | None
    view: ColumnView


def nice_axis(values: list[float]) -> tuple[float, float, float]:
    """Thang chia gọn (bước 1, 2, 2,5 hay 5 × 10ⁿ), gốc 0, chừa chỗ cho nhãn số trên cột cao nhất."""
    low, high = min(0.0, min(values)), max(0.0, max(values))
    span = (high - low) or abs(high) or 1.0
    high_room = high + span * 0.08 if high > 0 else high
    low_room = low - span * 0.08 if low < 0 else low
    raw = ((high_room - low_room) or 1.0) / 5
    power = 10 ** math.floor(math.log10(raw))
    step = next(multiple * power for multiple in (1, 2, 2.5, 5, 10) if multiple * power >= raw)
    if all(float(value).is_integer() for value in values) and step < 1:
        step = 1.0
    bottom = math.floor(low_room / step) * step
    top = math.ceil(high_room / step) * step or step
    return bottom, top, step


def chart_views(prepared: Prepared, s: int, views: list[ColumnView]) -> list[ChartView]:
    sheet = prepared.book.sheets[s]
    data_rows = len(sheet.rows)
    out = []
    for index, chart in enumerate(sheet.charts):
        if len(sheet.columns) <= 8:
            row, col = 1 + index * CHART_ROWS, len(sheet.columns) + 1
        else:
            row, col = prepared.rows(s) + 2 + index * CHART_ROWS, 0
        category = column_index(chart.category)
        cols = [column_index(letter) for letter in chart.values]
        categories = [display(prepared.value(s, r, category), views[category]) for r in range(1, data_rows + 1)]
        series = []
        for col_index in cols:
            values = [prepared.value(s, r, col_index) for r in range(1, data_rows + 1)]
            numbers = [value if engine.is_number(value) else None for value in values]
            series.append((sheet.columns[col_index].header, numbers,
                           [display(value, views[col_index]) if value is not None else '' for value in numbers]))
        present = [value for _, numbers, _ in series for value in numbers if value is not None]
        axis = None if chart.type == 'pie' else nice_axis(present)
        out.append(ChartView(chart.type, chart.title, row, col, category, cols, categories, series, axis,
                             views[cols[0]].code, views[cols[0]]))
    return out


def summary(prepared: Prepared, limit: int = 1200) -> str:
    """Kết quả hàng tổng của từng trang, để Peto nêu đúng số trong câu trả lời mà không tự tính lại."""
    lines = []
    for s, sheet in enumerate(prepared.book.sheets):
        if not sheet.total:
            continue
        row = len(sheet.rows) + 1
        views = column_views(prepared, s)
        label = next((value for value in sheet.total if value and not value.startswith('=')), 'hàng tổng')
        parts = [f'{views[c].header} ({address(row, c)}) = {display(prepared.value(s, row, c), views[c])}'
                 for c, cell in enumerate(prepared.cells[s][row]) if cell.kind == 'formula']
        if parts:
            lines.append(f'Trang "{sheet.name}", {label}: ' + '; '.join(parts))
    text = '\n'.join(lines)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _cell_kind(value) -> str:
    return 'n' if engine.is_number(value) else 'b' if isinstance(value, bool) else 's'


def grid(prepared: Prepared) -> dict:
    """Dữ liệu cho lưới xem trong chat: chữ đã định dạng, công thức từng ô, độ rộng cột và biểu đồ."""
    sheets = []
    for s, sheet in enumerate(prepared.book.sheets):
        views = column_views(prepared, s)

        def cell(r: int, c: int):
            source = prepared.cells[s][r][c]
            value = prepared.value(s, r, c)
            if value is None and source.kind != 'formula':
                return None
            item = {'d': display(value, views[c]), 't': _cell_kind(value)}
            if source.kind == 'formula':
                item['f'] = source.formula.text
            return item

        data_rows = len(sheet.rows)
        charts = []
        for chart in chart_views(prepared, s, views):
            entry = {
                'type': chart.type, 'title': chart.title, 'row': chart.row, 'col': chart.col,
                'width': CHART_WIDTH, 'height': CHART_HEIGHT, 'categories': chart.categories,
                'series': [{'name': name, 'values': values, 'labels': labels} for name, values, labels in chart.series],
            }
            if chart.axis:
                low, high, step = chart.axis
                ticks = [low + step * index for index in range(int(round((high - low) / step)) + 1)]
                entry['axis'] = {'min': low, 'max': high, 'step': step, 'labels': [display(tick, chart.view) for tick in ticks]}
            charts.append(entry)
        sheets.append({
            'name': sheet.name, 'title': sheet.title or sheet.name,
            'columns': [{'header': view.header, 'width': view.pixels, 'wrap': view.wrap} for view in views],
            'rows': [[cell(r, c) for c in range(len(sheet.columns))] for r in range(1, data_rows + 1)],
            'total': [cell(data_rows + 1, c) for c in range(len(sheet.columns))] if sheet.total else None,
            'formulas': sum(item.kind == 'formula' for row in prepared.cells[s] for item in row),
            'charts': charts,
        })
    return {'title': prepared.book.title, 'sheets': sheets}
