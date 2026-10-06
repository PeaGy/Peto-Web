"""Đọc phần thân tệp Word cho Peto: đoạn văn, bảng, công thức Word (thành LaTeX), số thứ tự Word tự đánh (a), b), 1.1…)
và chữ gõ bằng phông Symbol; hình, biểu đồ và công thức MathType được đánh dấu tại chỗ vì Peto không đọc được.

Chỉ đọc XML trong bộ nhớ, không chạy gì trong tệp. reader._docx lo phần giới hạn tệp nén rồi gọi read_body.
"""
from __future__ import annotations

import re

from defusedxml.ElementTree import fromstring

from features.documents.math import omml_in, symbols
from features.documents.math.omml_in import WORD_NAMESPACES, local

PICTURE_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/picture"
CHART_NAMESPACES = {"http://schemas.openxmlformats.org/drawingml/2006/chart",
                    "http://schemas.microsoft.com/office/drawing/2014/chartex"}
COMPATIBILITY_NAMESPACE = "http://schemas.openxmlformats.org/markup-compatibility/2006"
VML_NAMESPACE = "urn:schemas-microsoft-com:vml"
OFFICE_NAMESPACE = "urn:schemas-microsoft-com:office:office"
# Kiểu số Word dùng trong numbering.xml → cách viết số.
_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _word(element) -> str:
    namespace, name = local(element)
    return name if namespace in WORD_NAMESPACES else ""


def _attr(element, name: str) -> str | None:
    if element is None:
        return None
    for key, value in element.attrib.items():
        if key == name or key.endswith("}" + name):
            return value
    return None


def _find(element, name: str):
    if element is None:
        return None
    return next((child for child in element if _word(child) == name), None)


