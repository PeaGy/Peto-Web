"""Đọc dữ liệu bảng tính Excel (.xlsx, .xlsm) người dùng gửi lên. Chạy trong tiến trình con của bộ đọc tài liệu.

Tự đọc gói ZIP và XML bằng defusedxml (cấm DTD và thực thể), đọc dần từng hàng và dừng ở giới hạn; không bao giờ chạy
macro hay tính lại công thức. Giá trị là kết quả Excel đã lưu trong tệp.

Chữ đưa cho Peto, mỗi hàng một dòng để công cụ tìm/đọc trong tệp dùng được:
    [Trang tính 1/2 "Bảng điểm" · vùng A1:G12 · 12 hàng có dữ liệu]
    Công thức F2:F11 (chép xuống, 10 ô): =ROUND((C2+D2*2+E2*3)/6,1)
    Hàng 2 | A: 1 | B: Nguyễn Minh Anh | F: 7.8
Số viết dạng máy (7.5), phần trăm 25%, ngày YYYY-MM-DD: đúng dạng ô mà create_spreadsheet nhận, nên Peto dựng lại được
bảng khi được nhờ sửa. Công thức gom theo vùng chép xuống hoặc chép sang phải, để khỏi lặp lại ở từng ô.
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from datetime import datetime, timedelta

from defusedxml.ElementTree import fromstring, iterparse

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM_MIME = "application/vnd.ms-excel.sheet.macroEnabled.12"
SPREADSHEET_MIMES = (XLSX_MIME, XLSM_MIME)
CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"     # gói OLE: .xls cũ, hoặc .xlsx đặt mật khẩu

MAX_ENTRIES = 5000
MAX_DECLARED_BYTES = 192 * 1024 * 1024
MAX_PART_BYTES = 48 * 1024 * 1024
MAX_SMALL_PART_BYTES = 8 * 1024 * 1024
MAX_SHEETS = 30
MAX_ROWS = 50_000           # mỗi trang tính
MAX_COLUMNS = 256
MAX_CELLS = 400_000         # cả tệp
MAX_STRINGS = 200_000
MAX_FORMULA_LINES = 300     # mỗi trang tính
CELL_CHARS = 1_000
# Ô gộp đè lên ô dữ liệu là lỗi hay gặp, nên liệt kê gần hết: trong bài thử ngày 5/10/2026, E10:F10 là vùng thứ 11, nằm
# sau "và 2 vùng khác", và Peto không thấy nó.
MAX_MERGES_SHOWN = 100
MAX_PADDED_SHOWN = 30
MAX_NAMES_SHOWN = 20
MAX_CHARTS = 30             # cả tệp
MAX_TEXT_BOXES = 40
MAX_NOTES = 200
# Đổi cách viết chữ của bảng tính thì tăng số này: tệp Excel đã đọc theo cách cũ được đọc lại ở lượt sau
# (reader.cached_document). 2 (5/10/2026): thêm biểu đồ, hộp chữ, hình, Bảng (Table), bảng tổng hợp, ghi chú trong ô.
# 3 (5/10/2026): chữ rỗng và chữ có khoảng trắng ở đầu/cuối ghi trong ngoặc kép, công thức trả về "" không còn bị coi là
# chưa tính, liệt kê tới 100 ô gộp.
SHEET_FORMAT = 3

_RELATIONSHIP_NAMESPACES = ("http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                            "http://purl.oclc.org/ooxml/officeDocument/relationships")
_BUILTIN_KINDS = {9: "percent", 10: "percent", 14: "date", 15: "date", 16: "date", 17: "date", 18: "time", 19: "time",
                  20: "time", 21: "time", 22: "datetime", 45: "time", 46: "time", 47: "time", 49: "text",
                  **{code: "date" for code in (*range(27, 37), *range(50, 59))}}
_ERRORS = {"#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#REF!", "#VALUE!", "#GETTING_DATA", "#SPILL!", "#CALC!"}
_LITERALS = re.compile(r"(\"(?:[^\"]|\"\")*\"|'(?:[^']|'')*')")
_REFERENCE = re.compile(r"(?<![A-Za-z0-9_.])(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})(?![A-Za-z0-9_(])")


class _Unreadable(Exception):
    """Tệp hỏng, sai cấu trúc hoặc vượt giới hạn; lời nhắn đã viết cho người dùng."""


class _Limited:
    """Luồng đọc một phần trong gói ZIP, dừng khi vượt số byte cho phép (chống tệp nén phình to)."""

    def __init__(self, stream, limit: int):
        self.stream, self.left = stream, limit

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.left + 1
        data = self.stream.read(min(size, self.left + 1))
        self.left -= len(data)
        if self.left < 0:
            raise _Unreadable("Một phần của tệp Excel quá lớn để đọc. Hãy chia nhỏ bảng tính.")
        return data


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _relationship_id(element) -> str:
    for key, value in element.attrib.items():
        if key.startswith("{") and key[1:].split("}", 1)[0] in _RELATIONSHIP_NAMESPACES and _local(key) == "id":
            return value
    return ""


def column_index(letters: str) -> int:
    index = 0
    for char in letters.upper():
        index = index * 26 + ord(char) - 64
    return index - 1


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _address(row: int, col: int) -> str:
    return f"{column_letter(col)}{row}"


def _number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def general(value: float) -> str:
    """Số dạng máy như Excel General: tối đa 15 chữ số có nghĩa, dấu chấm thập phân."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    text = f"{value:.15g}"
    if "e" in text:
        mantissa, exponent = text.split("e")
        return f"{mantissa}E{int(exponent):+03d}"
    return text


