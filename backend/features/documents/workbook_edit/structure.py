"""Chèn/xóa hàng hoặc cột, thêm và đổi tên trang tính, với mọi chỗ trỏ tới ô đổi theo như Excel làm.

Khi chèn/xóa trên trang T: ô của T dời chỗ; mọi công thức (mọi trang), tên vùng, định dạng có điều kiện, xác thực dữ
liệu, sparkline, siêu liên kết, vùng gộp, bộ lọc, Bảng, hình và biểu đồ đặt trên T, ghi chú, bảng tổng hợp và vùng số
liệu của biểu đồ trỏ vào T đều được dời hoặc nới theo. Trường hợp Excel cũng từ chối (chèn xuyên qua bảng tổng hợp,
một phần công thức mảng) thì từ chối với lời giải thích.
"""
from __future__ import annotations

import posixpath
import re

from lxml import etree

from features.documents.workbook_edit import meta, refs
from features.documents.workbook_edit.book import (WORKSHEET_CONTENT, WORKSHEET_TYPE, Book, SheetInfo)
from features.documents.workbook_edit.formulas import array_ranges, expand_shared, formula_map, set_formula
from features.documents.workbook_edit.package import DECLARATION, MAIN_NS, R_NS, EditError, local
from features.documents.workbook_edit.sheetxml import MARKER, Cell, Row, Worksheet, address, cell_inner, column_letter

_FORMULA_TAGS = ('formula', 'formula1', 'formula2', 'f')       # f: xm:f của phần mở rộng x14
_NOTE = re.compile(r'<v:shape\b.*?</v:shape>', re.S)


def _limit(axis: str) -> int:
    return refs.MAX_ROWS if axis == 'row' else refs.MAX_COLS


def _point(index: int, at: int, count: int, delete: bool) -> int | None:
    span = refs.map_span(index, index, at, count, delete, 1 << 30)
    return span[0] if span else None


def _clamp(index: int, at: int, count: int, delete: bool) -> int:
    """Chỉ số của một mép hình (neo của hình, biểu đồ): mép nằm trong vùng xóa thì dời về chỗ vừa xóa."""
    moved = _point(index, at, count, delete)
    return at if moved is None else moved


def remap(cells: set[tuple[int, int]], axis: str, at: int, count: int, delete: bool) -> set[tuple[int, int]]:
    out = set()
    for row, col in cells:
        moved = _point(row if axis == 'row' else col, at, count, delete)
        if moved is not None:
            out.add((moved, col) if axis == 'row' else (row, moved))
    return out


def _map_area(area, axis: str, at: int, count: int, delete: bool):
    r1, c1, r2, c2 = area
    if axis == 'row':
        span = refs.map_span(r1, r2, at, count, delete, refs.MAX_ROWS)
        return None if span is None else (span[0], c1, span[1], c2)
    span = refs.map_span(c1, c2, at, count, delete, refs.MAX_COLS)
    return None if span is None else (r1, span[0], r2, span[1])


def _map_sqref(text: str, axis: str, at: int, count: int, delete: bool) -> str:
    """Danh sách vùng cách nhau bằng dấu cách (sqref); vùng bị xóa hết thì bỏ."""
    out = []
    for part in text.split():
        area = meta.area_of(part)
        if area is None:
            out.append(part)
            continue
        moved = _map_area(area, axis, at, count, delete)
        if moved is not None:
            out.append(meta.area_text(*moved))
    return ' '.join(out)


class _Counter:
    def __init__(self):
        self.broken = 0

    def wrap(self, change):
        def counted(ref):
            result = change(ref)
            if result is not None and result.endswith('#REF!'):
                self.broken += 1
            return result
        return counted


# ---------- kiểm tra trước ----------

