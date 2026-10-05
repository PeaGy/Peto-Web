"""Công thức của từng ô trong trang tính đang sửa: công thức chung (shared formula, một ô gốc cho cả vùng chép) được
mở ra thành công thức riêng của từng ô khi cần đổi.
"""
from __future__ import annotations

from features.documents.workbook_edit import refs
from features.documents.workbook_edit.sheetxml import Cell, Worksheet, cell_inner


def formula_map(sheet: Worksheet) -> dict[tuple[int, int], tuple[str, dict[str, str]]]:
    """{(hàng, cột): (chữ công thức không có dấu =, thuộc tính thẻ f)}; ô phụ của công thức chung lấy chữ dời từ ô gốc."""
    masters: dict[str, tuple[int, int, str]] = {}
    out: dict[tuple[int, int], tuple[str, dict[str, str]]] = {}
    for row, col, cell in sheet.cells():
        if '<' not in cell.inner:
            continue
        text, attrs = cell.formula()
        if text is None:
            continue
        if attrs.get('t') == 'shared' and attrs.get('si') is not None:
            if text:
                masters[attrs['si']] = (row, col, text)
            elif attrs['si'] in masters:
                master_row, master_col, master = masters[attrs['si']]
                text = refs.rewrite(master, refs.relative(row - master_row, col - master_col))
        out[(row, col)] = (text, attrs)
    return out


def shared_groups(sheet: Worksheet) -> dict[str, list[tuple[int, int]]]:
    groups: dict[str, list[tuple[int, int]]] = {}
    for row, col, cell in sheet.cells():
        if '<' not in cell.inner:
            continue
        _, attrs = cell.formula()
        if attrs.get('t') == 'shared' and attrs.get('si') is not None:
            groups.setdefault(attrs['si'], []).append((row, col))
    return groups


def set_formula(sheet: Worksheet, row: int, col: int, cell: Cell, text: str, attrs: dict[str, str]) -> None:
    """Thay chữ công thức của ô, giữ kết quả đã lưu và các thuộc tính khác của thẻ f."""
    value = cell.value()
    cell.inner = cell_inner(sheet.prefix, formula=text, formula_attrs=attrs, value=value)
    sheet.put(row, col, cell)


def expand_shared(sheet: Worksheet, only: set[str] | None = None) -> int:
    """Mở công thức chung thành công thức riêng từng ô (tất cả, hoặc các nhóm si trong ``only``). Trả số ô đã đổi."""
    texts = formula_map(sheet)
    changed = 0
    for (row, col), (text, attrs) in texts.items():
        if attrs.get('t') != 'shared' or (only is not None and attrs.get('si') not in only):
            continue
        rest = {key: value for key, value in attrs.items() if key not in ('t', 'si', 'ref')}
        set_formula(sheet, row, col, sheet.get(row, col), text, rest)
        changed += 1
    return changed


def array_ranges(sheet: Worksheet) -> list[tuple[int, int, int, int, str]]:
    """Vùng công thức mảng và bảng dữ liệu (t="array" / "dataTable"): (hàng đầu, cột đầu, hàng cuối, cột cuối, loại)."""
    out = []
    for row, col, cell in sheet.cells():
        if '<' not in cell.inner:
            continue
        _, attrs = cell.formula()
        if attrs.get('t') in ('array', 'dataTable'):
            area = refs.scan(attrs.get('ref', '')).refs
            if area and area[0].r1 is not None and area[0].c1 is not None:
                found = area[0]
                out.append((found.r1, found.c1, found.r2, found.c2, attrs['t']))
            else:
                out.append((row, col, row, col, attrs['t']))
    return out
