"""Dàn công thức (cây latex.py) thành hình vẽ vector cho bản PDF, bằng phông STIX Two Math (OFL, có sẵn trong
assets/fonts) theo quy tắc của TeX: cỡ chữ chỉ số, khoảng cách giữa các loại ký hiệu, vị trí phân số theo trục toán.

Mỗi Box có bề rộng, chiều cao trên đường chân chữ, độ sâu dưới đường chân chữ và danh sách lệnh vẽ tương đối với gốc
(mép trái, đường chân chữ). Hằng số đọc từ bảng MATH của phông (phần nghìn em). Ngoặc, căn và dấu lớn khi giãn được vẽ
bằng nét vector, vì ReportLab chỉ vẽ được ký tự có mã Unicode chứ không lấy được các cỡ biến thể trong phông.
"""
from __future__ import annotations

import struct
import threading
import unicodedata
from dataclasses import dataclass, field

from core.config import BASE_DIR
from features.documents.math import latex as tree
from features.documents.math.omml_out import split_primes

MATH_FONT = "PetoMath"
FONT_FILE = BASE_DIR / "assets" / "fonts" / "STIXTwoMath-Regular.ttf"
# Bảng MATH của STIX Two Math 2.13 (đọc một lần bằng cách giải mã bảng; đổi phông thì đọc lại).
C = {
    "scriptPercentScaleDown": 70, "scriptScriptPercentScaleDown": 55, "axisHeight": 258, "accentBaseHeight": 480,
    "subscriptShiftDown": 210, "subscriptTopMax": 368, "subscriptBaselineDropMin": 160, "superscriptShiftUp": 360,
    "superscriptBottomMin": 120, "superscriptBaselineDropMax": 230, "subSuperscriptGapMin": 150,
    "superscriptBottomMaxWithSubscript": 380, "spaceAfterScript": 40, "upperLimitGapMin": 135,
    "upperLimitBaselineRiseMin": 300, "lowerLimitGapMin": 135, "lowerLimitBaselineDropMin": 670,
    "stackTopShiftUp": 470, "stackTopDisplayStyleShiftUp": 780, "stackBottomShiftDown": 385,
    "stackBottomDisplayStyleShiftDown": 690, "stackGapMin": 150, "stackDisplayStyleGapMin": 300,
    "fractionNumeratorShiftUp": 585, "fractionNumeratorDisplayStyleShiftUp": 640,
    "fractionDenominatorShiftDown": 585, "fractionDenominatorDisplayStyleShiftDown": 640,
    "fractionNumeratorGapMin": 68, "fractionNumDisplayStyleGapMin": 150, "fractionRuleThickness": 68,
    "fractionDenominatorGapMin": 68, "fractionDenomDisplayStyleGapMin": 150, "overbarVerticalGap": 175,
    "overbarRuleThickness": 68, "overbarExtraAscender": 68, "underbarVerticalGap": 175, "underbarRuleThickness": 68,
    "underbarExtraDescender": 68, "radicalVerticalGap": 85, "radicalDisplayStyleVerticalGap": 170,
    "radicalRuleThickness": 68, "radicalExtraAscender": 78, "radicalKernBeforeDegree": 65,
    "radicalKernAfterDegree": -335, "radicalDegreeBottomRaisePercent": 55, "delimitedSubFormulaMinHeight": 1325,
    "displayOperatorMinHeight": 1800,
}
SCALE = {"D": 1.0, "T": 1.0, "S": C["scriptPercentScaleDown"] / 100, "SS": C["scriptScriptPercentScaleDown"] / 100}
_SUB_STYLE = {"D": "S", "T": "S", "S": "SS", "SS": "SS"}
_FRAC_STYLE = {"D": "T", "T": "S", "S": "SS", "SS": "SS"}
# Khoảng cách giữa hai loại ký hiệu (đơn vị 1/18 em) theo bảng của TeX; số âm chỉ áp ở cỡ D và T.
_SPACING = {
    ("ord", "op"): 3, ("ord", "bin"): -4, ("ord", "rel"): -5, ("ord", "inner"): -3,
    ("op", "ord"): 3, ("op", "op"): 3, ("op", "rel"): -5, ("op", "inner"): -3,
    ("bin", "ord"): -4, ("bin", "op"): -4, ("bin", "open"): -4, ("bin", "inner"): -4,
    ("rel", "ord"): -5, ("rel", "op"): -5, ("rel", "open"): -5, ("rel", "inner"): -5,
    ("close", "op"): 3, ("close", "bin"): -4, ("close", "rel"): -5, ("close", "inner"): -3,
    ("punct", "ord"): -3, ("punct", "op"): -3, ("punct", "rel"): -3, ("punct", "open"): -3,
    ("punct", "close"): -3, ("punct", "punct"): -3, ("punct", "inner"): -3,
    ("inner", "ord"): -3, ("inner", "op"): 3, ("inner", "bin"): -4, ("inner", "rel"): -5, ("inner", "open"): -3,
    ("inner", "punct"): -3, ("inner", "inner"): -3,
}
_INTEGRALS = set("∫∬∭∮∯∰∱∲∳")
_ACCENT_GLYPHS = {"hat": "ˆ", "check": "ˇ", "tilde": "˜", "acute": "´", "grave": "`", "dot": "˙", "ddot": "¨",
                  "breve": "˘", "bar": "¯", "mathring": "˚", "dddot": "⃛"}
