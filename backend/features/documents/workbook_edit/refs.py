"""Dò và viết lại tham chiếu ô trong công thức Excel bất kỳ: công thức sẵn có trong tệp người dùng, vùng số liệu của
biểu đồ, tên vùng, định dạng có điều kiện, xác thực dữ liệu.

Khác sheets/formula.py (chỉ nhận cú pháp và các hàm Peto được viết), ở đây gặp gì lạ cũng giữ nguyên chữ: chỉ phần
tham chiếu ô được nhận ra và đổi. Chuỗi chữ, tên Bảng có cấu trúc (Bang1[Cột], [@Cột]), hằng mảng {…}, giá trị lỗi và
tham chiếu sang tệp khác ([1]Trang!A1) không bao giờ bị sửa nhầm.

Hàng và cột tính từ 0 như sheets/formula.Ref; None ở cả hai đầu là cả cột (A:C) hoặc cả hàng (2:5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from features.documents.sheets.formula import column_index, column_letter, quote_sheet

MAX_ROWS, MAX_COLS = 1_048_576, 16_384

_ERROR = re.compile(r'#(?:NULL!|DIV/0!|VALUE!|REF!|NAME\?|NUM!|N/A|GETTING_DATA|SPILL!|CALC!|BLOCKED!|CONNECT!|FIELD!'
                    r'|BUSY!|UNKNOWN!|EXTERNAL!|PYTHON!)', re.I)
_NUMBER = re.compile(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
_IDENT = re.compile(r'(?:[^\W\d]|\\)[\w.?\\]*')
_CELL = re.compile(r'(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})')
_COL = re.compile(r'(\$?)([A-Za-z]{1,3})')
_ROW = re.compile(r'(\$?)(\d{1,7})')
_QUOTED = re.compile(r"'((?:[^']|'')*)'")
# Sau một tham chiếu không được là chữ, số, dấu chấm, ngoặc mở hay dấu ! (khi đó nó là tên hàm, tên vùng hay tên trang).
_STOP = re.compile(r'[\w.(\[!]')
VOLATILE = frozenset({'INDIRECT', 'OFFSET', 'CELL', 'INFO', 'NOW', 'TODAY', 'RAND', 'RANDBETWEEN', 'RANDARRAY'})


class Unsupported(ValueError):
    """Công thức có cấu trúc chưa đổi được an toàn (tham chiếu 3D qua trang đang chèn/xóa)."""


@dataclass(frozen=True)
class Ref:
    start: int
    end: int
    body_start: int      # vị trí bắt đầu phần ô (sau dấu !)
    prefix: str          # chữ trước phần ô, gồm dấu ! ('' khi không ghi trang)
    sheet: str | None    # tên trang đã bỏ nháy; None khi không ghi trang
    sheet2: str | None   # trang cuối của tham chiếu 3D (Trang1:Trang3!A1)
    external: bool       # trỏ sang tệp khác
    kind: str            # cell, area, cols, rows
    r1: int | None
    c1: int | None
    r2: int | None
    c2: int | None
    ar1: bool = False
    ac1: bool = False
    ar2: bool = False
    ac2: bool = False


@dataclass(frozen=True)
class Name:
    sheet: str | None    # trang ghi kèm (Trang!TênVùng), None khi không ghi
    name: str
    start: int           # đầu phần trang (hoặc đầu tên khi không ghi trang)
    body_start: int      # đầu tên


@dataclass
class Scan:
    refs: list[Ref] = field(default_factory=list)
    names: list[Name] = field(default_factory=list)
    functions: set[str] = field(default_factory=set)
    tables: set[str] = field(default_factory=set)
    structured: bool = False     # có tham chiếu Bảng có cấu trúc (kể cả [@Cột] không ghi tên Bảng)
    external: bool = False
    errors: bool = False         # có chữ #REF! … trong công thức

    @property
    def volatile(self) -> bool:
        return any(name.rsplit('.', 1)[-1] in VOLATILE for name in self.functions)


def _valid_cell(col: str, row: str) -> tuple[int, int] | None:
    c, r = column_index(col), int(row) - 1
    return (r, c) if c < MAX_COLS and 0 <= r < MAX_ROWS else None


def _stops(text: str, pos: int) -> bool:
    """Tham chiếu kết thúc hợp lệ ở ``pos``."""
    return pos >= len(text) or not _STOP.match(text, pos)


def _body(text: str, pos: int):
    """Phần ô bắt đầu ở ``pos``: (kind, r1, c1, r2, c2, cờ $, vị trí cuối) hoặc None."""
    match = _CELL.match(text, pos)
    if match and (first := _valid_cell(match.group(2), match.group(4))):
        end = match.end()
        if text[end:end + 1] == ':':
            second = _CELL.match(text, end + 1)
            if second and (last := _valid_cell(second.group(2), second.group(4))) and _stops(text, second.end()):
                return ('area', first[0], first[1], last[0], last[1],
                        (bool(match.group(3)), bool(match.group(1)), bool(second.group(3)), bool(second.group(1))),
                        second.end())
        if _stops(text, end) and text[end:end + 1] != ':':
            return 'cell', first[0], first[1], first[0], first[1], (bool(match.group(3)), bool(match.group(1)),
                                                                    bool(match.group(3)), bool(match.group(1))), end
        if _stops(text, end) and text[end:end + 1] == ':' and not _CELL.match(text, end + 1):
            # A1:INDEX(…) hay A1:B — dấu : là phép toán vùng với thứ khác, chỉ A1 là tham chiếu.
            return 'cell', first[0], first[1], first[0], first[1], (bool(match.group(3)), bool(match.group(1)),
                                                                    bool(match.group(3)), bool(match.group(1))), end
    match = _COL.match(text, pos)
    if match and text[match.end():match.end() + 1] == ':':
        second = _COL.match(text, match.end() + 1)
        if second and _stops(text, second.end()) and not text[second.end():second.end() + 1].isdigit():
            c1, c2 = column_index(match.group(2)), column_index(second.group(2))
            if max(c1, c2) < MAX_COLS:
                return 'cols', None, min(c1, c2), None, max(c1, c2), (False, bool(match.group(1)), False,
                                                                      bool(second.group(1))), second.end()
    match = _ROW.match(text, pos)
    if match and text[match.end():match.end() + 1] == ':':
        second = _ROW.match(text, match.end() + 1)
        if second and _stops(text, second.end()):
            r1, r2 = int(match.group(2)) - 1, int(second.group(2)) - 1
            if 0 <= min(r1, r2) and max(r1, r2) < MAX_ROWS:
                return 'rows', min(r1, r2), None, max(r1, r2), None, (bool(match.group(1)), False,
                                                                      bool(second.group(1)), False), second.end()
    return None


def _bracket_end(text: str, pos: int) -> int:
    """Vị trí ngay sau dấu ] khớp với dấu [ ở ``pos`` (ngoặc lồng nhau; ' thoát ký tự đặc biệt trong tên cột Bảng)."""
    depth, index = 0, pos
    while index < len(text):
        char = text[index]
        if char == "'" and index + 1 < len(text):
            index += 2
            continue
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def scan(text: str) -> Scan:
    out = Scan()
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == '"':
            end = pos + 1
            while end < len(text):
                if text[end] == '"':
                    if text[end + 1:end + 2] == '"':
                        end += 2
                        continue
                    break
                end += 1
            pos = end + 1
            continue
        if char == '{':
            end = pos + 1
            while end < len(text) and text[end] != '}':
                if text[end] == '"':
                    end = text.find('"', end + 1)
                    if end < 0:
                        end = len(text)
                end += 1
            pos = end + 1
            continue
        if char == '#':
            match = _ERROR.match(text, pos)
            if match:
                out.errors = out.errors or match.group(0).upper() == '#REF!'
                pos = match.end()
            else:
                pos += 1
            continue
        start = pos
        sheet = sheet2 = None
        external = False
        prefix_end = None
        if char == '[':
            end = _bracket_end(text, pos)
            # [1]Trang!A1 là tệp khác; còn lại là tham chiếu Bảng có cấu trúc ([@Cột], [[#Totals],[Cột]]).
            after = _QUOTED.match(text, end) or _IDENT.match(text, end)
            if after and text[after.end():after.end() + 1] == '!':
                external = True
                sheet = after.group(1).replace("''", "'") if after.re is _QUOTED else after.group(0)
                prefix_end = after.end() + 1
            else:
                out.structured = True
                pos = end
                continue
        elif char == "'":
            match = _QUOTED.match(text, pos)
            if match and text[match.end():match.end() + 1] == '!':
                name = match.group(1).replace("''", "'")
                if name.startswith('['):
                    external = True
                    name = name[name.find(']') + 1:] if ']' in name else name
                sheet, _, sheet2 = name.partition(':')
                sheet2 = sheet2 or None
                prefix_end = match.end() + 1
            else:
                pos = (match.end() if match else pos + 1)
                continue
        elif char.isalpha() or char in '_\\':
            match = _IDENT.match(text, pos)
            word = match.group(0) if match else char
            after = match.end() if match else pos + 1
            if text[after:after + 1] == '!':
                sheet, prefix_end = word, after + 1
            elif text[after:after + 1] == ':' and (second := _IDENT.match(text, after + 1)) \
                    and text[second.end():second.end() + 1] == '!' and not _body(text, pos):
                sheet, sheet2, prefix_end = word, second.group(0), second.end() + 1
            else:
                body = _body(text, pos)
                if body:
                    _add(out, text, start, pos, '', None, None, False, body)
                    pos = body[-1]
                    continue
                if text[after:after + 1] == '(':
                    out.functions.add(word.upper())
                elif text[after:after + 1] == '[':
                    out.tables.add(word)
                    out.structured = True
                    after = _bracket_end(text, after)
                elif word.upper() not in ('TRUE', 'FALSE'):
                    out.names.append(Name(None, word, start, start))
                pos = after
                continue
        elif char == '$' or char.isdigit():
            body = _body(text, pos)
            if body:
                _add(out, text, start, pos, '', None, None, False, body)
                pos = body[-1]
                continue
            match = _NUMBER.match(text, pos)
            pos = match.end() if match else pos + 1
            continue
        else:
            pos += 1
            continue
        # Có phần trang (Trang!, 'Trang có dấu cách'!, [1]Trang!, Trang1:Trang3!): tiếp theo là ô, tên vùng hoặc #REF!.
        out.external = out.external or external
        body = _body(text, prefix_end)
        if body:
            _add(out, text, start, prefix_end, text[start:prefix_end], sheet, sheet2, external, body)
            pos = body[-1]
            continue
        match = _IDENT.match(text, prefix_end)
        if match:
            if not external:
                out.names.append(Name(sheet, match.group(0), start, prefix_end))
            pos = match.end()
        else:
            pos = prefix_end
    return out


def _add(out: Scan, text: str, start: int, body_start: int, prefix: str, sheet, sheet2, external: bool, body) -> None:
    kind, r1, c1, r2, c2, flags, end = body
    out.refs.append(Ref(start, end, body_start, prefix, sheet, sheet2, external, kind, r1, c1, r2, c2, *flags))


# ---------- viết lại ----------

def _cell(row: int, col: int, abs_row: bool, abs_col: bool) -> str:
    return f'{"$" if abs_col else ""}{column_letter(col)}{"$" if abs_row else ""}{row + 1}'


def body_text(ref: Ref, r1, c1, r2, c2) -> str:
    """Phần ô của ``ref`` với tọa độ mới, giữ nguyên dấu $ và kiểu (ô, vùng, cả cột, cả hàng)."""
    if ref.kind == 'cell':
        return _cell(r1, c1, ref.ar1, ref.ac1)
    if ref.kind == 'area':
        return f'{_cell(r1, c1, ref.ar1, ref.ac1)}:{_cell(r2, c2, ref.ar2, ref.ac2)}'
    if ref.kind == 'cols':
        return f'{"$" if ref.ac1 else ""}{column_letter(c1)}:{"$" if ref.ac2 else ""}{column_letter(c2)}'
    return f'{"$" if ref.ar1 else ""}{r1 + 1}:{"$" if ref.ar2 else ""}{r2 + 1}'


def rewrite(text: str, change) -> str:
    """Thay từng tham chiếu bằng ``change(ref)`` (chữ mới gồm cả phần trang) khi hàm đó trả chữ; None thì giữ."""
    found = scan(text).refs
    if not found:
        return text
    parts, last = [], 0
    for ref in found:
        new = change(ref)
        if new is None:
            continue
        parts.append(text[last:ref.start])
        parts.append(new)
        last = ref.end
    if not parts:
        return text
    parts.append(text[last:])
    return ''.join(parts)


def map_span(low: int, high: int, at: int, count: int, delete: bool, limit: int) -> tuple[int, int] | None:
    """Khoảng [low, high] (hàng hay cột) sau khi chèn ``count`` hàng/cột ở vị trí ``at`` hoặc xóa [at, at+count).
    None khi cả khoảng bị xóa. Như Excel: chèn ở giữa thì khoảng nới ra, chèn ngay đầu thì cả khoảng dời xuống."""
    if not delete:
        if at <= low:
            low, high = low + count, high + count
        elif at <= high:
            high += count
        if low >= limit:
            return None
        return low, min(high, limit - 1)
    end = at + count - 1
    if high < at:
        return low, high
    if low > end:
        return low - count, high - count
    if low >= at and high <= end:
        return None
    return (low if low < at else at), (high - count if high > end else at - 1)


def same_sheet(name: str | None, other: str) -> bool:
    return name is not None and name.casefold() == other.casefold()


def adjacent(ref: Ref, axis: str, at: int) -> bool:
    """Vùng nhiều hàng (nhiều cột) kết thúc ngay trước chỗ chèn: vùng dữ liệu mà hàng tổng ngay dưới cộng lại."""
    if ref.kind != 'area':
        return False
    if axis == 'row':
        return ref.r2 == at - 1 and ref.r1 < ref.r2
    return ref.c2 == at - 1 and ref.c1 < ref.c2


def shifter(own_sheet: str | None, target: str, axis: str, at: int, count: int, delete: bool,
            order: list[str] | None = None, extend=None):
    """Hàm đổi tham chiếu khi chèn/xóa hàng (axis='row') hay cột ('col') trên trang ``target``. ``own_sheet`` là trang
    chứa công thức (tham chiếu không ghi trang thuộc trang đó); None cho chữ luôn ghi trang (tên vùng, biểu đồ).
    ``extend(ref)`` trả True cho vùng kết thúc ngay trên chỗ chèn cần nới thêm các hàng mới (hàng tổng ngay dưới)."""
    def change(ref: Ref):
        if extend is not None and not delete and not ref.external and ref.sheet2 is None \
                and same_sheet(ref.sheet if ref.sheet is not None else own_sheet, target) \
                and adjacent(ref, axis, at) and extend(ref):
            if axis == 'row':
                return ref.prefix + body_text(ref, ref.r1, ref.c1, min(ref.r2 + count, MAX_ROWS - 1), ref.c2)
            return ref.prefix + body_text(ref, ref.r1, ref.c1, ref.r2, min(ref.c2 + count, MAX_COLS - 1))
        return _shift(ref)

    def _shift(ref: Ref):
        if ref.external:
            return None
        if ref.sheet2 is not None:
            names = [name.casefold() for name in order or []]
            try:
                low, high = sorted((names.index(ref.sheet.casefold()), names.index(ref.sheet2.casefold())))
                inside = low <= names.index(target.casefold()) <= high
            except ValueError:
                inside = same_sheet(ref.sheet, target) or same_sheet(ref.sheet2, target)
            if inside:
                raise Unsupported('tham chiếu 3D qua nhiều trang tính')
            return None
        sheet = ref.sheet if ref.sheet is not None else own_sheet
        if not same_sheet(sheet, target):
            return None
        r1, c1, r2, c2 = ref.r1, ref.c1, ref.r2, ref.c2
        if axis == 'row':
            if ref.kind == 'cols':
                return None
            span = map_span(r1, r2, at, count, delete, MAX_ROWS)
            if span == (r1, r2):
                return None
            if span is None:
                return ref.prefix + '#REF!'
            r1, r2 = span
        else:
            if ref.kind == 'rows':
                return None
            span = map_span(c1, c2, at, count, delete, MAX_COLS)
            if span == (c1, c2):
                return None
            if span is None:
                return ref.prefix + '#REF!'
            c1, c2 = span
        return ref.prefix + body_text(ref, r1, c1, r2, c2)
    return change


def relative(rows: int, cols: int):
    """Hàm dời tham chiếu tương đối (không có $) đi ``rows`` hàng, ``cols`` cột: chép công thức sang ô khác như Excel
    (kéo điền, công thức chung của nhiều ô). Ra ngoài trang tính thì thành #REF!."""
    def change(ref: Ref):
        r1, c1, r2, c2 = ref.r1, ref.c1, ref.r2, ref.c2
        if ref.kind != 'cols':
            r1 = r1 if ref.ar1 else r1 + rows
            r2 = r2 if ref.ar2 else r2 + rows
        if ref.kind != 'rows':
            c1 = c1 if ref.ac1 else c1 + cols
            c2 = c2 if ref.ac2 else c2 + cols
        if (r1, c1, r2, c2) == (ref.r1, ref.c1, ref.r2, ref.c2):
            return None
        if ref.kind != 'cols' and not (0 <= min(r1, r2) and max(r1, r2) < MAX_ROWS):
            return ref.prefix + '#REF!'
        if ref.kind != 'rows' and not (0 <= min(c1, c2) and max(c1, c2) < MAX_COLS):
            return ref.prefix + '#REF!'
        return ref.prefix + body_text(ref, r1, c1, r2, c2)
    return change


def renamer(old: str, new: str):
    """Hàm đổi tên trang trong phần trang của tham chiếu (cả hai đầu của tham chiếu 3D)."""
    def change(ref: Ref):
        if ref.external or not (same_sheet(ref.sheet, old) or same_sheet(ref.sheet2, old)):
            return None
        first = new if same_sheet(ref.sheet, old) else ref.sheet
        if ref.sheet2 is None:
            prefix = quote_sheet(first) + '!'
        else:
            last = new if same_sheet(ref.sheet2, old) else ref.sheet2
            span = f'{first}:{last}'
            prefix = (span if quote_sheet(first) == first and quote_sheet(last) == last
                      else "'" + span.replace("'", "''") + "'") + '!'
        return prefix + ref_body(ref)
    return change


def ref_body(ref: Ref) -> str:
    return body_text(ref, ref.r1, ref.c1, ref.r2, ref.c2)


# ---------- tham chiếu Bảng có cấu trúc (Bang1[Cột], [@Cột], Bang1[[#This Row],[Cột]]) ----------

@dataclass
class Structured:
    table: str | None        # tên Bảng; None là Bảng chứa chính ô công thức ([@Cột])
    start: int               # vị trí '[' mở
    end: int                 # ngay sau ']' đóng
    columns: list[str]       # tên cột (đã bỏ ký tự thoát '); hai tên với range=True là khoảng cột
    specials: set[str]       # #all, #data, #headers, #totals, #this row (chữ thường)
    range: bool = False


def _split_items(content: str) -> list[tuple[str, str]]:
    """Các mục của phần trong ngoặc (ngăn bằng , hoặc : ở mức ngoài cùng): (mục, dấu ngăn đứng trước)."""
    items, depth, start, separator, index = [], 0, 0, '', 0
    while index < len(content):
        char = content[index]
        if char == "'":
            index += 2
            continue
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
        elif char in ',:' and depth == 0:
            items.append((content[start:index], separator))
            separator, start = char, index + 1
        index += 1
    items.append((content[start:], separator))
    return items


def _unescape_column(name: str) -> str:
    return re.sub(r"'(.)", r'\1', name)


def _escape_column(name: str) -> str:
    return re.sub(r"([\[\]#'])", r"'\1", name)


def _item(raw: str) -> tuple[str | None, str | None, bool]:
    """(tên cột, mục đặc biệt, có @) của một mục."""
    text = raw.strip()
    this_row = text.startswith('@')
    if this_row:
        text = text[1:].strip()
    if text.startswith('[') and text.endswith(']'):
        text = text[1:-1]
    if not text:
        return None, '#this row' if this_row else None, this_row
    if text.startswith('#'):
        return None, text.casefold(), this_row
    return _unescape_column(text), '#this row' if this_row else None, this_row


def structured(text: str) -> list[Structured]:
    out = []
    for match in _structured_spans(text):
        table, start, end = match
        content = text[start + 1:end - 1]
        columns, specials, ranged = [], set(), False
        for raw, separator in _split_items(content):
            name, special, _ = _item(raw)
            if special:
                specials.add(special)
            if name is not None:
                columns.append(name)
                ranged = ranged or separator == ':'
        out.append(Structured(table, start, end, columns, specials, ranged))
    return out


def _structured_spans(text: str):
    """(tên Bảng hoặc None, vị trí '[', vị trí sau ']') của mọi tham chiếu có cấu trúc, bỏ qua chuỗi chữ."""
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == '"':
            end = pos + 1
            while end < len(text):
                if text[end] == '"':
                    if text[end + 1:end + 2] == '"':
                        end += 2
                        continue
                    break
                end += 1
            pos = end + 1
            continue
        if char == "'":
            match = _QUOTED.match(text, pos)
            pos = match.end() if match else pos + 1
            continue
        if char.isalpha() or char in '_\\':
            match = _IDENT.match(text, pos)
            after = match.end() if match else pos + 1
            if text[after:after + 1] == '[':
                end = _bracket_end(text, after)
                yield match.group(0), after, end
                pos = end
                continue
            pos = after
            continue
        if char == '[':
            end = _bracket_end(text, pos)
            after = _QUOTED.match(text, end) or _IDENT.match(text, end)
            if not (after and text[after.end():after.end() + 1] == '!'):
                yield None, pos, end
            pos = end
            continue
        pos += 1


def rename_column(text: str, table: str, old: str, new: str, inside: bool) -> str:
    """Đổi tên cột ``old`` thành ``new`` trong tham chiếu tới Bảng ``table`` (có ghi tên Bảng, hoặc không ghi tên khi
    công thức nằm trong chính Bảng đó: ``inside``)."""
    spans = [span for span in _structured_spans(text)
             if (span[0] is not None and span[0].casefold() == table.casefold()) or (span[0] is None and inside)]
    for _, start, end in reversed(spans):
        content = text[start + 1:end - 1]
        items = _split_items(content)
        rebuilt, changed = [], False
        for raw, separator in items:
            name, special, this_row = _item(raw)
            if name is not None and name.casefold() == old.casefold():
                escaped = _escape_column(new)
                if len(items) == 1:
                    raw = ('@' if this_row else '') + (f'[{escaped}]' if this_row and raw.strip()[1:].strip().startswith('[')
                                                       else escaped)
                else:
                    raw = ('@' if this_row else '') + f'[{escaped}]'
                changed = True
            rebuilt.append(separator + raw)
        if changed:
            text = text[:start + 1] + ''.join(rebuilt) + text[end - 1:]
    return text


def rename_sheet(text: str, old: str, new: str) -> str:
    """Đổi tên trang trong cả tham chiếu ô lẫn tên vùng có ghi trang (Trang!TênVùng)."""
    text = rewrite(text, renamer(old, new))
    spans = [item for item in scan(text).names if same_sheet(item.sheet, old)]
    for item in reversed(spans):
        text = text[:item.start] + quote_sheet(new) + '!' + text[item.body_start:]
    return text
