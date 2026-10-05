"""Công cụ edit_spreadsheet: lược đồ cho model, đọc từng thay đổi, áp lên tệp theo thứ tự rồi tính lại công thức.

Mỗi thay đổi dùng tọa độ của tệp ngay trước nó (chèn 2 hàng ở hàng 12 rồi ghi A12 là ghi vào hàng mới chèn), như khi
người dùng làm lần lượt trong Excel. Một thay đổi sai thì cả lượt không ghi gì, lỗi nói rõ thay đổi thứ mấy và sai ở
đâu để model sửa rồi gọi lại.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from features.documents.sheets import engine
from features.documents.sheets.formula import FUNCTIONS, FormulaError, parse, quote_sheet
from features.documents.workbook_edit import meta, refs
from features.documents.workbook_edit.book import Book, SheetInfo, excel_serial
from features.documents.workbook_edit.formulas import array_ranges, expand_shared, formula_map, shared_groups
from features.documents.workbook_edit.package import EditError
from features.documents.workbook_edit.recalc import recalculate
from features.documents.workbook_edit.sheetxml import Cell, Worksheet, address, cell_inner, column_index, column_letter
from features.documents.workbook_edit.styles import DATE_ID, DATETIME_ID
from features.documents.workbook_reader import general, show_number

ACTIONS = ('set', 'fill', 'clear', 'format', 'insert_rows', 'delete_rows', 'insert_columns', 'delete_columns',
           'add_sheet', 'rename_sheet')
NUMBER_FORMATS = ('general', 'text', 'number', 'percent', 'vnd', 'usd', 'date')
MAX_CHANGES = 40
MAX_CELLS = 20_000          # ô ghi hoặc định dạng trong một lượt
MAX_SHIFT = 1_000           # số hàng/cột chèn hoặc xóa một lần
MAX_VALUE = 4_000
_COLOR = re.compile(r'#?[0-9A-Fa-f]{6}')
_MACHINE = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
_PERCENT = re.compile(r'([+-]?(?:\d+(?:\.(\d*))?|\.(\d+)))%')
_DATE = re.compile(r'(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?')
_LOCAL_NUMBER = re.compile(r'[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?|[+-]?\d+,\d+')
_AREA = re.compile(r'\$?([A-Za-z]{1,3})\$?(\d{1,7})(?::\$?([A-Za-z]{1,3})\$?(\d{1,7}))?')
_COLUMNS = re.compile(r'\$?([A-Za-z]{1,3})(?::\$?([A-Za-z]{1,3}))?')
_ROWS = re.compile(r'\$?(\d{1,7})(?::\$?(\d{1,7}))?')
_BAD_NAME = re.compile(r'[\\/?*\[\]:]')

_NULLABLE_STRING = {'type': ['string', 'null']}
CHANGE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'action': {'type': 'string', 'enum': list(ACTIONS), 'description': (
            'set: ghi giá trị/công thức theo lưới values từ ô đầu của range. fill: một giá trị hoặc công thức cho cả '
            'vùng range, công thức chép như kéo điền trong Excel (viết cho ô đầu vùng, tham chiếu tương đối tự dời). '
            'clear: xóa nội dung, giữ định dạng. format: đổi định dạng của range. insert_rows/delete_rows: range là '
            'hàng ("12" hoặc "12:14"), chèn hàng trống vào đúng vị trí đó (hàng cũ dời xuống, theo định dạng hàng '
            'trên) hoặc xóa. insert_columns/delete_columns: range là cột ("D" hoặc "D:E"). add_sheet: thêm trang tính '
            'tên sheet vào cuối. rename_sheet: đổi tên trang sheet thành new_name. Công thức, vùng gộp, biểu đồ, '
            'Bảng… tự dời theo khi chèn/xóa.')},
        'sheet': {'type': 'string', 'description': 'Tên trang tính đúng như trong [Trang tính … "tên"].'},
        'range': {**_NULLABLE_STRING, 'description': 'Ô hoặc vùng như B5, A12:F14; hàng hoặc cột khi chèn/xóa; null với add_sheet, rename_sheet.'},
        'values': {'type': ['array', 'null'], 'items': {'type': 'array', 'items': _NULLABLE_STRING}, 'description': (
            'Chỉ với set: các hàng giá trị bắt đầu từ ô đầu của range; null trong lưới là giữ nguyên ô đó, "" là xóa '
            'nội dung ô.')},
        'value': {**_NULLABLE_STRING, 'description': 'Chỉ với fill: giá trị hoặc công thức điền cho cả vùng.'},
        'format_from': {**_NULLABLE_STRING, 'description': (
            'Chép định dạng (set, fill, format). Một ô là góc trên trái của vùng nguồn cùng cỡ vùng đích, ứng từng ô: A11 '
            'khi thêm hàng 12 giống hàng 11, E1 khi thêm cột F giống cột E. Một vùng thì lặp lại trên vùng đích: A1:A1 '
            'là mọi ô giống A1. null là giữ định dạng sẵn có của ô (hàng vừa chèn đã theo định dạng hàng trên).')},
        'bold': {'type': ['boolean', 'null']},
        'italic': {'type': ['boolean', 'null']},
        'font_color': {**_NULLABLE_STRING, 'description': 'Màu chữ #RRGGBB, null là giữ nguyên.'},
        'fill_color': {**_NULLABLE_STRING, 'description': 'Màu nền #RRGGBB, "none" là bỏ màu nền, null là giữ nguyên.'},
        'number_format': {'type': ['string', 'null'], 'enum': [*NUMBER_FORMATS, None], 'description': (
            'Định dạng số: number (1.234.567), percent, vnd (₫), usd ($), date (dd/mm/yyyy), text (@), general.')},
        'decimals': {'type': ['integer', 'null'], 'description': 'Số chữ số thập phân 0–4, đi cùng number_format.'},
        'align': {'type': ['string', 'null'], 'enum': ['left', 'center', 'right', None]},
        'new_name': {**_NULLABLE_STRING, 'description': 'Tên mới khi rename_sheet; null với các thao tác khác.'},
    },
    'required': ['action', 'sheet', 'range', 'values', 'value', 'format_from', 'bold', 'italic', 'font_color',
                 'fill_color', 'number_format', 'decimals', 'align', 'new_name'],
}
SCHEMA = {
    'type': 'function', 'name': 'edit_spreadsheet', 'strict': True,
    'description': (
        'Sửa thẳng tệp Excel người dùng đã gửi trong hội thoại (hoặc bản Peto đã sửa trước đó), giữ nguyên định dạng, '
        'màu, ô gộp, công thức khác, biểu đồ, bảng tổng hợp, ghi chú và macro của tệp. Kết quả là tệp mới để tải; tệp '
        'gốc không đổi. Dùng khi người dùng nhờ sửa, bổ sung, điền, xóa hay định dạng trong tệp của họ; tạo bảng mới '
        'thì dùng create_spreadsheet. Địa chỉ ô lấy từ "Hàng N | A: …" khi đọc tệp. Giá trị là chuỗi: chữ; số dạng '
        'máy (1500000, 7.5); phần trăm 8%; ngày YYYY-MM-DD; TRUE/FALSE; công thức bắt đầu bằng = theo cú pháp Excel '
        "tiếng Anh, dấu phẩy ngăn tham số, trang khác viết 'Tên trang'!A1; muốn giữ đúng chữ (mã 0123, chữ bắt đầu "
        "bằng =) thì thêm dấu ' ở đầu. Công thức mới chỉ dùng các hàm: " + ', '.join(sorted(FUNCTIONS)) + '. Gộp mọi '
        'thay đổi của một yêu cầu vào một lần gọi, theo thứ tự làm. Không bịa số liệu. Tiếng Việt phải có đầy đủ dấu.'),
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'file': {'type': 'string', 'description': (
                'Tên tệp Excel đúng như trong [Tệp đính kèm: …] hoặc tên tệp Peto đã sửa; luôn sửa bản mới nhất của tệp '
                'đó.')},
            'changes': {'type': 'array', 'items': CHANGE_SCHEMA, 'description': f'1–{MAX_CHANGES} thay đổi, làm lần lượt.'},
        },
        'required': ['file', 'changes'],
    },
}


class ChangeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['set', 'fill', 'clear', 'format', 'insert_rows', 'delete_rows', 'insert_columns', 'delete_columns',
                    'add_sheet', 'rename_sheet']
    sheet: str = Field(max_length=200)
    range: str | None = Field(None, max_length=60)
    values: list[list[str | None]] | None = Field(None, max_length=5_000)
    value: str | None = Field(None, max_length=MAX_VALUE)
    format_from: str | None = Field(None, max_length=60)
    bold: bool | None = None
    italic: bool | None = None
    font_color: str | None = Field(None, max_length=20)
    fill_color: str | None = Field(None, max_length=20)
    number_format: Literal['general', 'text', 'number', 'percent', 'vnd', 'usd', 'date'] | None = None
    decimals: int | None = Field(None, ge=0, le=10)
    align: Literal['left', 'center', 'right'] | None = None
    new_name: str | None = Field(None, max_length=200)


class EditInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str = Field(min_length=1, max_length=300)
    changes: list[ChangeInput] = Field(min_length=1, max_length=MAX_CHANGES)


# ---------- giá trị ô ----------

@dataclass
class Value:
    kind: str                     # blank, number, text, bool, formula
    number: float = 0.0
    text: str = ''
    flag: bool = False
    formula: object = None        # sheets.formula.Formula
    hint: str | None = None       # percent, date, datetime: cần định dạng số tương ứng
    decimals: int = 0


def parse_value(raw: str, style_kind: str, date1904: bool) -> Value:
    """Đọc một giá trị model gửi. Ô định dạng chữ (@) giữ số dưới dạng chữ, như Excel khi gõ vào ô như vậy."""
    if raw == '':
        return Value('blank')
    if raw.startswith("'"):
        return Value('text', text=raw[1:])
    if raw.startswith('=') and raw.strip() != '=':
        try:
            return Value('formula', formula=parse(raw))
        except FormulaError as error:
            raise EditError(f'công thức {raw[:80]}: {error}') from None
    text = raw.strip()
    if text.upper() in ('TRUE', 'FALSE'):
        return Value('bool', flag=text.upper() == 'TRUE')
    if _MACHINE.fullmatch(text):
        if style_kind == 'text':
            return Value('text', text=raw)
        number = float(text)
        if not abs(number) < 1e308:
            raise EditError(f'số {text[:30]} quá lớn')
        return Value('number', number=number)
    match = _PERCENT.fullmatch(text)
    if match:
        decimals = len(match.group(2) or match.group(3) or '')
        return Value('number', number=float(match.group(1)) / 100, hint='percent', decimals=min(decimals, 4))
    match = _DATE.fullmatch(text)
    if match:
        try:
            moment = datetime(*(int(part) for part in match.groups(default='0')))
        except ValueError:
            raise EditError(f'ngày {text} không có thật') from None
        serial = excel_serial(moment, date1904)
        if serial < (0 if date1904 else 61):
            raise EditError(f"Excel không lưu được ngày {text} (trước 01/03/1900); ghi thành chữ bằng dấu ' ở đầu")
        return Value('number', number=serial, hint='datetime' if match.group(4) else 'date')
    if _LOCAL_NUMBER.fullmatch(text):
        raise EditError(f'"{text}": viết số dạng máy như 1500000 hay 7.5 (dấu chấm thập phân, không dấu phân cách hàng '
                        "nghìn); muốn ghi đúng chữ như vậy thì thêm dấu ' ở đầu")
    return Value('text', text=raw)


def show(value, kind: str = 'number', date1904: bool = False, decimals: int = 0) -> str:
    """Giá trị ô viết cho model, cùng cách viết với bộ đọc tệp (số dạng máy, phần trăm, ngày ISO)."""
    if value is None or value == '':
        return '(trống)'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, engine.XLError):
        return value.code
    if isinstance(value, float):
        try:
            return show_number(value, kind, date1904, decimals)
        except (ValueError, OverflowError):
            return general(value)
    text = ' '.join(str(value).split())
    return f'"{text[:60]}…"' if len(text) > 60 else f'"{text}"'


# ---------- vùng ô ----------

def _strip_sheet(text: str, sheet: str) -> str:
    text = (text or '').strip().replace(' ', '')
    if '!' in text:
        prefix, _, rest = text.rpartition('!')
        name = prefix[1:-1].replace("''", "'") if prefix.startswith("'") and prefix.endswith("'") else prefix
        if name.casefold().replace(' ', '') != sheet.casefold().replace(' ', ''):
            raise EditError(f'vùng {text} ghi trang khác với sheet "{sheet}"')
        text = rest
    return text


def parse_area(text: str | None, sheet: str, used: tuple[int, int, int, int] | None = None) -> tuple[int, int, int, int]:
    """(Hàng đầu, cột đầu, hàng cuối, cột cuối) tính từ 0. Cả cột (C:C) hay cả hàng (5:5) thì cắt theo vùng có ô."""
    body = _strip_sheet(text or '', sheet)
    match = _AREA.fullmatch(body)
    if match:
        c1, r1 = column_index(match.group(1)), int(match.group(2)) - 1
        c2, r2 = (column_index(match.group(3)), int(match.group(4)) - 1) if match.group(3) else (c1, r1)
        area = (min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
    elif _COLUMNS.fullmatch(body) and used:
        match = _COLUMNS.fullmatch(body)
        c1 = column_index(match.group(1))
        c2 = column_index(match.group(2)) if match.group(2) else c1
        area = (used[0], min(c1, c2), used[2], max(c1, c2))
    elif _ROWS.fullmatch(body) and used:
        match = _ROWS.fullmatch(body)
        r1 = int(match.group(1)) - 1
        r2 = int(match.group(2)) - 1 if match.group(2) else r1
        area = (min(r1, r2), used[1], max(r1, r2), used[3])
    else:
        raise EditError(f'range "{(text or "")[:40]}" không phải ô hay vùng ô (như B5 hoặc A12:F14)')
    if area[0] < 0 or area[2] >= refs.MAX_ROWS or area[3] >= refs.MAX_COLS:
        raise EditError(f'vùng {text} nằm ngoài giới hạn của Excel')
    return area


def parse_span(text: str | None, sheet: str, axis: str) -> tuple[int, int]:
    body = _strip_sheet(text or '', sheet)
    if axis == 'row':
        match = _ROWS.fullmatch(body)
        if not match:
            raise EditError(f'range "{(text or "")[:40]}" cần là số hàng như "12" hoặc "12:14"')
        low, high = int(match.group(1)) - 1, int(match.group(2) or match.group(1)) - 1
        limit = refs.MAX_ROWS
    else:
        match = _COLUMNS.fullmatch(body)
        if not match:
            raise EditError(f'range "{(text or "")[:40]}" cần là chữ cột như "D" hoặc "D:F"')
        low, high = column_index(match.group(1)), column_index(match.group(2) or match.group(1))
        limit = refs.MAX_COLS
    low, high = min(low, high), max(low, high)
    if low < 0 or high >= limit:
        raise EditError(f'{text} nằm ngoài giới hạn của Excel')
    if high - low + 1 > MAX_SHIFT:
        raise EditError(f'mỗi lần chỉ chèn hoặc xóa tối đa {MAX_SHIFT} hàng/cột')
    return low, high


def sheet_label(name: str) -> str:
    """Tên trang trong dòng thay đổi: luôn trong nháy đơn, để lưới xem tách được trang và vùng ('Lương'!A1:B5)."""
    return "'" + name.replace("'", "''") + "'"


def area_label(sheet: str, r1: int, c1: int, r2: int, c2: int) -> str:
    return f'{sheet_label(sheet)}!{meta.area_text(r1, c1, r2, c2)}'


def compress(cells: set[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Gộp các ô thành ít vùng chữ nhật (chạy theo cột rồi ghép các cột liền nhau cùng khoảng hàng)."""
    runs: dict[tuple[int, int], list[int]] = {}
    by_col: dict[int, list[int]] = {}
    for row, col in cells:
        by_col.setdefault(col, []).append(row)
    for col, rows in by_col.items():
        rows.sort()
        start = previous = rows[0]
        for row in rows[1:] + [None]:
            if row is not None and row == previous + 1:
                previous = row
                continue
            runs.setdefault((start, previous), []).append(col)
            if row is not None:
                start = previous = row
    areas = []
    for (low, high), cols in runs.items():
        cols.sort()
        first = last = cols[0]
        for col in cols[1:] + [None]:
            if col is not None and col == last + 1:
                last = col
                continue
            areas.append((low, first, high, last))
            if col is not None:
                first = last = col
    return sorted(areas)


