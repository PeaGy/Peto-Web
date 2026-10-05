"""Tính lại công thức sau khi sửa tệp, để kết quả lưu trong tệp (trình xem trên điện thoại, LibreOffice, lưới xem của
Peto, và Peto ở lượt sau) đúng với số mới.

Chỉ tính công thức "bẩn": công thức mới, và công thức trỏ (trực tiếp hay qua công thức khác) vào ô vừa đổi hoặc vào
trang vừa chèn/xóa hàng cột. Công thức bẩn mà bộ tính chưa hiểu (hàm ngoài danh sách của create_spreadsheet, tên vùng,
Bảng có cấu trúc, INDIRECT…) thì bỏ kết quả cũ: kết quả cũ có thể đã sai, còn Excel sẽ tính lại khi mở tệp
(fullCalcOnLoad). Thứ tự tính theo phụ thuộc, bằng ngăn xếp nên chuỗi ô nối nhau dài không tràn đệ quy.
"""
from __future__ import annotations

from bisect import bisect_left, insort
from dataclasses import dataclass, field
from datetime import date

from features.documents.sheets import engine
from features.documents.sheets.formula import FormulaError, parse
from features.documents.workbook_edit import refs
from features.documents.workbook_edit.formulas import formula_map
from features.documents.workbook_edit.sheetxml import replace_value

MAX_PASSES = 40
SMALL_BOX = 64          # vùng nhỏ hơn thế này thì xét từng ô thay vì quét theo cột


@dataclass
class Item:
    sheet: int
    row: int
    col: int
    text: str
    boxes: list[tuple[int, int, int, int, int]] = field(default_factory=list)   # (trang, hàng đầu, cột đầu, hàng cuối, cột cuối)
    unknown: bool = False       # phụ thuộc không xác định được (INDIRECT, OFFSET, tên vùng lạ…)
    array: bool = False


@dataclass
class Report:
    computed: int = 0                                   # công thức sẵn có đã tính lại
    left: list[tuple[str, str, set[str]]] = field(default_factory=list)   # (trang, ô, hàm) để Excel tính khi mở
    results: dict[tuple[str, int, int], object] = field(default_factory=dict)   # kết quả công thức mới
    errors: list[tuple[str, int, int, str, str]] = field(default_factory=list)  # công thức mới ra lỗi
    cycles: list[tuple[str, int, int]] = field(default_factory=list)
    cells: set[tuple[str, int, int]] = field(default_factory=set)  # mọi ô công thức đã tính lại hay bỏ kết quả


class _Index:
    """Các ô theo cột → danh sách hàng đã sắp xếp, để hỏi nhanh "vùng này có ô nào"."""

    def __init__(self):
        self.columns: dict[int, dict[int, list[int]]] = {}

    def add(self, sheet: int, row: int, col: int) -> None:
        rows = self.columns.setdefault(sheet, {}).setdefault(col, [])
        position = bisect_left(rows, row)
        if position == len(rows) or rows[position] != row:
            rows.insert(position, row)

    def any(self, box) -> bool:
        sheet, r1, c1, r2, c2 = box
        for col, rows in self.columns.get(sheet, {}).items():
            if c1 <= col <= c2 and rows:
                position = bisect_left(rows, r1)
                if position < len(rows) and rows[position] <= r2:
                    return True
        return False

    def inside(self, box) -> list[tuple[int, int, int]]:
        sheet, r1, c1, r2, c2 = box
        out = []
        for col, rows in self.columns.get(sheet, {}).items():
            if c1 <= col <= c2:
                position = bisect_left(rows, r1)
                while position < len(rows) and rows[position] <= r2:
                    out.append((sheet, rows[position], col))
                    position += 1
        return out


def _value_xml(value) -> tuple[str, str]:
    """(Chữ trong thẻ v, thuộc tính t) của một kết quả."""
    if isinstance(value, bool):
        return ('1' if value else '0'), 'b'
    if isinstance(value, engine.XLError):
        return value.code, 'e'
    if isinstance(value, str):
        return value, 'str'
    number = float(value or 0.0)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number)), 'n'
    return repr(number), 'n'