_LETTERLIKE = {
    ("italic", "h"): "ℎ", ("double-struck", "C"): "ℂ", ("double-struck", "H"): "ℍ", ("double-struck", "N"): "ℕ",
    ("double-struck", "P"): "ℙ", ("double-struck", "Q"): "ℚ", ("double-struck", "R"): "ℝ",
    ("double-struck", "Z"): "ℤ", ("script", "B"): "ℬ", ("script", "E"): "ℰ", ("script", "F"): "ℱ",
    ("script", "H"): "ℋ", ("script", "I"): "ℐ", ("script", "L"): "ℒ", ("script", "M"): "ℳ", ("script", "R"): "ℛ",
    ("script", "e"): "ℯ", ("script", "g"): "ℊ", ("script", "o"): "ℴ", ("fraktur", "C"): "ℭ",
    ("fraktur", "H"): "ℌ", ("fraktur", "I"): "ℑ", ("fraktur", "R"): "ℜ", ("fraktur", "Z"): "ℨ",
}
_STYLE_NAMES = {"italic": "ITALIC", "bold": "BOLD", "bold-italic": "BOLD ITALIC", "double-struck": "DOUBLE-STRUCK",
                "script": "SCRIPT", "fraktur": "FRAKTUR", "sans-serif": "SANS-SERIF", "monospace": "MONOSPACE"}
_GREEK_NAMES = {"ϵ": "EPSILON SYMBOL", "ϑ": "THETA SYMBOL", "ϕ": "PHI SYMBOL", "ϖ": "PI SYMBOL", "ϱ": "RHO SYMBOL",
                "ϰ": "KAPPA SYMBOL"}
_DIGITS = "ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE".split()
_font_lock = threading.Lock()
_glyphs = None


@dataclass
class Box:
    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    ops: list = field(default_factory=list)
    italic: float = 0.0
    cls: str = "ord"
    single: bool = False  # một ký tự đơn (chỉ số đặt theo độ cao chuẩn, không theo đỉnh ký tự)

    def place(self, other: "Box", x: float, y: float) -> None:
        if other.ops:
            self.ops.append(("box", x, y, other))
        self.height = max(self.height, y + other.height)
        self.depth = max(self.depth, other.depth - y)


def styled(char: str, font: str | None) -> str:
    """Ký tự hiển thị theo kiểu chữ toán: chữ Latinh và chữ Hy Lạp thường mặc định nghiêng (khối Mathematical
    Alphanumeric Symbols), \\mathbb{R} thành ℝ…"""
    if len(char) != 1:
        return char
    style = "italic" if font is None else font
    if style == "upright":
        return char
    if style == "italic" and not (char.isascii() and char.isalpha()) and not _greek_small(char):
        return char
    if (style, char) in _LETTERLIKE:
        return _LETTERLIKE[(style, char)]
    try:
        if char.isascii() and char.isdigit():
            return unicodedata.lookup(f"MATHEMATICAL {_STYLE_NAMES[style]} DIGIT {_DIGITS[int(char)]}")
        if char.isascii() and char.isalpha():
            case = "CAPITAL" if char.isupper() else "SMALL"
            return unicodedata.lookup(f"MATHEMATICAL {_STYLE_NAMES[style]} {case} {char.upper()}")
        if "GREEK" in unicodedata.name(char, ""):
            name = _GREEK_NAMES.get(char)
            if name is None:
                parts = unicodedata.name(char).split()
                name = ("CAPITAL " if "CAPITAL" in parts else "SMALL ") + parts[-1]
            return unicodedata.lookup(f"MATHEMATICAL {_STYLE_NAMES[style]} {name}")
    except (KeyError, ValueError):
        pass
    return char


def _greek_small(char: str) -> bool:
    return "GREEK SMALL" in unicodedata.name(char, "") or char in _GREEK_NAMES


class Glyphs:
    """Bề rộng và khung chữ (bbox) từng ký tự của phông toán, đọc thẳng từ bảng glyf qua dữ liệu ReportLab đã nạp."""

    def __init__(self):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        with _font_lock:
            if MATH_FONT not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(MATH_FONT, str(FONT_FILE)))
        self.font = pdfmetrics.getFont(MATH_FONT)
        face = self.font.face
        self.cmap = face.charToGlyph
        try:
            self.glyf = face.get_table_pos("glyf")[0]
            self.locations = face.glyphPos
            self.data = face._ttf_data
        except Exception:
            self.glyf = None
        self.cache: dict[str, tuple[float, float, float, float, float]] = {}

    def has(self, text: str) -> bool:
        return all(ord(char) in self.cmap or unicodedata.combining(char) for char in text)

    def metrics(self, text: str) -> tuple[float, float, float, float, float]:
        """(bề rộng, x nhỏ nhất, y nhỏ nhất, x lớn nhất, y lớn nhất) theo em."""
        if text in self.cache:
            return self.cache[text]
        advance = self.font.stringWidth(text, 1.0)
        x_min = y_min = 0.0
        x_max = y_max = 0.0
        position = 0.0
        first = True
        for char in text:
            width = self.font.stringWidth(char, 1.0)
            box = self._bbox(char)
            if box is not None:
                left, bottom, right, top = box
                if first:
                    x_min, y_min, x_max, y_max = position + left, bottom, position + right, top
                    first = False
                else:
                    x_min, y_min = min(x_min, position + left), min(y_min, bottom)
                    x_max, y_max = max(x_max, position + right), max(y_max, top)
            position += width
        value = (advance, x_min, y_min, x_max, y_max)
        self.cache[text] = value
        return value

    def _bbox(self, char: str) -> tuple[float, float, float, float] | None:
        glyph = self.cmap.get(ord(char))
        if glyph is None or self.glyf is None:
            return None
        start = self.locations[glyph]
        if self.locations[glyph + 1] == start:
            return None
        offset = self.glyf + start
        _, left, bottom, right, top = struct.unpack(">hhhhh", self.data[offset:offset + 10])
        return left / 1000, bottom / 1000, right / 1000, top / 1000


def glyphs() -> Glyphs:
    global _glyphs
    if _glyphs is None:
        _glyphs = Glyphs()
    return _glyphs


@dataclass
class TextFonts:
    """Phông chữ của văn bản cho \\text{…} trong công thức (cùng phông với đoạn văn của tài liệu)."""
    regular: str
    bold: str
    italic: str