# ---------- phiên sửa ----------

@dataclass
class Outcome:
    data: bytes
    lines: list[str]
    changed: dict[str, list[tuple[int, int, int, int]]]
    results: list[str]
    notes: list[str]
    macro: bool
    sheets: list[str] = field(default_factory=list)


class Session:
    def __init__(self, book: Book, today: date):
        self.book, self.today = book, today
        self.lines: list[str] = []
        self.notes: list[str] = []
        self.changed: dict[str, set[tuple[int, int]]] = {}
        self.formatted: dict[str, set[tuple[int, int]]] = {}
        self.new: dict[str, set[tuple[int, int]]] = {}
        self.structural: set[str] = set()
        self.cells = 0
        self.formulas_touched = False

    # ---------- dùng chung ----------

    def worksheet(self, name: str) -> tuple[SheetInfo, Worksheet]:
        info, sheet = self.book.sheet(name)
        if self.book.protected(sheet):
            raise EditError(f'trang "{info.name}" đang được bảo vệ (Protect Sheet). Nhờ người dùng bỏ bảo vệ trong Excel '
                            'rồi gửi lại tệp')
        return info, sheet

    def count(self, amount: int) -> None:
        self.cells += amount
        if self.cells > MAX_CELLS:
            raise EditError(f'một lượt chỉ sửa tối đa {MAX_CELLS:,} ô; chia thành nhiều lượt'.replace(',', '.'))

    def kind_of(self, style: int) -> tuple[str, int]:
        return self.book.styles.kind(style)

    def guard(self, info: SheetInfo, sheet: Worksheet, area: tuple[int, int, int, int], values: bool = True) -> None:
        """Từ chối như Excel: ghi vào giữa ô gộp, vào bảng tổng hợp, vào một phần công thức mảng hay hàng tổng của Bảng."""
        r1, c1, r2, c2 = area
        if values:
            for merge in meta.merges(sheet):
                if meta.overlaps(area, merge):
                    for row in range(max(r1, merge[0]), min(r2, merge[2]) + 1):
                        for col in range(max(c1, merge[1]), min(c2, merge[3]) + 1):
                            if (row, col) != (merge[0], merge[1]):
                                raise EditError(f'ô {address(row, col)} nằm trong vùng gộp '
                                                f'{meta.area_text(*merge)}; ghi vào ô đầu {address(merge[0], merge[1])}')
            for name, place, _ in meta.pivots(self.book, sheet):
                if meta.overlaps(area, place):
                    raise EditError(f'vùng {meta.area_text(*area)} chạm bảng tổng hợp "{name}" '
                                    f'({meta.area_text(*place)}); Excel không cho ghi vào đó, hãy ghi ra ô khác')
            for low_row, low_col, high_row, high_col, kind in array_ranges(sheet):
                block = (low_row, low_col, high_row, high_col)
                inside = r1 <= low_row and c1 <= low_col and r2 >= high_row and c2 >= high_col
                if meta.overlaps(area, block) and not inside:
                    what = 'bảng dữ liệu (Data Table)' if kind == 'dataTable' else 'công thức mảng'
                    raise EditError(f'vùng {meta.area_text(*area)} chạm một phần {what} {meta.area_text(*block)}; '
                                    'chỉ sửa được cả vùng đó')
            for table in meta.tables(self.book, sheet):
                if table.totals and r1 <= table.r2 <= r2 and meta.overlaps(area, (table.r2, table.c1, table.r2, table.c2)):
                    raise EditError(f'hàng {table.r2 + 1} là hàng tổng của Bảng "{table.name}" do Excel quản lý; sửa hàng '
                                    'tổng trong Excel')

    def mark(self, info: SheetInfo, cells, new: bool = False) -> None:
        bucket = self.changed.setdefault(info.part, set())
        bucket.update(cells)
        if new:
            self.new.setdefault(info.part, set()).update(cells)

    def unshare(self, sheet: Worksheet, area: tuple[int, int, int, int]) -> None:
        """Mở các công thức chung có ô nằm trong vùng sắp ghi, để ô còn lại không mất công thức gốc."""
        groups = {si for si, cells in shared_groups(sheet).items()
                  if any(area[0] <= row <= area[2] and area[1] <= col <= area[3] for row, col in cells)}
        if groups:
            expand_shared(sheet, groups)

    def style_from(self, info: SheetInfo, sheet: Worksheet, source: str | None, area, r: int, c: int) -> int | None:
        """Kiểu chép cho ô (r, c) của vùng đích ``area``. Nguồn là một ô: góc trên trái của vùng nguồn cùng cỡ (A11 cho
        hàng 12 giống hàng 11); nguồn là một vùng: lặp lại vùng đó trên vùng đích (A1:A1 là mọi ô giống A1)."""
        if not source:
            return None
        top, left, bottom, right = parse_area(source, info.name)
        if ':' not in source:
            row, col = top + (r - area[0]), left + (c - area[1])
        else:
            row = top + (r - area[0]) % (bottom - top + 1)
            col = left + (c - area[1]) % (right - left + 1)
        if row >= refs.MAX_ROWS or col >= refs.MAX_COLS:
            return None
        found = sheet.get(row, col)
        return found.style if found else sheet.default_style(row, col)

    def write(self, info: SheetInfo, sheet: Worksheet, r: int, c: int, value: Value, style: int | None) -> None:
        existing = sheet.get(r, c)
        if style is None:
            style = existing.style if existing is not None else sheet.default_style(r, c)
        kind, _ = self.kind_of(style)
        if value.hint == 'percent' and kind != 'percent':
            style = self.book.styles.derive(style, number_format='0' + ('.' + '0' * value.decimals if value.decimals else '') + '%')
        elif value.hint == 'date' and kind not in ('date', 'datetime'):
            style = self.book.styles.derive(style, number_format=DATE_ID)
        elif value.hint == 'datetime' and kind != 'datetime':
            style = self.book.styles.derive(style, number_format=DATETIME_ID)
        attrs = {'r': address(r, c)}
        if style:
            attrs['s'] = str(style)
        prefix = sheet.prefix
        if value.kind == 'blank':
            inner = ''
        elif value.kind == 'number':
            number = value.number
            inner = cell_inner(prefix, value=str(int(number)) if number == int(number) and abs(number) < 1e15 else repr(number))
        elif value.kind == 'bool':
            attrs['t'] = 'b'
            inner = cell_inner(prefix, value='1' if value.flag else '0')
        elif value.kind == 'text':
            attrs['t'] = 's'
            inner = cell_inner(prefix, value=str(self.book.strings.add(value.text)))
        else:
            inner = cell_inner(prefix, formula=value.formula.text[1:])
            self.formulas_touched = True
        if not inner and not style:
            sheet.put(r, c, None)
        else:
            sheet.put(r, c, Cell(attrs, inner))
        self.mark(info, [(r, c)], new=value.kind == 'formula')

    def check_formula(self, value: Value) -> None:
        for ref in value.formula.refs:
            if ref.sheet is not None:
                target = self.book.info(ref.sheet)
                if target.kind != 'worksheet':
                    raise EditError(f'công thức trỏ tới "{ref.sheet}" là trang biểu đồ')

    def old(self, sheet: Worksheet, r: int, c: int) -> str:
        cell = sheet.get(r, c)
        if cell is None:
            return '(trống)'
        text, _ = cell.formula()
        if text:
            return '=' + text
        kind, decimals = self.kind_of(cell.style)
        return show(self.book.value(cell), kind, self.book.date1904, decimals)

    def new_text(self, value: Value) -> str:
        if value.kind == 'formula':
            return value.formula.text
        if value.kind == 'blank':
            return '(trống)'
        if value.kind == 'bool':
            return 'TRUE' if value.flag else 'FALSE'
        if value.kind == 'text':
            return show(value.text)
        return show(value.number, value.hint if value.hint in ('percent', 'date', 'datetime') else 'number',
                    self.book.date1904, value.decimals)

    def styled(self, change: ChangeInput) -> dict:
        options = {}
        if change.bold is not None:
            options['bold'] = change.bold
        if change.italic is not None:
            options['italic'] = change.italic
        if change.font_color is not None:
            if not _COLOR.fullmatch(change.font_color.strip()):
                raise EditError(f'font_color "{change.font_color}" cần dạng #RRGGBB')
            options['color'] = change.font_color.strip()
        if change.fill_color is not None:
            color = change.fill_color.strip()
            if color.lower() != 'none' and not _COLOR.fullmatch(color):
                raise EditError(f'fill_color "{change.fill_color}" cần dạng #RRGGBB hoặc "none"')
            options['fill'] = 'none' if color.lower() == 'none' else color
        if change.align is not None:
            options['align'] = change.align
        if change.number_format is not None:
            options['number_format'] = number_code(change.number_format, change.decimals)
        elif change.decimals is not None:
            raise EditError('decimals cần đi cùng number_format')
        return options

    def apply_styles(self, info: SheetInfo, sheet: Worksheet, area, options: dict, source: str | None) -> int:
        """Đổi kiểu cho mọi ô trong vùng (ô chưa có thì tạo ô trống mang kiểu). Trả số ô."""
        count = 0
        for r in range(area[0], area[2] + 1):
            for c in range(area[1], area[3] + 1):
                existing = sheet.get(r, c)
                base = self.style_from(info, sheet, source, area, r, c)
                if base is None:
                    base = existing.style if existing is not None else sheet.default_style(r, c)
                style = self.book.styles.derive(base, **options) if options else base
                if existing is not None:
                    if existing.style == style:
                        continue
                    existing.attrs['s'] = str(style)
                    sheet.put(r, c, existing)
                elif style:
                    sheet.put(r, c, Cell({'r': address(r, c), 's': str(style)}, ''))
                else:
                    continue
                count += 1
                self.formatted.setdefault(info.part, set()).add((r, c))
        return count

    # ---------- thao tác ----------

    def apply(self, change: ChangeInput) -> None:
        action = change.action
        if action != 'rename_sheet' and change.new_name is not None:
            raise EditError(f'{action} không dùng new_name (chỉ rename_sheet)')
        if action not in ('set', 'fill', 'clear', 'format'):
            extra = [name for name in ('values', 'value', 'format_from', 'bold', 'italic', 'font_color', 'fill_color',
                                       'number_format', 'decimals', 'align') if getattr(change, name) is not None]
            if extra:
                raise EditError(f'{action} không dùng {", ".join(extra)}; ghi hay định dạng ô thì thêm một thay đổi set, '
                                'fill hoặc format sau đó')
            if action in ('add_sheet', 'rename_sheet') and change.range is not None:
                raise EditError(f'{action} không dùng range')
        getattr(self, f'_{action}')(change)

    def _set(self, change: ChangeInput) -> None:
        info, sheet = self.worksheet(change.sheet)
        if not change.values:
            raise EditError('set cần values (lưới giá trị), không để trống')
        if change.value is not None:
            raise EditError('set dùng values; value chỉ dành cho fill')
        top, left, bottom, right = parse_area(change.range, info.name)
        height = len(change.values)
        width = max(len(row) for row in change.values)
        if (bottom, right) != (top, left) and (bottom - top + 1, right - left + 1) != (height, width):
            raise EditError(f'range {change.range} là {bottom - top + 1}×{right - left + 1} ô nhưng values là '
                            f'{height}×{width}; cho range là ô đầu hoặc đúng cỡ lưới')
        area = (top, left, top + height - 1, left + width - 1)
        if area[2] >= refs.MAX_ROWS or area[3] >= refs.MAX_COLS:
            raise EditError('values vượt ra ngoài giới hạn của Excel')
        targets = [(top + i, left + j, raw) for i, row in enumerate(change.values) for j, raw in enumerate(row)
                   if raw is not None]
        self.count(len(targets))
        self.guard(info, sheet, area)
        self.unshare(sheet, area)
        headers = self._table_headers(sheet, area)
        before = [(r, c, self.old(sheet, r, c)) for r, c, _ in targets[:3]]
        written = []
        for r, c, raw in targets:
            existing = sheet.get(r, c)
            kind, _ = self.kind_of(existing.style if existing else sheet.default_style(r, c))
            try:
                value = parse_value(raw, kind, self.book.date1904)
                if value.kind == 'formula':
                    self.check_formula(value)
                value = self._header_value(headers, info, sheet, r, c, value)
            except EditError as error:
                raise EditError(f'ô {address(r, c)}: {error}') from None
            self.write(info, sheet, r, c, value, self.style_from(info, sheet, change.format_from, area, r, c))
            written.append((r, c, value))
        options = self.styled(change)
        if options:
            self.apply_styles(info, sheet, area, options, None)
        self._grow_tables(info, sheet, area)
        if len(written) == 1:
            r, c, value = written[0]
            self.lines.append(f'{area_label(info.name, r, c, r, c)}: {before[0][2]} → {self.new_text(value)}')
        elif written:
            formulas = sum(value.kind == 'formula' for _, _, value in written)
            extra = f', {formulas} công thức' if formulas else ''
            self.lines.append(f'{area_label(info.name, *area)}: ghi {len(written)} ô{extra}')
        if options:
            self.lines.append(f'{area_label(info.name, *area)}: {describe_style(change)}')

    def _fill(self, change: ChangeInput) -> None:
        info, sheet = self.worksheet(change.sheet)
        if change.value is None:
            raise EditError('fill cần value (giá trị hoặc công thức)')
        if change.values is not None:
            raise EditError('fill dùng value; values chỉ dành cho set')
        area = parse_area(change.range, info.name, sheet.bounds())
        total = (area[2] - area[0] + 1) * (area[3] - area[1] + 1)
        self.count(total)
        self.guard(info, sheet, area)
        self.unshare(sheet, area)
        headers = self._table_headers(sheet, area)
        first = sheet.get(area[0], area[1])
        kind, _ = self.kind_of(first.style if first else sheet.default_style(area[0], area[1]))
        try:
            base = parse_value(change.value, kind, self.book.date1904)
            if base.kind == 'formula':
                self.check_formula(base)
        except EditError as error:
            raise EditError(f'ô {address(area[0], area[1])}: {error}') from None
        for r in range(area[0], area[2] + 1):
            for c in range(area[1], area[3] + 1):
                value = base
                if base.kind == 'formula' and (r, c) != (area[0], area[1]):
                    text = refs.rewrite(base.formula.text[1:], refs.relative(r - area[0], c - area[1]))
                    try:
                        value = Value('formula', formula=parse('=' + text))
                    except FormulaError:
                        raise EditError(f'chép công thức {base.formula.text} tới ô {address(r, c)} thì tham chiếu ra '
                                        'ngoài trang tính; dùng $ để giữ cố định') from None
                elif base.kind not in ('formula', 'blank'):
                    existing = sheet.get(r, c)
                    cell_kind, _ = self.kind_of(existing.style if existing else sheet.default_style(r, c))
                    value = parse_value(change.value, cell_kind, self.book.date1904)
                try:
                    value = self._header_value(headers, info, sheet, r, c, value)
                except EditError as error:
                    raise EditError(f'ô {address(r, c)}: {error}') from None
                self.write(info, sheet, r, c, value, self.style_from(info, sheet, change.format_from, area, r, c))
        options = self.styled(change)
        if options:
            self.apply_styles(info, sheet, area, options, None)
        self._grow_tables(info, sheet, area)
        how = f'công thức {base.formula.text}' + (' (chép theo từng ô)' if total > 1 else '') \
            if base.kind == 'formula' else self.new_text(base)
        self.lines.append(f'{area_label(info.name, *area)}: điền {how}' + (f' vào {total} ô' if total > 1 else ''))
        if options:
            self.lines.append(f'{area_label(info.name, *area)}: {describe_style(change)}')

    def _clear(self, change: ChangeInput) -> None:
        info, sheet = self.worksheet(change.sheet)
        bounds = sheet.bounds()
        area = parse_area(change.range, info.name, bounds)
        if bounds is None:
            self.lines.append(f'{area_label(info.name, *area)}: đã trống sẵn')
            return
        self.guard(info, sheet, area)
        for table in meta.tables(self.book, sheet):
            if table.header and meta.overlaps(area, (table.r1, table.c1, table.r1, table.c2)):
                raise EditError(f'hàng {table.r1 + 1} là tên cột của Bảng "{table.name}", không xóa được; đổi tên cột '
                                'bằng set')
        self.unshare(sheet, area)
        cleared = 0
        for r in range(max(area[0], bounds[0]), min(area[2], bounds[2]) + 1):
            row = sheet.rows.get(r)
            if row is None:
                continue
            for c in [col for col in row.cells if area[1] <= col <= area[3]]:
                cell = row.cells[c]
                if cell.empty:
                    continue
                cleared += 1
                self.count(1)
                if cell.style:
                    sheet.put(r, c, Cell({'r': address(r, c), 's': str(cell.style)}, ''))
                else:
                    sheet.put(r, c, None)
                self.mark(info, [(r, c)])
        self.lines.append(f'{area_label(info.name, *area)}: xóa nội dung {cleared} ô, giữ định dạng')

    def _format(self, change: ChangeInput) -> None:
        info, sheet = self.worksheet(change.sheet)
        if change.values is not None or change.value is not None:
            raise EditError('format chỉ đổi định dạng; ghi giá trị thì dùng set hoặc fill')
        options = self.styled(change)
        if not options and not change.format_from:
            raise EditError('format cần ít nhất một định dạng (bold, italic, font_color, fill_color, number_format, '
                            'align) hoặc format_from')
        area = parse_area(change.range, info.name, sheet.bounds() or (0, 0, 0, 0))
        self.count((area[2] - area[0] + 1) * (area[3] - area[1] + 1))
        count = self.apply_styles(info, sheet, area, options, change.format_from)
        what = describe_style(change) or f'chép định dạng từ {change.format_from}'
        self.lines.append(f'{area_label(info.name, *area)}: {what}' + ('' if count else ' (ô đã có sẵn định dạng này)'))

    def _insert_rows(self, change: ChangeInput) -> None:
        self._shift(change, 'row', delete=False)

    def _delete_rows(self, change: ChangeInput) -> None:
        self._shift(change, 'row', delete=True)

    def _insert_columns(self, change: ChangeInput) -> None:
        self._shift(change, 'col', delete=False)

    def _delete_columns(self, change: ChangeInput) -> None:
        self._shift(change, 'col', delete=True)

    def _shift(self, change: ChangeInput, axis: str, delete: bool) -> None:
        from features.documents.workbook_edit import structure
        info, sheet = self.worksheet(change.sheet)
        low, high = parse_span(change.range, info.name, axis)
        count = high - low + 1
        broken, totals = structure.shift(self.book, info, sheet, axis, low, count, delete)
        for bucket in (self.changed, self.new, self.formatted):
            if info.part in bucket:
                bucket[info.part] = structure.remap(bucket[info.part], axis, low, count, delete)
        self.structural.add(info.name)
        self.formulas_touched = True
        # Dòng thay đổi ghi vùng là cả hàng (9:10) hay cả cột (G:H), như tham chiếu Excel.
        def span(first: int, last: int) -> str:
            return f'{first + 1}:{last + 1}' if axis == 'row' else f'{column_letter(first)}:{column_letter(last)}'
        unit = 'hàng' if axis == 'row' else 'cột'
        where = f'{sheet_label(info.name)}!{span(low, high)}'
        if delete:
            moved = 'các hàng phía dưới dời lên' if axis == 'row' else 'các cột bên phải dời sang'
            self.lines.append(f'{where}: xóa {count} {unit}; {moved}')
        else:
            near = (f'hàng {low}' if axis == 'row' else f'cột {column_letter(low - 1)}') if low > 0 else ''
            self.lines.append(f'{where}: chèn {count} {unit} trống' + (f' (theo định dạng {near})' if near else ''))
        if totals:
            self.lines.append(f'{sheet_label(info.name)}!{span(high + 1, high + 1)}: {totals} công thức tổng nới ra để '
                              f'tính cả {unit} mới')
        if broken:
            self.notes.append(f'{broken} công thức hoặc tên vùng trỏ vào {unit} vừa xóa nên thành #REF!.')

    def _add_sheet(self, change: ChangeInput) -> None:
        from features.documents.workbook_edit import structure
        name = check_sheet_name(change.sheet, self.book)
        structure.add_sheet(self.book, name)
        self.lines.append(f'{sheet_label(name)}: thêm trang tính mới')

    def _rename_sheet(self, change: ChangeInput) -> None:
        from features.documents.workbook_edit import structure
        info = self.book.info(change.sheet)
        if not change.new_name:
            raise EditError('rename_sheet cần new_name')
        name = check_sheet_name(change.new_name, self.book, info.name)
        if self.book.locked:
            raise EditError('cấu trúc tệp đang khóa (Protect Workbook) nên không đổi tên trang được')
        old = info.name
        structure.rename_sheet(self.book, info, name)
        self.formulas_touched = True
        self.lines.append(f'{sheet_label(name)}: đổi tên từ "{old}"; công thức, biểu đồ, tên vùng trỏ tới trang này đổi theo')

    # ---------- Bảng (Table) ----------

    def _table_headers(self, sheet: Worksheet, area) -> dict[tuple[int, int], meta.Table]:
        out = {}
        for table in meta.tables(self.book, sheet):
            if table.header and meta.overlaps(area, (table.r1, table.c1, table.r1, table.c2)):
                for c in range(max(area[1], table.c1), min(area[3], table.c2) + 1):
                    out[(table.r1, c)] = table
        return out

    def _header_value(self, headers, info: SheetInfo, sheet: Worksheet, r: int, c: int, value: Value) -> Value:
        """Ô tên cột của Bảng: phải là chữ, và tên trong định nghĩa Bảng đổi theo (Excel báo tệp hỏng khi lệch)."""
        table = headers.get((r, c))
        if table is None:
            return value
        if value.kind in ('formula', 'blank'):
            raise EditError(f'ô {address(r, c)} là tên cột của Bảng "{table.name}", cần là chữ')
        text = value.text if value.kind == 'text' else self.new_text(value).strip('"')
        text = ' '.join(text.split())
        columns = table.columns()
        index = c - table.c1
        others = {(column.get('name') or '').casefold() for position, column in enumerate(columns) if position != index}
        if not text or text.casefold() in others:
            raise EditError(f'tên cột "{text}" trống hoặc trùng tên cột khác của Bảng "{table.name}"')
        if 0 <= index < len(columns):
            from features.documents.workbook_edit import structure
            old = columns[index].get('name') or ''
            columns[index].set('name', text)
            if old != text:
                structure.rename_table_column(self.book, sheet, table, old, text)
                self.formulas_touched = True
            self.book.package.write_xml(table.part, table.root)
        return Value('text', text=text)

    def _grow_tables(self, info: SheetInfo, sheet: Worksheet, area) -> None:
        """Ghi ngay cạnh phải hay ngay dưới một Bảng thì Bảng nới ra như Excel làm khi gõ (cột mới có tên ở hàng tiêu
        đề; hàng mới chép công thức của các cột tính)."""
        for table in meta.tables(self.book, sheet):
            grown = False
            while table.header and area[1] <= table.c2 + 1 <= area[3] and area[0] <= table.r2 and area[2] >= table.r1:
                header = sheet.get(table.r1, table.c2 + 1)
                name = self.book.value(header) if header is not None else None
                if not isinstance(name, str) or not name.strip():
                    break
                if name.strip().casefold() in {(column.get('name') or '').casefold() for column in table.columns()}:
                    break
                table.set_area(table.r1, table.c1, table.r2, table.c2 + 1)
                table.add_column(' '.join(name.split()))
                grown = True
            while not table.totals and area[0] <= table.r2 + 1 <= area[2] and area[1] <= table.c2 and area[3] >= table.c1:
                row = sheet.rows.get(table.r2 + 1)
                if row is None or not any(table.c1 <= col <= table.c2 and not cell.empty for col, cell in row.cells.items()):
                    break
                table.set_area(table.r1, table.c1, table.r2 + 1, table.c2)
                self._fill_calculated(info, sheet, table, table.r2)
                grown = True
            if grown:
                self.book.package.write_xml(table.part, table.root)
                self.lines.append(f'{area_label(info.name, table.r1, table.c1, table.r2, table.c2)}: Bảng "{table.name}" nới '
                                  'ra để gồm ô vừa ghi')

    def _fill_calculated(self, info: SheetInfo, sheet: Worksheet, table: meta.Table, row: int) -> None:
        texts = formula_map(sheet)
        for position, column in enumerate(table.columns()):
            if not any(child.tag.endswith('calculatedColumnFormula') for child in column):
                continue
            col = table.c1 + position
            existing = sheet.get(row, col)
            if existing is not None and not existing.empty:
                continue
            above = texts.get((row - 1, col))
            if not above or not above[0]:
                continue
            style = sheet.get(row - 1, col).style if sheet.get(row - 1, col) else 0
            text = refs.rewrite(above[0], refs.relative(1, 0))
            attrs = {'r': address(row, col)}
            if style:
                attrs['s'] = str(style)
            sheet.put(row, col, Cell(attrs, cell_inner(sheet.prefix, formula=text)))
            self.mark(info, [(row, col)])
            self.formulas_touched = True


