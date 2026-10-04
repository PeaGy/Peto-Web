"""Ghi bảng tính đã tính (spec.Prepared) thành tệp XLSX bằng XlsxWriter.

Công thức ghi kèm kết quả đã tính, nên trình xem không tự tính (xem nhanh trên điện thoại, LibreOffice) vẫn hiện đúng
số; XlsxWriter đặt cờ để Excel tính lại khi mở. Hàng tên cột tô màu, cố định khi cuộn, có nút lọc; hàng dữ liệu xen màu
bằng định dạng có điều kiện nên vẫn xen đúng sau khi người dùng sắp xếp; biểu đồ là biểu đồ gốc của Excel, trục số đặt
cố định giống lưới xem.
"""
from __future__ import annotations

from io import BytesIO

from features.documents.sheets import engine
from features.documents.sheets.spec import Prepared
from features.documents.sheets.view import ACCENT, CHART_HEIGHT, CHART_WIDTH, PIE, SERIES, chart_views, column_views

HEADER_FILL, HEADER_TEXT, GRID, BAND, TOTAL_FILL = '#E2F0EE', '#0B3D37', '#D5DBE0', '#F6F9F9', '#EDF4F2'


class _Formats:
    """Bộ đệm định dạng: XlsxWriter cần mỗi tổ hợp là một đối tượng Format dùng lại."""

    def __init__(self, workbook):
        self.workbook = workbook
        self.cache = {}

    def get(self, role: str, code: str | None = None, wrap: bool = False):
        key = (role, code, wrap)
        if key not in self.cache:
            props = {'valign': 'vcenter', 'border': 1, 'border_color': GRID}
            if role == 'header':
                props.update(bold=True, bg_color=HEADER_FILL, font_color=HEADER_TEXT, align='center', text_wrap=True,
                             bottom=2, bottom_color='#' + ACCENT)
            elif role == 'total':
                props.update(bold=True, bg_color=TOTAL_FILL, top=2, top_color='#' + ACCENT)
            if code:
                props['num_format'] = code
            if wrap:
                props['text_wrap'] = True
            self.cache[key] = self.workbook.add_format(props)
        return self.cache[key]


def _write(sheet, row: int, col: int, cell, value, cell_format):
    if cell.kind == 'formula':
        cached = value
        if not isinstance(value, (bool, str)):
            cached = int(value) if float(value).is_integer() and abs(value) < 1e15 else float(value)
        sheet.write_formula(row, col, cell.formula.text, cell_format, cached)
    elif cell.kind == 'text':
        sheet.write_string(row, col, cell.value, cell_format)
    elif cell.kind in ('number', 'date'):
        sheet.write_number(row, col, cell.value, cell_format)
    else:
        sheet.write_blank(row, col, None, cell_format)


def _chart(workbook, name: str, chart, data_rows: int):
    kind = chart.type
    excel = workbook.add_chart({'type': kind})
    single = len(chart.value_cols) == 1
    for index, col in enumerate(chart.value_cols):
        series = {
            'name': [name, 0, col],
            'categories': [name, 1, chart.category_col, data_rows, chart.category_col],
            'values': [name, 1, col, data_rows, col],
        }
        color = '#' + SERIES[index % len(SERIES)]
        if kind == 'pie':
            slices = [PIE[position % len(PIE)] for position in range(data_rows)]
            series['points'] = [{'fill': {'color': '#' + fill}, 'border': {'color': '#FFFFFF'}} for fill, _ in slices]
            series['data_labels'] = {'percentage': True, 'custom': [{'font': {'color': '#' + text, 'bold': True}}
                                                                    for _, text in slices]}
        elif kind == 'line':
            series['line'] = {'color': color, 'width': 2.25}
            series['marker'] = {'type': 'circle', 'size': 6, 'fill': {'color': color}, 'border': {'color': color}}
        else:
            series['fill'] = {'color': color}
            series['border'] = {'none': True}
            series['gap'] = 80
            if single:
                series['data_labels'] = {'value': True, 'num_format': chart.code or 'General'}
        excel.add_series(series)
    excel.set_title({'name': chart.title, 'name_font': {'size': 13, 'bold': True, 'color': '#333333'}})
    if kind == 'pie':
        excel.set_legend({'position': 'right'})
    else:
        low, high, step = chart.axis
        value_axis = {'min': low, 'max': high, 'major_unit': step, 'num_format': chart.code or 'General',
                      'major_gridlines': {'visible': True, 'line': {'color': '#E4E7E9'}}, 'line': {'none': True}}
        category_axis = {'line': {'color': '#BFC5CA'}}
        if kind == 'bar':
            excel.set_x_axis(value_axis)
            excel.set_y_axis(category_axis)
        else:
            excel.set_y_axis(value_axis)
            excel.set_x_axis(category_axis)
        excel.set_legend({'none': True} if single else {'position': 'bottom'})
    excel.set_size({'width': CHART_WIDTH, 'height': CHART_HEIGHT})
    return excel


def render(prepared: Prepared) -> bytes:
    import xlsxwriter
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_numbers': False, 'strings_to_formulas': False,
                                            'strings_to_urls': False})
    book = prepared.book
    workbook.set_properties({'title': book.title, 'author': 'Peto', 'comments': 'Tạo bởi Peto'})
    formats = _Formats(workbook)
    band = workbook.add_format({'bg_color': BAND})
    for s, sheet in enumerate(book.sheets):
        worksheet = workbook.add_worksheet(sheet.name)
        views = column_views(prepared, s)
        data_rows = len(sheet.rows)
        last_col = len(sheet.columns) - 1
        for c, view in enumerate(views):
            worksheet.set_column(c, c, view.width)
        for r, row in enumerate(prepared.cells[s]):
            role = 'header' if r == 0 else 'total' if sheet.total and r == data_rows + 1 else 'data'
            for c, cell in enumerate(row):
                view = views[c]
                cell_format = formats.get(role, None if role == 'header' else view.code, view.wrap and role != 'header')
                _write(worksheet, r, c, cell, prepared.value(s, r, c), cell_format)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, data_rows, last_col)
        if data_rows >= 2:
            worksheet.conditional_format(1, 0, data_rows, last_col,
                                         {'type': 'formula', 'criteria': '=MOD(ROW(),2)=1', 'format': band})
        # In: khổ A4, vừa một trang ngang, lặp hàng tên cột, tiêu đề ở đầu trang và số trang ở chân trang.
        worksheet.set_paper(9)
        if sum(view.width for view in views) > 100:
            worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
        worksheet.repeat_rows(0)
        worksheet.set_margins(left=0.4, right=0.4, top=0.75, bottom=0.75)
        worksheet.center_horizontally()
        worksheet.set_header('&C&"-,Bold"&12' + (sheet.title or sheet.name).replace('&', '&&')[:200])
        worksheet.set_footer('&CTrang &P / &N')
        for chart in chart_views(prepared, s, views):
            worksheet.insert_chart(chart.row, chart.col, _chart(workbook, sheet.name, chart, data_rows),
                                   {'x_offset': 10, 'y_offset': 4, 'object_position': 1})
    workbook.close()
    return output.getvalue()


def cached_values(prepared: Prepared) -> dict:
    """Kết quả đã tính của các ô công thức (để test và để báo lại cho model)."""
    return {(s, r, c): value for s, sheet in enumerate(prepared.cells) for r, row in enumerate(sheet)
            for c, cell in enumerate(row) if cell.kind == 'formula'
            for value in [prepared.value(s, r, c)] if not isinstance(value, engine.XLError)}