def _check(book: Book, info: SheetInfo, sheet: Worksheet, axis: str, at: int, count: int, delete: bool) -> None:
    end = at + count - 1
    unit = 'hàng' if axis == 'row' else 'cột'

    def inside(low: int, high: int) -> bool:
        """Chèn xuyên qua [low, high] (không phải ngay mép trên/trái) hoặc xóa chạm một phần khoảng đó."""
        if not delete:
            return low < at <= high
        return not (end < low or at > high)

    def span(area):
        return (area[0], area[2]) if axis == 'row' else (area[1], area[3])

    bounds = sheet.bounds()
    if not delete and bounds and (bounds[2] if axis == 'row' else bounds[3]) + count >= _limit(axis):
        raise EditError(f'chèn thêm {count} {unit} sẽ đẩy dữ liệu ra ngoài giới hạn của Excel')
    for name, area, _ in meta.pivots(book, sheet):
        if inside(*span(area)):
            raise EditError(f'{unit} {_label(axis, at, end)} cắt qua bảng tổng hợp "{name}" ({meta.area_text(*area)}); Excel '
                            'cũng không cho chèn/xóa xuyên qua bảng tổng hợp')
    for low_row, low_col, high_row, high_col, kind in array_ranges(sheet):
        low, high = span((low_row, low_col, high_row, high_col))
        whole = delete and at <= low and end >= high
        if inside(low, high) and not whole:
            what = 'bảng dữ liệu (Data Table)' if kind == 'dataTable' else 'công thức mảng'
            raise EditError(f'{unit} {_label(axis, at, end)} cắt qua {what} '
                            f'{meta.area_text(low_row, low_col, high_row, high_col)}; Excel cũng không cho làm vậy')
    for table in meta.tables(book, sheet):
        area = (table.r1, table.c1, table.r2, table.c2)
        low, high = span(area)
        if axis == 'col' and inside(low, high):
            raise EditError(f'cột {_label(axis, at, end)} nằm trong Bảng "{table.name}" ({meta.area_text(*area)}); Peto chưa '
                            'chèn/xóa cột giữa một Bảng. Thêm cột ngay bên phải Bảng (ghi tên cột ở hàng tiêu đề) thì '
                            'Bảng tự nới ra')
        if axis == 'row' and delete and not (end < low or at > high):
            data_low = table.r1 + (1 if table.header else 0)
            data_high = table.r2 - (1 if table.totals else 0)
            if table.header and at <= table.r1 <= end:
                raise EditError(f'hàng {table.r1 + 1} là hàng tiêu đề của Bảng "{table.name}", không xóa được')
            if table.totals and at <= table.r2 <= end:
                raise EditError(f'hàng {table.r2 + 1} là hàng tổng của Bảng "{table.name}", không xóa được')
            if at <= data_low and end >= data_high:
                raise EditError(f'xóa hết hàng dữ liệu của Bảng "{table.name}" thì Bảng không còn hàng nào; giữ lại ít '
                                'nhất một hàng hoặc xóa nội dung bằng clear')
    for path in _pivot_caches(book):
        source = _worksheet_source(book, path)
        if source is not None and refs.same_sheet(source.get('sheet'), info.name) and delete:
            area = meta.area_of(source.get('ref', ''))
            if area and _map_area(area, axis, at, count, delete) is None:
                raise EditError(f'{unit} {_label(axis, at, end)} chứa toàn bộ vùng nguồn của một bảng tổng hợp; xóa '
                                'thì bảng tổng hợp mất nguồn')


def _label(axis: str, low: int, high: int) -> str:
    if axis == 'row':
        return f'{low + 1}' if low == high else f'{low + 1}–{high + 1}'
    return column_letter(low) if low == high else f'{column_letter(low)}–{column_letter(high)}'


# ---------- chèn / xóa ----------

def _totals(sheet: Worksheet, name: str, axis: str, at: int) -> tuple[set[tuple[int, int]], set[int]]:
    """Hàng tổng ngay dưới chỗ chèn: ô công thức ở hàng ``at`` cộng một vùng kết thúc ngay trên đó (SUM(D4:D8) ở hàng
    9 khi chèn ở hàng 9). Trả (các ô đó, hàng đầu của các vùng được cộng); với chèn cột thì đổi vai hàng/cột."""
    cells, starts = set(), set()
    for row, col, cell in sheet.cells():
        if (row if axis == 'row' else col) != at or '<' not in cell.inner:
            continue
        text, _ = cell.formula()
        for ref in refs.scan(text or '').refs:
            if refs.adjacent(ref, axis, at) and refs.same_sheet(ref.sheet if ref.sheet is not None else name, name)                     and ref.sheet2 is None and not ref.external:
                cells.add((row, col))
                starts.add(ref.r1 if axis == 'row' else ref.c1)
    return cells, starts