class Layout:
    def __init__(self, size: float, text_fonts: TextFonts):
        self.size = size
        self.text = text_fonts
        self.glyphs = glyphs()

    def em(self, style: str) -> float:
        return self.size * SCALE[style]

    def k(self, name: str, style: str) -> float:
        return C[name] / 1000 * self.em(style)

    # ---- dòng ----
    def row(self, items: list, style: str) -> Box:
        boxes: list[Box] = []
        current = style
        for index, item in enumerate(items):
            if isinstance(item, tree.Style):
                current = {"displaystyle": "D", "textstyle": "T", "scriptstyle": "S",
                           "scriptscriptstyle": "SS"}.get(item.name, current)
                continue
            boxes.append(self.node(item, current))
        return self.pack(boxes, current)

    def pack(self, boxes: list[Box], style: str) -> Box:
        classes = [box.cls for box in boxes]
        solid = [index for index, cls in enumerate(classes) if cls != "space"]
        # Dấu hai ngôi đứng đầu hay sau một phép toán thành dấu một ngôi (−x), như TeX.
        for position, index in enumerate(solid):
            if classes[index] != "bin":
                continue
            before = classes[solid[position - 1]] if position else None
            after = classes[solid[position + 1]] if position + 1 < len(solid) else None
            if before in {None, "bin", "op", "rel", "open", "punct"} or after in {None, "rel", "close", "punct"}:
                classes[index] = "ord"
        out = Box()
        x = 0.0
        previous = None
        mu = self.em(style) / 18
        for box, cls in zip(boxes, classes):
            if cls != "space" and previous is not None:
                space = _SPACING.get((previous, cls), 0)
                if space < 0 and style in {"S", "SS"}:
                    space = 0
                x += abs(space) * mu
            out.place(box, x, 0.0)
            x += box.width
            if cls != "space":
                previous = cls
        out.width = x
        out.italic = boxes[-1].italic if boxes else 0.0
        if len(boxes) == 1:
            out.cls = boxes[0].cls
            out.single = boxes[0].single
        return out

    # ---- nút ----
    def node(self, item, style: str) -> Box:
        if isinstance(item, tree.Sym):
            return self.symbol(item.char, style, item.font, item.cls)
        if isinstance(item, tree.Text):
            return self.words(item, style)
        if isinstance(item, tree.Group):
            box = self.row(item.body, style)
            box.cls = item.cls if item.cls != "ord" else ("ord" if not box.single else box.cls)
            if item.cls == "ord" and not box.single:
                box.cls = "ord"
            return box
        if isinstance(item, tree.Space):
            return Box(width=item.em * self.em(style), cls="space")
        if isinstance(item, tree.Frac):
            return self.fraction(item, style)
        if isinstance(item, tree.Sqrt):
            return self.radical(item, style)
        if isinstance(item, tree.Scripts):
            return self.scripts(item, style)
        if isinstance(item, tree.BigOp):
            return self.big_operator(item, style)
        if isinstance(item, tree.Func):
            return self.function(item, style)
        if isinstance(item, tree.Accent):
            return self.accent(item, style)
        if isinstance(item, tree.Delimited):
            return self.delimited(item, style)
        if isinstance(item, tree.BigDelim):
            box = self.delimiter(item.char, item.scale * 1.2 * self.em(style), style)
            box.cls = item.cls
            return box
        if isinstance(item, tree.Matrix):
            return self.matrix(item, style)
        if isinstance(item, tree.Over):
            return self.over(item, style)
        if isinstance(item, tree.Boxed):
            return self.boxed(item, style)
        if isinstance(item, tree.Phantom):
            inner = self.row(item.body, style)
            return Box(inner.width if item.horizontal else 0, inner.height if item.vertical else 0,
                       inner.depth if item.vertical else 0)
        return Box()

    def symbol(self, char: str, style: str, font: str | None = None, cls: str = "ord") -> Box:
        size = self.em(style)
        shown = styled(char, font)
        if not self.glyphs.has(shown):
            return self.plain(char, size, self.text.regular, cls)
        advance, x_min, y_min, x_max, y_max = self.glyphs.metrics(shown)
        box = Box(advance * size, max(y_max, 0) * size, max(-y_min, 0) * size,
                  [("text", 0.0, 0.0, MATH_FONT, size, shown)], cls=cls, single=len(char) == 1)
        if shown != char or font in {"italic", "bold-italic"}:
            box.italic = max(0.0, x_max - advance) * size
        return box

    def plain(self, text: str, size: float, font: str, cls: str = "ord") -> Box:
        from reportlab.pdfbase import pdfmetrics
        return Box(pdfmetrics.stringWidth(text, font, size), 0.75 * size, 0.22 * size,
                   [("text", 0.0, 0.0, font, size, text)], cls=cls)

    def words(self, item: tree.Text, style: str) -> Box:
        font = self.text.bold if item.bold else self.text.italic if item.italic else self.text.regular
        return self.plain(item.text, self.em(style), font)

    def upright(self, text: str, style: str) -> Box:
        size = self.em(style)
        if not self.glyphs.has(text):
            return self.plain(text, size, self.text.regular, "op")
        advance, _, y_min, _, y_max = self.glyphs.metrics(text)
        return Box(advance * size, max(y_max, 0) * size, max(-y_min, 0) * size,
                   [("text", 0.0, 0.0, MATH_FONT, size, text)], cls="op")

    # ---- phân số ----
    def fraction(self, item: tree.Frac, style: str) -> Box:
        display = (style == "D" and item.size != "text") or item.size == "display"
        outer = "D" if display else ("T" if style == "D" else style)
        inner = "T" if display else _FRAC_STYLE[outer]
        if item.size == "text" and style == "D":
            inner = "S"
        top = self.row(item.num, inner)
        bottom = self.row(item.den, inner)
        axis = self.k("axisHeight", outer)
        rule = self.k("fractionRuleThickness", outer)
        if item.bar:
            up = self.k("fractionNumeratorDisplayStyleShiftUp" if display else "fractionNumeratorShiftUp", outer)
            down = self.k("fractionDenominatorDisplayStyleShiftDown" if display else "fractionDenominatorShiftDown",
                          outer)
            gap_top = self.k("fractionNumDisplayStyleGapMin" if display else "fractionNumeratorGapMin", outer)
            gap_bottom = self.k("fractionDenomDisplayStyleGapMin" if display else "fractionDenominatorGapMin", outer)
            up = max(up, axis + rule / 2 + gap_top + top.depth)
            down = max(down, bottom.height - (axis - rule / 2 - gap_bottom))
        else:
            up = self.k("stackTopDisplayStyleShiftUp" if display else "stackTopShiftUp", outer)
            down = self.k("stackBottomDisplayStyleShiftDown" if display else "stackBottomShiftDown", outer)
            gap = self.k("stackDisplayStyleGapMin" if display else "stackGapMin", outer)
            clearance = (up - top.depth) - (bottom.height - down)
            if clearance < gap:
                up += (gap - clearance) / 2
                down += (gap - clearance) / 2
        pad = 0.12 * self.em(outer)
        width = max(top.width, bottom.width)
        box = Box(width + 2 * pad, cls="inner")
        box.place(top, pad + (width - top.width) / 2, up)
        box.place(bottom, pad + (width - bottom.width) / 2, -down)
        if item.bar:
            box.ops.append(("rule", pad, axis - rule / 2, width, rule))
        if item.left or item.right:
            return self.wrap(box, item.left, item.right, outer)
        return box

    # ---- căn ----
    def radical(self, item: tree.Sqrt, style: str) -> Box:
        body = self.row(item.body, style)
        size = self.em(style)
        rule = self.k("radicalRuleThickness", style)
        gap = self.k("radicalDisplayStyleVerticalGap" if style == "D" else "radicalVerticalGap", style)
        top = max(body.height, 0.45 * size) + gap + rule
        bottom = max(body.depth, 0.0)
        needed = top + bottom + 0.04 * size
        advance, _, y_min, x_max, y_max = self.glyphs.metrics("√")
        natural = (y_max - y_min) * size
        sign = Box(cls="ord")
        if needed <= natural * 1.6:
            scale = max(1.0, needed / natural)
            lift = top - y_max * size * scale
            glyph = Box(advance * size, y_max * size, -y_min * size, [("text", 0.0, 0.0, MATH_FONT, size, "√")])
            sign.ops.append(("scaled", 0.0, lift, 1.0, scale, glyph))
            right = x_max * size
            sign_depth = -(y_min * size * scale + lift)
        else:
            # Căn rất cao (ma trận dưới căn): vẽ dấu căn bằng nét.
            stroke = 0.06 * size
            right = 0.62 * size
            low = -bottom - 0.04 * size
            sign.ops.append(("path", [("m", 0.0, top * 0.42 + low * 0.58), ("l", 0.12 * size, top * 0.48 + low * 0.52),
                                      ("l", 0.33 * size, low), ("l", right, top - rule / 2)], False, stroke))
            sign_depth = -low
        box = Box(cls="ord")
        offset = 0.0
        if item.index:
            index = self.row(item.index, "SS")
            kern_before = self.k("radicalKernBeforeDegree", style)
            kern_after = self.k("radicalKernAfterDegree", style)
            raise_by = (top + sign_depth) * C["radicalDegreeBottomRaisePercent"] / 100 - sign_depth
            box.place(index, kern_before, raise_by + index.depth)
            offset = max(0.0, kern_before + index.width + kern_after)
        box.place(sign, offset, 0.0)
        box.depth = max(box.depth, sign_depth)
        pad = 0.06 * size
        box.ops.append(("rule", offset + right - rule * 0.3, top - rule, body.width + pad + rule * 0.3, rule))
        box.place(body, offset + right, 0.0)
        box.width = offset + right + body.width + pad
        box.height = max(box.height, top + self.k("radicalExtraAscender", style))
        return box

    # ---- chỉ số ----
    def attach(self, base: Box, sub: list | None, sup: list | None, style: str) -> Box:
        script_style = _SUB_STYLE[style]
        size = self.em(style)
        upper = self.row(sup, script_style) if sup else None
        lower = self.row(sub, script_style) if sub else None
        box = Box(cls=base.cls)
        box.place(base, 0.0, 0.0)
        width = base.width
        up = down = 0.0
        if upper is not None:
            up = self.k("superscriptShiftUp", style)
            if not base.single:
                up = max(up, base.height - self.k("superscriptBaselineDropMax", script_style))
            up = max(up, upper.depth + self.k("superscriptBottomMin", style))
        if lower is not None:
            down = self.k("subscriptShiftDown", style)
            if not base.single:
                down = max(down, base.depth + self.k("subscriptBaselineDropMin", script_style))
            down = max(down, lower.height - self.k("subscriptTopMax", style))
        if upper is not None and lower is not None:
            gap = (up - upper.depth) - (lower.height - down)
            minimum = self.k("subSuperscriptGapMin", style)
            if gap < minimum:
                down += minimum - gap
        after = self.k("spaceAfterScript", style)
        if upper is not None:
            box.place(upper, base.width + base.italic, up)
            width = max(width, base.width + base.italic + upper.width + after)
        if lower is not None:
            box.place(lower, base.width, -down)
            width = max(width, base.width + lower.width + after)
        box.width = width if (upper or lower) else base.width
        _ = size
        return box

    def scripts(self, item: tree.Scripts, style: str) -> Box:
        if isinstance(item.base, tree.Accent) and item.base.kind in {"overbrace", "underbrace"}:
            base = self.accent(item.base, style)
        else:
            base = self.node(item.base, style) if item.base is not None else Box(single=True)
        primes, rest = split_primes(item.sup)
        if primes:
            base = self.pack([base, self.symbol(primes, style)], style)
            base.single = True
        return self.attach(base, item.sub, rest, style)

    def limits(self, base: Box, sub: list | None, sup: list | None, style: str) -> Box:
        script_style = _SUB_STYLE[style]
        upper = self.row(sup, script_style) if sup else None
        lower = self.row(sub, script_style) if sub else None
        width = max(base.width, upper.width if upper else 0, lower.width if lower else 0)
        box = Box(width, cls=base.cls)
        box.place(base, (width - base.width) / 2, 0.0)
        if upper is not None:
            rise = max(self.k("upperLimitBaselineRiseMin", style) + base.height,
                       base.height + self.k("upperLimitGapMin", style) + upper.depth)
            box.place(upper, (width - upper.width) / 2, rise)
        if lower is not None:
            drop = max(self.k("lowerLimitBaselineDropMin", style) * 0.6 + base.depth,
                       base.depth + self.k("lowerLimitGapMin", style) + lower.height)
            box.place(lower, (width - lower.width) / 2, -drop)
        return box

    def big_operator(self, item: tree.BigOp, style: str) -> Box:
        size = self.em(style)
        display = style == "D"
        integral = item.char in _INTEGRALS
        use_limits = item.limits if item.limits is not None else (item.default_limits and display)
        scale = (2.0 if integral else 1.45) if display else (1.2 if integral else 1.0)
        advance, x_min, y_min, x_max, y_max = self.glyphs.metrics(item.char)
        glyph_size = size * scale
        axis = self.k("axisHeight", style)
        lift = axis - (y_max + y_min) / 2 * glyph_size
        operator = Box(advance * glyph_size, y_max * glyph_size + lift, -(y_min * glyph_size + lift),
                       [("text", 0.0, lift, MATH_FONT, glyph_size, item.char)], cls="op")
        operator.italic = max(0.0, x_max - advance) * glyph_size
        if not item.sub and not item.sup:
            return operator
        if use_limits:
            return self.limits(operator, item.sub, item.sup, style)
        box = self.attach(operator, item.sub, item.sup, style)
        if integral:
            box.width += 0.1 * size
        return box

    def function(self, item: tree.Func, style: str) -> Box:
        name = {"liminf": "lim inf", "limsup": "lim sup", "argmax": "arg max", "argmin": "arg min"}.get(item.name,
                                                                                                        item.name)
        base = self.upright(name, style)
        # Tên hàm coi như một ký hiệu: mũ của sin² và cos² cao bằng nhau như Word, không theo đỉnh chữ i.
        base.single = True
        use_limits = item.limits if item.limits is not None else (item.default_limits and style == "D")
        if item.sub is None and item.sup is None:
            return base
        if use_limits:
            return self.limits(base, item.sub, item.sup, style)
        box = self.attach(base, item.sub, item.sup, style)
        box.cls = "op"
        return box

    # ---- dấu trên chữ ----
    def accent(self, item: tree.Accent, style: str) -> Box:
        body = self.row(item.body, style)
        size = self.em(style)
        kind = item.kind
        box = Box(cls="ord")
        box.place(body, 0.0, 0.0)
        box.width = body.width
        if kind in {"overline", "underline"}:
            rule = self.k("overbarRuleThickness", style)
            gap = self.k("overbarVerticalGap", style)
            if kind == "overline":
                y = body.height + gap
                box.ops.append(("rule", 0.0, y, body.width, rule))
                box.height = y + rule + self.k("overbarExtraAscender", style)
            else:
                y = -body.depth - gap - rule
                box.ops.append(("rule", 0.0, y, body.width, rule))
                box.depth = -y + self.k("underbarExtraDescender", style)
            return box
        if kind in {"overbrace", "underbrace", "overparen", "underparen"}:
            over = kind.startswith("over")
            height = 0.36 * size if "brace" in kind else 0.2 * size
            gap = 0.08 * size
            y = body.height + gap if over else -body.depth - gap - height
            box.ops.append(_brace_path(0.0, y, body.width, height, size, over, "brace" in kind))
            if over:
                box.height = y + height
            else:
                box.depth = -y
            if item.label:
                label = self.row(item.label, _SUB_STYLE[style])
                if over:
                    box.place(label, (body.width - label.width) / 2, box.height + 0.06 * size + label.depth)
                else:
                    box.place(label, (body.width - label.width) / 2, -box.depth - 0.06 * size - label.height)
                box.width = max(box.width, label.width)
            return box
        if kind in {"cancel", "bcancel", "xcancel", "sout"}:
            stroke = 0.05 * size
            lines = []
            if kind in {"cancel", "xcancel"}:
                lines.append([("m", 0.0, -body.depth), ("l", body.width, body.height)])
            if kind in {"bcancel", "xcancel"}:
                lines.append([("m", 0.0, body.height), ("l", body.width, -body.depth)])
            if kind == "sout":
                axis = self.k("axisHeight", style)
                lines.append([("m", 0.0, axis), ("l", body.width, axis)])
            for line in lines:
                box.ops.append(("path", line, False, stroke))
            return box
        wide = kind in {"widehat", "widetilde", "widecheck", "overrightarrow", "overleftarrow",
                        "overleftrightarrow"} or (not body.single and kind in {"hat", "tilde", "vec", "check"})
        base_height = max(body.height, self.k("accentBaseHeight", style))
        if wide or kind == "vec":
            gap = 0.08 * size
            y = base_height + gap
            height = 0.22 * size if kind not in {"tilde", "widetilde"} else 0.16 * size
            mark = {"widehat": "hat", "widecheck": "check", "widetilde": "tilde", "overrightarrow": "vec",
                    "overleftarrow": "left", "overleftrightarrow": "both"}.get(kind, kind)
            skew = body.italic * 0.5 if body.single else 0.0
            width = max(body.width, 0.45 * size)
            start = (body.width - width) / 2 + skew
            box.ops.append(_wide_mark(mark, start, y, width, height, size))
            box.height = y + height
            return box
        glyph = _ACCENT_GLYPHS.get(kind, "ˆ")
        advance, x_min, y_min, x_max, y_max = self.glyphs.metrics(glyph)
        lift = max(0.0, body.height - self.k("accentBaseHeight", style))
        skew = body.italic * 0.6 if body.single else 0.0
        center = body.width / 2 + skew
        x = center - (x_min + x_max) / 2 * size
        box.ops.append(("text", x, lift, MATH_FONT, size, glyph))
        box.height = max(body.height, lift + y_max * size)
        return box

    # ---- ngoặc ----
    def delimiter(self, char: str, needed: float, style: str) -> Box:
        size = self.em(style)
        if not char:
            return Box(width=0.12 * size, cls="open")
        if self.glyphs.has(char):
            advance, x_min, y_min, x_max, y_max = self.glyphs.metrics(char)
            natural = (y_max - y_min) * size
            if needed <= natural * 1.08 or char not in _VECTOR_DELIMITERS:
                if needed > natural * 1.08:
                    scale = needed / natural
                    axis = self.k("axisHeight", style)
                    lift = axis - (y_max + y_min) / 2 * size * scale
                    glyph = Box(advance * size, y_max * size, -y_min * size, [("text", 0.0, 0.0, MATH_FONT, size, char)])
                    box = Box(advance * size, y_max * size * scale + lift, -(y_min * size * scale + lift))
                    box.ops.append(("scaled", 0.0, lift, 1.0, scale, glyph))
                    return box
                return Box(advance * size, y_max * size, -y_min * size,
                           [("text", 0.0, 0.0, MATH_FONT, size, char)])
        axis = self.k("axisHeight", style)
        top, bottom = axis + needed / 2, axis - needed / 2
        width, ops = _VECTOR_DELIMITERS[char](top, bottom, size)
        return Box(width, top, -bottom, ops)

    def wrap(self, inner: Box, left: str, right: str, style: str, middles: list | None = None) -> Box:
        axis = self.k("axisHeight", style)
        distance = max(inner.height - axis, inner.depth + axis)
        needed = max(2 * distance * 0.901, 2 * distance - 0.5 * self.em(style))
        boxes = [self.delimiter(left, needed, style)]
        boxes[0].cls = "open"
        boxes.append(inner)
        closing = self.delimiter(right, needed, style)
        closing.cls = "close"
        boxes.append(closing)
        box = self.pack(boxes, style)
        box.cls = "inner"
        return box

    def delimited(self, item: tree.Delimited, style: str) -> Box:
        parts = [self.row(part, style) for part in item.parts]
        inner_height = max((part.height for part in parts), default=0.0)
        inner_depth = max((part.depth for part in parts), default=0.0)
        axis = self.k("axisHeight", style)
        distance = max(inner_height - axis, inner_depth + axis)
        needed = max(2 * distance * 0.901, 2 * distance - 0.5 * self.em(style))
        pieces: list[Box] = []
        for index, part in enumerate(parts):
            if index:
                middle = self.delimiter(item.middles[index - 1], needed, style)
                middle.cls = "rel"
                pieces.append(middle)
            part.cls = "ord"
            pieces.append(part)
        inner = self.pack(pieces, style) if pieces else Box()
        return self.wrap(inner, item.left, item.right, style)

    # ---- ma trận, hệ, căn thẳng hàng ----
    def matrix(self, item: tree.Matrix, style: str) -> Box:
        size = self.em(style)
        if item.small:
            cell_style = "S" if style in {"D", "T"} else "SS"
        elif item.kind in {"aligned", "gathered"}:
            cell_style = style
        else:
            cell_style = "T" if style in {"D", "T"} else style
        width = max((len(row) for row in item.rows), default=0)
        cells: list[list[Box]] = []
        for row in item.rows:
            laid = []
            for column in range(width):
                content = row[column] if column < len(row) else []
                if item.kind == "aligned" and column % 2 == 1:
                    # Như amsmath: cột phải bắt đầu bằng "=" vẫn có khoảng cách của dấu quan hệ.
                    content = [tree.Group([])] + list(content)
                laid.append(self.row(content, cell_style))
            cells.append(laid)
        if item.kind == "aligned":
            justify = ["r" if column % 2 == 0 else "l" for column in range(width)]
        elif item.kind in {"cases", "rcases"}:
            justify = ["l"] * width
        elif item.kind == "array" and item.align:
            justify = [item.align[column] if column < len(item.align) else "c" for column in range(width)]
        else:
            justify = ["c"] * width
        columns = [max((row[column].width for row in cells), default=0.0) for column in range(width)]
        strut_height, strut_depth = 0.7 * self.em(cell_style), 0.3 * self.em(cell_style)
        heights = [max([strut_height] + [cell.height for cell in row]) for row in cells]
        depths = [max([strut_depth] + [cell.depth for cell in row]) for row in cells]
        row_gap = (0.25 if item.kind in {"aligned", "gathered"} else 0.18) * size
        if item.small:
            row_gap = 0.08 * size

        def gap_after(column: int) -> float:
            if item.kind == "aligned":
                return 0.0 if column % 2 == 0 else 1.5 * size
            if item.kind in {"cases", "rcases"}:
                return 1.0 * size
            return (0.5 if item.small else 0.8) * size

        total_height = sum(heights) + sum(depths) + row_gap * max(len(cells) - 1, 0)
        axis = self.k("axisHeight", style)
        box = Box(cls="inner")
        y_top = total_height / 2 + axis
        for row_index, row in enumerate(cells):
            baseline = y_top - heights[row_index]
            x = 0.0
            for column, cell in enumerate(row):
                slack = columns[column] - cell.width
                offset = 0.0 if justify[column] == "l" else slack if justify[column] == "r" else slack / 2
                box.place(cell, x + offset, baseline)
                x += columns[column] + (gap_after(column) if column < width - 1 else 0.0)
            y_top = baseline - depths[row_index] - row_gap
        box.width = sum(columns) + sum(gap_after(column) for column in range(width - 1))
        box.height = max(box.height, total_height / 2 + axis)
        box.depth = max(box.depth, total_height / 2 - axis)
        delimiters = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"), "vmatrix": ("|", "|"),
                      "Vmatrix": ("‖", "‖"), "cases": ("{", ""), "rcases": ("", "}")}
        if item.kind in delimiters:
            left, right = delimiters[item.kind]
            padded = Box(box.width + 0.1 * size, box.height, box.depth, [("box", 0.05 * size, 0.0, box)])
            return self.wrap(padded, left, right, style)
        return box

    def over(self, item: tree.Over, style: str) -> Box:
        size = self.em(style)
        script_style = _SUB_STYLE[style]
        upper = self.row(item.over, script_style) if item.over else None
        lower = self.row(item.under, script_style) if item.under else None
        arrow = (len(item.base) == 1 and isinstance(item.base[0], tree.Sym) and item.base[0].char in _ARROWS
                 and (upper is not None or lower is not None))
        if arrow:
            span = max(upper.width if upper else 0, lower.width if lower else 0) + 0.6 * size
            axis = self.k("axisHeight", style)
            base = Box(span, axis + 0.18 * size, -axis + 0.18 * size,
                       [_arrow_path(item.base[0].char, 0.0, axis, span, size)], cls="rel")
        else:
            base = self.row(item.base, style)
        box = Box(cls=item.cls)
        width = max(base.width, upper.width if upper else 0, lower.width if lower else 0)
        box.place(base, (width - base.width) / 2, 0.0)
        gap = 0.1 * size
        if upper is not None:
            box.place(upper, (width - upper.width) / 2, base.height + gap + upper.depth)
        if lower is not None:
            box.place(lower, (width - lower.width) / 2, -(base.depth + gap + lower.height))
        box.width = width
        return box

    def boxed(self, item: tree.Boxed, style: str) -> Box:
        body = self.row(item.body, style)
        size = self.em(style)
        pad = 0.25 * size
        stroke = 0.05 * size
        box = Box(body.width + 2 * pad, body.height + pad, body.depth + pad)
        box.ops.append(("frame", stroke / 2, -body.depth - pad + stroke / 2, body.width + 2 * pad - stroke,
                        body.height + body.depth + 2 * pad - stroke, stroke))
        box.ops.append(("box", pad, 0.0, body))
        return box


