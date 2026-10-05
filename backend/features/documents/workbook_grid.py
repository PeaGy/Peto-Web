"""Lưới xem cho tệp Excel Peto đã sửa: giá trị đã định dạng như Excel hiện (kiểu Việt Nam: 1.234.567,5), công thức,
màu nền, chữ đậm/nghiêng, màu chữ, viền, căn lề, độ rộng cột, chiều cao hàng, ô gộp, ô cố định, biểu đồ, và các ô vừa
sửa để tô nổi.

Khác lưới của create_spreadsheet (sheets/view.py, dựng lại từ JSON của bảng): tệp người dùng có bố cục tự do, nên lưới
là danh sách ô thưa theo hàng/cột thật của trang tính. Chỉ hiện phần đầu của trang quá lớn.
"""
from __future__ import annotations

import colorsys
import math
import re
from datetime import datetime, timedelta

from features.documents.workbook_edit import meta, refs
from features.documents.workbook_edit.book import Book
from features.documents.workbook_edit.formulas import formula_map
from features.documents.workbook_edit.package import local
from features.documents.workbook_reader import format_kind

MAX_GRID_ROWS, MAX_GRID_COLS = 500, 60
DEFAULT_WIDTH = 8.43            # đơn vị Excel: bề rộng chữ số 0 của phông mặc định
DEFAULT_HEIGHT = 15.0           # điểm
CHART_WIDTH, CHART_HEIGHT = 480, 288

# Bảng màu đánh số cũ của Excel (indexed), 0–63.
_INDEXED = (
    '000000', 'FFFFFF', 'FF0000', '00FF00', '0000FF', 'FFFF00', 'FF00FF', '00FFFF', '000000', 'FFFFFF', 'FF0000', '00FF00',
    '0000FF', 'FFFF00', 'FF00FF', '00FFFF', '800000', '008000', '000080', '808000', '800080', '008080', 'C0C0C0', '808080',
    '9999FF', '993366', 'FFFFCC', 'CCFFFF', '660066', 'FF8080', '0066CC', 'CCCCFF', '000080', 'FF00FF', 'FFFF00', '00FFFF',
    '800080', '800000', '008080', '0000FF', '00CCFF', 'CCFFFF', 'CCFFCC', 'FFFF99', '99CCFF', 'FF99CC', 'CC99FF', 'FFCC99',
    '3366FF', '33CCCC', '99CC00', 'FFCC00', 'FF9900', 'FF6600', '666699', '969696', '003366', '339966', '003300', '333300',
    '993300', '993366', '333399', '333333')
_BORDERS = {'thin': '1px solid', 'hair': '1px dotted', 'dotted': '1px dotted', 'dashed': '1px dashed', 'medium': '2px solid',
            'mediumDashed': '2px dashed', 'dashDot': '1px dashed', 'mediumDashDot': '2px dashed', 'dashDotDot': '1px dashed',
            'mediumDashDotDot': '2px dashed', 'slantDashDot': '2px dashed', 'thick': '3px solid', 'double': '3px double'}
_BUILTIN_CODES = {0: 'General', 1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 5: '#,##0 "₫";-#,##0 "₫"', 9: '0%',
                  10: '0.00%', 11: '0.00E+00', 12: '# ?/?', 13: '# ??/??', 14: 'dd/mm/yyyy', 15: 'd-mmm-yy', 16: 'd-mmm',
                  17: 'mmm-yy', 18: 'h:mm AM/PM', 19: 'h:mm:ss AM/PM', 20: 'h:mm', 21: 'h:mm:ss', 22: 'dd/mm/yyyy h:mm',
                  37: '#,##0 ;(#,##0)', 38: '#,##0 ;(#,##0)', 39: '#,##0.00;(#,##0.00)', 40: '#,##0.00;(#,##0.00)',
                  45: 'mm:ss', 46: '[h]:mm:ss', 47: 'mm:ss.0', 48: '##0.0E+0', 49: '@'}


# ---------- màu ----------