def _section(code: str) -> str:
    """Phần đầu (số dương) của mã định dạng, bỏ chữ trong nháy, ký tự thoát, [màu]/[$-…] và ký tự đệm.
    Giữ lại [h], [mm], [ss] (giờ cộng dồn): đó là thời gian chứ không phải nhãn màu."""
    cleaned = re.sub(r'"[^"]*"|\\.|_.|\*.', "", code or "")
    cleaned = re.sub(r"\[([^\]]*)\]", lambda match: match.group(1) if re.fullmatch(r"[hms]+", match.group(1), re.I) else "",
                     cleaned)
    return cleaned.split(";")[0].lower().replace("general", "")


def format_decimals(code: str) -> int:
    match = re.search(r"\.([0#?]+)", _section(code))
    return len(match.group(1)) if match else 0


def format_kind(code: str) -> str:
    """Loại hiển thị của một mã định dạng số: date, datetime, time, percent, text hay number."""
    section = _section(code)
    if "@" in section and not re.search(r"[0#?]", section):
        return "text"
    if "%" in section:
        return "percent"
    has_date = bool(re.search(r"[dy]", section))
    has_time = bool(re.search(r"[hs]", section))
    if has_date and has_time:
        return "datetime"
    if has_date:
        return "date"
    if has_time:
        return "time"
    if "m" in section and not re.search(r"[0#?]", section):
        return "date"       # "mmm yyyy" đã tính ở trên; "mmmm" riêng là tên tháng
    return "number"


def show_number(value: float, kind: str, date1904: bool, decimals: int = 0) -> str:
    if kind in ("date", "datetime", "time") and 0 <= value < 2_958_466:
        if date1904:
            base = datetime(1904, 1, 1)
        else:
            base = datetime(1899, 12, 31) if value < 61 else datetime(1899, 12, 30)
        moment = base + timedelta(seconds=round(value * 86400))
        if kind == "time" and value < 1:
            return moment.strftime("%H:%M:%S" if moment.second else "%H:%M")
        if kind == "date" or (moment.hour == moment.minute == moment.second == 0):
            return moment.strftime("%Y-%m-%d")
        return moment.strftime("%Y-%m-%d %H:%M" + (":%S" if moment.second else ""))
    if kind == "percent":
        # Phần trăm làm tròn như ô hiện trong Excel (0.0% thì 71.4%); số thường giữ đủ giá trị.
        return general(round(value * 100, min(decimals, 10))) + "%"
    return general(value)


def _clean_formula(text: str) -> str:
    return re.sub(r"_xlfn\.|_xlws\.|_xludf\.", "", text.strip())


def _outside_literals(text: str, change) -> str:
    parts = _LITERALS.split(text)
    return "".join(part if index % 2 else change(part) for index, part in enumerate(parts))


def relative_pattern(formula: str, row: int, col: int) -> str:
    """Công thức đổi tham chiếu tương đối thành độ lệch so với ô chứa nó: hai ô chép xuống từ nhau có cùng mẫu."""
    def replace(match):
        col_part = match.group(2).upper() if match.group(1) else f"C[{column_index(match.group(2)) - col}]"
        row_part = match.group(4) if match.group(3) else f"R[{int(match.group(4)) - row}]"
        return f"{match.group(1)}{col_part}{match.group(3)}{row_part}"
    return _outside_literals(formula, lambda part: _REFERENCE.sub(replace, part))


def shift_formula(formula: str, rows: int, cols: int) -> str:
    """Công thức chung (shared formula) của ô phụ thuộc: dời các tham chiếu tương đối theo độ lệch so với ô gốc."""
    def replace(match):
        col = column_index(match.group(2)) + (0 if match.group(1) else cols)
        row = int(match.group(4)) + (0 if match.group(3) else rows)
        if col < 0 or row < 1:
            return "#REF!"
        return f"{match.group(1)}{column_letter(col)}{match.group(3)}{row}"
    return _outside_literals(formula, lambda part: _REFERENCE.sub(replace, part))


