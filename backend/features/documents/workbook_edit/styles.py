"""Kiểu ô (xl/styles.xml) khi sửa tệp: loại hiển thị của từng kiểu, và kiểu mới dựng từ kiểu cũ của ô (thêm đậm, màu
chữ, màu nền, căn lề, định dạng số). Kiểu cũ không bao giờ bị sửa, vì nhiều ô khác có thể đang dùng chung nó; kiểu mới
trùng hệt một kiểu đã có thì dùng lại kiểu đó.
"""
from __future__ import annotations

from copy import deepcopy

from lxml import etree

from features.documents.workbook_edit.package import MAIN_NS, EditError, local, parse
from features.documents.workbook_reader import _BUILTIN_KINDS, format_decimals, format_kind

# Mã định dạng số có sẵn của Excel (không ghi trong tệp), để tìm lại id khi cần.
BUILTIN = {'General': 0, '0': 1, '0.00': 2, '#,##0': 3, '#,##0.00': 4, '0%': 9, '0.00%': 10, '0.00E+00': 11, '@': 49}
DATE_ID, DATETIME_ID = 14, 22


def argb(color: str) -> str:
    return 'FF' + color.lstrip('#').upper()


MINIMAL = (f'<styleSheet xmlns="{MAIN_NS}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/><family val="2"/>'
           '</font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill '
           'patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/>'
           '</border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles '
           'count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles '
           'count="0"/></styleSheet>')
STYLES_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles'
STYLES_CONTENT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'