def _theme(book: Book) -> list[str]:
    """Màu chủ đề theo chỉ số Excel dùng (0 nền 1, 1 chữ 1, 2 nền 2, 3 chữ 2, 4–9 nhấn, 10–11 liên kết)."""
    targets = book.rels.find('/theme')
    if not targets or not book.package.exists(targets[0]):
        return []
    try:
        root = book.package.xml(targets[0])
    except Exception:
        return []
    scheme = next((element for element in root.iter() if isinstance(element.tag, str) and local(element.tag) == 'clrScheme'),
                  None)
    if scheme is None:
        return []
    colors = []
    for slot in scheme:
        value = ''
        for child in slot:
            if local(child.tag) == 'srgbClr':
                value = child.get('val', '')
            elif local(child.tag) == 'sysClr':
                value = child.get('lastClr', '')
        colors.append(value.upper() or '000000')
    if len(colors) >= 4:
        colors[0], colors[1], colors[2], colors[3] = colors[1], colors[0], colors[3], colors[2]
    return colors


def _tint(color: str, tint: float) -> str:
    red, green, blue = (int(color[index:index + 2], 16) / 255 for index in (0, 2, 4))
    hue, light, saturation = colorsys.rgb_to_hls(red, green, blue)
    light = light * (1 + tint) if tint < 0 else light * (1 - tint) + tint
    red, green, blue = colorsys.hls_to_rgb(hue, min(max(light, 0.0), 1.0), saturation)
    return ''.join(f'{round(part * 255):02X}' for part in (red, green, blue))


def _color(element, theme: list[str], indexed: list[str]) -> str | None:
    """'#RRGGBB' của một thẻ màu (rgb, theme + tint, indexed); None là màu tự động."""
    if element is None or element.get('auto') in ('1', 'true'):
        return None
    value = None
    if element.get('rgb'):
        value = element.get('rgb')[-6:].upper()
    elif element.get('theme') is not None:
        try:
            value = theme[int(element.get('theme'))]
        except (ValueError, IndexError):
            return None
    elif element.get('indexed') is not None:
        try:
            number = int(element.get('indexed'))
        except ValueError:
            return None
        if number >= len(indexed):
            return None
        value = indexed[number]
    if not value or not re.fullmatch(r'[0-9A-F]{6}', value):
        return None
    try:
        tint = float(element.get('tint') or 0)
    except ValueError:
        tint = 0.0
    return '#' + (_tint(value, tint) if tint else value)


# ---------- kiểu ô ----------

