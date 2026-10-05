"""XML của một trang tính khi sửa: tách hàng và ô của sheetData, ghi lại đúng hàng đã đổi.

sheetData có thể rất lớn nên không dựng cây XML cho nó: hàng và ô được tách bằng biểu thức chính quy theo đúng cú pháp
Excel ghi (thẻ row, c, f, v, is), giữ nguyên chữ gốc của mọi hàng không đổi. Phần ngoài sheetData (vùng gộp, định dạng
có điều kiện, xác thực, siêu liên kết…) nhỏ, mở bằng lxml khi cần sửa (skeleton).
"""
from __future__ import annotations

import html
import re

from features.documents.workbook_edit.package import DECLARATION, EditError, parse

_ATTR = re.compile(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
_TAG_ATTRS = r'((?:[^>"\']|"[^"]*"|\'[^\']*\')*?)'
_ROW = re.compile(r'<(?:[\w.-]+:)?row\b' + _TAG_ATTRS + r'(/>|>(.*?)</(?:[\w.-]+:)?row\s*>)', re.S)
_CELL = re.compile(r'<(?:[\w.-]+:)?c\b' + _TAG_ATTRS + r'(/>|>(.*?)</(?:[\w.-]+:)?c\s*>)', re.S)
_F = re.compile(r'<(?:[\w.-]+:)?f\b' + _TAG_ATTRS + r'(/>|>(.*?)</(?:[\w.-]+:)?f\s*>)', re.S)
_V = re.compile(r'<(?:[\w.-]+:)?v\s*(/>|>(.*?)</(?:[\w.-]+:)?v\s*>)', re.S)
_IS = re.compile(r'<(?:[\w.-]+:)?is\s*>(.*?)</(?:[\w.-]+:)?is\s*>', re.S)
_T = re.compile(r'<(?:[\w.-]+:)?t\b[^>]*?(?:/>|>(.*?)</(?:[\w.-]+:)?t\s*>)', re.S)
_RPH = re.compile(r'<(?:[\w.-]+:)?rPh\b.*?</(?:[\w.-]+:)?rPh\s*>', re.S)
_REF = re.compile(r'([A-Za-z]{1,3})(\d{1,7})$')
_INVALID = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')
_ESCAPE_X = re.compile(r'_(x[0-9A-Fa-f]{4}_)')
MARKER = 'peto-sheet-data'


def attributes(text: str) -> dict[str, str]:
    """Thuộc tính của một thẻ, giữ nguyên chữ đã thoát (&amp;…) để ghi lại y như cũ."""
    return {match.group(1): match.group(2) if match.group(2) is not None else match.group(3)
            for match in _ATTR.finditer(text)}


def attribute_text(attrs: dict[str, str]) -> str:
    return ''.join(f' {key}="{value}"' for key, value in attrs.items())


def unescape(text: str) -> str:
    return html.unescape(text)


def escape(text: str) -> str:
    """Chữ đưa vào XML: bỏ ký tự điều khiển XML không cho phép, thoát &, <, > và mẫu _xHHHH_ (Excel đọc mẫu đó thành ký
    tự, nên chữ thật có mẫu ấy phải thoát dấu gạch dưới)."""
    text = _ESCAPE_X.sub(r'_x005F_\1', _INVALID.sub('', text))
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def escape_attr(text: str) -> str:
    return escape(text).replace('"', '&quot;')


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


class Cell:
    __slots__ = ('attrs', 'inner', 'raw')

    def __init__(self, attrs: dict[str, str], inner: str, raw: str | None = None):
        self.attrs, self.inner, self.raw = attrs, inner, raw

    @property
    def kind(self) -> str:
        return self.attrs.get('t', 'n')

    @property
    def style(self) -> int:
        try:
            return int(self.attrs.get('s', '0') or 0)
        except ValueError:
            return 0

    def formula(self) -> tuple[str | None, dict[str, str]]:
        """(Chữ công thức đã bỏ thoát, thuộc tính thẻ f); (None, {}) khi ô không có công thức."""
        match = _F.search(self.inner)
        if not match:
            return None, {}
        return unescape(match.group(3) or '') if match.group(2) != '/>' else '', attributes(match.group(1))

    def value(self) -> str | None:
        match = _V.search(self.inner)
        if not match or match.group(1) == '/>':
            return None
        return unescape(match.group(2) or '')

    def inline(self) -> str:
        match = _IS.search(self.inner)
        if not match:
            return ''
        body = _RPH.sub('', match.group(1))
        return ''.join(unescape(part.group(1) or '') for part in _T.finditer(body))

    @property
    def empty(self) -> bool:
        return not self.inner.strip()


def cell_inner(prefix: str, formula: str | None = None, formula_attrs: dict[str, str] | None = None,
               value: str | None = None, inline: str | None = None) -> str:
    parts = []
    if formula is not None:
        attrs = attribute_text(formula_attrs or {})
        parts.append(f'<{prefix}f{attrs}>{escape(formula)}</{prefix}f>' if formula else f'<{prefix}f{attrs}/>')
    if value is not None:
        parts.append(f'<{prefix}v>{escape(value)}</{prefix}v>')
    if inline is not None:
        space = ' xml:space="preserve"' if inline != inline.strip() or '\n' in inline else ''
        parts.append(f'<{prefix}is><{prefix}t{space}>{escape(inline)}</{prefix}t></{prefix}is>')
    return ''.join(parts)


def replace_value(cell: Cell, prefix: str, value: str | None, kind: str | None) -> None:
    """Đổi kết quả đã lưu của ô công thức, giữ thẻ f nguyên văn. ``value`` None là bỏ kết quả (Excel tính khi mở)."""
    match = _F.search(cell.inner)
    formula = match.group(0) if match else ''
    cell.inner = formula + (f'<{prefix}v>{escape(value)}</{prefix}v>' if value is not None else '')
    if kind and kind != 'n':
        cell.attrs['t'] = kind
    else:
        cell.attrs.pop('t', None)
    cell.raw = None


class Row:
    __slots__ = ('index', 'attrs', 'cells', 'extra', 'raw')

    def __init__(self, index: int, attrs: dict[str, str], cells: dict[int, Cell], extra: str = '', raw: str | None = None):
        self.index, self.attrs, self.cells, self.extra, self.raw = index, attrs, cells, extra, raw


class Worksheet:
    """Một trang tính: ``rows`` là {hàng (từ 0): Row}. Hàng có raw là hàng chưa đổi, ghi lại nguyên chữ gốc."""

    def __init__(self, name: str, part: str, text: str):
        self.name, self.part, self.original = name, part, text
        match = re.search(r'<(?:([\w.-]+):)?sheetData\b' + _TAG_ATTRS + r'(/?)>', text)
        if not match:
            raise EditError(f'Trang "{name}" thiếu phần dữ liệu ô. Thử mở bằng Excel rồi lưu lại.')
        self.prefix = f'{match.group(1)}:' if match.group(1) else ''
        self.before = text[:match.start()]
        if match.group(3) == '/':
            self.open_tag = f'<{self.prefix}sheetData{match.group(2)}>'
            body, self.after = '', text[match.end():]
        else:
            close = f'</{self.prefix}sheetData>'
            end = text.rfind(close)
            if end < match.end():
                raise EditError(f'Trang "{name}" bị lỗi cấu trúc. Thử mở bằng Excel rồi lưu lại.')
            self.open_tag = match.group(0)
            body, self.after = text[match.end():end], text[end + len(close):]
        self.rows: dict[int, Row] = {}
        self.modified = False
        self.skeleton_root = None
        self._columns: list[tuple[int, int, dict[str, str]]] | None = None
        self._parse(body)

    def _parse(self, body: str) -> None:
        position, previous = 0, -1
        for match in _ROW.finditer(body):
            if body[position:match.start()].strip():
                raise EditError(f'Trang "{self.name}" có cấu trúc lạ trong vùng ô. Thử mở bằng Excel rồi lưu lại.')
            position = match.end()
            attrs = attributes(match.group(1))
            try:
                index = int(attrs['r']) - 1 if 'r' in attrs else previous + 1
            except ValueError:
                index = previous + 1
            if index <= previous or index >= 1_048_576:
                raise EditError(f'Trang "{self.name}" có thứ tự hàng lạ. Thử mở bằng Excel rồi lưu lại.')
            previous = index
            cells: dict[int, Cell] = {}
            extra = []
            inner = match.group(3) or ''
            cell_position, last_col = 0, -1
            for cell in _CELL.finditer(inner):
                gap = inner[cell_position:cell.start()]
                if gap.strip():
                    extra.append(gap.strip())
                cell_position = cell.end()
                cell_attrs = attributes(cell.group(1))
                reference = _REF.match(cell_attrs.get('r', ''))
                col = column_index(reference.group(1)) if reference else last_col + 1
                if reference and int(reference.group(2)) - 1 != index:
                    raise EditError(f'Trang "{self.name}" có ô sai hàng. Thử mở bằng Excel rồi lưu lại.')
                last_col = col
                cells[col] = Cell(cell_attrs, cell.group(3) or '', cell.group(0) if reference else None)
            if inner[cell_position:].strip():
                extra.append(inner[cell_position:].strip())
            self.rows[index] = Row(index, attrs, cells, ''.join(extra), match.group(0) if 'r' in attrs else None)
        if body[position:].strip():
            raise EditError(f'Trang "{self.name}" có cấu trúc lạ trong vùng ô. Thử mở bằng Excel rồi lưu lại.')

    # ---------- đọc ----------

    def get(self, row: int, col: int) -> Cell | None:
        found = self.rows.get(row)
        return found.cells.get(col) if found else None

    def cells(self):
        for index in sorted(self.rows):
            row = self.rows[index]
            for col in sorted(row.cells):
                yield index, col, row.cells[col]

    def count(self) -> int:
        return sum(len(row.cells) for row in self.rows.values())

    def bounds(self) -> tuple[int, int, int, int] | None:
        """Vùng có ô (kể cả ô chỉ có định dạng), như thẻ dimension."""
        rows = [index for index, row in self.rows.items() if row.cells]
        if not rows:
            return None
        cols = [col for row in self.rows.values() for col in row.cells]
        return min(rows), min(cols), max(rows), max(cols)

    def columns(self) -> list[tuple[int, int, dict[str, str]]]:
        """Các thẻ col (cột đầu, cột cuối tính từ 0, thuộc tính) trong phần trước sheetData."""
        if self._columns is None:
            self._columns = []
            for match in re.finditer(r'<(?:[\w.-]+:)?col\b' + _TAG_ATTRS + r'/?>', self.before):
                attrs = attributes(match.group(1))
                try:
                    self._columns.append((int(attrs.get('min', '1')) - 1, int(attrs.get('max', '1')) - 1, attrs))
                except ValueError:
                    continue
        return self._columns

    def default_style(self, row: int, col: int) -> int:
        """Kiểu của một ô trống khi gõ vào, như Excel: kiểu của hàng nếu hàng có định dạng riêng, không thì của cột."""
        found = self.rows.get(row)
        if found and found.attrs.get('customFormat') in ('1', 'true') and found.attrs.get('s'):
            try:
                return int(found.attrs['s'])
            except ValueError:
                pass
        for low, high, attrs in self.columns():
            if low <= col <= high and attrs.get('style'):
                try:
                    return int(attrs['style'])
                except ValueError:
                    return 0
        return 0

    # ---------- ghi ----------

    def put(self, row: int, col: int, cell: Cell | None) -> None:
        """Đặt (hoặc bỏ khi None) một ô; hàng chưa có thì tạo."""
        found = self.rows.get(row)
        if found is None:
            if cell is None:
                return
            found = self.rows[row] = Row(row, {'r': str(row + 1)}, {})
        if cell is None:
            found.cells.pop(col, None)
        else:
            cell.raw = None
            found.cells[col] = cell
        found.raw = None
        self.modified = True

    def touch(self, row: int) -> None:
        if row in self.rows:
            self.rows[row].raw = None
            self.modified = True

    def skeleton(self):
        """Cây lxml của phần ngoài sheetData (sheetData thay bằng một thẻ đánh dấu rỗng)."""
        if self.skeleton_root is None:
            marker = f'<{self.prefix}sheetData {MARKER}="1"/>'
            self.skeleton_root = parse((self.before + marker + self.after).encode('utf-8'))
        self.modified = True
        return self.skeleton_root

    def set_dimension(self) -> None:
        bounds = self.bounds()
        ref = 'A1' if bounds is None else (address(bounds[0], bounds[1]) if bounds[:2] == bounds[2:] else
                                           f'{address(bounds[0], bounds[1])}:{address(bounds[2], bounds[3])}')
        if self.skeleton_root is not None:
            for element in self.skeleton_root.iter():
                if isinstance(element.tag, str) and element.tag.rsplit('}', 1)[-1] == 'dimension':
                    element.set('ref', ref)
                    return
            return
        self.before = re.sub(r'(<(?:[\w.-]+:)?dimension\b[^>]*?\bref=")[^"]*(")', lambda match: match.group(1) + ref +
                             match.group(2), self.before, count=1)

    def text(self) -> str:
        if not self.modified:
            return self.original
        before, after = self.before, self.after
        if self.skeleton_root is not None:
            from lxml import etree
            serialized = etree.tostring(self.skeleton_root, encoding='unicode')
            match = re.search(r'<(?:[\w.-]+:)?sheetData\b[^>]*\b' + MARKER + r'="1"[^>]*/>', serialized)
            if not match:
                raise EditError('Không ghi lại được trang tính.')
            before, after = DECLARATION + serialized[:match.start()], serialized[match.end():]
        parts = [before, self.open_tag]
        for index in sorted(self.rows):
            parts.append(self._row_xml(self.rows[index]))
        parts.append(f'</{self.prefix}sheetData>')
        parts.append(after)
        return ''.join(parts)

    def _row_xml(self, row: Row) -> str:
        if row.raw is not None:
            return row.raw
        prefix = self.prefix
        attrs = dict(row.attrs)
        attrs['r'] = str(row.index + 1)
        attrs = {'r': attrs.pop('r'), **attrs}
        if 'spans' in attrs:
            if row.cells:
                attrs['spans'] = f'{min(row.cells) + 1}:{max(row.cells) + 1}'
            else:
                attrs.pop('spans')
        cells = []
        for col in sorted(row.cells):
            cell = row.cells[col]
            if cell.raw is not None:
                cells.append(cell.raw)
                continue
            cell_attrs = {'r': address(row.index, col), **{key: value for key, value in cell.attrs.items() if key != 'r'}}
            if cell_attrs.get('s') in ('0', ''):
                cell_attrs.pop('s')
            body = cell.inner
            cells.append(f'<{prefix}c{attribute_text(cell_attrs)}>{body}</{prefix}c>' if body else
                         f'<{prefix}c{attribute_text(cell_attrs)}/>')
        content = ''.join(cells) + row.extra
        if not content and set(attrs) <= {'r', 'spans'}:
            return ''
        return f'<{prefix}row{attribute_text(attrs)}>{content}</{prefix}row>' if content else \
            f'<{prefix}row{attribute_text(attrs)}/>'