class Styles:
    def __init__(self, package, path: str | None, book=None):
        self.package, self.path, self.book = package, path, book
        self.root = package.xml(path) if path else None
        self.changed = False
        self._cache: dict[tuple, int] = {}
        self.namespace = self.root.tag[1:].split('}')[0] if self.root is not None and self.root.tag.startswith('{') else ''

    def _create(self) -> None:
        """Tệp không có bảng kiểu ô (một số phần mềm ghi tệp như vậy): tạo bảng tối thiểu như Excel khi cần định dạng."""
        if self.book is None:
            raise EditError('Tệp không có bảng kiểu ô (styles.xml) nên Peto chưa đổi được định dạng.')
        self.path = 'xl/styles.xml'
        self.root = parse(MINIMAL.encode('utf-8'))
        self.namespace = MAIN_NS
        self.book.rels.add(STYLES_TYPE, self.path)
        self.book.content_types.override(self.path, STYLES_CONTENT)
        self.changed = True

    def _section(self, name: str, create: bool = False):
        if self.root is None:
            self._create()
        for child in self.root:
            if local(child.tag) == name:
                return child
        if not create:
            return None
        element = self._element(name)
        # numFmts luôn đứng đầu styleSheet.
        self.root.insert(0, element)
        return element

    def _tag(self, name: str) -> str:
        return f'{{{self.namespace}}}{name}' if self.namespace else name

    def _element(self, name: str, **attrs):
        """Phần tử mới dùng không gian tên mặc định như tệp Excel (không sinh tiền tố ns0:), để so khớp được với phần tử
        sẵn có."""
        return etree.Element(self._tag(name), attrs, nsmap={None: self.namespace} if self.namespace else None)

    def _items(self, section: str, item: str) -> list:
        found = self._section(section) if self.root is not None else None
        return [child for child in found if local(child.tag) == item] if found is not None else []

    def _append(self, section: str, element) -> int:
        container = self._section(section, create=True)
        container.append(element)
        items = [child for child in container if local(child.tag) == local(element.tag)]
        container.set('count', str(len(items)))
        self.changed = True
        return len(items) - 1

    # ---------- đọc ----------

    def code(self, index: int) -> tuple[int, str]:
        """(numFmtId, mã định dạng) của kiểu ô ``index``."""
        xfs = self._items('cellXfs', 'xf')
        if not xfs:
            return 0, 'General'
        xf = xfs[index] if 0 <= index < len(xfs) else xfs[0]
        try:
            number = int(xf.get('numFmtId', '0'))
        except ValueError:
            number = 0
        for item in self._items('numFmts', 'numFmt'):
            if item.get('numFmtId') == str(number):
                return number, item.get('formatCode', '')
        return number, next((code for code, key in BUILTIN.items() if key == number), '')

    def kind(self, index: int) -> tuple[str, int]:
        """(Loại hiển thị: number, percent, date, datetime, time, text; số chữ số thập phân)."""
        number, code = self.code(index)
        if code and number not in BUILTIN.values():
            return format_kind(code), format_decimals(code)
        return _BUILTIN_KINDS.get(number, 'number'), 2 if number in (2, 4, 10) else 0

    def count(self) -> int:
        return len(self._items('cellXfs', 'xf'))

    # ---------- tạo kiểu mới ----------

    def derive(self, index: int, *, number_format: int | str | None = None, bold: bool | None = None,
               italic: bool | None = None, color: str | None = None, fill: str | None = None,
               align: str | None = None) -> int:
        """Kiểu mới = kiểu ``index`` cộng các thay đổi; trả chỉ số kiểu trong cellXfs."""
        key = (index, number_format, bold, italic, color, fill, align)
        if key in self._cache:
            return self._cache[key]
        if self.root is None:
            self._create()
        xfs = self._items('cellXfs', 'xf')
        if not xfs:
            raise EditError('Bảng kiểu ô của tệp bị thiếu nên Peto chưa đổi được định dạng.')
        base = xfs[index] if 0 <= index < len(xfs) else xfs[0]
        xf = deepcopy(base)
        if number_format is not None:
            xf.set('numFmtId', str(self._number_format(number_format)))
            xf.set('applyNumberFormat', '1')
        if bold is not None or italic is not None or color is not None:
            xf.set('fontId', str(self._font(_int(base.get('fontId')), bold, italic, color)))
            xf.set('applyFont', '1')
        if fill is not None:
            xf.set('fillId', str(self._fill(fill)))
            xf.set('applyFill', '1')
        if align is not None:
            alignment = next((child for child in xf if local(child.tag) == 'alignment'), None)
            if alignment is None:
                alignment = self._element('alignment')
                xf.insert(0, alignment)
            alignment.set('horizontal', align)
            xf.set('applyAlignment', '1')
        serialized = _canonical(xf)
        result = next((number for number, existing in enumerate(xfs) if _canonical(existing) == serialized), None)
        if result is None:
            result = self._append('cellXfs', xf)
        self._cache[key] = result
        return result

    def _number_format(self, value: int | str) -> int:
        if isinstance(value, int):
            return value
        if value in BUILTIN:
            return BUILTIN[value]
        formats = self._items('numFmts', 'numFmt')
        for item in formats:
            if item.get('formatCode') == value:
                return _int(item.get('numFmtId'))
        number = max([163, *(_int(item.get('numFmtId')) for item in formats)]) + 1
        element = self._element('numFmt', numFmtId=str(number), formatCode=value)
        self._append('numFmts', element)
        return number

    def _font(self, index: int, bold: bool | None, italic: bool | None, color: str | None) -> int:
        fonts = self._items('fonts', 'font')
        if not fonts:
            raise EditError('Bảng kiểu ô của tệp thiếu phông chữ nên Peto chưa đổi được định dạng.')
        font = deepcopy(fonts[index] if 0 <= index < len(fonts) else fonts[0])
        for name, wanted in (('i', italic), ('b', bold)):
            if wanted is None:
                continue
            for child in [child for child in font if local(child.tag) == name]:
                font.remove(child)
            if wanted:
                font.insert(0, self._element(name))
        if color is not None:
            for child in [child for child in font if local(child.tag) == 'color']:
                font.remove(child)
            element = self._element('color', rgb=argb(color))
            anchor = next((position for position, child in enumerate(font) if local(child.tag) in ('name', 'family',
                                                                                                  'charset', 'scheme')), None)
            font.insert(anchor if anchor is not None else len(font), element)
        return self._reuse('fonts', 'font', fonts, font)

    def _fill(self, color: str) -> int:
        if color == 'none':
            return 0
        fills = self._items('fills', 'fill')
        fill = self._element('fill')
        pattern = etree.SubElement(fill, self._tag('patternFill'), patternType='solid')
        etree.SubElement(pattern, self._tag('fgColor'), rgb=argb(color))
        etree.SubElement(pattern, self._tag('bgColor'), indexed='64')
        return self._reuse('fills', 'fill', fills, fill)

    def _reuse(self, section: str, item: str, existing: list, element) -> int:
        serialized = _canonical(element)
        for number, current in enumerate(existing):
            if _canonical(current) == serialized:
                return number
        return self._append(section, element)

    def save(self) -> None:
        if self.changed and self.path:
            self.package.write_xml(self.path, self.root)
            self.changed = False


def _canonical(element) -> bytes:
    """Dạng chuẩn để so hai phần tử, không tính các khai báo không gian tên thừa hưởng từ phần tử cha."""
    return etree.tostring(element, method='c14n', exclusive=True)


def _int(value) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