class _Styles:
    """Kiểu ô của tệp đổi sang dạng gọn cho trình duyệt; mỗi kiểu khác nhau một số thứ tự trong bảng ``table``."""

    def __init__(self, book: Book):
        self.book = book
        root = book.styles.root
        self.theme = _theme(book)
        self.indexed = list(_INDEXED)
        self.codes: dict[int, str] = dict(_BUILTIN_CODES)
        self.fonts, self.fills, self.borders, self.xfs = [], [], [], []
        if root is not None:
            for section in root:
                name = local(section.tag)
                children = [child for child in section if isinstance(child.tag, str)]
                if name == 'numFmts':
                    for item in children:
                        try:
                            self.codes[int(item.get('numFmtId', '-1'))] = item.get('formatCode', '')
                        except ValueError:
                            continue
                elif name == 'fonts':
                    self.fonts = children
                elif name == 'fills':
                    self.fills = children
                elif name == 'borders':
                    self.borders = children
                elif name == 'cellXfs':
                    self.xfs = children
                elif name == 'colors':
                    palette = next((child for child in section if local(child.tag) == 'indexedColors'), None)
                    if palette is not None:
                        custom = [item.get('rgb', '')[-6:].upper() for item in palette if local(item.tag) == 'rgbColor']
                        self.indexed[:len(custom)] = custom
        self.base_size = self._font_size(self.fonts[0]) if self.fonts else 11.0
        self.table: list[dict] = []
        self._index: dict[str, int] = {}
        self._cache: dict[int, tuple[int | None, str]] = {}

    @staticmethod
    def _font_size(font) -> float:
        size = next((child for child in font if local(child.tag) == 'sz'), None)
        try:
            return float(size.get('val')) if size is not None else 11.0
        except (TypeError, ValueError):
            return 11.0

    def code(self, index: int) -> str:
        return self.of(index)[1]

    def of(self, index: int) -> tuple[int | None, str]:
        """(Số thứ tự kiểu trong bảng gửi trình duyệt hoặc None khi không có gì đặc biệt, mã định dạng số)."""
        if index in self._cache:
            return self._cache[index]
        xf = self.xfs[index] if 0 <= index < len(self.xfs) else (self.xfs[0] if self.xfs else None)
        if xf is None:
            return None, 'General'
        try:
            code = self.codes.get(int(xf.get('numFmtId', '0')), 'General')
        except ValueError:
            code = 'General'
        style: dict = {}
        font = self._pick(self.fonts, xf.get('fontId'))
        if font is not None:
            for child in font:
                name = local(child.tag)
                if name in ('b', 'i', 'strike') and child.get('val', '1') not in ('0', 'false'):
                    style[{'b': 'b', 'i': 'i', 'strike': 'x'}[name]] = 1
                elif name == 'u' and child.get('val', 'single') != 'none':
                    style['u'] = 1
                elif name == 'color':
                    color = _color(child, self.theme, self.indexed)
                    if color and color != '#000000':
                        style['c'] = color
            size = self._font_size(font)
            if abs(size - self.base_size) > 0.1:
                style['z'] = size
        fill = self._pick(self.fills, xf.get('fillId'))
        if fill is not None:
            pattern = next((child for child in fill if local(child.tag) == 'patternFill'), None)
            gradient = next((child for child in fill if local(child.tag) == 'gradientFill'), None)
            if pattern is not None and pattern.get('patternType') not in (None, 'none'):
                foreground = next((child for child in pattern if local(child.tag) == 'fgColor'), None)
                color = _color(foreground, self.theme, self.indexed)
                if color:
                    style['f'] = color
            elif gradient is not None:
                stop = next((child for child in gradient.iter() if isinstance(child.tag, str) and local(child.tag) == 'color'), None)
                color = _color(stop, self.theme, self.indexed)
                if color:
                    style['f'] = color
        border = self._pick(self.borders, xf.get('borderId'))
        if border is not None:
            for child in border:
                side = {'left': 'l', 'right': 'r', 'top': 't', 'bottom': 'b', 'start': 'l', 'end': 'r'}.get(local(child.tag))
                line = _BORDERS.get(child.get('style') or '')
                if side and line:
                    color = _color(next((item for item in child if local(item.tag) == 'color'), None), self.theme,
                                   self.indexed) or '#000000'
                    style.setdefault('bd', {})[side] = f'{line} {color}'
        alignment = next((child for child in xf if local(child.tag) == 'alignment'), None)
        if alignment is not None:
            horizontal = alignment.get('horizontal')
            if horizontal in ('left', 'center', 'right', 'justify', 'centerContinuous', 'distributed'):
                style['h'] = {'centerContinuous': 'center', 'distributed': 'justify'}.get(horizontal, horizontal)
            if alignment.get('vertical') in ('top', 'center'):
                style['v'] = alignment.get('vertical')
            if alignment.get('wrapText') in ('1', 'true'):
                style['w'] = 1
            try:
                if int(alignment.get('indent') or 0):
                    style['in'] = int(alignment.get('indent'))
            except ValueError:
                pass
        result = (self._intern(style) if style else None, code)
        self._cache[index] = result
        return result

    @staticmethod
    def _pick(items: list, value):
        try:
            number = int(value or 0)
        except ValueError:
            return None
        return items[number] if 0 <= number < len(items) else None

    def _intern(self, style: dict) -> int:
        key = repr(sorted(style.items()))
        if key not in self._index:
            self._index[key] = len(self.table)
            self.table.append(style)
        return self._index[key]


# ---------- định dạng số ----------

def _sections(code: str) -> list[str]:
    parts, current, quoted, bracket = [], '', False, False
    for char in code:
        if char == '"':
            quoted = not quoted
        elif char == '[' and not quoted:
            bracket = True
        elif char == ']' and not quoted:
            bracket = False
        if char == ';' and not quoted and not bracket:
            parts.append(current)
            current = ''
            continue
        current += char
    parts.append(current)
    return parts


def _group(digits: str) -> str:
    out = []
    while len(digits) > 3:
        out.insert(0, digits[-3:])
        digits = digits[:-3]
    out.insert(0, digits)
    return '.'.join(out)


