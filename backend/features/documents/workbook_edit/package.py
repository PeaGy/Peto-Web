"""Gói ZIP của tệp Excel khi sửa: đọc từng phần có giới hạn cỡ, ghi lại phần đã đổi, giữ nguyên thứ tự, tên, ngày giờ
và cách nén của mọi phần khác.

Phần XML nhỏ (quan hệ, kiểu nội dung, workbook, styles, biểu đồ, bản vẽ, Bảng, ghi chú, bảng tổng hợp) mở bằng lxml,
vì lxml giữ nguyên các khai báo không gian tên: ElementTree bỏ khai báo nó cho là thừa, trong khi mc:Ignorable="x14ac"
vẫn cần chúng, và Excel báo tệp hỏng. Không bao giờ nhận DTD hay thực thể.
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile

from lxml import etree

from features.documents.workbook_reader import (CFB_MAGIC, MAX_DECLARED_BYTES, MAX_ENTRIES, MAX_PART_BYTES, _Limited,
                                                _Unreadable)

REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
MAX_SMALL_XML = 16 * 1024 * 1024

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
                          remove_blank_text=False, remove_comments=False)


class EditError(ValueError):
    """Lời giải thích (tiếng Việt) vì sao chưa sửa được; trả về cho model để sửa yêu cầu hoặc báo người dùng."""


def check_prolog(data: bytes) -> None:
    if re.search(rb'<!DOCTYPE|<!ENTITY', data[:8192], re.I):
        raise EditError('Tệp Excel có phần khai báo DTD lạ nên Peto không sửa. Hãy mở bằng Excel rồi lưu lại.')


def parse(data: bytes):
    check_prolog(data)
    try:
        return etree.fromstring(data, _PARSER)
    except etree.XMLSyntaxError:
        raise EditError('Một phần của tệp Excel bị lỗi cấu trúc. Hãy mở bằng Excel rồi lưu lại.') from None


def serialize(root) -> bytes:
    return (DECLARATION + etree.tostring(root, encoding='unicode')).encode('utf-8')


def local(tag) -> str:
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def resolve(folder: str, target: str) -> str:
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(folder, target))


class Relationships:
    """Tệp .rels của một phần: đọc, thêm, bỏ quan hệ."""

    def __init__(self, package: 'Package', part: str):
        self.package, self.part = package, part
        folder, name = posixpath.split(part)
        self.folder = folder
        self.path = posixpath.join(folder, '_rels', name + '.rels')
        self.root = package.xml(self.path) if package.exists(self.path) else etree.Element(f'{{{REL_NS}}}Relationships',
                                                                                         nsmap={None: REL_NS})
        self.changed = False

    def items(self) -> list[tuple[str, str, str, bool]]:
        """(Id, loại, đường dẫn trong gói, là liên kết ngoài)."""
        out = []
        for item in self.root:
            if local(item.tag) != 'Relationship':
                continue
            external = item.get('TargetMode') == 'External'
            target = item.get('Target', '')
            out.append((item.get('Id', ''), item.get('Type', ''), target if external else resolve(self.folder, target),
                        external))
        return out

    def find(self, suffix: str) -> list[str]:
        return [target for _, kind, target, external in self.items() if kind.endswith(suffix) and not external]

    def target(self, rid: str) -> str | None:
        return next((target for key, _, target, external in self.items() if key == rid and not external), None)

    def add(self, kind: str, target_part: str) -> str:
        used = {key for key, *_ in self.items()}
        number = 1
        while f'rId{number}' in used:
            number += 1
        rid = f'rId{number}'
        relative = posixpath.relpath(target_part, self.folder or '.') if self.folder else target_part
        etree.SubElement(self.root, f'{{{REL_NS}}}Relationship', Id=rid, Type=kind, Target=relative)
        self.changed = True
        return rid

    def remove(self, rid: str) -> None:
        for item in list(self.root):
            if item.get('Id') == rid:
                self.root.remove(item)
                self.changed = True

    def save(self) -> None:
        if self.changed:
            self.package.write(self.path, serialize(self.root))
            self.changed = False


class Package:
    def __init__(self, data: bytes):
        if data.startswith(CFB_MAGIC):
            raise EditError('Tệp Excel đang đặt mật khẩu, hoặc là định dạng .xls cũ. Mở khóa hoặc lưu lại thành .xlsx rồi '
                            'gửi lại nhé.')
        try:
            self.archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise EditError('Tệp không phải Excel .xlsx hợp lệ. Thử mở bằng Excel rồi lưu lại.') from None
        self.infos = self.archive.infolist()
        if (len(self.infos) > MAX_ENTRIES or sum(item.file_size for item in self.infos) > MAX_DECLARED_BYTES
                or len({item.filename for item in self.infos}) != len(self.infos)):
            raise EditError('Tệp Excel có cấu trúc nén quá lớn hoặc không hợp lệ.')
        if any(item.flag_bits & 1 for item in self.infos):
            raise EditError('Tệp Excel bị mã hóa. Hãy gửi bản đã mở khóa.')
        self.names = {item.filename: item for item in self.infos}
        self.changed: dict[str, bytes] = {}
        self.added: list[str] = []
        self.removed: set[str] = set()
        self._xml: dict[str, object] = {}
        self._rels: dict[str, Relationships] = {}

    def exists(self, name: str) -> bool:
        return name in self.changed or (name in self.names and name not in self.removed)

    def parts(self) -> list[str]:
        return [name for name in [*self.names, *self.added] if self.exists(name)]

    def read(self, name: str, limit: int = MAX_PART_BYTES) -> bytes:
        if name in self.changed:
            return self.changed[name]
        if name not in self.names or name in self.removed:
            raise EditError('Tệp Excel thiếu một phần cần thiết. Thử mở bằng Excel rồi lưu lại.')
        try:
            return _Limited(self.archive.open(self.names[name]), limit).read()
        except _Unreadable as error:
            raise EditError(str(error)) from None
        except (zipfile.BadZipFile, EOFError, OSError, ValueError):
            raise EditError('Một phần của tệp Excel bị hỏng. Thử mở bằng Excel rồi lưu lại.') from None

    def text(self, name: str) -> str:
        data = self.read(name)
        check_prolog(data)
        head = data[:200].decode('ascii', 'replace').lower()
        match = re.search(r'encoding=["\']([\w-]+)', head)
        if data.startswith((b'\xff\xfe', b'\xfe\xff')) or (match and match.group(1) not in ('utf-8', 'utf8')):
            raise EditError('Tệp Excel lưu bằng bảng mã lạ (không phải UTF-8). Hãy mở bằng Excel rồi lưu lại.')
        try:
            return data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise EditError('Một phần của tệp Excel bị lỗi bảng mã. Hãy mở bằng Excel rồi lưu lại.') from None

    def xml(self, name: str):
        """Phần XML nhỏ, mở một lần và dùng chung; sửa trên cây rồi gọi write_xml."""
        if name not in self._xml:
            self._xml[name] = parse(self.read(name, MAX_SMALL_XML))
        return self._xml[name]

    def write_xml(self, name: str, root) -> None:
        self._xml[name] = root
        self.write(name, serialize(root))

    def write(self, name: str, data: bytes) -> None:
        if name not in self.names and name not in self.added:
            self.added.append(name)
        self.removed.discard(name)
        self.changed[name] = data

    def remove(self, name: str) -> None:
        self.changed.pop(name, None)
        self._xml.pop(name, None)
        if name in self.added:
            self.added.remove(name)
        self.removed.add(name)

    def relationships(self, part: str) -> Relationships:
        """Quan hệ của một phần, dùng chung một đối tượng cho mỗi phần để các chỗ sửa không đè nhau."""
        if part not in self._rels:
            self._rels[part] = Relationships(self, part)
        return self._rels[part]

    def save(self) -> bytes:
        for relations in self._rels.values():
            relations.save()
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for info in self.infos:
                if not self.exists(info.filename):
                    continue
                data = self.changed.get(info.filename)
                if data is None:
                    data = self.read(info.filename)
                entry = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                entry.compress_type = info.compress_type if info.compress_type in (zipfile.ZIP_STORED,
                                                                                   zipfile.ZIP_DEFLATED) else zipfile.ZIP_DEFLATED
                entry.external_attr = info.external_attr
                archive.writestr(entry, data)
            for name in self.added:
                if self.exists(name):
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, self.changed[name])
        return output.getvalue()


class ContentTypes:
    PATH = '[Content_Types].xml'

    def __init__(self, package: Package):
        self.package = package
        self.root = package.xml(self.PATH)
        self.changed = False

    def of(self, part: str) -> str:
        name = '/' + part
        for item in self.root:
            if local(item.tag) == 'Override' and item.get('PartName', '').casefold() == name.casefold():
                return item.get('ContentType', '')
        extension = part.rsplit('.', 1)[-1].casefold()
        for item in self.root:
            if local(item.tag) == 'Default' and item.get('Extension', '').casefold() == extension:
                return item.get('ContentType', '')
        return ''

    def override(self, part: str, content_type: str) -> None:
        name = '/' + part
        for item in self.root:
            if local(item.tag) == 'Override' and item.get('PartName', '').casefold() == name.casefold():
                item.set('ContentType', content_type)
                self.changed = True
                return
        etree.SubElement(self.root, f'{{{CT_NS}}}Override', PartName=name, ContentType=content_type)
        self.changed = True

    def remove(self, part: str) -> None:
        name = '/' + part
        for item in list(self.root):
            if local(item.tag) == 'Override' and item.get('PartName', '').casefold() == name.casefold():
                self.root.remove(item)
                self.changed = True

    def save(self) -> None:
        if self.changed:
            self.package.write_xml(self.PATH, self.root)
            self.changed = False