def shift(book: Book, info: SheetInfo, sheet: Worksheet, axis: str, at: int, count: int,
          delete: bool) -> tuple[int, int]:
    """Chèn ``count`` hàng/cột trống ở ``at`` (tính từ 0) hoặc xóa [at, at+count). Trả (số tham chiếu thành #REF!,
    số ô hàng tổng được nới thêm hàng/cột mới)."""
    _check(book, info, sheet, axis, at, count, delete)
    order = [item.name for item in book.sheets]
    counter = _Counter()
    worksheets = [book.worksheet(item) for item in book.data_sheets()]
    for current in worksheets:
        expand_shared(current)
    # Chèn ngay trên hàng tổng: người dùng muốn tổng gồm cả hàng mới, nên vùng của hàng tổng (và biểu đồ dùng cùng cột)
    # nới ra. Excel không tự làm, chỉ báo tam giác xanh "công thức bỏ sót ô kề bên".
    totals, starts = _totals(sheet, info.name, axis, at) if not delete and at > 0 else (set(), set())
    # Công thức trong ô của mọi trang.
    for current in worksheets:
        change = counter.wrap(refs.shifter(current.name, info.name, axis, at, count, delete, order))
        grow = counter.wrap(refs.shifter(current.name, info.name, axis, at, count, delete, order, extend=lambda ref: True))
        for row, col, cell in list(current.cells()):
            if '<' not in cell.inner:
                continue
            text, attrs = cell.formula()
            if not text:
                continue
            updated = refs.rewrite(text, grow if current is sheet and (row, col) in totals else change)
            ref_attr = attrs.get('ref')
            if current is sheet and ref_attr and attrs.get('t') in ('array', 'dataTable'):
                area = meta.area_of(ref_attr)
                moved = _map_area(area, axis, at, count, delete) if area else None
                if moved:
                    attrs = {**attrs, 'ref': meta.area_text(*moved)}
            if updated != text or attrs.get('ref') != ref_attr:
                set_formula(current, row, col, cell, updated, attrs)
    _move_cells(sheet, axis, at, count, delete)
    _update_skeleton(sheet, info.name, axis, at, count, delete, counter, order)
    for current in worksheets:
        if current is not sheet:
            _update_formulas_in_skeleton(current, info.name, axis, at, count, delete, counter, order)
    for element in book.defined_names():
        if element.text:
            updated = refs.rewrite(element.text, counter.wrap(refs.shifter(None, info.name, axis, at, count, delete, order)))
            if updated != element.text:
                element.text = updated
                book.workbook_changed = True
    for table in meta.tables(book, sheet):
        old = (table.r1, table.c1, table.r2, table.c2)
        moved = _map_area(old, axis, at, count, delete)
        if moved and moved != old:
            table.set_area(*moved)
            if axis == 'row' and not delete and old[0] < at <= old[2]:
                _fill_table_formulas(sheet, table, at, count)
            for child in table.root.iter():
                if local(child.tag) in ('sortState', 'sortCondition') and child.get('ref'):
                    area = meta.area_of(child.get('ref'))
                    target = _map_area(area, axis, at, count, delete) if area else None
                    if target:
                        child.set('ref', meta.area_text(*target))
            book.package.write_xml(table.part, table.root)
    _update_drawings(book, sheet, axis, at, count, delete)
    _update_notes(book, sheet, axis, at, count, delete)
    _update_pivots(book, info, sheet, axis, at, count, delete)
    # Biểu đồ vẽ đúng khối dữ liệu đó (cùng hàng đầu, cả cột nhãn lẫn cột số) cũng nới theo.
    same_block = (lambda ref: (ref.r1 if axis == 'row' else ref.c1) in starts) if starts else None
    _update_charts(book, refs.shifter(None, info.name, axis, at, count, delete, order, extend=same_block), counter)
    sheet.set_dimension()
    return counter.broken, len(totals)