_ARROWS = set("→←↔⇒⇐⇔↦")


def _arrow_path(char: str, x: float, y: float, width: float, size: float) -> tuple:
    stroke = 0.05 * size
    head = 0.25 * size
    commands: list = []
    double = char in "⇒⇐⇔"
    offsets = (-0.07 * size, 0.07 * size) if double else (0.0,)
    for offset in offsets:
        commands += [("m", x, y + offset), ("l", x + width, y + offset)]
    if char in "→⇒↔⇔↦":
        commands += [("m", x + width - head, y + head * 0.55), ("l", x + width, y), ("l", x + width - head, y - head * 0.55)]
    if char in "←⇐↔⇔":
        commands += [("m", x + head, y + head * 0.55), ("l", x, y), ("l", x + head, y - head * 0.55)]
    if char == "↦":
        commands += [("m", x, y + head * 0.5), ("l", x, y - head * 0.5)]
    return ("path", commands, False, stroke)


def _wide_mark(kind: str, x: float, y: float, width: float, height: float, size: float) -> tuple:
    stroke = 0.045 * size
    if kind in {"hat", "check"}:
        top, bottom = (y + height, y) if kind == "hat" else (y, y + height)
        return ("path", [("m", x, bottom), ("l", x + width / 2, top), ("l", x + width, bottom)], False, stroke)
    if kind == "tilde":
        middle = y + height / 2
        return ("path", [("m", x, middle - height * 0.2),
                         ("c", x + width * 0.25, middle + height * 0.9, x + width * 0.5, middle - height * 0.6,
                          x + width * 0.75, middle + height * 0.3),
                         ("c", x + width * 0.85, middle + height * 0.6, x + width * 0.95, middle + height * 0.4,
                          x + width, middle + height * 0.25)], False, stroke)
    arrow = {"vec": "→", "left": "←", "both": "↔"}.get(kind, "→")
    return _arrow_path(arrow, x, y + height / 2, width, size * 0.75)