def recalculate(book, changed: dict[str, set[tuple[int, int]]], structural: set[str],
                new: dict[str, set[tuple[int, int]]], today: date) -> Report:
    """``changed``/``new``: {phần trang tính: ô đã ghi / ô có công thức mới}; ``structural``: tên trang vừa chèn/xóa hàng
    cột. Ghi kết quả vào XML các ô công thức bẩn."""
    report = Report()
    infos = book.data_sheets()
    sheets = [book.worksheet(info) for info in infos]
    position = {sheet.part: index for index, sheet in enumerate(sheets)}
    by_name = {info.name.casefold(): index for index, info in enumerate(infos)}
    data: list[engine.SheetData] = []
    items: dict[tuple[int, int, int], Item] = {}
    texts_by_sheet = []
    for index, sheet in enumerate(sheets):
        texts = formula_map(sheet)
        texts_by_sheet.append(texts)
        bounds = sheet.bounds()
        frame = engine.SheetData(infos[index].name, (bounds[2] + 1) if bounds else 0, (bounds[3] + 1) if bounds else 0)
        for row, col, cell in sheet.cells():
            value = book.value(cell)
            if value is not None and value != '':
                frame.values[(row, col)] = value
            elif (row, col) in texts:
                frame.values[(row, col)] = value
        data.append(frame)
        for (row, col), (text, attrs) in texts.items():
            items[(index, row, col)] = Item(index, row, col, text, array=attrs.get('t') in ('array', 'dataTable'))
    if not items:
        return report

    names = _defined_names(book, by_name)
    tables = _tables(book, sheets)
    structural_index = {by_name[name.casefold()] for name in structural if name.casefold() in by_name}
    for key, item in items.items():
        found = refs.scan(item.text)
        if found.volatile or found.external:
            item.unknown = item.unknown or found.volatile
        for ref in found.refs:
            if ref.external:
                continue
            if ref.sheet2 is not None:
                item.unknown = True
                continue
            target = item.sheet if ref.sheet is None else by_name.get(ref.sheet.casefold())
            if target is None:
                continue
            item.boxes.append((target, 0 if ref.r1 is None else ref.r1, 0 if ref.c1 is None else ref.c1,
                               refs.MAX_ROWS - 1 if ref.r2 is None else ref.r2,
                               refs.MAX_COLS - 1 if ref.c2 is None else ref.c2))
        for name in found.names:
            scope = by_name.get(name.sheet.casefold()) if name.sheet else item.sheet
            boxes = names.get((scope, name.name.casefold())) or names.get((None, name.name.casefold()))
            if boxes is None:
                item.unknown = True
            else:
                item.boxes.extend(boxes)
        if found.structured:
            for reference in refs.structured(item.text):
                boxes = _structured_boxes(reference, item, tables)
                if boxes is None:
                    item.unknown = True
                else:
                    item.boxes.extend(boxes)

    # Công thức bẩn: lan từ ô đã đổi qua các công thức trỏ tới chúng, theo thứ tự hàng (thường chỉ một hai lượt).
    dirty = _Index()
    marked: set[tuple[int, int, int]] = set()
    for part, cells in changed.items():
        if part in position:
            for row, col in cells:
                dirty.add(position[part], row, col)
    new_keys = {(position[part], row, col) for part, cells in new.items() if part in position for row, col in cells}
    for key in new_keys:
        if key in items:
            marked.add(key)
            dirty.add(*key)
    pending = sorted(key for key in items if key not in marked)
    for _ in range(MAX_PASSES):
        still, grew = [], False
        for key in pending:
            item = items[key]
            if item.unknown or any(box[0] in structural_index for box in item.boxes) or item.sheet in structural_index \
                    and not item.boxes or any(dirty.any(box) for box in item.boxes):
                marked.add(key)
                dirty.add(*key)
                grew = True
            else:
                still.append(key)
        pending = still
        if not grew:
            break
    else:
        marked.update(pending)
    report.cells = {(infos[sheet].name, row, col) for sheet, row, col in marked}
    if not marked:
        return report

    # Tính theo thứ tự phụ thuộc giữa các công thức bẩn.
    formula_index = _Index()
    for key in marked:
        formula_index.add(*key)
    members: dict[tuple, list] = {}

    def dependencies(item: Item) -> list[tuple[int, int, int]]:
        out = []
        for box in item.boxes:
            sheet, r1, c1, r2, c2 = box
            if (r2 - r1 + 1) * (c2 - c1 + 1) <= SMALL_BOX:
                out.extend((sheet, row, col) for row in range(r1, r2 + 1) for col in range(c1, c2 + 1)
                           if (sheet, row, col) in marked)
            else:
                if box not in members:
                    members[box] = formula_index.inside(box)
                out.extend(members[box])
        return out

    evaluator = engine.Evaluator(data, today)
    parsed: dict[tuple, object] = {}
    state: dict[tuple, int] = {}
    failed: set[tuple] = set()
    for root in sorted(marked):
        if state.get(root):
            continue
        stack = [(root, iter(dependencies(items[root])))]
        state[root] = 1
        while stack:
            key, deps = stack[-1]
            advanced = False
            for dep in deps:
                if dep == key:
                    failed.add(key)
                    report.cycles.append((infos[key[0]].name, key[1], key[2]))
                    continue
                status = state.get(dep, 0)
                if status == 1:
                    failed.add(key)
                    failed.add(dep)
                    report.cycles.append((infos[key[0]].name, key[1], key[2]))
                elif status == 0:
                    state[dep] = 1
                    stack.append((dep, iter(dependencies(items[dep]))))
                    advanced = True
                    break
            if advanced:
                continue
            stack.pop()
            state[key] = 2
            item = items[key]
            if key not in failed and not item.unknown and not item.array \
                    and not any(dep in failed for dep in dependencies(item)):
                try:
                    formula = parsed.get(key) or parse('=' + item.text)
                    parsed[key] = formula
                    value = evaluator.evaluate(formula, data[item.sheet])
                except (FormulaError, ValueError, RecursionError, OverflowError, ZeroDivisionError):
                    failed.add(key)
                else:
                    data[item.sheet].values[(item.row, item.col)] = value
                    _store(book, sheets[item.sheet], item, value)
                    if key in new_keys:
                        report.results[(infos[item.sheet].name, item.row, item.col)] = value
                        if isinstance(value, engine.XLError):
                            report.errors.append((infos[item.sheet].name, item.row, item.col, item.text, value.code))
                    else:
                        report.computed += 1
                    continue
            failed.add(key)
            _store(book, sheets[item.sheet], item, None)
            found = refs.scan(item.text)
            report.left.append((infos[item.sheet].name, f'{_letter(item.col)}{item.row + 1}', found.functions))
    return report