def number_code(kind: str, decimals: int | None) -> int | str:
    fraction = ('.' + '0' * min(decimals, 4)) if decimals else ''
    return {
        'general': 0, 'text': 49, 'number': f'#,##0{fraction}', 'percent': f'0{fraction}%',
        'vnd': f'#,##0{fraction} "₫"', 'usd': f'"$"#,##0{fraction if decimals is not None else ".00"}', 'date': 'dd/mm/yyyy',
    }[kind]


def describe_style(change: ChangeInput) -> str:
    parts = []
    if change.bold is not None:
        parts.append('in đậm' if change.bold else 'bỏ in đậm')
    if change.italic is not None:
        parts.append('in nghiêng' if change.italic else 'bỏ in nghiêng')
    if change.font_color:
        parts.append(f'chữ màu {change.font_color}')
    if change.fill_color:
        parts.append('bỏ màu nền' if change.fill_color.lower() == 'none' else f'nền {change.fill_color}')
    if change.number_format:
        names = {'general': 'kiểu chung', 'text': 'kiểu chữ', 'number': 'số', 'percent': 'phần trăm', 'vnd': 'tiền đồng',
                 'usd': 'đô la', 'date': 'ngày'}
        parts.append(f'định dạng {names[change.number_format]}' + (f', {change.decimals} số lẻ' if change.decimals else ''))
    if change.align:
        parts.append({'left': 'căn trái', 'center': 'căn giữa', 'right': 'căn phải'}[change.align])
    if change.format_from:
        parts.append(f'chép định dạng từ {change.format_from}')
    return ', '.join(parts)


