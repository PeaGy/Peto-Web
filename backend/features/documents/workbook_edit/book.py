"""Một tệp Excel đang được sửa: trang tính, bảng chữ dùng chung, kiểu ô, tên vùng, và giá trị từng ô để tính lại công
thức. Ghi lại tệp bằng finish(): chỉ các phần đã đổi được viết lại.
"""
from __future__ import annotations

import io
import posixpath
import re
from dataclasses import dataclass
from datetime import date, datetime

from defusedxml.ElementTree import iterparse
from lxml import etree

from features.documents.sheets import engine
from features.documents.workbook_edit.package import (MAIN_NS, R_NS, ContentTypes, EditError, Package, check_prolog,
                                                      local, serialize)
from features.documents.workbook_edit.sheetxml import Cell, Worksheet, escape
from features.documents.workbook_edit.styles import Styles
from features.documents.workbook_reader import MAX_STRINGS

MAX_EDIT_CELLS = 250_000        # cả tệp; tệp lớn hơn thì không sửa trực tiếp
WORKSHEET_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet'
STRINGS_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings'
WORKSHEET_CONTENT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'
STRINGS_CONTENT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml'
MACRO_CONTENT = 'application/vnd.ms-excel.sheet.macroEnabled.main+xml'
_PROTECTED = re.compile(r'<(?:[\w.-]+:)?sheetProtection\b[^>]*\bsheet\s*=\s*["\'](?:1|true)["\']')


@dataclass
class SheetInfo:
    name: str
    part: str
    kind: str           # worksheet, chartsheet, other
    state: str
    element: object     # thẻ <sheet> trong workbook.xml


class SharedStrings:
    """Bảng chữ dùng chung (sharedStrings.xml). Chữ mới được nối vào cuối bảng; chữ trơn đã có thì dùng lại."""

    def __init__(self, package: Package, path: str | None):
        self.package, self.path = package, path
        self.strings: list[str] = []
        self.plain: dict[str, int] = {}
        self.new: list[str] = []
        self.references = 0
        if not path or not package.exists(path):
            self.path = None
            return
        data = package.read(path)
        check_prolog(data)
        for _, element in iterparse(io.BytesIO(data), events=('end',), forbid_dtd=True):
            if local(element.tag) != 'si':
                continue
            parts, rich = [], False
            for child in element:
                name = local(child.tag)
                if name == 't':
                    parts.append(child.text or '')
                elif name == 'r':
                    rich = True
                    parts.extend(grand.text or '' for grand in child if local(grand.tag) == 't')
            text = ''.join(parts)
            if not rich and text not in self.plain:
                self.plain[text] = len(self.strings)
            self.strings.append(text)
            element.clear()
            if len(self.strings) > MAX_STRINGS:
                raise EditError('Tệp có quá nhiều chữ khác nhau để Peto sửa trực tiếp.')

    def get(self, index: int) -> str:
        return self.strings[index] if 0 <= index < len(self.strings) else ''

    def add(self, text: str) -> int:
        self.references += 1
        if text in self.plain:
            return self.plain[text]
        index = len(self.strings)
        self.strings.append(text)
        self.plain[text] = index
        self.new.append(text)
        return index

    def save(self, book: 'Book') -> None:
        if not self.new and not self.references:
            return
        if self.path is None:
            if not self.new:
                return
            self.path = 'xl/sharedStrings.xml'
            items = ''.join(_string_item(text, '') for text in self.strings)
            body = (f'<sst xmlns="{MAIN_NS}" count="{self.references}" uniqueCount="{len(self.strings)}">{items}</sst>')
            self.package.write(self.path, (serialize_declaration() + body).encode('utf-8'))
            book.rels.add(STRINGS_TYPE, self.path)
            book.content_types.override(self.path, STRINGS_CONTENT)
            return
        text = self.package.text(self.path)
        root = re.search(r'<(?:([\w.-]+):)?sst\b[^>]*>', text)
        close = text.rfind(f'</{root.group(1)}:sst>' if root and root.group(1) else '</sst>') if root else -1
        if not root or close < 0:
            raise EditError('Bảng chữ của tệp bị lỗi cấu trúc. Hãy mở bằng Excel rồi lưu lại.')
        prefix = f'{root.group(1)}:' if root.group(1) else ''
        opening = root.group(0)

        def bump(name: str, amount: int, value: str) -> str:
            match = re.search(rf'\b{name}\s*=\s*"(\d+)"', value)
            return value if not match else value[:match.start(1)] + str(int(match.group(1)) + amount) + value[match.end(1):]

        opening = bump('uniqueCount', len(self.new), bump('count', self.references, opening))
        items = ''.join(_string_item(item, prefix) for item in self.new)
        text = text[:root.start()] + opening + text[root.end():close] + items + text[close:]
        self.package.write(self.path, text.encode('utf-8'))
        self.new, self.references = [], 0