def _brace_path(x: float, y: float, width: float, height: float, size: float, over: bool, brace: bool) -> tuple:
    stroke = 0.05 * size
    sign = 1 if over else -1
    base = y if over else y + height
    tip = base + sign * height
    if not brace:
        return ("path", [("m", x, base), ("c", x + width * 0.2, tip, x + width * 0.8, tip, x + width, base)], False,
                stroke)
    middle = x + width / 2
    shoulder = base + sign * height * 0.5
    radius = min(height * 0.6, width * 0.12)
    return ("path", [("m", x, base), ("c", x, shoulder, x + radius, shoulder, x + radius * 1.5, shoulder),
                     ("l", middle - radius * 1.5, shoulder),
                     ("c", middle - radius * 0.5, shoulder, middle, shoulder, middle, tip),
                     ("c", middle, shoulder, middle + radius * 0.5, shoulder, middle + radius * 1.5, shoulder),
                     ("l", x + width - radius * 1.5, shoulder),
                     ("c", x + width - radius, shoulder, x + width, shoulder, x + width, base)], False, stroke)


def _paren(top: float, bottom: float, size: float, right: bool) -> tuple[float, list]:
    height = top - bottom
    width = min(0.35 * size + 0.04 * height, 0.8 * size)
    thick = min(0.07 * size + 0.012 * height, 0.13 * size)
    thin = 0.035 * size
    outer, inner = (0.08 * size, 0.08 * size + thick) if not right else (width - 0.08 * size, width - 0.08 * size - thick)
    end = width - 0.06 * size if not right else 0.06 * size
    middle = (top + bottom) / 2
    path = [("m", end, top),
            ("c", outer, top - height * 0.18, outer, bottom + height * 0.18, end, bottom),
            ("l", end + (thin if not right else -thin), bottom + thin),
            ("c", inner, bottom + height * 0.25, inner, top - height * 0.25, end + (thin if not right else -thin), top - thin),
            ("z",)]
    _ = middle
    return width, [("path", path, True, 0.0)]


