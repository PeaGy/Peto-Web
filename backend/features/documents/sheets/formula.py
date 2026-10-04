"""Đọc công thức Excel do model viết: tách từ, dựng cây cú pháp và chuẩn hóa chữ công thức sẽ ghi vào tệp.

Chỉ nhận cú pháp Excel tiếng Anh (dấu phẩy ngăn tham số, dấu chấm thập phân) và các hàm trong FUNCTIONS. Không bao giờ
eval chữ do model gửi: công thức thành cây gồm số, chữ, ô, phép toán và lời gọi hàm có tên trong danh sách. Lỗi nói rõ
sai ở đâu để model sửa rồi gọi lại.

Cây là tuple: ('num', số), ('str', chữ), ('bool', đúng/sai), ('ref', Ref), ('neg' | 'pos' | 'pct', con),
('bin', phép, trái, phải), ('call', TÊN, [tham số]), ('missing',) cho tham số bỏ trống như IF(A1,,1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_ROWS, MAX_COLS = 1_048_576, 16_384
MAX_FORMULA = 400
MAX_DEPTH = 40


class FormulaError(ValueError):
    """Công thức sai cú pháp hoặc dùng thứ chưa hỗ trợ."""


# Tên hàm → (số tham số ít nhất, nhiều nhất; None là không giới hạn). Chỉ hàm có từ Excel 2007, không cần tiền tố
# _xlfn., nên mọi bản Excel, Google Sheets và LibreOffice đều đọc được.
FUNCTIONS: dict[str, tuple[int, int | None]] = {
    'SUM': (1, None), 'AVERAGE': (1, None), 'MIN': (1, None), 'MAX': (1, None), 'COUNT': (1, None),
    'COUNTA': (1, None), 'COUNTBLANK': (1, 1), 'PRODUCT': (1, None), 'SUMIF': (2, 3), 'SUMIFS': (3, None),
    'COUNTIF': (2, 2), 'COUNTIFS': (2, None), 'AVERAGEIF': (2, 3), 'AVERAGEIFS': (3, None), 'MEDIAN': (1, None),
    'LARGE': (2, 2), 'SMALL': (2, 2), 'RANK': (2, 3), 'STDEV': (1, None), 'SUMPRODUCT': (1, None),
    'ROUND': (2, 2), 'ROUNDUP': (2, 2), 'ROUNDDOWN': (2, 2), 'INT': (1, 1), 'TRUNC': (1, 2), 'MOD': (2, 2),
    'ABS': (1, 1), 'SQRT': (1, 1), 'POWER': (2, 2),
    'IF': (2, 3), 'IFERROR': (2, 2), 'AND': (1, None), 'OR': (1, None), 'NOT': (1, 1), 'TRUE': (0, 0), 'FALSE': (0, 0),
    'LEFT': (1, 2), 'RIGHT': (1, 2), 'MID': (3, 3), 'LEN': (1, 1), 'UPPER': (1, 1), 'LOWER': (1, 1),
    'PROPER': (1, 1), 'TRIM': (1, 1), 'CONCATENATE': (1, None), 'VALUE': (1, 1), 'SUBSTITUTE': (3, 4),
    'TODAY': (0, 0), 'DATE': (3, 3), 'YEAR': (1, 1), 'MONTH': (1, 1), 'DAY': (1, 1), 'DATEDIF': (3, 3),
    'VLOOKUP': (3, 4), 'HLOOKUP': (3, 4), 'INDEX': (2, 3), 'MATCH': (2, 3), 'CHOOSE': (2, None),
    'ISBLANK': (1, 1), 'ISNUMBER': (1, 1), 'ISTEXT': (1, 1), 'ISERROR': (1, 1),
    'PMT': (3, 5), 'FV': (3, 5), 'PV': (3, 5),
}
# Hàm nhận vùng điều kiện theo cặp (vùng, điều kiện): SUMIFS/AVERAGEIFS có thêm vùng cần tính ở đầu.
_PAIRS = {'SUMIFS': 1, 'AVERAGEIFS': 1, 'COUNTIFS': 0}

_BINARY = {'=': 10, '<>': 10, '<': 10, '>': 10, '<=': 10, '>=': 10, '&': 20, '+': 30, '-': 30, '*': 40, '/': 40, '^': 50}
_UNARY, _PERCENT = 60, 70


@dataclass(frozen=True)
class Ref:
    """Một ô hoặc vùng ô. Hàng, cột tính từ 0; None ở cả hai đầu là cả cột (A:A) hoặc cả hàng (2:2)."""
    sheet: str | None
    r1: int | None
    c1: int | None
    r2: int | None
    c2: int | None
    text: str

    @property
    def single(self) -> bool:
        return self.r1 is not None and self.c1 is not None and self.r1 == self.r2 and self.c1 == self.c2


@dataclass(frozen=True)
class Token:
    kind: str           # num, str, bool, ref, func, op, lparen, rparen, comma, end
    text: str           # chữ đã chuẩn hóa để ghi lại vào tệp
    value: object = None
    pos: int = 0


def column_index(letters: str) -> int:
    index = 0
    for char in letters.upper():
        index = index * 26 + ord(char) - 64
    return index - 1


def column_letter(index: int) -> str:
    letters = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def address(row: int, col: int) -> str:
    return f'{column_letter(col)}{row + 1}'


def quote_sheet(name: str) -> str:
    """Tên trang tính trong công thức: tên chỉ có chữ ASCII, số, gạch dưới thì để trần, còn lại đặt trong nháy đơn."""
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', name) and not re.fullmatch(r'[A-Za-z]{1,3}\d+', name):
        return name
    return "'" + name.replace("'", "''") + "'"


_SHEET = r"(?:'((?:[^']|'')+)'|([^\W\d][\w.]*))!"
_CELL = r'(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})'
_PATTERNS = [
    ('cells', re.compile(rf'(?:{_SHEET})?{_CELL}(?::{_CELL})?(?![\w(.])')),
    ('cols', re.compile(rf'(?:{_SHEET})?(\$?)([A-Za-z]{{1,3}}):(\$?)([A-Za-z]{{1,3}})(?![\w(.])')),
    ('rows', re.compile(rf'(?:{_SHEET})?(\$?)(\d{{1,7}}):(\$?)(\d{{1,7}})(?![\w.(])')),
    ('num', re.compile(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')),
    ('func', re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)\s*\(')),
    ('bool', re.compile(r'(TRUE|FALSE)(?![\w(.])', re.I)),
    ('op', re.compile(r'<>|<=|>=|[-+*/^&=<>%]')),
]


def _normalize_separators(text: str) -> str:
    """Model hay viết dấu chấm phẩy như Excel bản tiếng Việt. Không lẫn dấu phẩy thì đổi sang dấu phẩy chuẩn."""
    outside = re.sub(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'', '', text)
    if ';' not in outside:
        return text
    if ',' in outside:
        raise FormulaError('dùng dấu phẩy để ngăn tham số và dấu chấm cho số thập phân (=ROUND(A1*1.5,0)), '
                           'không trộn dấu chấm phẩy với dấu phẩy')
    parts = re.split(r'("(?:[^"]|"")*"|\'(?:[^\']|\'\')*\')', text)
    return ''.join(part if index % 2 else part.replace(';', ',') for index, part in enumerate(parts))


def _check_cell(col: str, row: str) -> tuple[int, int]:
    c, r = column_index(col), int(row) - 1
    if c >= MAX_COLS or not 0 <= r < MAX_ROWS:
        raise FormulaError(f'ô {col.upper()}{row} nằm ngoài giới hạn của Excel')
    return r, c


def _sheet_of(match) -> str | None:
    if match.group(1) is not None:
        return match.group(1).replace("''", "'")
    return match.group(2)


def tokenize(source: str) -> list[Token]:
    text = source.translate(str.maketrans({'“': '"', '”': '"', '„': '"', '‟': '"', '‘': "'", '’': "'"}))
    text = _normalize_separators(text)
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char.isspace():
            pos += 1
            continue
        if char == '"':
            match = re.compile(r'"((?:[^"]|"")*)"').match(text, pos)
            if not match:
                raise FormulaError('thiếu dấu " đóng chuỗi chữ')
            tokens.append(Token('str', match.group(0), match.group(1).replace('""', '"'), pos))
            pos = match.end()
            continue
        if char in '(),':
            kind = {'(': 'lparen', ')': 'rparen', ',': 'comma'}[char]
            tokens.append(Token(kind, char, None, pos))
            pos += 1
            continue
        if char == '#':
            raise FormulaError('không viết giá trị lỗi như #N/A vào công thức')
        for kind, pattern in _PATTERNS:
            match = pattern.match(text, pos)
            if not match:
                continue
            if kind == 'cells':
                sheet = _sheet_of(match)
                r1, c1 = _check_cell(match.group(4), match.group(6))
                r2, c2 = (_check_cell(match.group(8), match.group(10)) if match.group(8) else (r1, c1))
                first = f'{match.group(3)}{match.group(4).upper()}{match.group(5)}{match.group(6)}'
                second = f':{match.group(7)}{match.group(8).upper()}{match.group(9)}{match.group(10)}' if match.group(8) else ''
                prefix = quote_sheet(sheet) + '!' if sheet else ''
                ref = Ref(sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2), prefix + first + second)
                tokens.append(Token('ref', ref.text, ref, pos))
            elif kind == 'cols':
                sheet = _sheet_of(match)
                c1, c2 = column_index(match.group(4)), column_index(match.group(6))
                if max(c1, c2) >= MAX_COLS:
                    raise FormulaError(f'cột {match.group(0)} nằm ngoài giới hạn của Excel')
                prefix = quote_sheet(sheet) + '!' if sheet else ''
                body = f'{match.group(3)}{match.group(4).upper()}:{match.group(5)}{match.group(6).upper()}'
                ref = Ref(sheet, None, min(c1, c2), None, max(c1, c2), prefix + body)
                tokens.append(Token('ref', ref.text, ref, pos))
            elif kind == 'rows':
                sheet = _sheet_of(match)
                r1, r2 = int(match.group(4)) - 1, int(match.group(6)) - 1
                if not (0 <= r1 < MAX_ROWS and 0 <= r2 < MAX_ROWS):
                    raise FormulaError(f'hàng {match.group(0)} nằm ngoài giới hạn của Excel')
                prefix = quote_sheet(sheet) + '!' if sheet else ''
                body = f'{match.group(3)}{match.group(4)}:{match.group(5)}{match.group(6)}'
                ref = Ref(sheet, min(r1, r2), None, max(r1, r2), None, prefix + body)
                tokens.append(Token('ref', ref.text, ref, pos))
            elif kind == 'num':
                tokens.append(Token('num', match.group(0), float(match.group(0)), pos))
            elif kind == 'func':
                name = match.group(1).upper()
                tokens.append(Token('func', name + '(', name, pos))
            elif kind == 'bool':
                tokens.append(Token('bool', match.group(1).upper(), match.group(1).upper() == 'TRUE', pos))
            else:
                tokens.append(Token('op', match.group(0), match.group(0), pos))
            pos = match.end()
            break
        else:
            word = re.compile(r"[^\s(),+\-*/^&=<>%\"]+").match(text, pos)
            name = word.group(0) if word else char
            if '!' in text[pos:] and not name.endswith('!'):
                raise FormulaError(f'không hiểu "{name}". Tên trang tính có dấu cách hay dấu tiếng Việt phải đặt trong '
                                   "nháy đơn, ví dụ 'Bảng điểm'!A1")
            raise FormulaError(f'không hiểu "{name}": không phải hàm, số hay địa chỉ ô (chưa hỗ trợ tên vùng)')
    tokens.append(Token('end', '', None, len(text)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def peek(self) -> Token:
        return self.tokens[self.index]

    def next(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expr(self, min_bp: int = 0, depth: int = 0):
        if depth > MAX_DEPTH:
            raise FormulaError('công thức lồng quá sâu')
        token = self.next()
        if token.kind == 'op' and token.text in '+-':
            operand = self.expr(_UNARY, depth + 1)
            left = ('neg' if token.text == '-' else 'pos', operand)
        elif token.kind == 'num':
            left = ('num', token.value)
        elif token.kind == 'str':
            left = ('str', token.value)
        elif token.kind == 'bool':
            left = ('bool', token.value)
        elif token.kind == 'ref':
            left = ('ref', token.value)
        elif token.kind == 'func':
            left = self.call(token, depth)
        elif token.kind == 'lparen':
            left = self.expr(0, depth + 1)
            if self.next().kind != 'rparen':
                raise FormulaError('thiếu dấu ")"')
        elif token.kind == 'end':
            raise FormulaError('công thức kết thúc giữa chừng')
        else:
            raise FormulaError(f'thiếu giá trị trước "{token.text}"')
        while True:
            token = self.peek()
            if token.kind == 'op' and token.text == '%':
                if _PERCENT < min_bp:
                    break
                self.next()
                left = ('pct', left)
                continue
            if token.kind == 'op' and token.text in _BINARY:
                power = _BINARY[token.text]
                if power < min_bp:
                    break
                self.next()
                left = ('bin', token.text, left, self.expr(power + 1, depth + 1))
                continue
            break
        return left

    def call(self, token: Token, depth: int):
        name = token.value
        if name not in FUNCTIONS:
            raise FormulaError(f'hàm {name} chưa được hỗ trợ. Dùng các hàm: {", ".join(sorted(FUNCTIONS))}')
        args = []
        if self.peek().kind == 'rparen':
            self.next()
        else:
            while True:
                if self.peek().kind in ('comma', 'rparen'):
                    args.append(('missing',))
                else:
                    args.append(self.expr(0, depth + 1))
                separator = self.next()
                if separator.kind == 'rparen':
                    break
                if separator.kind != 'comma':
                    raise FormulaError(f'thiếu dấu phẩy hoặc ")" trong {name}(…)')
        low, high = FUNCTIONS[name]
        if len(args) < low or (high is not None and len(args) > high):
            expected = f'{low}' if low == high else f'{low}–{high}' if high is not None else f'từ {low}'
            raise FormulaError(f'{name} cần {expected} tham số, đang có {len(args)}')
        if name in _PAIRS and (len(args) - _PAIRS[name]) % 2:
            raise FormulaError(f'{name} cần các cặp (vùng điều kiện, điều kiện)')
        return ('call', name, args)


@dataclass(frozen=True)
class Formula:
    text: str            # công thức chuẩn hóa, bắt đầu bằng =
    tree: tuple
    refs: tuple[Ref, ...]


def parse(source: str) -> Formula:
    """Đọc một công thức (có hoặc không có dấu = đầu). Lỗi là FormulaError với lời giải thích tiếng Việt."""
    body = source.strip()
    if body.startswith('='):
        body = body[1:]
    if not body.strip():
        raise FormulaError('công thức trống')
    if len(body) > MAX_FORMULA:
        raise FormulaError(f'công thức dài quá {MAX_FORMULA} ký tự; tách bớt sang cột phụ')
    tokens = tokenize(body)
    parser = _Parser(tokens)
    tree = parser.expr()
    if parser.peek().kind != 'end':
        extra = parser.peek()
        raise FormulaError(f'thừa "{extra.text}" sau khi công thức đã đủ (thiếu toán tử hoặc dấu phẩy?)')
    refs = tuple(token.value for token in tokens if token.kind == 'ref')
    return Formula('=' + ''.join(token.text for token in tokens), tree, refs)


def functions_used(tree) -> set[str]:
    found = set()
    stack = [tree]
    while stack:
        node = stack.pop()
        if node[0] == 'call':
            found.add(node[1])
            stack.extend(node[2])
        elif node[0] in ('neg', 'pos', 'pct'):
            stack.append(node[1])
        elif node[0] == 'bin':
            stack.extend(node[2:])
    return found