def check_sheet_name(name: str, book: Book, current: str | None = None) -> str:
    name = ' '.join(str(name or '').split())
    if not name or len(name) > 31 or _BAD_NAME.search(name) or name.startswith("'") or name.endswith("'"):
        raise EditError(f'tên trang "{name[:40]}" không hợp lệ: 1–31 ký tự, không chứa \\ / ? * [ ] : và không mở '
                        "hay kết thúc bằng dấu '")
    if name.casefold() == 'history':
        raise EditError('Excel dành riêng tên trang "History"')
    for item in book.sheets:
        if item.name.casefold() == name.casefold() and item.name != current:
            raise EditError(f'đã có trang tên "{item.name}"')
    return name


def describe_change(change: ChangeInput) -> str:
    where = f' {change.range}' if change.range else ''
    return f'{change.action} {sheet_label(change.sheet)}{where}'


def apply(data: bytes, changes: list[ChangeInput], today: date) -> Outcome:
    """Áp các thay đổi lên tệp; lỗi là EditError đã ghi rõ thay đổi thứ mấy."""
    book = Book(data)
    session = Session(book, today)
    for number, change in enumerate(changes, start=1):
        try:
            session.apply(change)
        except EditError as error:
            raise EditError(f'Thay đổi {number} ({describe_change(change)}): {error}') from None
        except refs.Unsupported as error:
            raise EditError(f'Thay đổi {number} ({describe_change(change)}): tệp có {error}, Peto chưa chèn/xóa được '
                            'an toàn ở trang này') from None
    results: list[str] = []
    if session.formulas_touched or session.changed:
        report = recalculate(book, session.changed, session.structural, session.new, today)
        cycles = {(sheet, row, col) for sheet, row, col in report.cycles}
        new_cells = {(info.name, row, col) for info in book.data_sheets() for row, col in session.new.get(info.part, ())}
        looped = sorted(new_cells & cycles)
        if looped:
            sheet, row, col = looped[0]
            raise EditError(f'Công thức mới ở {area_label(sheet, row, col, row, col)} tạo vòng tham chiếu (ô tự trỏ lại '
                            'chính nó qua các ô khác). Sửa công thức rồi gọi lại.')
        if report.errors:
            sheet, row, col, text, code = report.errors[0]
            hint = engine.ERROR_HELP.get(code, 'kiểm tra lại dữ liệu ô được trỏ tới')
            more = f' (và {len(report.errors) - 1} ô khác)' if len(report.errors) > 1 else ''
            raise EditError(f'Công thức mới ở {area_label(sheet, row, col, row, col)} (={text}) ra {code}{more}: {hint}. '
                            'Sửa công thức, hoặc bọc IFERROR nếu lỗi là cố ý, rồi gọi lại.')
        results = summarize_results(book, report.results)
        if report.computed:
            session.notes.append(f'Đã tính lại {report.computed} công thức sẵn có trỏ tới ô vừa đổi.')
        if report.left:
            functions = sorted({name.removeprefix('_XLFN.').removeprefix('_XLWS.') for _, _, names in report.left
                                for name in names if name.removeprefix('_XLFN.').removeprefix('_XLWS.') not in FUNCTIONS})
            cells = ', '.join(f'{sheet_label(sheet)}!{cell}' for sheet, cell, _ in report.left[:5])
            more = f' và {len(report.left) - 5} ô khác' if len(report.left) > 5 else ''
            session.notes.append(f'{len(report.left)} công thức ({cells}{more}) Excel sẽ tự tính khi mở tệp'
                                 + (f' (dùng {", ".join(functions[:6])})' if functions else '')
                                 + '; trình xem khác có thể hiện trống ở đó.')
        book.calc_on_load()
        book.drop_calc_chain()
    changed: dict[str, list[tuple[int, int, int, int]]] = {}
    for info in book.data_sheets():
        cells = session.changed.get(info.part, set()) | session.formatted.get(info.part, set())
        if cells:
            changed[info.name] = compress(cells)
    output = book.finish()
    return Outcome(output, session.lines, changed, results, session.notes, book.macro,
                   [info.name for info in book.data_sheets()])


