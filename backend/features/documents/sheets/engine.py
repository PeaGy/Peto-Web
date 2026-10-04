"""Tính công thức như Excel để ghi sẵn kết quả vào tệp (Excel tính lại khi mở) và hiện trong lưới xem.

XlsxWriter không tính công thức: nó ghi 0 làm kết quả đọng lại, nên trình xem trên điện thoại, LibreOffice (mặc định không
tính lại tệp Excel) và thẻ xem trước sẽ hiện 0. Ở đây tính đúng theo quy tắc của Excel cho các hàm trong
formula.FUNCTIONS: kiểu dữ liệu, làm tròn kiểu thập phân 15 chữ số, so sánh, điều kiện COUNTIF, dò VLOOKUP/MATCH.

Ô được tính theo thứ tự phụ thuộc (sắp xếp tô pô), nên chuỗi ô nối nhau dài không làm tràn đệ quy; vòng tham chiếu báo
lỗi. Giá trị: float (số, cả ngày tháng dạng số sê-ri), str, bool, None (ô trống), XLError.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import deque
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation

from features.documents.sheets.formula import MAX_COLS, MAX_ROWS, Formula, Ref, address

EPOCH = date(1899, 12, 30)
MIN_SERIAL, MAX_SERIAL = 61, 2_958_465      # 01/03/1900 … 31/12/9999; chưa mô phỏng ngày 29/02/1900 không có thật
MAX_RANGE_CELLS = 2_000_000


class XLError:
    """Giá trị lỗi của Excel (#DIV/0!, #VALUE!…), là một giá trị chứ không phải ngoại lệ, như trong Excel."""
    __slots__ = ('code',)

    def __init__(self, code: str):
        self.code = code

    def __eq__(self, other):
        return isinstance(other, XLError) and other.code == self.code

    def __hash__(self):
        return hash(self.code)

    def __repr__(self):
        return self.code


DIV0, VALUE, REF, NA, NUM = (XLError(code) for code in ('#DIV/0!', '#VALUE!', '#REF!', '#N/A', '#NUM!'))
# Không phải lỗi Excel: dò gần đúng trên cột chưa sắp xếp. Excel vẫn ra một kết quả khó đoán, nên từ chối để model sửa.
UNSORTED = XLError('#UNSORTED')
ERROR_HELP = {
    '#DIV/0!': 'chia cho 0 hoặc trung bình của vùng không có số',
    '#VALUE!': 'sai kiểu dữ liệu: chữ trong phép tính, hay cả vùng ô ở chỗ chỉ nhận một ô (dùng SUM, SUMIFS hoặc '
               'SUMPRODUCT cho vùng)',
    '#REF!': 'tham chiếu ra ngoài vùng (số cột của VLOOKUP, INDEX lớn hơn vùng)',
    '#N/A': 'không tìm thấy giá trị cần dò',
    '#NUM!': 'số không hợp lệ (căn số âm, ngày ngoài khoảng, k của LARGE/SMALL…)',
    '#UNSORTED': 'dò gần đúng (VLOOKUP/HLOOKUP thiếu FALSE, MATCH kiểu 1 hay -1) cần cột dò cùng kiểu và đã sắp xếp; muốn '
                 'dò chính xác thì thêm FALSE (VLOOKUP) hoặc 0 (MATCH)',
}


class _Fail(Exception):
    """Dừng một hàm khi gặp giá trị lỗi; giá trị lỗi đó thành kết quả của hàm."""

    def __init__(self, error: XLError):
        self.error = error


MISSING = object()   # tham số bỏ trống, như IF(A1,,1)


class SheetData:
    """Một trang tính để tính: kích thước vùng có dữ liệu và giá trị từng ô (ô trống không có khóa)."""

    def __init__(self, name: str, nrows: int, ncols: int):
        self.name, self.nrows, self.ncols = name, nrows, ncols
        self.values: dict[tuple[int, int], object] = {}


class Range:
    """Vùng ô. Ô ngoài vùng có dữ liệu luôn trống, nên chỉ duyệt phần giao với vùng dữ liệu."""
    __slots__ = ('sheet', 'r1', 'c1', 'r2', 'c2')

    def __init__(self, sheet: SheetData, r1: int, c1: int, r2: int, c2: int):
        self.sheet, self.r1, self.c1, self.r2, self.c2 = sheet, r1, c1, r2, c2

    @property
    def height(self) -> int:
        return self.r2 - self.r1 + 1

    @property
    def width(self) -> int:
        return self.c2 - self.c1 + 1

    @property
    def area(self) -> int:
        return self.height * self.width

    def get(self, i: int, j: int):
        if not (0 <= i < self.height and 0 <= j < self.width):
            return None
        return self.sheet.values.get((self.r1 + i, self.c1 + j))

    def used(self):
        """(i, j, giá trị) của các ô có dữ liệu trong vùng, theo từng hàng."""
        for r in range(self.r1, min(self.r2, self.sheet.nrows - 1) + 1):
            for c in range(self.c1, min(self.c2, self.sheet.ncols - 1) + 1):
                value = self.sheet.values.get((r, c))
                if value is not None:
                    yield r - self.r1, c - self.c1, value

    def values(self) -> list:
        return [value for _, _, value in self.used()]

    def resized(self, height: int, width: int) -> 'Range':
        return Range(self.sheet, self.r1, self.c1, self.r1 + height - 1, self.c1 + width - 1)

    def vector(self) -> list:
        """Một hàng hay một cột thành danh sách, cắt ở phần có dữ liệu (phần sau toàn ô trống)."""
        if self.width == 1:
            last = min(self.r2, self.sheet.nrows - 1) - self.r1
            return [self.get(i, 0) for i in range(max(0, last + 1))]
        last = min(self.c2, self.sheet.ncols - 1) - self.c1
        return [self.get(0, j) for j in range(max(0, last + 1))]


def positions(ranges: list[Range]) -> tuple[list[tuple[int, int]], int]:
    """Các vị trí (i, j) chạm ô có dữ liệu ở ít nhất một vùng (các vùng cùng cỡ), và số vị trí còn lại trống ở mọi vùng."""
    height, width = ranges[0].height, ranges[0].width
    i_hi = max(min(height - 1, rg.sheet.nrows - 1 - rg.r1) for rg in ranges)
    j_hi = max(min(width - 1, rg.sheet.ncols - 1 - rg.c1) for rg in ranges)
    if i_hi < 0 or j_hi < 0:
        return [], height * width
    inside = [(i, j) for i in range(i_hi + 1) for j in range(j_hi + 1)]
    return inside, height * width - len(inside)


# ---------- đổi kiểu như Excel ----------
_NUMERIC = re.compile(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(%?)\s*')


def is_number(value) -> bool:
    return isinstance(value, float)


def scalar(value):
    """Giá trị đơn: vùng một ô thành giá trị ô đó; vùng nhiều ô ở chỗ cần một giá trị là #VALUE!."""
    if isinstance(value, Range):
        return value.get(0, 0) if value.height == 1 and value.width == 1 else VALUE
    if value is MISSING:
        return None
    return value


def parse_number(text: str) -> float | None:
    match = _NUMERIC.fullmatch(text)
    if not match:
        return None
    number = float(match.group(1))
    return number / 100 if match.group(2) else number


def to_number(value):
    if isinstance(value, XLError):
        return value
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        number = parse_number(value)
        return VALUE if number is None else number
    return VALUE


def general(number: float) -> str:
    """Số kiểu General của Excel khi ghép chuỗi: tối đa 15 chữ số có nghĩa, dấu chấm thập phân."""
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    text = f'{number:.15g}'
    if 'e' in text:
        mantissa, exponent = text.split('e')
        return f'{mantissa}E{int(exponent):+03d}'
    return text


def to_text(value):
    if isinstance(value, XLError):
        return value
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, float):
        return general(value)
    return value


def to_bool(value):
    if isinstance(value, XLError):
        return value
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value != 0
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in ('TRUE', 'FALSE'):
            return upper == 'TRUE'
    return VALUE


def round15(number: float) -> float:
    return float(f'{number:.15g}')


def _kind(value) -> int:
    return 0 if isinstance(value, float) else 1 if isinstance(value, str) else 2


def order(a, b) -> int:
    """So sánh như Excel: số < chữ < TRUE/FALSE; chữ không phân biệt hoa thường; số so ở 15 chữ số có nghĩa."""
    if a is None:
        a = '' if isinstance(b, str) else False if isinstance(b, bool) else 0.0
    if b is None:
        b = '' if isinstance(a, str) else False if isinstance(a, bool) else 0.0
    ka, kb = _kind(a), _kind(b)
    if ka != kb:
        return (ka > kb) - (ka < kb)
    if ka == 0:
        a, b = round15(a), round15(b)
    elif ka == 1:
        a, b = a.casefold(), b.casefold()
    return (a > b) - (a < b)


def _check(value):
    if isinstance(value, XLError):
        raise _Fail(value)
    return value


def _num(value) -> float:
    return _check(to_number(_check(scalar(value))))


def _text(value) -> str:
    return _check(to_text(_check(scalar(value))))


def _int(value) -> int:
    number = _num(value)
    return int(number)      # Excel cắt phần lẻ về phía 0 cho số lượng như số ký tự, số chữ số


def _finite(number: float):
    if isinstance(number, complex) or not math.isfinite(number):
        raise _Fail(NUM)
    return float(number)


# ---------- điều kiện kiểu COUNTIF ----------
def _wildcard(pattern: str):
    parts = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == '~' and index + 1 < len(pattern) and pattern[index + 1] in '*?~':
            parts.append(re.escape(pattern[index + 1]))
            index += 2
            continue
        parts.append('.*' if char == '*' else '.' if char == '?' else re.escape(char))
        index += 1
    return re.compile(''.join(parts), re.I | re.S)


def criterion(raw):
    """Điều kiện của COUNTIF/SUMIF/…IFS thành hàm kiểm tra một giá trị ô."""
    value = _check(scalar(raw))
    if value is None:
        value = ''
    if isinstance(value, bool):
        return lambda cell: isinstance(cell, bool) and cell == value
    if isinstance(value, float):
        target = round15(value)
        return lambda cell: is_number(cell) and round15(cell) == target
    match = re.match(r'(<=|>=|<>|<|>|=)?(.*)', value, re.S)
    op, operand = match.group(1) or '', match.group(2)
    if operand == '':
        if op == '':
            return lambda cell: cell is None or cell == ''
        if op == '=':
            return lambda cell: cell is None
        if op == '<>':
            return lambda cell: cell is not None and cell != ''
    number = parse_number(operand)
    if number is not None:
        target = round15(number)
        tests = {'': lambda c: c == target, '=': lambda c: c == target, '<>': lambda c: c != target,
                 '<': lambda c: c < target, '>': lambda c: c > target, '<=': lambda c: c <= target, '>=': lambda c: c >= target}
        test = tests[op]
        if op == '<>':
            return lambda cell: not (is_number(cell) and round15(cell) == target)
        return lambda cell: is_number(cell) and test(round15(cell))
    upper = operand.strip().upper()
    if upper in ('TRUE', 'FALSE') and op in ('', '=', '<>'):
        flag = upper == 'TRUE'
        if op == '<>':
            return lambda cell: not (isinstance(cell, bool) and cell == flag)
        return lambda cell: isinstance(cell, bool) and cell == flag
    if op in ('', '=', '<>'):
        pattern = _wildcard(operand)
        if op == '<>':
            return lambda cell: not (isinstance(cell, str) and pattern.fullmatch(cell))
        return lambda cell: isinstance(cell, str) and bool(pattern.fullmatch(cell))
    folded = operand.casefold()
    compare = {'<': lambda a: a < folded, '>': lambda a: a > folded, '<=': lambda a: a <= folded, '>=': lambda a: a >= folded}[op]
    return lambda cell: isinstance(cell, str) and compare(cell.casefold())


def _same_shape(ranges: list) -> list[Range]:
    for rg in ranges:
        if not isinstance(rg, Range):
            raise _Fail(VALUE)
    if any(rg.height != ranges[0].height or rg.width != ranges[0].width for rg in ranges):
        raise _Fail(VALUE)
    return ranges


def _matching(ranges: list[Range], tests) -> tuple[list[tuple[int, int]], int]:
    """Vị trí mà mọi vùng điều kiện đều khớp; vị trí trống ở mọi vùng chỉ được đếm khi mọi điều kiện nhận ô trống."""
    inside, blank = positions(ranges)
    # Ô lỗi trong vùng điều kiện chỉ là ô không khớp, như Excel; lỗi trong vùng cần cộng thì lan ra (_conditional).
    hits = [(i, j) for i, j in inside if all(not isinstance(rg.get(i, j), XLError) and test(rg.get(i, j))
                                             for rg, test in zip(ranges, tests))]
    blank_hits = blank if all(test(None) for test in tests) else 0
    return hits, blank_hits


# ---------- dò tìm ----------
def _equal_lookup(target, cell) -> bool:
    if isinstance(target, str):
        return isinstance(cell, str) and bool(_wildcard(target).fullmatch(cell))
    if cell is None:
        return False
    return _kind(target) == _kind(cell) and order(target, cell) == 0


def _approximate(target, cells: list, descending: bool = False) -> int:
    """Vị trí (từ 0) theo kiểu dò gần đúng của Excel trên dữ liệu đã sắp xếp: lớn nhất ≤ target (giảm dần: nhỏ nhất ≥)."""
    present = [(index, cell) for index, cell in enumerate(cells) if cell is not None]
    if any(_kind(cell) != _kind(target) for _, cell in present):
        raise _Fail(UNSORTED)
    for (_, first), (_, second) in zip(present, present[1:]):
        if (order(first, second) < 0) if descending else (order(first, second) > 0):
            raise _Fail(UNSORTED)
    found = -1
    for index, cell in present:
        if (order(cell, target) >= 0) if descending else (order(cell, target) <= 0):
            found = index
        else:
            break
    if found < 0:
        raise _Fail(NA)
    return found


def _round(number: float, digits: int, mode) -> float:
    try:
        value = Decimal(f'{number:.15g}')
        result = value.quantize(Decimal(1).scaleb(-digits), rounding=mode)
    except InvalidOperation:
        return number
    return float(result)


def serial(day: date) -> float:
    return float((day - EPOCH).days)


def to_date(value) -> date:
    number = _num(value)
    if not MIN_SERIAL <= number <= MAX_SERIAL:
        raise _Fail(NUM)
    return EPOCH + timedelta(days=int(number))


class Evaluator:
    def __init__(self, sheets: list[SheetData], today: date):
        self.sheets = sheets
        self.today = today
        self.by_name = {sheet.name.casefold(): sheet for sheet in sheets}

    # ---------- tham chiếu ----------
    def sheet_of(self, ref: Ref, current: SheetData) -> SheetData:
        if ref.sheet is None:
            return current
        sheet = self.by_name.get(ref.sheet.casefold())
        if sheet is None:
            raise _Fail(REF)
        return sheet

    def range_of(self, ref: Ref, current: SheetData) -> Range:
        sheet = self.sheet_of(ref, current)
        r1 = 0 if ref.r1 is None else ref.r1
        r2 = MAX_ROWS - 1 if ref.r2 is None else ref.r2
        c1 = 0 if ref.c1 is None else ref.c1
        c2 = MAX_COLS - 1 if ref.c2 is None else ref.c2
        return Range(sheet, r1, c1, r2, c2)

    # ---------- biểu thức ----------
    def evaluate(self, formula: Formula, sheet: SheetData):
        try:
            value = self.node(formula.tree, sheet)
        except _Fail as failure:
            return failure.error
        value = scalar(value)
        if value is None:
            return 0.0
        return value

    def node(self, node, sheet: SheetData):
        kind = node[0]
        if kind in ('num', 'str', 'bool'):
            return node[1]
        if kind == 'ref':
            return self.range_of(node[1], sheet)
        if kind == 'missing':
            return MISSING
        if kind == 'neg':
            return -_num(self.node(node[1], sheet))
        if kind == 'pos':
            return _check(scalar(self.node(node[1], sheet)))
        if kind == 'pct':
            return _num(self.node(node[1], sheet)) / 100
        if kind == 'bin':
            return self.binary(node[1], self.node(node[2], sheet), self.node(node[3], sheet))
        if kind == 'call':
            return self.call(node[1], node[2], sheet)
        raise _Fail(VALUE)

    def binary(self, op: str, left, right):
        if op == '&':
            return _text(left) + _text(right)
        if op in ('=', '<>', '<', '>', '<=', '>='):
            a, b = _check(scalar(left)), _check(scalar(right))
            result = order(a, b)
            return {'=': result == 0, '<>': result != 0, '<': result < 0, '>': result > 0,
                    '<=': result <= 0, '>=': result >= 0}[op]
        x, y = _num(left), _num(right)
        try:
            if op == '+':
                return _finite(x + y)
            if op == '-':
                return _finite(x - y)
            if op == '*':
                return _finite(x * y)
            if op == '/':
                if y == 0:
                    raise _Fail(DIV0)
                return _finite(x / y)
            if x == 0 and y < 0:
                raise _Fail(DIV0)
            if x < 0 and y != int(y):
                raise _Fail(NUM)
            return _finite(x ** y)
        except OverflowError:
            raise _Fail(NUM) from None

    def call(self, name: str, nodes: list, sheet: SheetData):
        # Hàm rẽ nhánh chỉ tính nhánh được chọn, như Excel.
        if name == 'IF':
            condition = _check(to_bool(_check(scalar(self.node(nodes[0], sheet)))))
            if condition:
                chosen = self.node(nodes[1], sheet)
                return 0.0 if chosen is MISSING else chosen
            if len(nodes) < 3:
                return False
            chosen = self.node(nodes[2], sheet)
            return 0.0 if chosen is MISSING else chosen
        if name == 'IFERROR':
            try:
                value = scalar(self.node(nodes[0], sheet))
            except _Fail as failure:
                value = failure.error
            if isinstance(value, XLError):
                fallback = self.node(nodes[1], sheet)
                return 0.0 if fallback is MISSING else fallback
            return value
        if name == 'ISERROR':
            try:
                value = scalar(self.node(nodes[0], sheet))
            except _Fail:
                return True
            return isinstance(value, XLError)
        if name == 'CHOOSE':
            index = _int(self.node(nodes[0], sheet))
            if not 1 <= index < len(nodes):
                raise _Fail(VALUE)
            chosen = self.node(nodes[index], sheet)
            return 0.0 if chosen is MISSING else chosen
        args = [self.node(item, sheet) for item in nodes]
        return getattr(self, 'f_' + name.replace('.', '_'))(*args)

    # ---------- thống kê ----------
    @staticmethod
    def _numbers(args) -> list[float]:
        found = []
        for arg in args:
            if isinstance(arg, Range):
                for value in arg.values():
                    _check(value)
                    if is_number(value):
                        found.append(value)
            elif arg is MISSING:
                found.append(0.0)
            else:
                found.append(_check(to_number(_check(arg))))
        return found

    def f_SUM(self, *args):
        return _finite(math.fsum(self._numbers(args)))

    def f_AVERAGE(self, *args):
        numbers = self._numbers(args)
        if not numbers:
            raise _Fail(DIV0)
        return _finite(math.fsum(numbers) / len(numbers))

    def f_MIN(self, *args):
        numbers = self._numbers(args)
        return min(numbers) if numbers else 0.0

    def f_MAX(self, *args):
        numbers = self._numbers(args)
        return max(numbers) if numbers else 0.0

    def f_PRODUCT(self, *args):
        numbers = self._numbers(args)
        return _finite(math.prod(numbers)) if numbers else 0.0

    def f_COUNT(self, *args):
        count = 0
        for arg in args:
            if isinstance(arg, Range):
                count += sum(1 for value in arg.values() if is_number(value))
            elif arg is not MISSING and not isinstance(arg, XLError) and not isinstance(to_number(arg), XLError) and arg is not None:
                count += 1
        return float(count)

    def f_COUNTA(self, *args):
        count = 0
        for arg in args:
            if isinstance(arg, Range):
                count += len(arg.values())
            elif arg is not MISSING and arg is not None:
                count += 1
        return float(count)

    def f_COUNTBLANK(self, rg):
        if not isinstance(rg, Range):
            raise _Fail(VALUE)
        filled = sum(1 for value in rg.values() if value != '')
        return float(rg.area - filled)

    def f_MEDIAN(self, *args):
        numbers = self._numbers(args)
        if not numbers:
            raise _Fail(NUM)
        return float(statistics.median(numbers))

    def _kth(self, array, k, largest: bool):
        numbers = sorted(self._numbers([array]), reverse=largest)
        index = math.ceil(_num(k) - 1e-12)
        if not 1 <= index <= len(numbers):
            raise _Fail(NUM)
        return numbers[index - 1]

    def f_LARGE(self, array, k):
        return self._kth(array, k, True)

    def f_SMALL(self, array, k):
        return self._kth(array, k, False)

    def f_RANK(self, number, ref, ascending=MISSING):
        target = round15(_num(number))
        if not isinstance(ref, Range):
            raise _Fail(VALUE)
        numbers = [round15(value) for value in self._numbers([ref])]
        if target not in numbers:
            raise _Fail(NA)
        up = ascending is not MISSING and _num(ascending) != 0
        return float(1 + sum(1 for value in numbers if (value < target if up else value > target)))

    def f_STDEV(self, *args):
        numbers = self._numbers(args)
        if len(numbers) < 2:
            raise _Fail(DIV0)
        return float(statistics.stdev(numbers))

    def f_SUMPRODUCT(self, *arrays):
        ranges = [rg if isinstance(rg, Range) else None for rg in arrays]
        if any(rg is None for rg in ranges):
            if all(not isinstance(rg, Range) for rg in arrays):
                return _finite(math.prod(_num(value) for value in arrays))
            raise _Fail(VALUE)
        _same_shape(ranges)
        inside, _ = positions(ranges)
        total = []
        for i, j in inside:
            product = 1.0
            for rg in ranges:
                value = _check(rg.get(i, j))
                product *= value if is_number(value) else 0.0
            total.append(product)
        return _finite(math.fsum(total))

    # ---------- theo điều kiện ----------
    def f_COUNTIF(self, rg, raw):
        if not isinstance(rg, Range):
            raise _Fail(VALUE)
        hits, blank = _matching([rg], [criterion(raw)])
        return float(len(hits) + blank)

    def f_COUNTIFS(self, *args):
        ranges = _same_shape(list(args[0::2]))
        hits, blank = _matching(ranges, [criterion(raw) for raw in args[1::2]])
        return float(len(hits) + blank)

    def _conditional(self, values: Range, ranges: list[Range], raws: list) -> list[float]:
        _same_shape([values, *ranges])
        hits, _ = _matching(ranges, [criterion(raw) for raw in raws])
        found = []
        for i, j in hits:
            value = _check(values.get(i, j))
            if is_number(value):
                found.append(value)
        return found

    def f_SUMIF(self, rg, raw, values=MISSING):
        if not isinstance(rg, Range):
            raise _Fail(VALUE)
        target = rg if values is MISSING else values
        if not isinstance(target, Range):
            raise _Fail(VALUE)
        return _finite(math.fsum(self._conditional(target.resized(rg.height, rg.width), [rg], [raw])))

    def f_AVERAGEIF(self, rg, raw, values=MISSING):
        if not isinstance(rg, Range):
            raise _Fail(VALUE)
        target = rg if values is MISSING else values
        if not isinstance(target, Range):
            raise _Fail(VALUE)
        found = self._conditional(target.resized(rg.height, rg.width), [rg], [raw])
        if not found:
            raise _Fail(DIV0)
        return _finite(math.fsum(found) / len(found))

    def f_SUMIFS(self, values, *args):
        if not isinstance(values, Range):
            raise _Fail(VALUE)
        return _finite(math.fsum(self._conditional(values, list(args[0::2]), list(args[1::2]))))

    def f_AVERAGEIFS(self, values, *args):
        if not isinstance(values, Range):
            raise _Fail(VALUE)
        found = self._conditional(values, list(args[0::2]), list(args[1::2]))
        if not found:
            raise _Fail(DIV0)
        return _finite(math.fsum(found) / len(found))

    # ---------- làm tròn và số học ----------
    def f_ROUND(self, number, digits):
        return _round(_num(number), _int(digits), ROUND_HALF_UP)

    def f_ROUNDUP(self, number, digits):
        return _round(_num(number), _int(digits), ROUND_UP)

    def f_ROUNDDOWN(self, number, digits):
        return _round(_num(number), _int(digits), ROUND_DOWN)

    def f_TRUNC(self, number, digits=MISSING):
        return _round(_num(number), 0 if digits is MISSING else _int(digits), ROUND_DOWN)

    def f_INT(self, number):
        return float(math.floor(_num(number)))

    def f_MOD(self, number, divisor):
        x, d = _num(number), _num(divisor)
        if d == 0:
            raise _Fail(DIV0)
        return _finite(x - d * math.floor(x / d))

    def f_ABS(self, number):
        return abs(_num(number))

    def f_SQRT(self, number):
        x = _num(number)
        if x < 0:
            raise _Fail(NUM)
        return math.sqrt(x)

    def f_POWER(self, number, power):
        return self.binary('^', number, power)

    # ---------- logic ----------
    def _flags(self, args) -> list[bool]:
        found = []
        for arg in args:
            if isinstance(arg, Range):
                for value in arg.values():
                    _check(value)
                    if isinstance(value, (bool, float)):
                        found.append(bool(value))
            elif arg is not MISSING:
                found.append(_check(to_bool(_check(arg))))
        if not found:
            raise _Fail(VALUE)
        return found

    def f_AND(self, *args):
        return all(self._flags(args))

    def f_OR(self, *args):
        return any(self._flags(args))

    def f_NOT(self, value):
        return not _check(to_bool(_check(scalar(value))))

    def f_TRUE(self):
        return True

    def f_FALSE(self):
        return False

    # ---------- chữ ----------
    def f_LEFT(self, text, count=MISSING):
        value, n = _text(text), 1 if count is MISSING else _int(count)
        if n < 0:
            raise _Fail(VALUE)
        return value[:n]

    def f_RIGHT(self, text, count=MISSING):
        value, n = _text(text), 1 if count is MISSING else _int(count)
        if n < 0:
            raise _Fail(VALUE)
        return value[-n:] if n else ''

    def f_MID(self, text, start, count):
        value, begin, n = _text(text), _int(start), _int(count)
        if begin < 1 or n < 0:
            raise _Fail(VALUE)
        return value[begin - 1:begin - 1 + n]

    def f_LEN(self, text):
        return float(len(_text(text)))

    def f_UPPER(self, text):
        return _text(text).upper()

    def f_LOWER(self, text):
        return _text(text).lower()

    def f_PROPER(self, text):
        out, previous = [], False
        for char in _text(text):
            out.append(char.lower() if previous else char.upper())
            previous = char.isalpha()
        return ''.join(out)

    def f_TRIM(self, text):
        return re.sub(' +', ' ', _text(text).strip(' '))

    def f_CONCATENATE(self, *parts):
        return ''.join(_text(part) for part in parts)

    def f_VALUE(self, text):
        value = _check(scalar(text))
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            number = parse_number(value)
            if number is not None:
                return number
        if value is None:
            return 0.0
        raise _Fail(VALUE)

    def f_SUBSTITUTE(self, text, old, new, instance=MISSING):
        value, find, replace = _text(text), _text(old), _text(new)
        if not find:
            return value
        if instance is MISSING:
            return value.replace(find, replace)
        nth = _int(instance)
        if nth < 1:
            raise _Fail(VALUE)
        start = -1
        for _ in range(nth):
            start = value.find(find, start + 1)
            if start < 0:
                return value
        return value[:start] + replace + value[start + len(find):]

    # ---------- ngày tháng ----------
    def f_TODAY(self):
        return serial(self.today)

    def f_DATE(self, year, month, day):
        y, m, d = _int(year), _int(month), _int(day)
        if y < 0 or y > 9999:
            raise _Fail(NUM)
        if y < 1900:
            y += 1900
        total = y * 12 + (m - 1)
        year_value, month_value = divmod(total, 12)
        if not 1 <= year_value <= 9999:
            raise _Fail(NUM)
        try:
            value = date(year_value, month_value + 1, 1) + timedelta(days=d - 1)
        except (OverflowError, ValueError):
            raise _Fail(NUM) from None
        number = serial(value)
        if not MIN_SERIAL <= number <= MAX_SERIAL:
            raise _Fail(NUM)
        return number

    def f_YEAR(self, value):
        return float(to_date(value).year)

    def f_MONTH(self, value):
        return float(to_date(value).month)

    def f_DAY(self, value):
        return float(to_date(value).day)

    def f_DATEDIF(self, start, end, unit):
        first, last, kind = to_date(start), to_date(end), _text(unit).strip().upper()
        if first > last:
            raise _Fail(NUM)
        if kind == 'D':
            return float((last - first).days)
        months = (last.year - first.year) * 12 + last.month - first.month - (1 if last.day < first.day else 0)
        if kind == 'M':
            return float(months)
        if kind == 'Y':
            return float(months // 12)
        raise _Fail(NUM)

    # ---------- dò tìm ----------
    def _lookup(self, target, table, index, approximate, vertical: bool):
        value = _check(scalar(target))
        if value is None:
            raise _Fail(NA)
        if not isinstance(table, Range):
            raise _Fail(VALUE)
        column = _int(index)
        if column < 1:
            raise _Fail(VALUE)
        if column > (table.width if vertical else table.height):
            raise _Fail(REF)
        loose = approximate is MISSING or _check(to_bool(_check(scalar(approximate))))
        keys = (table.resized(table.height, 1) if vertical else table.resized(1, table.width)).vector()
        for key in keys:
            _check(key)
        if loose:
            found = _approximate(value, keys)
        else:
            found = next((position for position, key in enumerate(keys) if _equal_lookup(value, key)), -1)
            if found < 0:
                raise _Fail(NA)
        return table.get(found, column - 1) if vertical else table.get(column - 1, found)

    def f_VLOOKUP(self, target, table, index, approximate=MISSING):
        return self._lookup(target, table, index, approximate, True)

    def f_HLOOKUP(self, target, table, index, approximate=MISSING):
        return self._lookup(target, table, index, approximate, False)

    def f_MATCH(self, target, lookup, kind=MISSING):
        value = _check(scalar(target))
        if value is None:
            raise _Fail(NA)
        if not isinstance(lookup, Range) or (lookup.height > 1 and lookup.width > 1):
            raise _Fail(NA)
        mode = 1 if kind is MISSING else _int(kind)
        cells = lookup.vector()
        for cell in cells:
            _check(cell)
        if mode == 0:
            found = next((position for position, cell in enumerate(cells) if _equal_lookup(value, cell)), -1)
            if found < 0:
                raise _Fail(NA)
        else:
            found = _approximate(value, cells, descending=mode < 0)
        return float(found + 1)

    def f_INDEX(self, table, row, column=MISSING):
        if not isinstance(table, Range):
            if row is not MISSING and _int(row) in (0, 1) and (column is MISSING or _int(column) in (0, 1)):
                return _check(scalar(table))
            raise _Fail(REF)
        r = _int(row)
        if column is MISSING:
            if table.width == 1:
                c = 1
            elif table.height == 1:
                r, c = 1, r
            else:
                raise _Fail(VALUE)
        else:
            c = _int(column)
        if r == 0 or c == 0:
            raise _Fail(VALUE)
        if not (1 <= r <= table.height and 1 <= c <= table.width):
            raise _Fail(REF)
        return table.get(r - 1, c - 1)

    # ---------- thông tin ----------
    def f_ISBLANK(self, value):
        if isinstance(value, Range):
            return value.height == 1 and value.width == 1 and value.get(0, 0) is None
        return False

    def f_ISNUMBER(self, value):
        return is_number(scalar(value))

    def f_ISTEXT(self, value):
        return isinstance(scalar(value), str)

    # ---------- tài chính ----------
    def _money(self, rate, periods, payment_type):
        r, n = _num(rate), _num(periods)
        kind = 0.0 if payment_type is MISSING else (1.0 if _num(payment_type) else 0.0)
        return r, n, kind

    def f_PMT(self, rate, periods, present, future=MISSING, payment_type=MISSING):
        r, n, kind = self._money(rate, periods, payment_type)
        pv, fv = _num(present), 0.0 if future is MISSING else _num(future)
        if n == 0:
            raise _Fail(NUM)
        if r == 0:
            return _finite(-(pv + fv) / n)
        growth = (1 + r) ** n
        return _finite(-(r * (fv + pv * growth)) / ((1 + r * kind) * (growth - 1)))

    def f_FV(self, rate, periods, payment, present=MISSING, payment_type=MISSING):
        r, n, kind = self._money(rate, periods, payment_type)
        pmt, pv = _num(payment), 0.0 if present is MISSING else _num(present)
        if r == 0:
            return _finite(-(pv + pmt * n))
        growth = (1 + r) ** n
        return _finite(-(pv * growth + pmt * (1 + r * kind) * (growth - 1) / r))

    def f_PV(self, rate, periods, payment, future=MISSING, payment_type=MISSING):
        r, n, kind = self._money(rate, periods, payment_type)
        pmt, fv = _num(payment), 0.0 if future is MISSING else _num(future)
        if r == 0:
            return _finite(-(fv + pmt * n))
        growth = (1 + r) ** n
        return _finite(-(fv + pmt * (1 + r * kind) * (growth - 1) / r) / growth)


class CycleError(ValueError):
    """Các ô công thức tham chiếu vòng tròn."""

    def __init__(self, cells: list[str]):
        super().__init__(', '.join(cells))
        self.cells = cells


def compute(sheets: list[SheetData], formulas: dict[tuple[int, int, int], Formula], today: date) -> dict:
    """Tính mọi ô công thức ``{(trang, hàng, cột): Formula}`` theo thứ tự phụ thuộc; ghi kết quả vào ``sheets``.

    Trả ``{(trang, hàng, cột): giá trị}``. Tham chiếu tới trang tính không có phải được kiểm tra trước (spec).
    """
    evaluator = Evaluator(sheets, today)
    by_sheet: dict[int, list[tuple[int, int]]] = {}
    for s, r, c in formulas:
        by_sheet.setdefault(s, []).append((r, c))
    index_of = {sheet.name.casefold(): position for position, sheet in enumerate(sheets)}
    needs: dict[tuple, set] = {}
    for key, formula in formulas.items():
        found = set()
        for ref in formula.refs:
            target = key[0] if ref.sheet is None else index_of.get(ref.sheet.casefold())
            if target is None:
                continue
            r1, r2 = (0, MAX_ROWS - 1) if ref.r1 is None else (ref.r1, ref.r2)
            c1, c2 = (0, MAX_COLS - 1) if ref.c1 is None else (ref.c1, ref.c2)
            if (r2 - r1 + 1) * (c2 - c1 + 1) > MAX_RANGE_CELLS and ref.r1 is not None and ref.c1 is not None:
                raise ValueError(f'vùng {ref.text} quá lớn')
            for r, c in by_sheet.get(target, ()):
                if r1 <= r <= r2 and c1 <= c <= c2:
                    found.add((target, r, c))
        needs[key] = found
    waiting = {key: len(found) for key, found in needs.items()}
    users: dict[tuple, list] = {}
    for key, found in needs.items():
        for dependency in found:
            users.setdefault(dependency, []).append(key)
    ready = deque(sorted(key for key, count in waiting.items() if count == 0))
    results: dict = {}
    while ready:
        key = ready.popleft()
        sheet = sheets[key[0]]
        value = evaluator.evaluate(formulas[key], sheet)
        sheet.values[(key[1], key[2])] = value
        results[key] = value
        for user in users.get(key, ()):
            waiting[user] -= 1
            if waiting[user] == 0:
                ready.append(user)
    if len(results) < len(formulas):
        stuck = sorted(key for key in formulas if key not in results)
        raise CycleError([f'{sheets[s].name}!{address(r, c)}' for s, r, c in stuck[:6]])
    return results
