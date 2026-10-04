"""Đầu vào của công cụ create_spreadsheet: lược đồ cho model, kiểm tra từng ô, tính cả bảng, đọc lại bảng đã lưu.

Mỗi trang tính là đúng một bảng bắt đầu từ ô A1: hàng 1 là tên cột, dữ liệu từ hàng 2, hàng tổng (nếu có) ngay sau hàng
dữ liệu cuối. Cách đánh địa chỉ cố định như vậy để model viết đúng công thức (=SUM(C2:C11)) mà không phải đoán bảng nằm
đâu. Ô là chuỗi: chữ, số dạng máy, phần trăm, ngày ISO hoặc công thức; kiểu cột quyết định cách đọc và cách hiển thị.

Bảng lưu lại dạng JSON gọn (Workbook.to_json) để Peto đọc lại khi được nhờ sửa ở lượt sau; công thức lưu ở dạng đã chuẩn
hóa, đúng như chữ ghi vào tệp.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from features.documents.export import clean_text
from features.documents.sheets import engine
from features.documents.sheets.formula import FUNCTIONS, Formula, FormulaError, address, column_index, column_letter, parse

FORMATS = ('text', 'number', 'percent', 'vnd', 'usd', 'date')
CHARTS = ('column', 'bar', 'line', 'pie')
MAX_SHEETS, MAX_COLUMNS, MAX_DATA_ROWS, MAX_CELLS = 5, 20, 300, 4000
MAX_CHARTS_PER_SHEET, MAX_CHARTS, MAX_SERIES = 4, 8, 4
MAX_CHART_ROWS, MAX_PIE = 60, 10
MAX_TEXT, MAX_HEADER, MAX_TITLE = 300, 80, 120

_STRING = {'type': 'string'}
COLUMN_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'header': {'type': 'string', 'description': 'Tên cột ở hàng 1, ngắn gọn.'},
        'format': {'type': 'string', 'enum': list(FORMATS), 'description': (
            'Kiểu của cả cột. text: chữ (mã số, số điện thoại cũng là text). number: số. percent: phần trăm, ô viết '
            '8% còn công thức trả tỉ lệ như 0.08. vnd: tiền đồng. usd: đô la Mỹ. date: ngày, ô viết YYYY-MM-DD.')},
        'decimals': {'type': ['integer', 'null'], 'description': (
            'Số chữ số thập phân hiển thị (0–4), null để tự chọn. Điểm số thường 1 hoặc 2.')},
    },
    'required': ['header', 'format', 'decimals'],
}
CHART_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'type': {'type': 'string', 'enum': list(CHARTS), 'description': (
            'column: cột đứng; bar: thanh ngang (nhãn dài); line: đường theo thời gian; pie: tỉ lệ các phần, một cột '
            'số, tối đa 10 hàng.')},
        'title': {'type': 'string'},
        'category_column': {'type': 'string', 'description': 'Chữ cái của cột làm nhãn, ví dụ "A".'},
        'value_columns': {'type': 'array', 'items': _STRING, 'description': (
            'Chữ cái các cột số làm chuỗi số liệu, 1–4 cột (pie đúng 1). Biểu đồ lấy mọi hàng dữ liệu, không lấy '
            'hàng tổng.')},
    },
    'required': ['type', 'title', 'category_column', 'value_columns'],
}
SHEET_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'name': {'type': 'string', 'description': 'Tên trang tính, tối đa 31 ký tự, không chứa : \\ / ? * [ ].'},
        'title': {'type': ['string', 'null'], 'description': 'Tiêu đề in ở đầu mỗi trang giấy khi in; null thì dùng tên trang tính.'},
        'columns': {'type': 'array', 'items': COLUMN_SCHEMA, 'description': 'columns[0] là cột A, columns[1] là cột B…, tối đa 20 cột.'},
        'rows': {'type': 'array', 'items': {'type': 'array', 'items': _STRING}, 'description': (
            'Các hàng dữ liệu, mỗi hàng đúng số ô bằng số cột. rows[0] là hàng 2, rows[i] là hàng i+2. Ô trống là "".')},
        'total_row': {'type': ['array', 'null'], 'items': _STRING, 'description': (
            'Hàng tổng in đậm, nằm ngay sau hàng dữ liệu cuối (hàng len(rows)+2), cùng số ô; null nếu không cần. '
            'Ví dụ ["Tổng", "", "=SUM(C2:C11)"].')},
        'charts': {'type': 'array', 'items': CHART_SCHEMA, 'description': 'Biểu đồ Excel thật của trang này, [] nếu không cần.'},
    },
    'required': ['name', 'title', 'columns', 'rows', 'total_row', 'charts'],
}
SCHEMA = {
    'type': 'function', 'name': 'create_spreadsheet', 'strict': True,
    'description': (
        'Tạo tệp Excel XLSX thật (công thức thật đã tính sẵn kết quả, biểu đồ gốc của Excel), lưu theo tài khoản và hiện '
        'lưới xem ngay trong chat. Gọi khi người dùng nhờ lập bảng tính, file Excel, bảng điểm, bảng lương, bảng chi '
        'tiêu, thống kê có công thức hay biểu đồ; không dán bảng vào chat thay cho tệp. Mỗi trang tính là một bảng từ ô '
        'A1: hàng 1 là tên cột, rows[0] là hàng 2, hàng tổng ngay sau hàng dữ liệu cuối. Ô là chuỗi: chữ; số dạng máy '
        '(1500000, 7.5: dấu chấm thập phân, không dấu phân cách hàng nghìn); phần trăm 8%; ngày YYYY-MM-DD; hoặc công '
        'thức bắt đầu bằng = theo cú pháp Excel tiếng Anh, dấu phẩy ngăn tham số (=ROUND(AVERAGE(C2:C11),1)), trang '
        "khác viết 'Tên trang'!A1. Cột tính lặp lại công thức cho từng hàng, dùng số hàng của chính hàng đó. Chỉ dùng "
        'các hàm: ' + ', '.join(sorted(FUNCTIONS)) + '. VLOOKUP dò chính xác thì thêm FALSE. Không tính vùng ô trong '
        'phép toán (A2:A9*B2:B9); dùng SUMPRODUCT hoặc SUMIFS. Không bịa số liệu: chỉ dùng số người dùng đưa, có trong '
        'tệp hay nguồn đã dẫn; khi cần dữ liệu mẫu thì nói rõ là mẫu. Tiếng Việt phải có đầy đủ dấu.'),
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'title': {'type': 'string', 'description': 'Tên bảng tính, cũng là tên tệp.'},
            'sheets': {'type': 'array', 'items': SHEET_SCHEMA, 'description': 'Các trang tính, 1–5 trang.'},
        },
        'required': ['title', 'sheets'],
    },
}


class ColumnInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    header: str = Field(max_length=300)
    format: Literal['text', 'number', 'percent', 'vnd', 'usd', 'date']
    decimals: int | None = None


class ChartInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['column', 'bar', 'line', 'pie']
    title: str = Field(max_length=300)
    category_column: str = Field(max_length=8)
    value_columns: list[str] = Field(max_length=12)


class SheetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=200)
    title: str | None = Field(None, max_length=400)
    columns: list[ColumnInput] = Field(max_length=60)
    rows: list[list[str]] = Field(max_length=1200)
    total_row: list[str] | None = Field(None, max_length=60)
    charts: list[ChartInput] = Field(default_factory=list, max_length=20)


class WorkbookInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=300)
    sheets: list[SheetInput] = Field(min_length=1, max_length=20)


@dataclass
class Column:
    header: str
    format: str = 'text'
    decimals: int | None = None


@dataclass
class Chart:
    type: str
    title: str
    category: str
    values: list[str]


@dataclass
class Sheet:
    name: str
    columns: list[Column]
    rows: list[list[str]]
    title: str = ''
    total: list[str] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)


@dataclass
class Workbook:
    title: str
    sheets: list[Sheet]

    def to_json(self) -> str:
        """JSON gọn để lưu và để Peto đọc lại: bỏ trường rỗng, giữ nguyên ô trống trong hàng và decimals = 0."""
        def compact(value):
            if isinstance(value, dict):
                return {key: compact(item) for key, item in value.items() if item is not None and item != '' and item != []}
            if isinstance(value, list):
                return [compact(item) for item in value]
            return value
        return json.dumps(compact(asdict(self)), ensure_ascii=False)


def load(content: str) -> Workbook:
    """Đọc lại JSON đã lưu (Workbook.to_json)."""
    data = json.loads(content)
    sheets = []
    for item in data.get('sheets', []):
        sheets.append(Sheet(
            name=item['name'], title=item.get('title', ''), rows=item.get('rows', []), total=item.get('total', []),
            columns=[Column(**column) for column in item.get('columns', [])],
            charts=[Chart(**chart) for chart in item.get('charts', [])]))
    return Workbook(title=data['title'], sheets=sheets)


# ---------- đọc từng ô ----------
@dataclass(frozen=True)
class Cell:
    kind: str                     # blank, text, number, date, formula
    value: object = None          # số (float, ngày là số sê-ri) hoặc chữ
    formula: Formula | None = None


BLANK = Cell('blank')
_MACHINE = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
_NUMBERISH = re.compile(r'[+-]?[\d\s.,]*\d[\d\s.,]*')
_CURRENCY = re.compile(r'^\s*(?:\$|US\$)?\s*(.*?)\s*(?:₫|đ|vnđ|vnd|usd|\$)?\s*$', re.I)
_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def _line(value: str | None) -> str:
    return ' '.join(clean_text(value or '').split())


def parse_cell(raw: str, column: Column, where: str) -> Cell:
    """Một ô theo kiểu cột. Chữ có chữ cái trong cột số (như "Vắng") giữ là chữ; số viết sai dạng thì báo lỗi."""
    text = clean_text(raw)
    if not text:
        return BLANK
    if text.startswith('=') and len(text) > 1:
        try:
            return Cell('formula', formula=parse(text))
        except FormulaError as error:
            raise ValueError(f'{where}: công thức "{text[:80]}" sai: {error}.') from None
    if len(text) > MAX_TEXT:
        raise ValueError(f'{where}: ô dài quá {MAX_TEXT} ký tự; rút gọn hoặc tách sang cột khác.')
    kind = column.format
    if kind == 'text':
        return Cell('text', text)
    if kind == 'date':
        match = _ISO.fullmatch(text)
        if match:
            try:
                day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                raise ValueError(f'{where}: ngày "{text}" không có thật.') from None
            if day < date(1900, 3, 1):
                raise ValueError(f'{where}: ngày phải từ 01/03/1900 trở đi.')
            return Cell('date', engine.serial(day))
        if re.fullmatch(r'[\d\s./-]+', text):
            raise ValueError(f'{where}: ngày "{text}" phải viết dạng YYYY-MM-DD, ví dụ 2026-10-04.')
        return Cell('text', text)
    if kind == 'percent':
        match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%', text)
        if match:
            return Cell('number', float(match.group(1)) / 100)
        if _NUMBERISH.fullmatch(text):
            raise ValueError(f'{where}: cột phần trăm viết dạng 8% hoặc 12.5% (không viết "{text}").')
        return Cell('text', text)
    body = _CURRENCY.match(text).group(1) if kind in ('vnd', 'usd') else text
    if _MACHINE.fullmatch(body):
        return Cell('number', float(body))
    if _NUMBERISH.fullmatch(body):
        raise ValueError(f'{where}: "{text}" phải là số dạng máy như 1500000 hoặc 7.5 (dấu chấm thập phân, không dấu '
                         'phân cách hàng nghìn).')
    return Cell('text', text)


def _sheet_name(raw: str, index: int, seen: set[str]) -> str:
    name = _line(raw)
    where = f'Trang tính {index}'
    if not name:
        raise ValueError(f'{where}: thiếu tên.')
    if len(name) > 31:
        raise ValueError(f'{where}: tên "{name}" dài quá 31 ký tự (giới hạn của Excel).')
    if re.search(r'[:\\/?*\[\]]', name) or name.startswith("'") or name.endswith("'"):
        raise ValueError(f'{where}: tên "{name}" không được chứa : \\ / ? * [ ] hay bắt đầu, kết thúc bằng dấu nháy.')
    if name.casefold() == 'history':
        raise ValueError(f'{where}: Excel dành riêng tên History; chọn tên khác.')
    if name.casefold() in seen:
        raise ValueError(f'{where}: tên "{name}" bị trùng.')
    seen.add(name.casefold())
    return name


def _letter(raw: str, columns: list[Column], where: str) -> str:
    letter = raw.strip().upper()
    if not re.fullmatch(r'[A-Z]{1,2}', letter) or column_index(letter) >= len(columns):
        last = column_letter(len(columns) - 1)
        raise ValueError(f'{where}: cột "{raw}" không có; bảng có cột A–{last}.')
    return letter


def normalize(spec: WorkbookInput) -> Workbook:
    """Làm sạch chữ và kiểm tra cấu trúc. Lỗi nói rõ trang, ô nào sai gì để model sửa rồi gọi lại."""
    if len(spec.sheets) > MAX_SHEETS:
        raise ValueError(f'Bảng tính tối đa {MAX_SHEETS} trang tính. Gộp bớt rồi gọi lại.')
    title = _line(spec.title)
    if not title:
        raise ValueError('Tên bảng tính trống.')
    seen: set[str] = set()
    sheets: list[Sheet] = []
    cells = 0
    charts = 0
    for index, raw in enumerate(spec.sheets, start=1):
        name = _sheet_name(raw.name, index, seen)
        where = f'Trang "{name}"'
        if not 1 <= len(raw.columns) <= MAX_COLUMNS:
            raise ValueError(f'{where}: cần 1–{MAX_COLUMNS} cột, đang có {len(raw.columns)}.')
        columns = []
        for number, column in enumerate(raw.columns):
            header = _line(column.header)
            if not header:
                raise ValueError(f'{where}: cột {column_letter(number)} thiếu tên.')
            if len(header) > MAX_HEADER:
                raise ValueError(f'{where}: tên cột {column_letter(number)} dài quá {MAX_HEADER} ký tự.')
            if column.decimals is not None and not 0 <= column.decimals <= 4:
                raise ValueError(f'{where}: decimals của cột {column_letter(number)} phải từ 0 đến 4.')
            columns.append(Column(header, column.format, column.decimals))
        if len(raw.rows) > MAX_DATA_ROWS:
            raise ValueError(f'{where}: tối đa {MAX_DATA_ROWS} hàng dữ liệu, đang có {len(raw.rows)}.')
        rows = []
        for row_index, row in enumerate(raw.rows):
            if len(row) != len(columns):
                raise ValueError(f'{where}: hàng {row_index + 2} (rows[{row_index}]) có {len(row)} ô, cần đúng {len(columns)} '
                                 'ô như số cột.')
            rows.append([clean_text(value) for value in row])
        total = []
        if raw.total_row is not None:
            if len(raw.total_row) != len(columns):
                raise ValueError(f'{where}: total_row có {len(raw.total_row)} ô, cần đúng {len(columns)} ô.')
            total = [clean_text(value) for value in raw.total_row]
            if not any(total):
                total = []
        cells += len(columns) * (len(rows) + 1 + bool(total))
        if len(raw.charts) > MAX_CHARTS_PER_SHEET:
            raise ValueError(f'{where}: tối đa {MAX_CHARTS_PER_SHEET} biểu đồ mỗi trang.')
        sheet_charts = []
        for chart_index, chart in enumerate(raw.charts, start=1):
            place = f'{where}, biểu đồ {chart_index}'
            chart_title = _line(chart.title)
            if not chart_title:
                raise ValueError(f'{place}: thiếu tiêu đề.')
            category = _letter(chart.category_column, columns, place)
            values = [_letter(value, columns, place) for value in chart.value_columns]
            if not 1 <= len(values) <= MAX_SERIES or len(set(values)) != len(values):
                raise ValueError(f'{place}: value_columns cần 1–{MAX_SERIES} cột khác nhau.')
            if chart.type == 'pie' and len(values) != 1:
                raise ValueError(f'{place}: biểu đồ tròn chỉ có một cột số.')
            if category in values:
                raise ValueError(f'{place}: cột nhãn không được trùng cột số.')
            sheet_charts.append(Chart(chart.type, chart_title[:MAX_TITLE], category, values))
        charts += len(sheet_charts)
        sheets.append(Sheet(name=name, title=_line(raw.title)[:MAX_TITLE], columns=columns, rows=rows, total=total,
                            charts=sheet_charts))
    if cells > MAX_CELLS:
        raise ValueError(f'Bảng tính có {cells} ô, tối đa {MAX_CELLS}. Bớt hàng hoặc cột rồi gọi lại.')
    if charts > MAX_CHARTS:
        raise ValueError(f'Tối đa {MAX_CHARTS} biểu đồ mỗi bảng tính.')
    return Workbook(title=title[:MAX_TITLE], sheets=sheets)


# ---------- tính cả bảng ----------
@dataclass
class Prepared:
    """Bảng đã đọc và tính xong: ô đã phân loại và giá trị từng ô (hàng 0 là tên cột)."""
    book: Workbook
    cells: list[list[list[Cell]]]
    values: list[dict[tuple[int, int], object]]

    def rows(self, index: int) -> int:
        sheet = self.book.sheets[index]
        return 1 + len(sheet.rows) + bool(sheet.total)

    def value(self, index: int, row: int, col: int):
        return self.values[index].get((row, col))

    @property
    def formulas(self) -> int:
        return sum(cell.kind == 'formula' for sheet in self.cells for row in sheet for cell in row)


def _check_refs(book: Workbook, cells, sizes):
    names = {sheet.name.casefold(): position for position, sheet in enumerate(book.sheets)}
    for s, sheet in enumerate(book.sheets):
        for r, row in enumerate(cells[s]):
            for c, cell in enumerate(row):
                if cell.kind != 'formula':
                    continue
                where = f'{sheet.name}!{address(r, c)}'
                for ref in cell.formula.refs:
                    target = s if ref.sheet is None else names.get(ref.sheet.casefold())
                    if target is None:
                        known = ', '.join(f"'{item.name}'" for item in book.sheets)
                        raise ValueError(f'{where}: công thức {cell.formula.text} nhắc tới trang tính "{ref.sheet}" không có '
                                         f'(các trang: {known}).')
                    nrows, ncols = sizes[target]
                    if (ref.r1 is not None and ref.r1 >= nrows) or (ref.c1 is not None and ref.c1 >= ncols):
                        label = book.sheets[target].name
                        raise ValueError(f'{where}: {ref.text} nằm ngoài bảng của trang "{label}" (bảng có hàng 1–{nrows}, cột '
                                         f'A–{column_letter(ncols - 1)}). Kiểm tra lại số hàng: rows[0] là hàng 2.')


def prepare(book: Workbook, today: date) -> Prepared:
    """Phân loại ô, kiểm tra tham chiếu, tính mọi công thức và kiểm tra biểu đồ. Lỗi nào cũng là ValueError dễ hiểu."""
    cells: list[list[list[Cell]]] = []
    sizes = []
    sheets_data = []
    formulas: dict[tuple[int, int, int], Formula] = {}
    for s, sheet in enumerate(book.sheets):
        grid = [[Cell('text', column.header) for column in sheet.columns]]
        body = [*sheet.rows, *([sheet.total] if sheet.total else [])]
        for r, row in enumerate(body, start=1):
            grid.append([parse_cell(raw, column, f'{sheet.name}!{address(r, c)}')
                         for c, (raw, column) in enumerate(zip(row, sheet.columns))])
        cells.append(grid)
        sizes.append((len(grid), len(sheet.columns)))
        data = engine.SheetData(sheet.name, len(grid), len(sheet.columns))
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell.kind == 'formula':
                    formulas[(s, r, c)] = cell.formula
                elif cell.kind != 'blank':
                    data.values[(r, c)] = cell.value
        sheets_data.append(data)
    _check_refs(book, cells, sizes)
    try:
        results = engine.compute(sheets_data, formulas, today)
    except engine.CycleError as error:
        raise ValueError(f'Có vòng tham chiếu (công thức tự dùng lại kết quả của chính nó): {error}. Hàng tổng không được '
                         'cộng cả chính nó; sửa vùng ô rồi gọi lại.') from None
    errors = []
    for (s, r, c), value in sorted(results.items()):
        if isinstance(value, engine.XLError):
            code = value.code
            text = cells[s][r][c].formula.text
            shown = 'lỗi dò gần đúng' if code == '#UNSORTED' else code
            errors.append(f'{book.sheets[s].name}!{address(r, c)} {text} ra {shown}: {engine.ERROR_HELP.get(code, "")}')
    if errors:
        more = f' (và {len(errors) - 5} ô khác)' if len(errors) > 5 else ''
        raise ValueError('Công thức ra lỗi: ' + '; '.join(errors[:5]) + more + '. Sửa công thức hoặc dữ liệu (có thể bọc '
                         'IFERROR nếu lỗi là có chủ ý) rồi gọi lại.')
    prepared = Prepared(book, cells, [data.values for data in sheets_data])
    for s, sheet in enumerate(book.sheets):
        _check_charts(prepared, s)
    return prepared


def _check_charts(prepared: Prepared, s: int):
    sheet = prepared.book.sheets[s]
    data_rows = len(sheet.rows)
    for index, chart in enumerate(sheet.charts, start=1):
        place = f'Trang "{sheet.name}", biểu đồ {index}'
        if not data_rows:
            raise ValueError(f'{place}: trang chưa có hàng dữ liệu.')
        limit = MAX_PIE if chart.type == 'pie' else MAX_CHART_ROWS
        if data_rows > limit:
            hint = ' Lập một bảng tổng hợp (ví dụ trang Thống kê) làm nguồn cho biểu đồ.' if chart.type == 'pie' else ''
            raise ValueError(f'{place}: biểu đồ {chart.type} tối đa {limit} hàng dữ liệu, trang có {data_rows}.{hint}')
        for letter in chart.values:
            col = column_index(letter)
            numbers = []
            for r in range(1, data_rows + 1):
                value = prepared.value(s, r, col)
                if value is None:
                    continue
                if not engine.is_number(value):
                    raise ValueError(f'{place}: cột {letter} phải là số, ô {letter}{r + 1} là "{value}".')
                numbers.append(value)
            if not numbers:
                raise ValueError(f'{place}: cột {letter} chưa có số nào.')
            if chart.type == 'pie' and (min(numbers) < 0 or sum(numbers) <= 0):
                raise ValueError(f'{place}: biểu đồ tròn cần các số không âm, tổng lớn hơn 0.')


def plain_text(book: Workbook) -> str:
    """Chữ của bảng (không gồm công thức), để kiểm tra tiếng Việt bị gửi không dấu."""
    parts = [book.title]
    for sheet in book.sheets:
        parts += [sheet.name, sheet.title, *(column.header for column in sheet.columns),
                  *(chart.title for chart in sheet.charts)]
        parts += [cell for row in [*sheet.rows, sheet.total] for cell in row if cell and not cell.startswith('=')]
    return '\n'.join(part for part in parts if part)