def _bracket(top: float, bottom: float, size: float, right: bool, floor: bool = False, ceil: bool = False):
    width = 0.32 * size
    stem = 0.06 * size
    serif = 0.05 * size
    x = 0.08 * size if not right else width - 0.08 * size - stem
    ops = [("rule", x, bottom, stem, top - bottom)]
    arm_x = x if not right else 0.08 * size
    arm_width = width - 0.16 * size + (stem if not right else stem)
    if not floor:
        ops.append(("rule", arm_x, top - serif, arm_width, serif))
    if not ceil:
        ops.append(("rule", arm_x, bottom, arm_width, serif))
    return width, ops


def _brace(top: float, bottom: float, size: float, right: bool):
    height = top - bottom
    width = min(0.45 * size + 0.02 * height, 0.7 * size)
    stroke = min(0.06 * size + 0.006 * height, 0.1 * size)
    middle = (top + bottom) / 2
    x0, x1, x2 = (width * 0.75, width * 0.45, width * 0.1) if not right else (width * 0.25, width * 0.55, width * 0.9)
    path = [("m", x0, top),
            ("c", x1, top, x1, top - height * 0.05, x1, top - height * 0.12),
            ("l", x1, middle + height * 0.1),
            ("c", x1, middle + height * 0.02, x2 + (x1 - x2) * 0.4, middle, x2, middle),
            ("c", x2 + (x1 - x2) * 0.4, middle, x1, middle - height * 0.02, x1, middle - height * 0.1),
            ("l", x1, bottom + height * 0.12),
            ("c", x1, bottom + height * 0.05, x1, bottom, x0, bottom)]
    return width, [("path", path, False, stroke)]