def run(data: bytes, changes: list[dict], today: str, excerpt_chars: int) -> dict:
    """Hàm thuần cho tiến trình con (anyio.to_process): sửa tệp rồi đọc lại tệp mới cho Peto. Không ném lỗi: lỗi của tệp
    hay của thay đổi trả về {'error': lời giải thích}; lỗi lạ kèm 'internal' để máy chủ ghi log."""
    try:
        outcome = apply(data, [ChangeInput.model_validate(item) for item in changes], date.fromisoformat(today))
    except EditError as error:
        return {'error': str(error)}
    except Exception as error:   # lỗi lập trình: không để hỏng cả lượt chat
        return {'error': 'Peto chưa sửa được tệp này do lỗi bên trong bộ sửa.', 'internal': f'{type(error).__name__}: '
                f'{str(error)[:300]}'}
    from features.documents.workbook_reader import read_workbook
    readout = read_workbook(outcome.data, excerpt_chars)
    return {'data': outcome.data, 'lines': outcome.lines, 'changed': outcome.changed, 'results': outcome.results,
            'notes': outcome.notes, 'macro': outcome.macro, 'sheets': outcome.sheets, 'readout': readout.get('text', ''),
            'readout_partial': readout.get('status') == 'partial'}


def changed_line(changed: dict[str, list[tuple[int, int, int, int]]], limit: int = 3_000) -> str:
    """Dòng "Ô đã sửa: …" lưu trong nội dung tài liệu: Peto đọc được ở lượt sau, lưới xem dùng để tô ô đã sửa."""
    parts = [area_label(sheet, *area) for sheet, areas in changed.items() for area in areas]
    text = ', '.join(parts)
    if len(text) > limit:
        text = text[:text.rfind(', ', 0, limit)] + ', …'
    return text


def summarize_results(book: Book, results: dict, limit: int = 12) -> list[str]:
    """Kết quả các công thức mới, theo từng cột: vài ô đầu và ô cuối, đủ để Peto nêu số mà không tự tính lại."""
    by_column: dict[tuple[str, int], list[tuple[int, object]]] = {}
    for (sheet, row, col), value in results.items():
        by_column.setdefault((sheet, col), []).append((row, value))
    lines = []
    for (sheet, col), items in sorted(by_column.items()):
        items.sort()
        info, worksheet = book.sheet(sheet)
        shown = items if len(items) <= 4 else items[:2] + items[-2:]
        parts = []
        for row, value in shown:
            cell = worksheet.get(row, col)
            kind, decimals = book.styles.kind(cell.style) if cell else ('number', 0)
            parts.append(f'{address(row, col)} = {show(value, kind, book.date1904, decimals)}')
        if len(items) > 4:
            parts.insert(2, '…')
        lines.append(f'{sheet_label(sheet)}: ' + '; '.join(parts))
        if len(lines) >= limit:
            break
    return lines
