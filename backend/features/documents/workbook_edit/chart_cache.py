"""Số liệu lưu sẵn trong biểu đồ: numCache/strCache của biểu đồ thường, lvl của biểu đồ kiểu mới (chartEx).

Excel vẽ lại biểu đồ từ ô khi mở tệp, nhưng trình xem trên điện thoại và bộ đọc của Peto (workbook_parts) dùng số lưu
sẵn. Bản sửa bảng điểm ngày 5/10/2026 để nguyên số đó: ô đếm xếp loại đã là Giỏi 2, Khá 2 mà biểu đồ vẫn đọc ra Giỏi 1,
Khá 0. Nên chuỗi số liệu nào trỏ vào ô vừa đổi, hay vào trang vừa chèn/xóa hàng cột, được lấy lại từ ô như kết quả công
thức (recalc). Biểu đồ không bị chạm giữ nguyên từng byte.
"""
from __future__ import annotations

from lxml import etree

from features.documents.sheets import engine
from features.documents.workbook_edit import refs
from features.documents.workbook_edit.book import Book
from features.documents.workbook_edit.package import local
from features.documents.workbook_edit.structure import chart_parts
from features.documents.workbook_reader import general

MAX_POINTS = 10_000


def refresh(book: Book, touched: dict[str, set[tuple[int, int]]], structural: set[str]) -> int:
    """``touched``: tên trang → ô vừa đổi giá trị (ô ghi mới và công thức tính lại); ``structural``: tên trang vừa
    chèn/xóa hàng cột. Trả về số biểu đồ đã cập nhật."""
    touched = {name.casefold(): cells for name, cells in touched.items() if cells}
    structural = {name.casefold() for name in structural}
    if not touched and not structural:
        return 0
    updated = 0
    for path in chart_parts(book):
        root = book.package.xml(path)
        changed = False
        for element in list(root.iter()):
            if not isinstance(element.tag, str):
                continue
            name = local(element.tag)
            if name in ('numRef', 'strRef'):
                changed = _refresh_cache(book, element, touched, structural) or changed
            elif name in ('numDim', 'strDim'):
                changed = _refresh_level(book, element, touched, structural) or changed
        if changed:
            book.package.write_xml(path, root)
            updated += 1
    return updated


def _child(element, name: str):
    return next((child for child in element if isinstance(child.tag, str) and local(child.tag) == name), None)


def _values(book: Book, reference: str, touched, structural) -> list | None:
    """Giá trị các ô của vùng (một vùng có tên trang) khi vùng chạm ô vừa đổi hay trang vừa chèn/xóa; None khi không
    cần hoặc không lấy lại được (tên vùng, nhiều vùng, cả cột, vùng quá lớn): khi đó số lưu sẵn giữ nguyên."""
    found = refs.scan(reference or '')
    if len(found.refs) != 1 or found.names:
        return None
    ref = found.refs[0]
    if ref.sheet is None or ref.sheet2 is not None or ref.external or None in (ref.r1, ref.c1, ref.r2, ref.c2):
        return None
    key = ref.sheet.casefold()
    if key not in structural and not any(ref.r1 <= row <= ref.r2 and ref.c1 <= col <= ref.c2
                                         for row, col in touched.get(key, ())):
        return None
    if (ref.r2 - ref.r1 + 1) * (ref.c2 - ref.c1 + 1) > MAX_POINTS:
        return None
    try:
        sheet = book.worksheet(book.info(ref.sheet))
    except Exception:
        return None
    values = []
    for row in range(ref.r1, ref.r2 + 1):
        for col in range(ref.c1, ref.c2 + 1):
            cell = sheet.get(row, col)
            values.append(book.value(cell) if cell is not None else None)
    return values


def _number(value) -> str | None:
    """Điểm của chuỗi số: ô không phải số (trống, chữ, lỗi) không có điểm, như Excel ghi."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return str(int(number)) if number == int(number) and abs(number) < 1e15 else repr(number)


def _text(value) -> str | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, engine.XLError):
        return value.code
    if isinstance(value, float):
        return general(value)
    return str(value)


def _points(values: list, numeric: bool) -> list[tuple[int, str]]:
    show = _number if numeric else _text
    return [(index, text) for index, value in enumerate(values) if (text := show(value)) is not None]


def _refresh_cache(book: Book, element, touched, structural) -> bool:
    """c:numRef / c:strRef: c:f rồi c:numCache (formatCode, ptCount, pt…) hoặc c:strCache (ptCount, pt…)."""
    formula = _child(element, 'f')
    numeric = local(element.tag) == 'numRef'
    cache = _child(element, 'numCache' if numeric else 'strCache')
    if formula is None or cache is None:
        return False
    values = _values(book, formula.text, touched, structural)
    if values is None:
        return False
    points = _points(values, numeric)
    count = _child(cache, 'ptCount')
    old = [(point.get('idx'), (_child(point, 'v').text or '') if _child(point, 'v') is not None else None)
           for point in cache if isinstance(point.tag, str) and local(point.tag) == 'pt']
    if count is not None and count.get('val') == str(len(values)) and old == [(str(i), t) for i, t in points]:
        return False
    prefix = element.tag[:len(element.tag) - len(local(element.tag))]
    for child in list(cache):
        if isinstance(child.tag, str) and local(child.tag) in ('ptCount', 'pt'):
            cache.remove(child)
    code = _child(cache, 'formatCode')
    at = list(cache).index(code) + 1 if code is not None else 0
    count = etree.Element(prefix + 'ptCount', val=str(len(values)))
    cache.insert(at, count)
    for offset, (index, text) in enumerate(points, start=1):
        point = etree.Element(prefix + 'pt', idx=str(index))
        etree.SubElement(point, prefix + 'v').text = text
        cache.insert(at + offset, point)
    return True


def _refresh_level(book: Book, element, touched, structural) -> bool:
    """cx:numDim / cx:strDim của chartEx: cx:f rồi một cx:lvl (ptCount, cx:pt mang giá trị). Nhãn nhiều tầng (nhiều
    lvl) giữ nguyên."""
    formula = _child(element, 'f')
    levels = [child for child in element if isinstance(child.tag, str) and local(child.tag) == 'lvl']
    if formula is None or len(levels) != 1:
        return False
    values = _values(book, formula.text, touched, structural)
    if values is None:
        return False
    level = levels[0]
    points = _points(values, local(element.tag) == 'numDim')
    old = [(point.get('idx'), point.text or '') for point in level if isinstance(point.tag, str) and local(point.tag) == 'pt']
    if level.get('ptCount') == str(len(values)) and old == [(str(i), t) for i, t in points]:
        return False
    prefix = element.tag[:len(element.tag) - len(local(element.tag))]
    for child in list(level):
        if isinstance(child.tag, str) and local(child.tag) == 'pt':
            level.remove(child)
    level.set('ptCount', str(len(values)))
    for offset, (index, text) in enumerate(points):
        point = etree.Element(prefix + 'pt', idx=str(index))
        point.text = text
        level.insert(offset, point)
    return True