def serialize_declaration() -> str:
    from features.documents.workbook_edit.package import DECLARATION
    return DECLARATION


def _string_item(text: str, prefix: str) -> str:
    space = ' xml:space="preserve"' if text != text.strip() or '\n' in text else ''
    return f'<{prefix}si><{prefix}t{space}>{escape(text)}</{prefix}t></{prefix}si>'


def excel_serial(day: date | datetime, date1904: bool) -> float:
    """Số sê-ri ngày của Excel (hệ 1900 hoặc 1904), có phần giờ."""
    moment = day if isinstance(day, datetime) else datetime(day.year, day.month, day.day)
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    delta = moment - base
    return delta.days + delta.seconds / 86400


class Book:
    def __init__(self, data: bytes):
        self.package = package = Package(data)
        office = next(iter(package.relationships('').find('/officeDocument')), 'xl/workbook.xml')
        if not package.exists(office):
            raise EditError('Không thấy phần dữ liệu của bảng tính. Tệp này có đúng là Excel .xlsx không?')
        self.workbook_part = office
        self.workbook = package.xml(office)
        if local(self.workbook.tag) != 'workbook':
            raise EditError('Tệp không phải bảng tính Excel.')
        self.rels = package.relationships(office)
        self.content_types = ContentTypes(package)
        self.macro = self.content_types.of(office) == MACRO_CONTENT
        self.workbook_changed = False
        self.date1904 = False
        self.locked = False
        self.sheets: list[SheetInfo] = []
        for section in self.workbook:
            name = local(section.tag)
            if name == 'workbookPr':
                self.date1904 = section.get('date1904', '').lower() in ('1', 'true')
            elif name == 'workbookProtection':
                self.locked = section.get('lockStructure', '').lower() in ('1', 'true')
            elif name == 'sheets':
                for item in section:
                    if local(item.tag) != 'sheet':
                        continue
                    rid = item.get(f'{{{R_NS}}}id') or next((value for key, value in item.attrib.items()
                                                             if local(key) == 'id'), '')
                    part = self.rels.target(rid) or ''
                    kind = next((relation for key, relation, *_ in self.rels.items() if key == rid), '')
                    self.sheets.append(SheetInfo(item.get('name', ''), part, 'worksheet' if kind.endswith('/worksheet')
                                                 else 'chartsheet' if kind.endswith('/chartsheet') else 'other',
                                                 item.get('state', 'visible'), item))
        self.strings = SharedStrings(package, next(iter(self.rels.find('/sharedStrings')), None))
        self.styles = Styles(package, next(iter(self.rels.find('/styles')), None), self)
        self.worksheets: dict[str, Worksheet] = {}
        self._loaded_cells = 0

    # ---------- trang tính ----------

    def info(self, name: str) -> SheetInfo:
        wanted = ' '.join(str(name or '').split())
        for item in self.sheets:
            if item.name == wanted:
                return item
        for item in self.sheets:
            if item.name.casefold() == wanted.casefold():
                return item
        listing = ', '.join(f'"{item.name}"' for item in self.sheets if item.kind == 'worksheet')
        raise EditError(f'Không có trang tính "{wanted[:60]}". Các trang tính: {listing}.')

    def worksheet(self, item: SheetInfo) -> Worksheet:
        if item.kind != 'worksheet':
            raise EditError(f'"{item.name}" là trang biểu đồ, không có ô để sửa.')
        if item.part not in self.worksheets:
            sheet = Worksheet(item.name, item.part, self.package.text(item.part))
            self._loaded_cells += sheet.count()
            if self._loaded_cells > MAX_EDIT_CELLS:
                raise EditError(f'Tệp lớn quá để Peto sửa trực tiếp (hơn {MAX_EDIT_CELLS:,} ô có dữ liệu). Hãy chia nhỏ '
                                'tệp, hoặc nhờ Peto tạo bảng tính mới từ phần cần dùng.'.replace(',', '.'))
            self.worksheets[item.part] = sheet
        sheet = self.worksheets[item.part]
        sheet.name = item.name
        return sheet

    def sheet(self, name: str) -> tuple[SheetInfo, Worksheet]:
        item = self.info(name)
        return item, self.worksheet(item)

    def data_sheets(self) -> list[SheetInfo]:
        return [item for item in self.sheets if item.kind == 'worksheet' and self.package.exists(item.part)]

    def protected(self, sheet: Worksheet) -> bool:
        return bool(_PROTECTED.search(sheet.before) or _PROTECTED.search(sheet.after))

    def sheet_rels(self, sheet: Worksheet):
        return self.package.relationships(sheet.part)

    # ---------- giá trị ô ----------

    def value(self, cell: Cell):
        """Giá trị kiểu bộ tính (float, str, bool, XLError, None) của một ô, theo kết quả đã lưu."""
        kind, raw = cell.kind, cell.value()
        if kind == 's':
            try:
                return self.strings.get(int(raw)) if raw is not None else None
            except ValueError:
                return None
        if kind == 'inlineStr':
            return cell.inline()
        if kind == 'str':
            return raw if raw is not None else ''
        if kind == 'b':
            return None if raw is None else raw.strip() in ('1', 'true')
        if kind == 'e':
            return engine.XLError(raw.strip()) if raw else None
        if kind == 'd':
            try:
                return excel_serial(datetime.fromisoformat(raw.strip().replace('Z', '')), self.date1904) if raw else None
            except ValueError:
                return raw
        if raw is None or not raw.strip():
            return None
        try:
            return float(raw)
        except ValueError:
            return raw

    # ---------- workbook.xml ----------

    def section(self, name: str):
        return next((child for child in self.workbook if local(child.tag) == name), None)

    def defined_names(self) -> list:
        names = self.section('definedNames')
        return [item for item in names if local(item.tag) == 'definedName'] if names is not None else []

    def calc_on_load(self) -> None:
        """Excel tính lại toàn bộ công thức khi mở tệp (kết quả Peto ghi sẵn chỉ để trình xem khác hiện đúng)."""
        calc = self.section('calcPr')
        if calc is None:
            namespace = self.workbook.tag[1:].split('}')[0] if self.workbook.tag.startswith('{') else MAIN_NS
            calc = etree.Element(f'{{{namespace}}}calcPr')
            # calcPr đứng sau definedNames (hoặc sheets, externalReferences, functionGroups) trong workbook.xml.
            anchor = None
            for position, child in enumerate(self.workbook):
                if local(child.tag) in ('sheets', 'functionGroups', 'externalReferences', 'definedNames'):
                    anchor = position
            self.workbook.insert((anchor + 1) if anchor is not None else len(self.workbook), calc)
            calc.set('calcId', '191029')
        if calc.get('fullCalcOnLoad') not in ('1', 'true'):
            calc.set('fullCalcOnLoad', '1')
        self.workbook_changed = True

    def drop_calc_chain(self) -> None:
        """Bỏ chuỗi tính (calcChain.xml): Excel dựng lại khi mở. Để nguyên thì Excel báo lỗi khi chuỗi nhắc ô không còn
        công thức."""
        for rid, kind, target, external in self.rels.items():
            if kind.endswith('/calcChain') and not external:
                self.rels.remove(rid)
                self.package.remove(target)
                self.content_types.remove(target)

    def next_part(self, folder: str, stem: str, extension: str) -> str:
        number = 1
        existing = {name.casefold() for name in self.package.parts()}
        while posixpath.join(folder, f'{stem}{number}.{extension}').casefold() in existing:
            number += 1
        return posixpath.join(folder, f'{stem}{number}.{extension}')

    def reader(self) -> '_ReaderView':
        """Gói nhìn như của bộ đọc (workbook_reader._Package), để dùng lại bộ đọc biểu đồ, ghi chú… (workbook_parts)."""
        return _ReaderView(self.package)

    def finish(self) -> bytes:
        for sheet in self.worksheets.values():
            if sheet.modified:
                self.package.write(sheet.part, sheet.text().encode('utf-8'))
        self.strings.save(self)
        self.styles.save()
        if self.workbook_changed:
            self.package.write_xml(self.workbook_part, self.workbook)
        self.content_types.save()
        return self.package.save()


class _ReaderView:
    """Đọc phần XML bằng defusedxml như bộ đọc tệp gửi lên (không có chú thích XML, cấm DTD)."""

    def __init__(self, package: Package):
        self.package = package
        self.names = set(package.parts())
        self._cache: dict[str, object] = {}

    def xml(self, name: str):
        if name not in self._cache:
            from defusedxml.ElementTree import fromstring
            data = self.package.read(name)
            check_prolog(data)
            self._cache[name] = fromstring(data, forbid_dtd=True)
        return self._cache[name]

    def relationships(self, part: str) -> dict[str, tuple[str, str]]:
        return {rid: (target, kind) for rid, kind, target, external in self.package.relationships(part).items()
                if not external}