def _store(book, sheet, item: Item, value) -> None:
    cell = sheet.get(item.row, item.col)
    if cell is None:
        return
    if value is None:
        if cell.value() is None:
            return
        replace_value(cell, sheet.prefix, None, None)
    else:
        text, kind = _value_xml(value)
        if cell.value() == text and cell.kind == kind:
            return
        replace_value(cell, sheet.prefix, text, kind)
    sheet.put(item.row, item.col, cell)


def _letter(col: int) -> str:
    from features.documents.workbook_edit.sheetxml import column_letter
    return column_letter(col)


def _defined_names(book, by_name: dict[str, int]) -> dict[tuple[int | None, str], list]:
    """Tên vùng → các vùng ô nó trỏ tới, theo phạm vi (None là cả tệp, số là trang có localSheetId đó)."""
    out: dict[tuple[int | None, str], list] = {}
    for element in book.defined_names():
        text = element.text or ''
        boxes = []
        unknown = False
        found = refs.scan(text)
        for ref in found.refs:
            target = by_name.get(ref.sheet.casefold()) if ref.sheet else None
            if ref.external or target is None:
                unknown = unknown or not ref.external
                continue
            boxes.append((target, 0 if ref.r1 is None else ref.r1, 0 if ref.c1 is None else ref.c1,
                          refs.MAX_ROWS - 1 if ref.r2 is None else ref.r2, refs.MAX_COLS - 1 if ref.c2 is None else ref.c2))
        if unknown or found.names or found.structured or found.volatile:
            continue
        scope = element.get('localSheetId')
        try:
            local_scope = int(scope) if scope is not None else None
        except ValueError:
            continue
        if local_scope is not None:
            # localSheetId đếm theo thứ tự mọi trang (cả trang biểu đồ); đổi sang thứ tự trang dữ liệu.
            everything = book.sheets
            if not 0 <= local_scope < len(everything) or everything[local_scope].name.casefold() not in by_name:
                continue
            local_scope = by_name[everything[local_scope].name.casefold()]
        out[(local_scope, (element.get('name') or '').casefold())] = boxes
    return out


@dataclass
class _Table:
    sheet: int
    r1: int
    c1: int
    r2: int
    c2: int
    header: bool
    totals: bool
    columns: list[str]


def _tables(book, sheets) -> dict[str, _Table]:
    """Tên Bảng → vùng, hàng tiêu đề/tổng và tên cột (để công thức Bang1[Cột] biết nó phụ thuộc đúng cột nào)."""
    from features.documents.workbook_edit import meta
    out = {}
    for index, sheet in enumerate(sheets):
        for table in meta.tables(book, sheet):
            info = _Table(index, table.r1, table.c1, table.r2, table.c2, table.header, table.totals,
                          [(column.get('name') or '').casefold() for column in table.columns()])
            for key in ('name', 'displayName'):
                if table.root.get(key):
                    out[table.root.get(key).casefold()] = info
    return out


def _structured_boxes(reference, item: Item, tables: dict[str, _Table]) -> list | None:
    """Vùng ô một tham chiếu Bảng trỏ tới: đúng các cột được nêu; hàng dữ liệu, tiêu đề, tổng hay chỉ hàng của ô."""
    if reference.table is not None:
        table = tables.get(reference.table.casefold())
    else:
        table = next((value for value in tables.values() if value.sheet == item.sheet and value.r1 <= item.row <= value.r2
                      and value.c1 <= item.col <= value.c2), None)
    if table is None:
        return None
    if reference.columns:
        try:
            indices = [table.columns.index(name.casefold()) for name in reference.columns]
        except ValueError:
            return None
        if reference.range and len(indices) == 2:
            indices = list(range(min(indices), max(indices) + 1))
        spans = [(table.c1 + index, table.c1 + index) for index in indices]
    else:
        spans = [(table.c1, table.c2)]
    data_top = table.r1 + (1 if table.header else 0)
    data_bottom = table.r2 - (1 if table.totals else 0)
    specials = reference.specials
    if '#this row' in specials:
        rows = [(item.row, item.row)]
    elif '#all' in specials:
        rows = [(table.r1, table.r2)]
    else:
        rows = []
        if '#headers' in specials and table.header:
            rows.append((table.r1, table.r1))
        if '#totals' in specials and table.totals:
            rows.append((table.r2, table.r2))
        if '#data' in specials or not (specials & {'#headers', '#totals'}):
            rows.append((data_top, data_bottom))
    return [(table.sheet, low, left, high, right) for low, high in rows for left, right in spans if low <= high]