def _general(number: float) -> str:
    if number == int(number) and abs(number) < 1e11:
        return str(int(number))
    text = f'{number:.10g}'
    if 'e' in text:
        mantissa, exponent = text.split('e')
        return f'{mantissa.replace(".", ",")}E{int(exponent):+03d}'
    return text.replace('.', ',')


def _literal(section: str) -> tuple[str, str, str]:
    """(chữ trước số, phần mẫu số, chữ sau số) của một đoạn mã định dạng; chữ trong nháy, ký tự thoát, ký hiệu tiền."""
    out = []
    index = 0
    while index < len(section):
        char = section[index]
        if char == '"':
            end = section.find('"', index + 1)
            end = len(section) if end < 0 else end
            out.append(('lit', section[index + 1:end]))
            index = end + 1
            continue
        if char == '\\' and index + 1 < len(section):
            out.append(('lit', section[index + 1]))
            index += 2
            continue
        if char == '[':
            end = section.find(']', index)
            end = len(section) if end < 0 else end
            inner = section[index + 1:end]
            if inner.startswith('$'):
                symbol = inner[1:].split('-')[0]
                if symbol:
                    out.append(('lit', symbol))
            index = end + 1
            continue
        if char in '_*' and index + 1 < len(section):
            if char == '_':
                out.append(('lit', ' '))
            index += 2
            continue
        out.append(('code', char))
        index += 1
    before, pattern, after = [], [], []
    seen_code = False
    for kind, text in out:
        if kind == 'code' and text in '0#?.,%Ee+-/' and (text not in '+-' or seen_code):
            seen_code = seen_code or text in '0#?'
            if not after:
                pattern.append(text)
                continue
        (after if pattern else before).append(text)
    return ''.join(before), ''.join(pattern), ''.join(after)


def _date_text(value: float, section: str, date1904: bool) -> str:
    base = datetime(1904, 1, 1) if date1904 else (datetime(1899, 12, 31) if value < 61 else datetime(1899, 12, 30))
    try:
        moment = base + timedelta(seconds=round(value * 86400))
    except OverflowError:
        return _general(value)
    cleaned = re.sub(r'"([^"]*)"', lambda match: '\x00' + match.group(1) + '\x01', section)
    cleaned = re.sub(r'\[\$[^\]]*\]|\[(?![hms]+\])[^\]]*\]|\\|_.|\*.', '', cleaned)
    tokens = re.findall(r'\x00[^\x01]*\x01|\[h+\]|\[m+\]|\[s+\]|yyyy|yy|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|AM/PM|am/pm|A/P|'
                        r'\.0+|.', cleaned, re.I)
    ampm = any(token.upper() in ('AM/PM', 'A/P') for token in tokens)
    out = []
    for position, token in enumerate(tokens):
        lower = token.lower()
        previous = next((item.lower() for item in reversed(tokens[:position]) if re.fullmatch(r'[a-z\[\]]+', item, re.I)), '')
        following = next((item.lower() for item in tokens[position + 1:] if re.fullmatch(r'[a-z\[\]]+', item, re.I)), '')
        if token.startswith('\x00'):
            out.append(token[1:-1])
        elif lower in ('yyyy',):
            out.append(f'{moment.year:04d}')
        elif lower == 'yy':
            out.append(f'{moment.year % 100:02d}')
        elif lower in ('mm', 'm') and (previous.startswith('h') or following.startswith('s')):
            out.append(f'{moment.minute:02d}' if lower == 'mm' else str(moment.minute))
        elif lower == 'mmmmm':
            out.append(f'T{moment.month}')
        elif lower == 'mmmm':
            out.append(f'Tháng {moment.month}')
        elif lower == 'mmm':
            out.append(f'Thg {moment.month}')
        elif lower == 'mm':
            out.append(f'{moment.month:02d}')
        elif lower == 'm':
            out.append(str(moment.month))
        elif lower == 'dddd':
            out.append(('Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật')[moment.weekday()])
        elif lower == 'ddd':
            out.append(('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')[moment.weekday()])
        elif lower == 'dd':
            out.append(f'{moment.day:02d}')
        elif lower == 'd':
            out.append(str(moment.day))
        elif lower.startswith('[h'):
            out.append(str(int(value * 24)))
        elif lower.startswith('[m'):
            out.append(str(int(value * 1440)))
        elif lower.startswith('[s'):
            out.append(str(int(value * 86400)))
        elif lower in ('hh', 'h'):
            hour = moment.hour % 12 or 12 if ampm else moment.hour
            out.append(f'{hour:02d}' if lower == 'hh' else str(hour))
        elif lower in ('ss', 's'):
            out.append(f'{moment.second:02d}' if lower == 'ss' else str(moment.second))
        elif lower in ('am/pm', 'a/p'):
            out.append(('SA' if moment.hour < 12 else 'CH'))
        elif lower.startswith('.0'):
            out.append(',' + f'{moment.microsecond / 1e6:.{len(token) - 1}f}'[2:])
        else:
            out.append(token)
    return ''.join(out)