def _move_cells(sheet: Worksheet, axis: str, at: int, count: int, delete: bool) -> None:
    if axis == 'row':
        rows: dict[int, Row] = {}
        for index in sorted(sheet.rows):
            row = sheet.rows[index]
            moved = _point(index, at, count, delete)
            if moved is None:
                continue
            if moved != index:
                row.index = moved
                row.raw = None
                for cell in row.cells.values():
                    cell.raw = None
            rows[moved] = row
        if not delete and at > 0 and (at - 1) in rows:
            # Hàng mới theo định dạng hàng ngay trên, như "Format Same As Above" mặc định của Excel.
            source = rows[at - 1]
            attrs = {key: value for key, value in source.attrs.items()
                     if key in ('s', 'customFormat', 'ht', 'customHeight', 'outlineLevel')}
            for index in range(at, at + count):
                cells = {col: Cell({'r': address(index, col), 's': cell.attrs['s']}, '')
                         for col, cell in source.cells.items() if cell.attrs.get('s') not in (None, '', '0')}
                if cells or attrs:
                    rows[index] = Row(index, {'r': str(index + 1), **attrs}, cells)
        sheet.rows = rows
    else:
        for row in sheet.rows.values():
            cells: dict[int, Cell] = {}
            changed = False
            for col in sorted(row.cells):
                cell = row.cells[col]
                moved = _point(col, at, count, delete)
                if moved is None:
                    changed = True
                    continue
                if moved != col:
                    cell.raw = None
                    changed = True
                cells[moved] = cell
            if not delete and at > 0 and (at - 1) in cells:
                left = cells[at - 1]
                if left.attrs.get('s') not in (None, '', '0'):
                    for col in range(at, at + count):
                        cells[col] = Cell({'r': address(row.index, col), 's': left.attrs['s']}, '')
                    changed = True
            if changed:
                row.cells = cells
                row.raw = None
    sheet.modified = True


def _update_skeleton(sheet: Worksheet, name: str, axis: str, at: int, count: int, delete: bool, counter: _Counter,
                     order: list[str]) -> None:
    root = sheet.skeleton()
    change = counter.wrap(refs.shifter(name, name, axis, at, count, delete, order))
    doomed = []
    widened = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = local(element.tag)
        if element.get(MARKER):
            continue
        if tag == 'autoFilter' and axis == 'col' and element.get('ref'):
            _shift_filter_columns(element, at, count, delete)
        for key in ('ref', 'sqref'):
            value = element.get(key)
            if value is None or tag in ('tablePart', 'legacyDrawing', 'drawing', 'dataRef'):
                continue
            moved = _map_sqref(value, axis, at, count, delete)
            single = tag == 'mergeCell' and meta.area_of(moved) is not None and \
                meta.area_of(moved)[:2] == meta.area_of(moved)[2:]
            if not moved or single:
                doomed.append(element)
            elif moved != value:
                element.set(key, moved)
        for key in ('activeCell', 'topLeftCell'):
            value = element.get(key)
            area = meta.area_of(value) if value else None
            if area:
                target = _map_area(area, axis, at, count, delete) or (
                    (at, area[1], at, area[1]) if axis == 'row' else (area[0], at, area[0], at))
                element.set(key, address(min(target[0], refs.MAX_ROWS - 1), min(target[1], refs.MAX_COLS - 1)))
        if tag == 'hyperlink' and element.get('location'):
            element.set('location', refs.rewrite(element.get('location'), change))
        if tag in _FORMULA_TAGS and element.text:
            element.text = refs.rewrite(element.text, change)
        if tag == 'sqref' and element.text:
            moved = _map_sqref(element.text, axis, at, count, delete)
            if not moved:
                doomed.append(element.getparent())
            else:
                element.text = moved
        if tag == 'col' and axis == 'col':
            try:
                low, high = int(element.get('min', '1')) - 1, int(element.get('max', '1')) - 1
            except ValueError:
                continue
            span = refs.map_span(low, high, at, count, delete, refs.MAX_COLS)
            if span is None:
                doomed.append(element)
            else:
                element.set('min', str(span[0] + 1))
                element.set('max', str(span[1] + 1))
                if not delete and span[1] == at - 1:
                    widened.append(element)
        if tag == 'brk' and ((axis == 'row' and local(element.getparent().tag) == 'rowBreaks')
                             or (axis == 'col' and local(element.getparent().tag) == 'colBreaks')):
            try:
                moved = _point(int(element.get('id', '0')), at, count, delete)
            except ValueError:
                continue
            if moved is None:
                doomed.append(element)
            else:
                element.set('id', str(moved))
        if tag in ('from', 'to') and axis_child(element, axis) is not None:
            target = axis_child(element, axis)
            try:
                target.text = str(_clamp(int(target.text), at, count, delete))
            except (TypeError, ValueError):
                pass
    for element in widened:
        # Cột mới chèn ngay bên phải lấy độ rộng và kiểu của cột bên trái, như Excel.
        attributes = {'min': str(at + 1), 'max': str(at + count)}
        attributes.update((key, value) for key, value in element.attrib.items()
                          if key not in ('min', 'max', 'hidden', 'outlineLevel', 'collapsed'))
        element.addnext(etree.Element(element.tag, attributes))
    for element in doomed:
        parent = element.getparent()
        if parent is None:
            continue
        # Định dạng có điều kiện/xác thực/siêu liên kết/vùng gộp mất hết vùng thì bỏ cả mục đó; vùng chọn về A1.
        if local(element.tag) == 'selection':
            element.set('sqref', 'A1')
            element.set('activeCell', 'A1')
            continue
        parent.remove(element)
    _tidy(root)


