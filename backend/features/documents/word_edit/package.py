"""Gói ZIP của tệp Word khi sửa: chỉ ghi lại word/document.xml, mọi phần khác (ảnh, kiểu, đánh số, đầu trang…) giữ
nguyên từng byte, cùng tên, thứ tự, ngày giờ và cách nén.

Phần XML mở bằng lxml, vì lxml giữ nguyên các khai báo không gian tên mà mc:Ignorable cần (ElementTree bỏ khai báo nó
cho là thừa, và Word báo tệp hỏng). Không bao giờ nhận DTD hay thực thể. Giới hạn cỡ giống bộ đọc (reader._docx).
"""
from __future__ import annotations

import io
import re
import zipfile

from lxml import etree

from features.documents.reader import MAX_XML_BYTES, MAX_ZIP_BYTES

MAX_ENTRIES = 2000
DOCUMENT = 'word/document.xml'
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
STRICT_W_NS = 'http://purl.oclc.org/ooxml/wordprocessingml/main'
DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
CFB_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
                          remove_blank_text=False, remove_comments=False)


class EditError(ValueError):
    """Lời giải thích (tiếng Việt) vì sao chưa sửa được; trả về cho model để sửa yêu cầu hoặc báo người dùng."""


def parse(data: bytes):
    if re.search(rb'<!DOCTYPE|<!ENTITY', data[:8192], re.I):
        raise EditError('Tệp Word có phần khai báo DTD lạ nên Peto không sửa. Hãy mở bằng Word rồi lưu lại.')
    try:
        return etree.fromstring(data, _PARSER)
    except etree.XMLSyntaxError:
        raise EditError('Một phần của tệp Word bị lỗi cấu trúc. Hãy mở bằng Word rồi lưu lại.') from None


class Package:
    def __init__(self, data: bytes):
        if data.startswith(CFB_MAGIC):
            raise EditError('Tệp Word đang đặt mật khẩu, hoặc là định dạng .doc cũ. Mở khóa hoặc lưu lại thành .docx rồi '
                            'gửi lại nhé.')
        try:
            self.archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise EditError('Tệp không phải Word .docx hợp lệ. Thử mở bằng Word rồi lưu lại.') from None
        self.infos = self.archive.infolist()
        if (len(self.infos) > MAX_ENTRIES or sum(item.file_size for item in self.infos) > MAX_ZIP_BYTES
                or len({item.filename for item in self.infos}) != len(self.infos)):
            raise EditError('Tệp Word có cấu trúc nén quá lớn hoặc không hợp lệ.')
        if any(item.flag_bits & 1 for item in self.infos):
            raise EditError('Tệp Word bị mã hóa. Hãy gửi bản đã mở khóa.')
        self.names = {item.filename: item for item in self.infos}
        if DOCUMENT not in self.names:
            raise EditError('Tệp Word thiếu phần nội dung (word/document.xml). Thử mở bằng Word rồi lưu lại.')

    def read(self, name: str) -> bytes | None:
        info = self.names.get(name)
        if info is None:
            return None
        if info.file_size > MAX_XML_BYTES:
            raise EditError('Nội dung tệp Word quá lớn để sửa. Hãy chia nhỏ tài liệu.')
        try:
            with self.archive.open(info) as member:
                data = member.read(MAX_XML_BYTES + 1)
        except (zipfile.BadZipFile, EOFError, OSError, ValueError):
            raise EditError('Một phần của tệp Word bị hỏng. Thử mở bằng Word rồi lưu lại.') from None
        if len(data) > MAX_XML_BYTES:
            raise EditError('Nội dung tệp Word quá lớn để sửa. Hãy chia nhỏ tài liệu.')
        return data

    def document(self):
        root = parse(self.read(DOCUMENT))
        if root.tag == f'{{{STRICT_W_NS}}}document':
            raise EditError('Tệp Word lưu kiểu "Strict Open XML" nên Peto chưa sửa được. Mở bằng Word, chọn Lưu thành '
                            'Word Document (.docx) rồi gửi lại.')
        if root.tag != f'{{{W_NS}}}document':
            raise EditError('Tệp không có cấu trúc Word quen thuộc. Thử mở bằng Word rồi lưu lại.')
        return root

    def optional(self, name: str):
        """numbering.xml, styles.xml: thiếu hay hỏng thì bỏ qua, như bộ đọc."""
        try:
            data = self.read(name)
            return parse(data) if data else None
        except EditError:
            return None

    def save(self, document_root) -> bytes:
        document = (DECLARATION + etree.tostring(document_root, encoding='unicode')).encode('utf-8')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for info in self.infos:
                try:
                    data = document if info.filename == DOCUMENT else self.archive.read(info)
                except (zipfile.BadZipFile, EOFError, OSError, ValueError):
                    raise EditError('Một phần của tệp Word bị hỏng. Thử mở bằng Word rồi lưu lại.') from None
                entry = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                entry.compress_type = info.compress_type if info.compress_type in (zipfile.ZIP_STORED,
                                                                                   zipfile.ZIP_DEFLATED) else zipfile.ZIP_DEFLATED
                entry.external_attr = info.external_attr
                archive.writestr(entry, data)
        return output.getvalue()