def _bar(top: float, bottom: float, size: float, double: bool = False):
    stem = 0.05 * size
    if double:
        return 0.3 * size, [("rule", 0.08 * size, bottom, stem, top - bottom),
                            ("rule", 0.08 * size + 0.12 * size, bottom, stem, top - bottom)]
    return 0.2 * size, [("rule", 0.075 * size, bottom, stem, top - bottom)]


def _angle(top: float, bottom: float, size: float, right: bool):
    height = top - bottom
    width = min(0.3 * size + 0.08 * height, 0.6 * size)
    tip, back = (0.06 * size, width - 0.06 * size) if not right else (width - 0.06 * size, 0.06 * size)
    return width, [("path", [("m", back, top), ("l", tip, (top + bottom) / 2), ("l", back, bottom)], False, 0.05 * size)]


_VECTOR_DELIMITERS = {
    "(": lambda t, b, s: _paren(t, b, s, False), ")": lambda t, b, s: _paren(t, b, s, True),
    "[": lambda t, b, s: _bracket(t, b, s, False), "]": lambda t, b, s: _bracket(t, b, s, True),
    "⌊": lambda t, b, s: _bracket(t, b, s, False, floor=True), "⌋": lambda t, b, s: _bracket(t, b, s, True, floor=True),
    "⌈": lambda t, b, s: _bracket(t, b, s, False, ceil=True), "⌉": lambda t, b, s: _bracket(t, b, s, True, ceil=True),
    "{": lambda t, b, s: _brace(t, b, s, False), "}": lambda t, b, s: _brace(t, b, s, True),
    "|": lambda t, b, s: _bar(t, b, s), "‖": lambda t, b, s: _bar(t, b, s, True),
    "⟨": lambda t, b, s: _angle(t, b, s, False), "⟩": lambda t, b, s: _angle(t, b, s, True),
}