def _shift_filter_columns(element, at: int, count: int, delete: bool) -> None:
    """Cột lọc của bộ lọc (filterColumn colId tính từ cột đầu vùng lọc) dời theo khi chèn/xóa cột trong vùng lọc."""
    area = meta.area_of(element.get('ref'))
    moved = _map_area(area, 'col', at, count, delete) if area else None
    if area is None or moved is None:
        return
    for child in [child for child in element if local(child.tag) == 'filterColumn']:
        try:
            absolute = area[1] + int(child.get('colId', '0'))
        except ValueError:
            continue
        target = _point(absolute, at, count, delete)
        if target is None:
            element.remove(child)
        else:
            child.set('colId', str(target - moved[1]))


def _fill_table_formulas(sheet: Worksheet, table: meta.Table, at: int, count: int) -> None:
    """Hàng mới chèn giữa Bảng nhận công thức của các cột tính (calculatedColumnFormula), như Excel tự điền."""
    texts = formula_map(sheet)
    for position, column in enumerate(table.columns()):
        if not any(local(child.tag) == 'calculatedColumnFormula' for child in column):
            continue
        col = table.c1 + position
        source_row = next((row for row in (at - 1, at + count) if texts.get((row, col), ('',))[0]
                           and table.r1 < row <= table.r2), None)
        if source_row is None:
            continue
        source = sheet.get(source_row, col)
        for row in range(at, at + count):
            text = refs.rewrite(texts[(source_row, col)][0], refs.relative(row - source_row, 0))
            attrs = {'r': address(row, col)}
            if source is not None and source.style:
                attrs['s'] = str(source.style)
            sheet.put(row, col, Cell(attrs, cell_inner(sheet.prefix, formula=text)))


def axis_child(element, axis: str):
    """Thẻ hàng (row) hay cột (col) trong một mép neo hình (xdr:from/xdr:to)."""
    wanted = 'row' if axis == 'row' else 'col'
    return next((child for child in element if local(child.tag) == wanted), None)


def _tidy(root) -> None:
    """Bỏ các thẻ chứa đã rỗng sau khi xóa và sửa thuộc tính count."""
    for name, item in (('mergeCells', 'mergeCell'), ('dataValidations', 'dataValidation'), ('hyperlinks', 'hyperlink'),
                       ('protectedRanges', 'protectedRange'), ('ignoredErrors', 'ignoredError'),
                       ('rowBreaks', 'brk'), ('colBreaks', 'brk'), ('cols', 'col'),
                       ('conditionalFormattings', 'conditionalFormatting'), ('dataValidations', 'dataValidation'),
                       ('sparklines', 'sparkline'), ('sortState', 'sortCondition')):
        for holder in [element for element in root.iter() if isinstance(element.tag, str) and local(element.tag) == name]:
            children = [child for child in holder if isinstance(child.tag, str) and local(child.tag) == item]
            if not children:
                parent = holder.getparent()
                if parent is not None:
                    parent.remove(holder)
                continue
            if holder.get('count') is not None:
                holder.set('count', str(len(children)))
            if holder.get('manualBreakCount') is not None:
                holder.set('manualBreakCount', str(len(children)))
    # Nhóm sparkline không còn sparkline nào, phần mở rộng rỗng.
    for name in ('sparklineGroup', 'sparklineGroups', 'ext', 'extLst'):
        for holder in [element for element in root.iter() if isinstance(element.tag, str) and local(element.tag) == name]:
            meaningful = [child for child in holder if isinstance(child.tag, str)]
            if name == 'sparklineGroup':
                meaningful = [child for child in meaningful if local(child.tag) == 'sparklines']
            if not meaningful and holder.getparent() is not None:
                holder.getparent().remove(holder)


