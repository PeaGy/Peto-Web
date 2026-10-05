"""Thông tin quanh ô của một trang tính đang sửa: vùng gộp, Bảng (Table), bảng tổng hợp. Dùng để chặn thay đổi Excel
cũng chặn (ghi vào giữa ô gộp, vào bảng tổng hợp) và để giữ Bảng khớp với ô (tên cột ở hàng tiêu đề, vùng của Bảng).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from features.documents.workbook_edit import refs
from features.documents.workbook_edit.package import local
from features.documents.workbook_edit.sheetxml import Worksheet, attributes

_MERGE = re.compile(r'<(?:[\w.-]+:)?mergeCell\b([^>]*?)/?>')


def area_of(text: str) -> tuple[int, int, int, int] | None:
    found = refs.scan(text or '').refs
    if not found or found[0].r1 is None or found[0].c1 is None:
        return None
    ref = found[0]
    return ref.r1, ref.c1, ref.r2, ref.c2


def area_text(r1: int, c1: int, r2: int, c2: int) -> str:
    from features.documents.workbook_edit.sheetxml import address
    return address(r1, c1) if (r1, c1) == (r2, c2) else f'{address(r1, c1)}:{address(r2, c2)}'


def merges(sheet: Worksheet) -> list[tuple[int, int, int, int]]:
    if sheet.skeleton_root is not None:
        texts = [element.get('ref', '') for element in sheet.skeleton_root.iter()
                 if isinstance(element.tag, str) and local(element.tag) == 'mergeCell']
    else:
        texts = [attributes(match.group(1)).get('ref', '') for match in _MERGE.finditer(sheet.after)]
    return [area for area in map(area_of, texts) if area]


@dataclass
class Table:
    part: str
    root: object
    name: str
    r1: int
    c1: int
    r2: int
    c2: int
    header: bool
    totals: bool

    def columns(self) -> list:
        holder = next((child for child in self.root if local(child.tag) == 'tableColumns'), None)
        return [child for child in holder if local(child.tag) == 'tableColumn'] if holder is not None else []

    def set_area(self, r1: int, c1: int, r2: int, c2: int) -> None:
        self.r1, self.c1, self.r2, self.c2 = r1, c1, r2, c2
        self.root.set('ref', area_text(r1, c1, r2, c2))
        for child in self.root:
            if local(child.tag) == 'autoFilter':
                child.set('ref', area_text(r1, c1, r2 - (1 if self.totals else 0), c2))

    def add_column(self, name: str) -> None:
        holder = next((child for child in self.root if local(child.tag) == 'tableColumns'), None)
        if holder is None:
            return
        used = [int(child.get('id', '0') or 0) for child in self.columns()]
        element = etree.SubElement(holder, holder.tag.replace('tableColumns', 'tableColumn'))
        element.set('id', str(max(used, default=0) + 1))
        element.set('name', name)
        holder.set('count', str(len(self.columns())))


def tables(book, sheet: Worksheet) -> list[Table]:
    out = []
    for target in book.package.relationships(sheet.part).find('/table'):
        if not book.package.exists(target):
            continue
        root = book.package.xml(target)
        area = area_of(root.get('ref', ''))
        if area is None:
            continue
        out.append(Table(target, root, root.get('displayName') or root.get('name', ''), *area,
                         (root.get('headerRowCount') or '1') != '0', (root.get('totalsRowCount') or '0') not in ('0', '')))
    return out


def all_tables(book) -> list[Table]:
    found = []
    for info in book.data_sheets():
        if info.part in book.worksheets:
            found.extend(tables(book, book.worksheets[info.part]))
    return found


def pivots(book, sheet: Worksheet) -> list[tuple[str, tuple[int, int, int, int], str]]:
    """(Tên, vùng, phần XML) của các bảng tổng hợp đặt trên trang."""
    out = []
    for target in book.package.relationships(sheet.part).find('/pivotTable'):
        if not book.package.exists(target):
            continue
        root = book.package.xml(target)
        location = next((child for child in root if local(child.tag) == 'location'), None)
        area = area_of(location.get('ref', '')) if location is not None else None
        if area:
            out.append((root.get('name', ''), area, target))
    return out


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