class _Package:
    def __init__(self, archive: zipfile.ZipFile):
        self.archive = archive
        self.names = {info.filename: info for info in archive.infolist()}

    def open(self, name: str, limit: int | None = None) -> _Limited:
        limit = MAX_PART_BYTES if limit is None else limit
        info = self.names.get(name)
        if info is None:
            raise _Unreadable("Tệp Excel thiếu một phần cần thiết. Thử mở bằng Excel rồi lưu lại.")
        if info.flag_bits & 1:
            raise _Unreadable("Tệp Excel bị mã hóa. Hãy gửi bản đã mở khóa.")
        return _Limited(self.archive.open(info), limit)

    def xml(self, name: str):
        stream = self.open(name, MAX_SMALL_PART_BYTES)
        return fromstring(stream.read(), forbid_dtd=True)

    def relationships(self, part: str) -> dict[str, tuple[str, str]]:
        """Id → (đường dẫn trong gói, loại quan hệ) của một phần."""
        folder, name = posixpath.split(part)
        path = posixpath.join(folder, "_rels", name + ".rels")
        if path not in self.names:
            return {}
        out = {}
        for item in self.xml(path):
            if _local(item.tag) != "Relationship" or item.get("TargetMode") == "External":
                continue
            target = item.get("Target", "")
            resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
            out[item.get("Id", "")] = (resolved, item.get("Type", ""))
        return out


def _shared_strings(package: _Package, path: str | None, flags: dict) -> list[str]:
    strings: list[str] = []
    if not path or path not in package.names:
        return strings
    for _, element in iterparse(package.open(path), events=("end",), forbid_dtd=True):
        if _local(element.tag) != "si":
            continue
        parts = []
        for child in element:
            name = _local(child.tag)
            if name == "t":
                parts.append(child.text or "")
            elif name == "r":
                parts.extend(grand.text or "" for grand in child if _local(grand.tag) == "t")
        strings.append("".join(parts))
        element.clear()
        if len(strings) >= MAX_STRINGS:
            flags["strings"] = True
            break
    return strings


def _styles(package: _Package, path: str | None) -> list[tuple[str, int]]:
    """(Loại hiển thị, số chữ số thập phân) của từng kiểu ô, theo thứ tự trong cellXfs."""
    if not path or path not in package.names:
        return []
    root = package.xml(path)
    custom = {}
    kinds = []
    for section in root:
        name = _local(section.tag)
        if name == "numFmts":
            for item in section:
                try:
                    custom[int(item.get("numFmtId", "-1"))] = item.get("formatCode", "")
                except ValueError:
                    continue
        elif name == "cellXfs":
            for item in section:
                try:
                    code = int(item.get("numFmtId", "0"))
                except ValueError:
                    code = 0
                if code in custom:
                    kinds.append((format_kind(custom[code]), format_decimals(custom[code])))
                else:
                    kinds.append((_BUILTIN_KINDS.get(code, "number"), 2 if code == 10 else 0))
    return kinds