def _update_formulas_in_skeleton(sheet: Worksheet, target: str, axis: str, at: int, count: int, delete: bool,
                                 counter: _Counter, order: list[str]) -> None:
    """Công thức của định dạng có điều kiện, xác thực, sparkline và siêu liên kết trên trang khác trỏ vào trang vừa
    chèn/xóa."""
    text = sheet.before + sheet.after
    if target.casefold() not in text.casefold() and refs.quote_sheet(target).casefold() not in text.casefold():
        return
    change = counter.wrap(refs.shifter(sheet.name, target, axis, at, count, delete, order))
    root = sheet.skeleton()
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = local(element.tag)
        if tag in _FORMULA_TAGS and element.text:
            element.text = refs.rewrite(element.text, change)
        if tag == 'hyperlink' and element.get('location'):
            element.set('location', refs.rewrite(element.get('location'), change))


def _update_drawings(book: Book, sheet: Worksheet, axis: str, at: int, count: int, delete: bool) -> None:
    for target in book.package.relationships(sheet.part).find('/drawing'):
        if not book.package.exists(target):
            continue
        root = book.package.xml(target)
        changed = False
        for anchor in root.iter():
            if not isinstance(anchor.tag, str) or local(anchor.tag) not in ('twoCellAnchor', 'oneCellAnchor'):
                continue
            mode = anchor.get('editAs', 'twoCell')
            if mode == 'absolute':
                continue
            start = next((child for child in anchor if local(child.tag) == 'from'), None)
            end = next((child for child in anchor if local(child.tag) == 'to'), None)
            first = axis_child(start, axis) if start is not None else None
            if first is None:
                continue
            try:
                before = int(first.text)
            except (TypeError, ValueError):
                continue
            after = _clamp(before, at, count, delete)
            first.text = str(after)
            changed = changed or after != before
            last = axis_child(end, axis) if end is not None else None
            if last is not None:
                try:
                    value = int(last.text)
                except (TypeError, ValueError):
                    continue
                # Hình "chỉ di chuyển" (oneCell) giữ nguyên cỡ; hình mặc định co giãn theo ô.
                moved = value + (after - before) if mode == 'oneCell' else _clamp(value, at, count, delete)
                last.text = str(max(moved, after))
                changed = True
        if changed:
            book.package.write_xml(target, root)


def _update_notes(book: Book, sheet: Worksheet, axis: str, at: int, count: int, delete: bool) -> None:
    relations = book.package.relationships(sheet.part)
    removed: set[tuple[int, int]] = set()
    for target in relations.find('/comments'):
        if not book.package.exists(target):
            continue
        root = book.package.xml(target)
        changed = False
        for comment in [element for element in root.iter() if isinstance(element.tag, str) and local(element.tag) == 'comment']:
            area = meta.area_of(comment.get('ref', ''))
            if area is None:
                continue
            moved = _map_area(area, axis, at, count, delete)
            if moved is None:
                removed.add(area[:2])
                comment.getparent().remove(comment)
                changed = True
            elif moved != area:
                comment.set('ref', address(moved[0], moved[1]))
                changed = True
        if changed:
            book.package.write_xml(target, root)
    for target in relations.find('/threadedComment'):
        if not book.package.exists(target):
            continue
        root = book.package.xml(target)
        gone: set[str] = set()
        changed = False
        for item in [element for element in root if local(element.tag) == 'threadedComment']:
            area = meta.area_of(item.get('ref', ''))
            if area is None:
                continue
            moved = _map_area(area, axis, at, count, delete)
            if moved is None or item.get('parentId') in gone:
                gone.add(item.get('id', ''))
                root.remove(item)
                changed = True
            elif moved != area:
                item.set('ref', address(moved[0], moved[1]))
                changed = True
        if changed:
            book.package.write_xml(target, root)
    for target in relations.find('/vmlDrawing'):
        if not book.package.exists(target):
            continue
        text = book.package.read(target).decode('utf-8', 'replace')
        updated = _NOTE.sub(lambda match: _vml_shape(match.group(0), axis, at, count, delete, removed), text)
        if updated != text:
            book.package.write(target, updated.encode('utf-8'))