def _roman(number: int) -> str:
    out = ""
    for value, letters in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                           (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        count, number = divmod(number, value)
        out += letters * count
    return out


def format_number(number: int, kind: str) -> str:
    """Số thứ tự theo kiểu số của Word (numFmt)."""
    if kind in {"lowerLetter", "upperLetter"}:
        position = max(number, 1) - 1
        letter = _LETTERS[position % 26] * (position // 26 + 1)
        return letter.upper() if kind == "upperLetter" else letter
    if kind in {"lowerRoman", "upperRoman"}:
        roman = _roman(max(number, 1))
        return roman.lower() if kind == "lowerRoman" else roman
    if kind == "decimalZero":
        return f"{number:02d}"
    if kind == "decimalEnclosedCircle" and 1 <= number <= 20:
        return chr(0x2460 + number - 1)
    if kind == "none":
        return ""
    return str(number)


def _bullet(text: str) -> str:
    """Dấu đầu dòng: ký tự riêng của phông Symbol/Wingdings (U+F0xx) đọc thành •, chữ o của Courier New thành ◦."""
    if not text:
        return "•"
    if any(0xF000 <= ord(char) <= 0xF0FF for char in text):
        return "•"
    return {"o": "◦", "§": "▪", "Ø": "➢", "ü": "✓", "q": "❑", "v": "❖"}.get(text, text)


class Numbering:
    """Đánh số như Word: đếm theo định nghĩa danh sách (abstractNum), cấp con đếm lại khi cấp trên tăng, startOverride
    bắt đầu lại danh sách ở lần dùng đầu của w:num đó; số thứ tự có thể đến từ kiểu đoạn (Heading 1 có số)."""

    def __init__(self, numbering_root, styles_root):
        self.levels: dict[str, dict[int, dict]] = {}
        self.style_links: dict[str, str] = {}
        self.nums: dict[str, tuple[str, dict[int, int], dict[int, dict]]] = {}
        self.styles: dict[str, tuple[str | None, str | None, str | None]] = {}
        self.default_style: str | None = None
        self.counters: dict[str, list[int | None]] = {}
        self.started: set[str] = set()
        if numbering_root is not None:
            for node in numbering_root:
                if _word(node) == "abstractNum":
                    abstract = _attr(node, "abstractNumId") or ""
                    self.levels[abstract] = {int(_attr(level, "ilvl") or 0): self._level(level)
                                             for level in node if _word(level) == "lvl"}
                    link = _find(node, "numStyleLink")
                    if link is not None:
                        self.style_links[abstract] = _attr(link, "val") or ""
                elif _word(node) == "num":
                    num = _attr(node, "numId") or ""
                    abstract = _attr(_find(node, "abstractNumId"), "val") or ""
                    starts, replaced = {}, {}
                    for override in node:
                        if _word(override) != "lvlOverride":
                            continue
                        level = int(_attr(override, "ilvl") or 0)
                        start = _find(override, "startOverride")
                        if start is not None:
                            starts[level] = _int(_attr(start, "val"), 1)
                        full = _find(override, "lvl")
                        if full is not None:
                            replaced[level] = self._level(full)
                    self.nums[num] = (abstract, starts, replaced)
        if styles_root is not None:
            for style in styles_root:
                if _word(style) != "style" or _attr(style, "type") != "paragraph":
                    continue
                style_id = _attr(style, "styleId") or ""
                if _attr(style, "default") in {"1", "true", "on"}:
                    self.default_style = style_id
                numbering = _find(_find(style, "pPr"), "numPr")
                self.styles[style_id] = (_attr(_find(numbering, "numId"), "val"),
                                         _attr(_find(numbering, "ilvl"), "val"),
                                         _attr(_find(style, "basedOn"), "val"))

    @staticmethod
    def _level(node) -> dict:
        restart = _find(node, "lvlRestart")
        return {"start": _int(_attr(_find(node, "start"), "val"), 1),
                "format": _attr(_find(node, "numFmt"), "val") or "decimal",
                "text": _attr(_find(node, "lvlText"), "val"),
                "restart": None if restart is None else _int(_attr(restart, "val"), 0),
                "legal": _find(node, "isLgl") is not None}

    def _abstract(self, num: str) -> str | None:
        entry = self.nums.get(num)
        if entry is None:
            return None
        abstract = entry[0]
        # Danh sách định nghĩa qua kiểu đánh số (numStyleLink): theo kiểu đó tới w:num thật, một bước là đủ.
        if not self.levels.get(abstract) and abstract in self.style_links:
            linked = self.styles.get(self.style_links[abstract], (None, None, None))[0]
            if linked and linked in self.nums:
                return self.nums[linked][0]
        return abstract

    def _definition(self, num: str, level: int) -> dict | None:
        entry = self.nums.get(num)
        if entry and level in entry[2]:
            return entry[2][level]
        abstract = self._abstract(num)
        return self.levels.get(abstract or "", {}).get(level)

    def _style_numbering(self, style_id: str | None) -> tuple[str | None, str | None]:
        num = level = None
        seen = set()
        while style_id and style_id not in seen and len(seen) < 12:
            seen.add(style_id)
            style_num, style_level, based = self.styles.get(style_id, (None, None, None))
            num = num if num is not None else style_num
            level = level if level is not None else style_level
            style_id = based
        return num, level

    def label(self, paragraph) -> str:
        properties = _find(paragraph, "pPr")
        direct = _find(properties, "numPr")
        num = _attr(_find(direct, "numId"), "val")
        level_text = _attr(_find(direct, "ilvl"), "val")
        if num is None or level_text is None:
            style_id = _attr(_find(properties, "pStyle"), "val") or self.default_style
            style_num, style_level = self._style_numbering(style_id)
            num = num if num is not None else style_num
            level_text = level_text if level_text is not None else style_level
        if not num or num == "0" or num not in self.nums:
            return ""
        level = min(max(_int(level_text, 0), 0), 8)
        abstract = self._abstract(num) or ""
        counters = self.counters.setdefault(abstract, [None] * 9)
        if num not in self.started:
            self.started.add(num)
            for overridden, start in self.nums[num][1].items():
                if 0 <= overridden <= 8:
                    counters[overridden] = start - 1
                    for deeper in range(overridden + 1, 9):
                        counters[deeper] = None
        definition = self._definition(num, level)
        if definition is None:
            return ""
        counters[level] = definition["start"] if counters[level] is None else counters[level] + 1
        for deeper in range(level + 1, 9):
            child = self._definition(num, deeper)
            restart = None if child is None else child["restart"]
            if restart is None or (restart != 0 and restart - 1 <= level):
                counters[deeper] = None
        if definition["format"] == "bullet":
            return _bullet(definition["text"] or "")
        text = definition["text"]
        if text is None:
            text = f"%{level + 1}."
        for position in range(9, 0, -1):
            marker = f"%{position}"
            if marker not in text:
                continue
            other = self._definition(num, position - 1) or definition
            value = counters[position - 1]
            if value is None:
                value = other["start"]
            kind = "decimal" if definition["legal"] and position - 1 != level else other["format"]
            text = text.replace(marker, format_number(value, kind))
        return text.strip()


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _symbol_run(run) -> bool:
    fonts = _find(_find(run, "rPr"), "rFonts")
    return fonts is not None and "Symbol" in {_attr(fonts, "ascii"), _attr(fonts, "hAnsi")}


def _symbol_text(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        base = code - 0xF000 if 0xF020 <= code <= 0xF0FF else code
        mapped = symbols.SYMBOL_FONT.get(base)
        out.append(mapped if mapped else (chr(base) if 0x20 <= base < 0x7F else char))
    return "".join(out)


class Body:
    """Đọc từng đoạn; đếm công thức, hình, biểu đồ và công thức MathType gặp trên đường."""

    def __init__(self, numbering: Numbering | None):
        self.numbering = numbering
        self.formulas = 0
        self.images = 0
        self.charts = 0
        self.mathtype = 0
        self.objects = 0

    def paragraph(self, element, numbered: bool = True) -> str:
        label = self.numbering.label(element) if numbered and self.numbering else ""
        parts: list[str] = []
        self._walk(element, parts, False)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(parts)).strip()
        return f"{label} {text}" if label and text else text

    def _walk(self, node, parts: list[str], symbol_font: bool) -> None:
        for child in node:
            namespace, name = local(child)
            if namespace in omml_in.MATH_NAMESPACES:
                if name == "oMathPara":
                    formulas = omml_in.math_paragraph(child)
                    self.formulas += len(formulas)
                    parts.extend(f"\n$${formula}$$\n" for formula in formulas)
                elif name == "oMath":
                    formula = omml_in.omml_to_latex(child)
                    if formula:
                        self.formulas += 1
                        parts.append(f"${formula}$")
                continue
            if namespace in WORD_NAMESPACES:
                if name == "r":
                    self._walk(child, parts, _symbol_run(child))
                elif name == "t":
                    text = child.text or ""
                    parts.append(_symbol_text(text) if symbol_font else text)
                elif name == "tab":
                    parts.append("\t")
                elif name in {"br", "cr"}:
                    parts.append("\n")
                elif name == "noBreakHyphen":
                    parts.append("-")
                elif name == "sym":
                    if (_attr(child, "font") or "").lower() == "symbol":
                        parts.append(symbols.symbol_font_char(_int_hex(_attr(child, "char"))))
                elif name == "object":
                    self._object(child, parts)
                elif name == "txbxContent":
                    for block in child:
                        if _word(block) == "p":
                            text = self.paragraph(block, numbered=False)
                            if text:
                                parts.append("\n" + text + "\n")
                        elif _word(block) == "tbl":
                            parts.append("\n" + "\n".join(self.table_rows(block)) + "\n")
                elif name not in {"del", "moveFrom", "rPr", "pPr", "instrText", "delText", "fldChar"}:
                    self._walk(child, parts, symbol_font)
                continue
            if namespace == COMPATIBILITY_NAMESPACE and name == "AlternateContent":
                # Bản Choice (DrawingML) và Fallback (VML) vẽ cùng một thứ: chỉ đọc một bản để không đếm hai lần.
                choice = next((item for item in child if local(item) == (COMPATIBILITY_NAMESPACE, "Choice")), None)
                self._walk(choice if choice is not None else child, parts, symbol_font)
            elif namespace == PICTURE_NAMESPACE and name == "pic":
                self.images += 1
                parts.append(f"[Hình {self.images} trong tệp]")
            elif namespace in CHART_NAMESPACES and name == "chart":
                self.charts += 1
                parts.append(f"[Biểu đồ {self.charts} trong tệp]")
            elif namespace == VML_NAMESPACE and name == "imagedata":
                self.images += 1
                parts.append(f"[Hình {self.images} trong tệp]")
            else:
                self._walk(child, parts, symbol_font)

    def _object(self, element, parts: list[str]) -> None:
        program = next((node.get("ProgID", "") for node in element.iter()
                        if local(node) == (OFFICE_NAMESPACE, "OLEObject")), "")
        if program.startswith("Equation") or "DSMT" in program or "MathType" in program:
            self.mathtype += 1
            parts.append(f"[Công thức MathType {self.mathtype}: Peto không đọc được]")
        else:
            self.objects += 1
            parts.append("[Đối tượng nhúng trong tệp]")

    def cell(self, element) -> str:
        texts = []
        for block in _blocks(element):
            if _word(block) == "p":
                texts.append(self.paragraph(block))
            else:
                texts.extend(self.table_rows(block))
        return " / ".join(texts)

    def table_rows(self, table) -> list[str]:
        rows = []
        for row in _rows(table):
            rows.append(" | ".join(self.cell(cell) for cell in row if _word(cell) == "tc"))
        return rows


def _int_hex(value: str | None) -> int:
    try:
        return int(value or "", 16)
    except ValueError:
        return 0


def _blocks(parent):
    """Đoạn và bảng theo thứ tự, kể cả trong vùng nội dung (sdt) và phần chèn của theo dõi thay đổi."""
    for child in parent:
        name = _word(child)
        if name in {"p", "tbl"}:
            yield child
        elif name in {"sdt", "sdtContent", "ins", "customXml", "moveTo", "smartTag"}:
            yield from _blocks(child)


def _rows(table):
    for child in table:
        name = _word(child)
        if name == "tr":
            yield child
        elif name in {"sdt", "sdtContent", "customXml"}:
            yield from _rows(child)


def parse(xml: bytes | None):
    return None if not xml else fromstring(xml, forbid_dtd=True)


def read_body(document_root, numbering_root, styles_root, max_chars: int) -> dict:
    """Chữ cho Peto: ``[Đoạn N]`` và ``[Bảng N]`` như trước, kèm số đếm công thức, hình, MathType."""
    body_element = next((child for child in document_root if _word(child) == "body"), None)
    if body_element is None:
        raise ValueError("Word thiếu phần nội dung")
    numbering = Numbering(numbering_root, styles_root) if numbering_root is not None else None
    body = Body(numbering)
    parts: list[str] = []
    used = paragraphs = tables = 0
    shortened = False
    for block in _blocks(body_element):
        if _word(block) == "p":
            value = body.paragraph(block)
            if not value:
                continue
            paragraphs += 1
            value = f"[Đoạn {paragraphs}]\n{value}\n\n"
        else:
            rows = body.table_rows(block)
            if not any(row.strip(" /|\t\n") for row in rows):
                continue
            tables += 1
            value = f"[Bảng {tables}]\n" + "\n".join(rows) + "\n\n"
        room = max_chars - used
        parts.append(value[:room])
        used += min(room, len(value))
        if len(value) > room:
            shortened = True
            break
    return {"text": "".join(parts).strip(), "shortened": shortened, "formulas": body.formulas,
            "images": body.images, "charts": body.charts, "mathtype": body.mathtype, "objects": body.objects}