def display(value, code: str, date1904: bool) -> str:
    """Giá trị ô như Excel hiện với mã định dạng ``code``, theo kiểu Việt Nam (1.234.567,5)."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, str):
        sections = _sections(code or 'General')
        if len(sections) >= 4 and '@' in sections[3]:
            before, _, after = sections[3].partition('@')
            return _literal(before)[0] + value + _literal(after)[0] if before or after else value
        return value
    if not isinstance(value, float):
        return str(value)
    if not math.isfinite(value):
        return '#NUM!'
    sections = _sections(code or 'General')
    if value < 0 and len(sections) >= 2:
        section, number, sign = sections[1], -value, ''
    elif value == 0 and len(sections) >= 3:
        section, number, sign = sections[2], value, ''
    else:
        section, number, sign = sections[0], abs(value), '-' if value < 0 else ''
    plain = re.sub(r'\[[^\]]*\]', '', section).strip()
    if not plain or plain.lower() == 'general':
        return sign + _general(number) if plain.lower() == 'general' or not plain else _general(value)
    kind = format_kind(section)
    if kind in ('date', 'datetime', 'time'):
        return sign + _date_text(number, section, date1904)
    before, pattern, after = _literal(section)
    if not re.search(r'[0#?]', pattern):
        return before + after if (before + after).strip() else _general(value)
    if re.search(r'[Ee][+-]', pattern):
        decimals = len(re.search(r'\.([0#]*)', pattern).group(1)) if '.' in pattern else 0
        text = f'{number:.{decimals}E}'
        mantissa, exponent = text.split('E')
        return sign + before + mantissa.replace('.', ',') + 'E' + f'{int(exponent):+03d}' + after
    if '%' in pattern:
        number *= 100
        after = '%' + after
    integer_part, _, fraction_part = pattern.replace('%', '').partition('.')
    scale = len(integer_part) - len(integer_part.rstrip(','))
    number /= 1000 ** scale
    decimals = len(re.sub(r'[^0#?]', '', fraction_part))
    required = len(re.sub(r'[^0?]', '', fraction_part))
    rounded = f'{number:.{decimals}f}'
    whole, _, fraction = rounded.partition('.')
    fraction = fraction.rstrip('0').ljust(required, '0') if decimals > required else fraction
    minimum = len(re.sub(r'[^0]', '', integer_part.rstrip(',')))
    whole = whole.lstrip('0') or ''
    whole = whole.rjust(minimum, '0')
    if ',' in integer_part.rstrip(','):
        whole = _group(whole) if whole else whole
    text = whole + (',' + fraction if fraction else '')
    if not text:
        text = '0'
    if sign and text.strip('0,.') == '':
        sign = ''
    return sign + before + text + after


# ---------- lưới ----------

def _width_px(width: float) -> int:
    return round(width * 7 + 5)


def _changed(text: str) -> dict[str, list[tuple[int, int, int, int]]]:
    """Ô đã sửa từ dòng "Ô đã sửa: 'Trang'!A1:B5, …" trong nội dung tài liệu."""
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    for ref in refs.scan(text or '').refs:
        if ref.sheet is not None and ref.r1 is not None and ref.c1 is not None:
            out.setdefault(ref.sheet, []).append((ref.r1, ref.c1, ref.r2, ref.c2))
    return out


def grid(data: bytes, title: str, changed_text: str = '') -> dict:
    book = Book(data)
    styles = _Styles(book)
    changed = _changed(changed_text)
    sheets = []
    for info in book.data_sheets():
        sheet = book.worksheet(info)
        texts = formula_map(sheet)
        bounds = sheet.bounds()
        widths: dict[int, tuple[float, bool]] = {}
        default_width = DEFAULT_WIDTH
        match = re.search(r'<(?:[\w.-]+:)?sheetFormatPr\b[^>]*\bdefaultColWidth="([\d.]+)"', sheet.before)
        if match:
            default_width = float(match.group(1))
        for low, high, attrs in sheet.columns():
            try:
                width = float(attrs.get('width', default_width))
            except ValueError:
                width = default_width
            for col in range(low, min(high, MAX_GRID_COLS) + 1):
                widths[col] = (width, attrs.get('hidden') in ('1', 'true'))
        default_height = DEFAULT_HEIGHT
        match = re.search(r'<(?:[\w.-]+:)?sheetFormatPr\b[^>]*\bdefaultRowHeight="([\d.]+)"', sheet.before)
        if match:
            default_height = float(match.group(1))
        last_row = min(bounds[2], MAX_GRID_ROWS - 1) if bounds else 0
        last_col = min(bounds[3], MAX_GRID_COLS - 1) if bounds else 0
        cells, heights, hidden_rows = [], {}, []
        formulas = 0
        for index, row in sheet.rows.items():
            if index > last_row:
                continue
            if row.attrs.get('ht') and row.attrs.get('customHeight') in ('1', 'true'):
                try:
                    heights[index] = round(float(row.attrs['ht']) * 4 / 3)
                except ValueError:
                    pass
            if row.attrs.get('hidden') in ('1', 'true'):
                hidden_rows.append(index)
            for col, cell in row.cells.items():
                if col > last_col:
                    continue
                style, code = styles.of(cell.style)
                value = book.value(cell)
                formula = texts.get((index, col))
                item: dict = {}
                if formula is not None:
                    formulas += 1
                    if formula[0]:
                        item['f'] = '=' + formula[0]
                    # Chưa có kết quả (Excel tính khi mở), theo đúng luật của bộ đọc: không có v hoặc v rỗng, trừ t="str"
                    # có thẻ v, tức công thức trả về "".
                    if not cell.value() and cell.kind != 'inlineStr' and not (cell.kind == 'str' and cell.has_value()):
                        item['p'] = 1
                if value is not None and value != '':
                    item['d'] = display(value, code, book.date1904)
                    item['t'] = 'n' if isinstance(value, float) else 'b' if isinstance(value, bool) else \
                        'e' if not isinstance(value, str) else 's'
                if style is not None:
                    item['s'] = style
                if item:
                    cells.append([index, col, item])
        pane = re.search(r'<(?:[\w.-]+:)?pane\b[^>]*>', sheet.before)
        freeze = [0, 0]
        if pane and re.search(r'state="frozen"', pane.group(0)):
            split = dict(re.findall(r'\b([xy]Split)="(\d+(?:\.\d+)?)"', pane.group(0)))
            freeze = [int(float(split.get('ySplit', 0))), int(float(split.get('xSplit', 0)))]
        merges = [list(area) for area in meta.merges(sheet) if area[0] <= last_row and area[1] <= last_col]
        charts = _charts(book, sheet, info.name, widths, default_width, heights, default_height, styles)
        used_cols = max([last_col, *(chart['col'] + 8 for chart in charts)]) + 1 if bounds or charts else 1
        sheets.append({
            'name': info.name, 'kind': 'workbook', 'hidden': info.state != 'visible',
            'cols': [{'width': _width_px(widths.get(col, (default_width, False))[0]),
                      **({'hidden': True} if widths.get(col, (0, False))[1] else {})} for col in range(min(used_cols, MAX_GRID_COLS))],
            'heights': {str(key): value for key, value in heights.items()},
            'hiddenRows': hidden_rows,
            'rowHeight': round(default_height * 4 / 3),
            'cells': cells, 'merges': merges, 'freeze': freeze,
            'changed': [list(area) for area in changed.get(info.name, [])],
            'charts': charts, 'formulas': formulas,
            'used': [bounds[2] + 1 if bounds else 0, bounds[3] + 1 if bounds else 0],
            'truncated': bool(bounds and (bounds[2] >= MAX_GRID_ROWS or bounds[3] >= MAX_GRID_COLS)),
        })
    return {'title': title, 'kind': 'workbook', 'styles': styles.table, 'sheets': sheets}


def _charts(book: Book, sheet, name: str, widths, default_width: float, heights, default_height: float, styles) -> list[dict]:
    """Biểu đồ cột, thanh, đường, tròn của trang: số liệu đọc lại từ ô theo vùng của biểu đồ (sau khi sửa thì số mới),
    thiếu vùng thì dùng số đã lưu trong biểu đồ."""
    from features.documents import workbook_parts
    from features.documents.sheets.view import nice_axis
    out = []
    for target in book.package.relationships(sheet.part).find('/drawing'):
        if not book.package.exists(target):
            continue
        try:
            drawing = workbook_parts.read_drawing(book.reader(), target, book.date1904)
        except Exception:
            continue
        for chart in drawing.charts:
            kind = chart.simple
            if kind is None or chart.anchor is None:
                continue
            r1, c1, r2, c2 = chart.anchor
            width = sum(_width_px(widths.get(col, (default_width, False))[0]) for col in range(c1, c2)) or CHART_WIDTH
            height = sum(heights.get(row, round(default_height * 4 / 3)) for row in range(r1, r2)) or CHART_HEIGHT
            series, categories, code = [], [], None
            for item in chart.series[:6]:
                values = _range_values(book, item.values_ref) or item.values
                labels = _range_values(book, item.categories_ref, styles) or item.categories
                numbers = [value if isinstance(value, float) else None for value in values]
                categories = categories or [str(label or '') for label in labels]
                code = code or _range_code(book, item.values_ref, styles)
                series.append({'name': _series_name(book, item, styles), 'values': numbers,
                               'labels': [display(value, code or 'General', book.date1904) if value is not None else ''
                                          for value in numbers]})
            if not series:
                continue
            entry = {'type': kind, 'title': chart.title, 'row': r1, 'col': c1, 'width': max(width, 240),
                     'height': max(height, 160), 'categories': categories, 'series': series}
            present = [value for item in series for value in item['values'] if value is not None]
            if kind != 'pie' and present:
                low, high, step = nice_axis(present)
                ticks = [low + step * index for index in range(int(round((high - low) / step)) + 1)]
                entry['axis'] = {'min': low, 'max': high, 'step': step,
                                 'labels': [display(float(tick), code or 'General', book.date1904) for tick in ticks]}
            out.append(entry)
    return out


def _range_values(book: Book, reference: str, styles: '_Styles | None' = None) -> list:
    """Giá trị các ô của một vùng (một tham chiếu có ghi trang); có ``styles`` thì là chữ đã định dạng."""
    found = refs.scan(reference or '').refs
    if len(found) != 1 or found[0].sheet is None or found[0].r1 is None or found[0].c1 is None:
        return []
    ref = found[0]
    try:
        info = book.info(ref.sheet)
        sheet = book.worksheet(info)
    except Exception:
        return []
    if (ref.r2 - ref.r1 + 1) * (ref.c2 - ref.c1 + 1) > 2_000:
        return []
    out = []
    for row in range(ref.r1, ref.r2 + 1):
        for col in range(ref.c1, ref.c2 + 1):
            cell = sheet.get(row, col)
            value = book.value(cell) if cell is not None else None
            if styles is not None:
                out.append(display(value, styles.code(cell.style) if cell else 'General', book.date1904) if value is not None else '')
            else:
                out.append(value)
    return out


def _range_code(book: Book, reference: str, styles: '_Styles') -> str | None:
    """Mã định dạng số của ô đầu một vùng, để nhãn biểu đồ hiện số như trong ô (1.500.000 ₫)."""
    found = refs.scan(reference or '').refs
    if len(found) != 1 or found[0].sheet is None or found[0].r1 is None or found[0].c1 is None:
        return None
    try:
        cell = book.worksheet(book.info(found[0].sheet)).get(found[0].r1, found[0].c1)
    except Exception:
        return None
    return styles.code(cell.style) if cell is not None else None


def _series_name(book: Book, series, styles: '_Styles') -> str:
    if series.name_ref:
        values = _range_values(book, series.name_ref, styles)
        if values and values[0]:
            return values[0]
    return series.name