def _vml_shape(shape: str, axis: str, at: int, count: int, delete: bool, removed: set[tuple[int, int]]) -> str:
    """Một hình VML (ô ghi chú cũ, nút điều khiển): dời hàng/cột và khung neo; ghi chú của ô bị xóa thì bỏ."""
    row = re.search(r'<x:Row>\s*(\d+)\s*</x:Row>', shape)
    col = re.search(r'<x:Column>\s*(\d+)\s*</x:Column>', shape)
    note = 'ObjectType="Note"' in shape
    if note and row and col:
        position = (int(row.group(1)), int(col.group(1)))
        index = position[0] if axis == 'row' else position[1]
        moved = _point(index, at, count, delete)
        if moved is None or position in removed:
            return ''
        if axis == 'row':
            shape = shape[:row.start(1)] + str(moved) + shape[row.end(1):]
        else:
            shape = shape[:col.start(1)] + str(moved) + shape[col.end(1):]

    def anchor(match):
        values = [part.strip() for part in match.group(1).split(',')]
        if len(values) != 8:
            return match.group(0)
        try:
            numbers = [int(value) for value in values]
        except ValueError:
            return match.group(0)
        positions = (2, 6) if axis == 'row' else (0, 4)
        for position in positions:
            numbers[position] = _clamp(numbers[position], at, count, delete)
        return '<x:Anchor>' + ', '.join(str(number) for number in numbers) + '</x:Anchor>'
    return re.sub(r'<x:Anchor>([^<]*)</x:Anchor>', anchor, shape)


def _pivot_caches(book: Book) -> list[str]:
    return [target for target in book.rels.find('/pivotCacheDefinition') if book.package.exists(target)]


def _worksheet_source(book: Book, path: str):
    root = book.package.xml(path)
    for element in root.iter():
        if isinstance(element.tag, str) and local(element.tag) == 'worksheetSource':
            return element
    return None


def _update_pivots(book: Book, info: SheetInfo, sheet: Worksheet, axis: str, at: int, count: int, delete: bool) -> None:
    for _, area, target in meta.pivots(book, sheet):
        moved = _map_area(area, axis, at, count, delete)
        if moved and moved != area:
            root = book.package.xml(target)
            location = next(child for child in root if local(child.tag) == 'location')
            location.set('ref', meta.area_text(*moved))
            book.package.write_xml(target, root)
    for path in _pivot_caches(book):
        source = _worksheet_source(book, path)
        if source is None or not refs.same_sheet(source.get('sheet'), info.name) or not source.get('ref'):
            continue
        area = meta.area_of(source.get('ref'))
        moved = _map_area(area, axis, at, count, delete) if area else None
        if moved and moved != area:
            source.set('ref', meta.area_text(*moved))
            book.package.write_xml(path, book.package.xml(path))


def _chart_parts(book: Book) -> list[str]:
    return [name for name in book.package.parts()
            if name.startswith('xl/charts/') and name.endswith('.xml') and '/_rels/' not in name
            and posixpath.basename(name).startswith(('chart', 'chartEx'))]


def _update_charts(book: Book, change, counter: _Counter | None = None) -> None:
    wrapped = counter.wrap(change) if counter else change
    for path in _chart_parts(book):
        root = book.package.xml(path)
        changed = False
        for element in root.iter():
            if isinstance(element.tag, str) and local(element.tag) == 'f' and element.text:
                updated = refs.rewrite(element.text, wrapped)
                if updated != element.text:
                    element.text = updated
                    changed = True
        if changed:
            book.package.write_xml(path, root)