def _cell_text(text: str) -> str:
    """Chữ của một ô trong dòng hàng. Chữ rỗng (công thức trả về ""), chữ có khoảng trắng ở đầu hoặc cuối và chữ bắt đầu
    bằng dấu nháy kép được ghi trong ngoặc kép, nháy bên trong viết đôi như chuỗi trong công thức Excel. Không có ngoặc
    thì dấu phân cách " | " nuốt mất khoảng trắng đó, mà tên "Lan " hay " Lan" là lỗi dữ liệu Peto cần thấy."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    quoted = text == "" or text != text.strip() or text.startswith('"')
    text = text.replace("\n", " ⏎ ")
    cut = ""
    if len(text) > CELL_CHARS:
        text, cut = text[:CELL_CHARS], f" …[cắt {_number(len(text) - CELL_CHARS)} ký tự]"
    return ('"' + text.replace('"', '""') + '"' if quoted else text) + cut


class _Sheet:
    def __init__(self, name: str, position: int, total: int, hidden: bool):
        self.name, self.position, self.total, self.hidden = name, position, total, hidden
        self.rows: list[str] = []
        self.formulas: dict[tuple[int, int], str] = {}
        self.merges: list[str] = []
        self.padded: list[str] = []                 # ô chữ có khoảng trắng ở đầu hoặc cuối
        # Bảng (Table), biểu đồ, hộp chữ, hình, bảng tổng hợp, ghi chú: các dòng đứng trước công thức (workbook_parts).
        self.extras: list[str] = []
        self.bounds = [None, None, None, None]      # hàng đầu, cột đầu, hàng cuối, cột cuối
        self.more_rows = False
        self.more_columns = False

    def touch(self, row: int, col: int):
        low_row, low_col, high_row, high_col = self.bounds
        self.bounds = [row if low_row is None else min(low_row, row), col if low_col is None else min(low_col, col),
                       row if high_row is None else max(high_row, row), col if high_col is None else max(high_col, col)]

    def formula_lines(self) -> list[str]:
        keys = {cell: relative_pattern(text, *cell) for cell, text in self.formulas.items()}
        used: set[tuple[int, int]] = set()
        groups = []
        for row, col in sorted(self.formulas, key=lambda cell: (cell[1], cell[0])):
            if (row, col) in used:
                continue
            end = row
            while (end + 1, col) in keys and keys[(end + 1, col)] == keys[(row, col)] and (end + 1, col) not in used:
                end += 1
            if end > row:
                used.update((r, col) for r in range(row, end + 1))
                groups.append((row, col, end, col, "chép xuống"))
        for row, col in sorted(self.formulas):
            if (row, col) in used:
                continue
            end = col
            while (row, end + 1) in keys and keys[(row, end + 1)] == keys[(row, col)] and (row, end + 1) not in used:
                end += 1
            used.update((row, c) for c in range(col, end + 1))
            groups.append((row, col, row, end, "chép sang phải" if end > col else ""))
        lines = []
        for row, col, last_row, last_col, how in sorted(groups):
            text = self.formulas[(row, col)]
            if how:
                count = (last_row - row + 1) * (last_col - col + 1)
                lines.append(f"Công thức {_address(row, col)}:{_address(last_row, last_col)} ({how}, {_number(count)} ô): {text}")
            else:
                lines.append(f"Công thức {_address(row, col)}: {text}")
        if len(lines) > MAX_FORMULA_LINES:
            lines = lines[:MAX_FORMULA_LINES] + [f"[… và {_number(len(lines) - MAX_FORMULA_LINES)} nhóm công thức khác …]"]
        return lines

    def lines(self) -> list[tuple[str, bool]]:
        """(Dòng chữ, có phải hàng dữ liệu): đầu trang tính, ô gộp và công thức trước, rồi tới từng hàng."""
        low_row, low_col, high_row, high_col = self.bounds
        area = f" · vùng {_address(low_row, low_col)}:{_address(high_row, high_col)}" if low_row is not None else ""
        state = " · đang ẩn" if self.hidden else ""
        head = [f'[Trang tính {self.position}/{self.total} "{self.name}"{area} · {_number(len(self.rows))} hàng có dữ liệu{state}]']
        if self.merges:
            shown = ", ".join(self.merges[:MAX_MERGES_SHOWN])
            more = f" và {_number(len(self.merges) - MAX_MERGES_SHOWN)} vùng khác" if len(self.merges) > MAX_MERGES_SHOWN else ""
            head.append(f"Ô gộp: {shown}{more}")
        if self.padded:
            shown = ", ".join(self.padded[:MAX_PADDED_SHOWN])
            more = f" và {_number(len(self.padded) - MAX_PADDED_SHOWN)} ô khác" if len(self.padded) > MAX_PADDED_SHOWN else ""
            head.append(f"Ô chữ có khoảng trắng ở đầu hoặc cuối: {shown}{more}")
        head.extend(self.extras)
        if not self.rows:
            head.append("(Trang tính trống.)")
        return [*((line, False) for line in [*head, *self.formula_lines()]), *((row, True) for row in self.rows)]


def condense(lines: list[tuple[str, int | None]], max_chars: int) -> str:
    """Phần đọc sẵn của bảng tính dài. ``lines`` là (dòng, số thứ tự trang tính nếu là hàng dữ liệu, ngược lại None).

    Khác log (document_reader.condense_text): không gộp các hàng cùng dạng, vì hàng dữ liệu nào cũng cùng dạng. Giữ mọi
    dòng đầu trang tính và công thức; mỗi trang giữ các hàng đầu và các hàng cuối (thường là hàng tổng) theo phần chữ
    của trang đó. Dòng báo bỏ qua ghi số dòng của tệp chữ, để Peto đọc tiếp bằng read_attachment_lines.
    """
    meta = sum(len(text) + 1 for text, sheet in lines if sheet is None)
    budget = max(max_chars - meta - 600, max_chars // 4)
    rows: dict[int, list[tuple[int, str]]] = {}
    for number, (text, sheet) in enumerate(lines, start=1):
        if sheet is not None:
            rows.setdefault(sheet, []).append((number, text))
    total = sum(len(text) + 1 for items in rows.values() for _, text in items) or 1
    keep: set[int] = set()
    for items in rows.values():
        cost = sum(len(text) + 1 for _, text in items)
        share = budget * cost / total
        if cost <= share:
            keep.update(number for number, _ in items)
            continue
        used, first = 0, 0
        while first < len(items) and used + len(items[first][1]) + 1 <= share * 0.6:
            used += len(items[first][1]) + 1
            keep.add(items[first][0])
            first += 1
        used, last = 0, len(items) - 1
        while last >= first and used + len(items[last][1]) + 1 <= share * 0.4:
            used += len(items[last][1]) + 1
            keep.add(items[last][0])
            last -= 1
    out: list[str] = []
    skipped: list[int] = []

    def flush():
        if skipped:
            low = re.match(r"Hàng (\d+)", lines[skipped[0] - 1][0])
            high = re.match(r"Hàng (\d+)", lines[skipped[-1] - 1][0])
            excel = f" (hàng Excel {low.group(1)}–{high.group(1)})" if low and high else ""
            out.append(f"[… bỏ qua dòng {_number(skipped[0])}–{_number(skipped[-1])} của tệp{excel}; đọc bằng "
                       "read_attachment_lines khi cần …]")
            skipped.clear()

    for number, (text, sheet) in enumerate(lines, start=1):
        if sheet is not None and number not in keep:
            skipped.append(number)
            continue
        flush()
        out.append(text)
    flush()
    excerpt = "\n".join(out)
    return excerpt if len(excerpt) <= max_chars else excerpt[:excerpt.rfind("\n", 0, max_chars)]


def _read_sheet(package: _Package, path: str, sheet: _Sheet, strings: list[str], kinds: list[tuple[str, int]], date1904: bool,
                budget: dict, flags: dict):
    masters: dict[str, tuple[int, int, str]] = {}
    cells: list[tuple[int, str]] = []
    row_number = 0
    next_col = 0
    for _, element in iterparse(package.open(path), events=("end",), forbid_dtd=True):
        name = _local(element.tag)
        if name == "c":
            reference = element.get("r", "")
            match = re.fullmatch(r"([A-Za-z]{1,3})(\d{1,7})", reference)
            col = column_index(match.group(1)) if match else next_col
            # Thẻ <row> kết thúc sau các ô của nó, nên số hàng của ô lấy từ địa chỉ ô; thiếu địa chỉ thì là hàng kế tiếp.
            cell_row = int(match.group(2)) if match else row_number + 1
            next_col = col + 1
            if col >= MAX_COLUMNS:
                sheet.more_columns = True
                element.clear()
                continue
            kind = element.get("t", "n")
            value_element = formula_element = inline = None
            for child in element:
                child_name = _local(child.tag)
                if child_name == "v":
                    value_element = child
                elif child_name == "f":
                    formula_element = child
                elif child_name == "is":
                    inline = child
            raw = value_element.text if value_element is not None and value_element.text is not None else None
            # Công thức trả về chữ rỗng: Excel ghi t="str" với <v></v>. Đó là kết quả đã lưu, không phải ô chưa tính.
            empty_text = kind == "str" and value_element is not None and raw is None
            if kind == "s" and raw is not None:
                try:
                    index = int(raw)
                except ValueError:
                    index = -1
                if 0 <= index < len(strings):
                    value = strings[index]
                else:
                    value = "…"
                    flags["strings"] = True
            elif kind == "inlineStr":
                value = "".join(node.text or "" for node in (inline.iter() if inline is not None else ()) if _local(node.tag) == "t")
            elif kind == "b":
                value = "TRUE" if raw == "1" else "FALSE" if raw is not None else ""
            elif kind in ("e", "str", "d"):
                value = raw or ""
            elif raw is not None:
                try:
                    style = int(element.get("s", "0") or 0)
                except ValueError:
                    style = 0
                try:
                    kind_of_cell, decimals = kinds[style] if style < len(kinds) else ("number", 0)
                    value = show_number(float(raw), kind_of_cell, date1904, decimals)
                except (ValueError, OverflowError):
                    value = raw
            else:
                value = ""
            formula = ""
            if formula_element is not None:
                body = formula_element.text
                kind_of_formula = formula_element.get("t", "normal")
                if body and body.strip():
                    formula = "=" + _clean_formula(body)
                    if kind_of_formula == "shared" and formula_element.get("si") is not None:
                        masters[formula_element.get("si")] = (cell_row, col, formula)
                elif kind_of_formula == "shared" and formula_element.get("si") in masters:
                    master_row, master_col, master = masters[formula_element.get("si")]
                    formula = shift_formula(master, cell_row - master_row, col - master_col)
                if formula and kind_of_formula == "array":
                    formula = "{" + formula + "}"
                if formula and raw is None and kind != "inlineStr" and not empty_text:
                    flags["uncached"] = flags.get("uncached", 0) + 1
                    value = "(chưa có kết quả)"
            if value != "" or formula:
                text = _cell_text(value)
                if value != value.strip():
                    sheet.padded.append(_address(cell_row, col))
                if text.startswith('"'):
                    flags["quoted"] = True
                cells.append((col, text))
                if formula:
                    sheet.formulas[(cell_row, col)] = formula
            element.clear()
        elif name == "row":
            reference = element.get("r")
            current = int(reference) if reference and reference.isdigit() else row_number + 1
            if cells:
                if len(sheet.rows) >= MAX_ROWS:
                    sheet.more_rows = True
                    element.clear()
                    break
                budget["cells"] -= len(cells)
                for col, _ in cells:
                    sheet.touch(current, col)
                sheet.rows.append(f"Hàng {current} | " + " | ".join(f"{column_letter(col)}: {text}" for col, text in cells))
                if budget["cells"] <= 0:
                    flags["cells"] = True
                    element.clear()
                    break
            cells = []
            row_number = current
            next_col = 0
            element.clear()
        elif name == "mergeCell" and element.get("ref"):
            sheet.merges.append(element.get("ref"))
            element.clear()


def _extras(package: _Package, part: str, people: dict[str, str], date1904: bool, counts: dict) -> list[str]:
    """Dòng mô tả Bảng (Table), bảng tổng hợp, biểu đồ, hộp chữ, hình và ghi chú của một trang tính. Giới hạn đếm trên cả
    tệp (counts) và không phụ thuộc max_chars, để số dòng của chữ đầy đủ khớp với phần đọc sẵn."""
    from features.documents import workbook_parts as parts

    relations = [(target, kind) for target, kind in package.relationships(part).values() if target in package.names]
    lines: list[str] = []

    def guarded(read, *args):
        try:
            return read(*args)
        except Exception:
            counts["failed"] += 1
            return None

    for target, kind in relations:
        if kind.endswith("/table") and (table := guarded(parts.read_table, package, target)):
            counts["tables"] += 1
            lines.append(parts.describe_table(table))
    for target, kind in relations:
        if kind.endswith("/pivotTable") and (pivot := guarded(parts.read_pivot, package, target)):
            counts["pivots"] += 1
            lines.append(parts.describe_pivot(pivot))
    images = []
    for target, kind in relations:
        if not kind.endswith("/drawing") or not (drawing := guarded(parts.read_drawing, package, target, date1904)):
            continue
        for chart in drawing.charts:
            counts["charts"] += 1
            if counts["charts"] <= MAX_CHARTS:
                lines.extend(parts.describe_chart(chart, f" ở {parts.area(*chart.anchor)}" if chart.anchor else ""))
        for where, text in drawing.texts:
            counts["texts"] += 1
            if counts["texts"] <= MAX_TEXT_BOXES:
                lines.append(f"Hộp chữ{where}: {text}")
        images.extend(drawing.images)
    if images:
        counts["images"] += len(images)
        described = [f"{where} ({text})" if text else where for where, text in images if text][:10]
        lines.append(f"Hình ảnh: {len(images)} hình, Peto chưa xem được nội dung hình"
                     + (": " + "; ".join(item.strip() for item in described) if described else "") + ".")
    notes = guarded(parts.read_notes, package, part, people) or []
    for note in notes:
        counts["notes"] += 1
        if counts["notes"] <= MAX_NOTES:
            lines.append(parts.describe_note(note))
    if counts["notes"] > MAX_NOTES and notes:
        lines.append(f"[… còn ghi chú khác chưa hiện, quá {MAX_NOTES} ghi chú …]")
    return lines


def _chart_sheet(package: _Package, part: str, date1904: bool, counts: dict) -> list[str]:
    """Biểu đồ của một trang biểu đồ (chartsheet)."""
    from features.documents import workbook_parts as parts

    lines: list[str] = []
    for target, kind in package.relationships(part).values():
        if not kind.endswith("/drawing") or target not in package.names:
            continue
        try:
            drawing = parts.read_drawing(package, target, date1904)
        except Exception:
            counts["failed"] += 1
            continue
        for chart in drawing.charts:
            counts["charts"] += 1
            if counts["charts"] <= MAX_CHARTS:
                lines.extend(parts.describe_chart(chart))
    return lines


def read_workbook(data: bytes, max_chars: int) -> dict:
    """Đọc cả bảng tính thành chữ; dài quá ``max_chars`` thì phần đọc sẵn gồm đầu, công thức và cuối mỗi trang tính."""
    from features.documents.reader import result

    if data.startswith(CFB_MAGIC):
        return result("encrypted", "Tệp Excel đang đặt mật khẩu, hoặc là định dạng .xls cũ. Mở khóa hoặc lưu lại thành "
                                   ".xlsx rồi gửi lại nhé.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) > MAX_ENTRIES or sum(item.file_size for item in entries) > MAX_DECLARED_BYTES
                    or len({item.filename for item in entries}) != len(entries)):
                return result("unreadable", "Tệp Excel có cấu trúc nén quá lớn hoặc không hợp lệ. Hãy lưu lại bản gọn hơn.")
            return _read(_Package(archive), max_chars)
    except _Unreadable as error:
        return result("unreadable", str(error))
    except (zipfile.BadZipFile, KeyError, ValueError, SyntaxError, EOFError):
        return result("unreadable", "Chưa đọc được tệp Excel: tệp hỏng hoặc không đúng định dạng .xlsx. Thử mở bằng Excel rồi "
                                    "lưu lại.")


def _read(package: _Package, max_chars: int) -> dict:
    from features.documents.reader import result

    office = next((target for target, kind in package.relationships("").values() if kind.endswith("/officeDocument")),
                  "xl/workbook.xml")
    if office not in package.names:
        raise _Unreadable("Không thấy phần dữ liệu của bảng tính. Tệp này có đúng là Excel .xlsx không?")
    workbook = package.xml(office)
    if _local(workbook.tag) != "workbook":
        raise _Unreadable("Tệp không phải bảng tính Excel.")
    relations = package.relationships(office)
    date1904 = False
    declared = []
    names = []
    for section in workbook:
        name = _local(section.tag)
        if name == "workbookPr":
            date1904 = section.get("date1904", "").lower() in ("1", "true")
        elif name == "sheets":
            for item in section:
                if _local(item.tag) == "sheet":
                    declared.append((item.get("name", ""), item.get("state", "visible"), _relationship_id(item)))
        elif name == "definedNames":
            for item in section:
                label = item.get("name", "")
                if item.get("hidden") in ("1", "true") or label.startswith("_xlnm.") or not (item.text or "").strip():
                    continue
                names.append(f"Tên vùng: {label} = {_clean_formula(item.text)}")
    find = lambda suffix: next((target for target, kind in relations.values() if kind.endswith(suffix)), None)  # noqa: E731
    flags: dict = {}
    strings = _shared_strings(package, find("/sharedStrings"), flags)
    kinds = _styles(package, find("/styles"))
    worksheets = [(label, state, relations.get(rid, ("", ""))) for label, state, rid in declared]
    data_sheets = [(label, state, target) for label, state, (target, kind) in worksheets if kind.endswith("/worksheet")]
    chart_sheets = [(label, target) for label, _, (target, kind) in worksheets
                    if kind.endswith("/chartsheet") and target in package.names]
    other = [label for label, _, (_, kind) in worksheets if not kind.endswith(("/worksheet", "/chartsheet"))]
    counts = dict.fromkeys(("tables", "pivots", "charts", "texts", "images", "notes", "failed"), 0)
    try:
        from features.documents.workbook_parts import read_people
        people = read_people(package, office)
    except Exception:
        people = {}
        counts["failed"] += 1
    budget = {"cells": MAX_CELLS}
    sheets: list[_Sheet] = []
    skipped_sheets = 0
    for position, (label, state, target) in enumerate(data_sheets, start=1):
        if position > MAX_SHEETS or flags.get("cells"):
            skipped_sheets += 1
            continue
        sheet = _Sheet(label, position, len(data_sheets), state != "visible")
        if target in package.names:
            _read_sheet(package, target, sheet, strings, kinds, date1904, budget, flags)
            sheet.extras = _extras(package, target, people, date1904, counts)
        sheets.append(sheet)
    listing = ", ".join(f'"{sheet.name}"' for sheet in sheets)
    charts_listing = f" · {len(chart_sheets)} trang biểu đồ" if chart_sheets else ""
    head = [f"[Bảng tính Excel · {len(data_sheets)} trang tính: {listing}{charts_listing}]"]
    if other:
        head.append("Trang khác chưa xem được (hộp thoại, macro cũ): " + ", ".join(f'"{label}"' for label in other))
    if names:
        head.extend(names[:MAX_NAMES_SHOWN])
        if len(names) > MAX_NAMES_SHOWN:
            head.append(f"[… và {_number(len(names) - MAX_NAMES_SHOWN)} tên vùng khác …]")
    if flags.get("quoted"):
        head.append('Chữ trong ngoặc kép được ghi đúng từng ký tự, ngoặc kép không thuộc giá trị: "" là chữ rỗng (công thức '
                    'trả về ""), " Lan" có khoảng trắng ở đầu, "Lan " ở cuối; dấu nháy kép bên trong viết đôi.')
    # Mỗi dòng kèm số trang tính nếu là hàng dữ liệu; một dòng trống giữa các khối. Dòng của chữ đầy đủ là dòng mà công cụ
    # read_attachment_lines đánh số, nên phần đọc sẵn rút gọn (condense) ghi đúng số dòng bỏ qua.
    lines: list[tuple[str, int | None]] = [(line, None) for line in head]
    for index, sheet in enumerate(sheets):
        lines.append(("", None))
        lines.extend((line, index if is_row else None) for line, is_row in sheet.lines())
    for label, target in chart_sheets:
        lines.append(("", None))
        lines.append((f'[Trang biểu đồ "{label}"]', None))
        lines.extend((line, None) for line in _chart_sheet(package, target, date1904, counts) or ["(Không đọc được biểu đồ.)"])
    text = "\n".join(line for line, _ in lines)
    rows = sum(len(sheet.rows) for sheet in sheets)
    formulas = sum(len(sheet.formulas) for sheet in sheets)
    notices = [f"Đã đọc {_number(len(sheets))} trang tính, {_number(rows)} hàng có dữ liệu"
               + (f", {_number(formulas)} ô công thức" if formulas else "") + "."]
    if formulas:
        notices.append("Giá trị công thức là kết quả đã lưu trong tệp.")
    hidden = sum(sheet.hidden for sheet in sheets)
    if hidden:
        notices.append(f"Có {hidden} trang tính đang ẩn, vẫn được đọc.")
    partial = False
    for sheet in sheets:
        if sheet.more_rows:
            partial = True
            notices.append(f'Trang "{sheet.name}" dài hơn {_number(MAX_ROWS)} hàng: Peto chỉ đọc {_number(MAX_ROWS)} hàng đầu.')
        if sheet.more_columns:
            partial = True
            notices.append(f'Trang "{sheet.name}" rộng hơn {MAX_COLUMNS} cột: phần sau cột {column_letter(MAX_COLUMNS - 1)} '
                           'chưa đọc.')
    if flags.get("cells") or skipped_sheets:
        partial = True
        notices.append("Bảng tính quá lớn: " + (f"{skipped_sheets} trang tính sau chưa đọc." if skipped_sheets else
                                                "phần cuối chưa đọc."))
    if flags.get("strings"):
        partial = True
        notices.append("Tệp có quá nhiều chữ khác nhau: một số ô chưa đọc được chữ.")
    if flags.get("uncached"):
        notices.append(f"{_number(flags['uncached'])} ô công thức chưa có kết quả lưu trong tệp (Excel tính khi mở tệp); "
                       "Peto chỉ thấy công thức của các ô này.")
    found = [f"{_number(counts[key])} {label}" for key, label in (("charts", "biểu đồ"), ("pivots", "bảng tổng hợp"),
                                                                  ("tables", "Bảng (Table)"), ("notes", "ghi chú trong ô"))
             if counts[key]]
    if found:
        notices.append("Có " + ", ".join(found) + ": Peto đọc chữ và số liệu của chúng, không thấy hình vẽ.")
    if counts["charts"] > MAX_CHARTS or counts["texts"] > MAX_TEXT_BOXES:
        notices.append("Tệp có quá nhiều biểu đồ hoặc hộp chữ: phần sau chưa hiện.")
    if counts["images"]:
        notices.append(f"Chưa xem được {_number(counts['images'])} hình ảnh trong tệp.")
    if counts["failed"]:
        partial = True
        notices.append("Một vài biểu đồ, ghi chú hoặc bảng trong tệp chưa đọc được.")
    if not rows and not counts["charts"]:
        return result("no_text", "Bảng tính không có ô nào có dữ liệu.", text, sheets=len(data_sheets),
                      sheets_read=len(sheets), rows=0, sheet_format=SHEET_FORMAT)
    details = {"sheets": len(data_sheets), "sheets_read": len(sheets), "rows": rows, "formulas": formulas,
               "sheet_format": SHEET_FORMAT}
    if len(text) > max_chars:
        notices.append("Bảng dài: Peto đọc sẵn phần đầu và phần cuối mỗi trang tính, khi cần sẽ tìm thêm trong tệp.")
        return result("partial", " ".join(notices), condense(lines, max_chars), total_characters=len(text),
                      lines=len(lines), **details)
    return result("partial" if partial else "ready", " ".join(notices), text, **details)