def layout(formula: tree.Formula, size: float, text_fonts: TextFonts) -> Box:
    engine = Layout(size, text_fonts)
    return engine.row(formula.body, "D" if formula.display else "T")


def draw(canvas, box: Box, x: float, y: float) -> None:
    """Vẽ Box với gốc (mép trái, đường chân chữ) tại (x, y), màu chữ hiện tại của canvas."""
    for op in box.ops:
        kind = op[0]
        if kind == "text":
            _, dx, dy, font, size, text = op
            canvas.setFont(font, size)
            canvas.drawString(x + dx, y + dy, text)
        elif kind == "rule":
            _, dx, dy, width, height = op
            canvas.rect(x + dx, y + dy, width, height, stroke=0, fill=1)
        elif kind == "frame":
            _, dx, dy, width, height, stroke = op
            canvas.setLineWidth(stroke)
            canvas.rect(x + dx, y + dy, width, height, stroke=1, fill=0)
        elif kind == "path":
            _, commands, fill, stroke = op
            path = canvas.beginPath()
            for command in commands:
                if command[0] == "m":
                    path.moveTo(x + command[1], y + command[2])
                elif command[0] == "l":
                    path.lineTo(x + command[1], y + command[2])
                elif command[0] == "c":
                    path.curveTo(x + command[1], y + command[2], x + command[3], y + command[4],
                                 x + command[5], y + command[6])
                elif command[0] == "z":
                    path.close()
            canvas.saveState()
            if stroke:
                canvas.setLineWidth(stroke)
                canvas.setLineCap(1)
                canvas.setLineJoin(1)
            canvas.drawPath(path, stroke=0 if fill else 1, fill=1 if fill else 0)
            canvas.restoreState()
        elif kind == "box":
            _, dx, dy, child = op
            draw(canvas, child, x + dx, y + dy)
        elif kind == "scaled":
            _, dx, dy, scale_x, scale_y, child = op
            canvas.saveState()
            canvas.translate(x + dx, y + dy)
            canvas.scale(scale_x, scale_y)
            draw(canvas, child, 0.0, 0.0)
            canvas.restoreState()