def rename_table_column(book: Book, sheet: Worksheet, table: meta.Table, old: str, new: str) -> None:
    """Đổi tên cột của Bảng trong mọi công thức dùng tên đó (Bang1[Lương], [@Lương]), như Excel làm khi sửa ô tiêu
    đề; để nguyên thì Excel báo công thức hỏng."""
    if old == new:
        return
    for item in book.data_sheets():
        current = book.worksheet(item)
        for row, col, cell in list(current.cells()):
            if '[' not in cell.inner:
                continue
            text, attrs = cell.formula()
            if not text:
                continue
            inside = current is sheet and table.r1 <= row <= table.r2 and table.c1 <= col <= table.c2
            updated = refs.rename_column(text, table.name, old, new, inside)
            if updated != text:
                set_formula(current, row, col, cell, updated, attrs)
    for element in table.root.iter():
        if isinstance(element.tag, str) and local(element.tag) in ('calculatedColumnFormula', 'totalsRowFormula') \
                and element.text:
            element.text = refs.rename_column(element.text, table.name, old, new, True)
    for element in book.defined_names():
        if element.text and '[' in element.text:
            updated = refs.rename_column(element.text, table.name, old, new, False)
            if updated != element.text:
                element.text = updated
                book.workbook_changed = True
    book.package.write_xml(table.part, table.root)


# ---------- trang tính ----------

def add_sheet(book: Book, name: str) -> SheetInfo:
    if book.locked:
        raise EditError('cấu trúc tệp đang khóa (Protect Workbook) nên không thêm trang được')
    sheets = book.section('sheets')
    if sheets is None:
        raise EditError('tệp thiếu danh sách trang tính')
    part = book.next_part('xl/worksheets', 'sheet', 'xml')
    namespace = book.workbook.tag[1:].split('}')[0] if book.workbook.tag.startswith('{') else MAIN_NS
    body = (f'<worksheet xmlns="{namespace}" xmlns:r="{R_NS}"><dimension ref="A1"/><sheetViews><sheetView '
            'workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/><sheetData/><pageMargins left="0.7" '
            'right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>')
    book.package.write(part, (DECLARATION + body).encode('utf-8'))
    rid = book.rels.add(WORKSHEET_TYPE, part)
    used = []
    for item in sheets:
        try:
            used.append(int(item.get('sheetId', '0')))
        except ValueError:
            continue
    element = etree.SubElement(sheets, sheets.tag[:-1] if sheets.tag.endswith('sheets') else 'sheet')
    element.set('name', name)
    element.set('sheetId', str(max(used, default=0) + 1))
    element.set(f'{{{R_NS}}}id', rid)
    book.content_types.override(part, WORKSHEET_CONTENT)
    book.workbook_changed = True
    info = SheetInfo(name, part, 'worksheet', 'visible', element)
    book.sheets.append(info)
    return info


def rename_sheet(book: Book, info: SheetInfo, name: str) -> None:
    old = info.name
    info.element.set('name', name)
    book.workbook_changed = True
    for item in book.data_sheets():
        current = book.worksheet(item)
        for row, col, cell in list(current.cells()):
            if '<' not in cell.inner:
                continue
            text, attrs = cell.formula()
            if text:
                updated = refs.rename_sheet(text, old, name)
                if updated != text:
                    set_formula(current, row, col, cell, updated, attrs)
        haystack = (current.before + current.after).casefold()
        if old.casefold() in haystack or refs.quote_sheet(old).casefold() in haystack:
            root = current.skeleton()
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = local(element.tag)
                if tag in _FORMULA_TAGS and element.text:
                    element.text = refs.rename_sheet(element.text, old, name)
                if tag == 'hyperlink' and element.get('location'):
                    element.set('location', refs.rename_sheet(element.get('location'), old, name))
    for element in book.defined_names():
        if element.text:
            element.text = refs.rename_sheet(element.text, old, name)
    for path in _chart_parts(book):
        root = book.package.xml(path)
        changed = False
        for element in root.iter():
            if isinstance(element.tag, str) and local(element.tag) == 'f' and element.text:
                updated = refs.rename_sheet(element.text, old, name)
                if updated != element.text:
                    element.text, changed = updated, True
        if changed:
            book.package.write_xml(path, root)
    for path in _pivot_caches(book):
        source = _worksheet_source(book, path)
        if source is not None and refs.same_sheet(source.get('sheet'), old):
            source.set('sheet', name)
            book.package.write_xml(path, book.package.xml(path))
    app = 'docProps/app.xml'
    if book.package.exists(app):
        try:
            root = book.package.xml(app)
        except EditError:
            root = None
        if root is not None:
            changed = False
            for element in root.iter():
                if isinstance(element.tag, str) and local(element.tag) == 'lpstr' and element.text == old:
                    element.text, changed = name, True
            if changed:
                book.package.write_xml(app, root)
    info.name = name
    if info.part in book.worksheets:
        book.worksheets[info.part].name = name
