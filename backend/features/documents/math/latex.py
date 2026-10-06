"""Phân tích công thức LaTeX Peto viết trong tài liệu ($…$, $$…$$) thành cây cấu trúc.

Cây này là nguồn chung cho hai bản: công thức Word thật (omml_out) và bản vẽ trong PDF (layout). Chỉ nhận một tập
lệnh có sẵn trong bảng (symbols.py) và các cấu trúc dưới đây; lệnh lạ bị từ chối kèm lời dặn bằng tiếng Việt để
Peto sửa công thức rồi gọi lại công cụ, như công thức Excel ở create_spreadsheet. Không bao giờ chạy hay mở rộng macro.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from features.documents.math import symbols

MAX_FORMULA = 4000
MAX_NODES = 3000
MAX_DEPTH = 40


class MathError(ValueError):
    """Công thức không dựng được; lời báo đọc được cho người và cho Peto."""


# ---------- Cây ----------
@dataclass
class Node:
    pass


@dataclass
class Sym(Node):
    """Một ký hiệu: chữ, số, phép toán, ngoặc. ``font`` là kiểu chữ (\\mathbb…), None là mặc định của công thức."""
    char: str
    cls: str = "ord"
    font: str | None = None


@dataclass
class Text(Node):
    """Chữ thường trong công thức (\\text{nếu }), viết đứng bằng phông chữ của văn bản."""
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Group(Node):
    body: list
    cls: str = "ord"


@dataclass
class Frac(Node):
    num: list
    den: list
    bar: bool = True
    size: str = "auto"  # auto, display (\dfrac), text (\tfrac)
    left: str = ""
    right: str = ""


@dataclass
class Sqrt(Node):
    body: list
    index: list | None = None


@dataclass
class Scripts(Node):
    base: Node | None
    sub: list | None = None
    sup: list | None = None


@dataclass
class BigOp(Node):
    char: str
    limits: bool | None = None  # None: theo loại toán tử (∑ dưới/trên, ∫ bên phải)
    sub: list | None = None
    sup: list | None = None
    default_limits: bool = True


@dataclass
class Func(Node):
    name: str
    limits: bool | None = None
    sub: list | None = None
    sup: list | None = None
    default_limits: bool = False


@dataclass
class Accent(Node):
    """hat, bar, vec… (dấu trên một chữ), overline/underline, overbrace/underbrace kèm nhãn, overparen (cung)."""
    kind: str
    body: list
    label: list | None = None


@dataclass
class Delimited(Node):
    left: str
    right: str
    parts: list  # các khúc giữa \middle
    middles: list = field(default_factory=list)


@dataclass
class BigDelim(Node):
    char: str
    scale: float
    cls: str = "ord"


@dataclass
class Matrix(Node):
    rows: list  # rows[i][j] là một danh sách nút
    kind: str = "matrix"  # matrix, pmatrix…, cases, aligned, gathered, array
    align: str = ""  # căn từng cột: l, c, r
    small: bool = False


@dataclass
class Space(Node):
    em: float


@dataclass
class Over(Node):
    """Chữ đặt trên/dưới một ký hiệu: \\overset, \\underset, \\stackrel, \\xrightarrow."""
    base: list
    over: list | None = None
    under: list | None = None
    cls: str = "ord"


@dataclass
class Boxed(Node):
    body: list


@dataclass
class Phantom(Node):
    body: list
    horizontal: bool = True
    vertical: bool = True


@dataclass
class Style(Node):
    """\\displaystyle, \\textstyle…: áp cho phần còn lại của dòng."""
    name: str


@dataclass
class Formula:
    body: list
    display: bool = False
    tag: str = ""


# ---------- Tách token ----------
@dataclass
class _Token:
    kind: str  # cmd, char, open, close, sup, sub, amp, prime, space, end
    value: str
    position: int


def _tokens(source: str) -> list[_Token]:
    out: list[_Token] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char == "\\":
            if index + 1 >= length:
                raise MathError("Công thức kết thúc bằng dấu \\ thừa.")
            following = source[index + 1]
            if following.isalpha():
                end = index + 1
                while end < length and source[end].isalpha():
                    end += 1
                name = source[index + 1:end]
                # \operatorname* và \hspace* là một lệnh.
                if end < length and source[end] == "*" and name in {"operatorname", "hspace", "vspace", "tag"}:
                    name += "*"
                    end += 1
                out.append(_Token("cmd", name, index))
                index = end
            else:
                out.append(_Token("cmd", following, index))
                index += 2
            continue
        if char == "{":
            out.append(_Token("open", char, index))
        elif char == "}":
            out.append(_Token("close", char, index))
        elif char == "^":
            out.append(_Token("sup", char, index))
        elif char == "_":
            out.append(_Token("sub", char, index))
        elif char == "&":
            out.append(_Token("amp", char, index))
        elif char == "'":
            out.append(_Token("prime", char, index))
        elif char in " \t\n\r":
            out.append(_Token("space", char, index))
        elif char == "~":
            out.append(_Token("cmd", "nobreakspace", index))
        else:
            out.append(_Token("char", char, index))
        index += 1
    out.append(_Token("end", "", length))
    return out


# ---------- Phân tích ----------
_ENVIRONMENTS = {"matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "cases", "dcases",
                 "rcases", "aligned", "align", "align*", "alignat", "alignat*", "gathered", "gather", "gather*",
                 "split", "array", "eqnarray", "eqnarray*", "equation", "equation*", "subarray", "multline",
                 "multline*", "CD"}
_BIG_DELIMITERS = {"big": 1.2, "Big": 1.8, "bigg": 2.4, "Bigg": 3.0}
_NEGATIONS = {"=": "≠", "<": "≮", ">": "≯", "≤": "≰", "≥": "≱", "∈": "∉", "∋": "∌", "⊂": "⊄", "⊃": "⊅",
              "⊆": "⊈", "⊇": "⊉", "≡": "≢", "∼": "≁", "≈": "≉", "≅": "≇", "∃": "∄", "∣": "∤", "∥": "∦",
              "≃": "≄", "⊢": "⊬", "⊨": "⊭", "←": "↚", "→": "↛", "↔": "↮", "⇐": "⇍", "⇒": "⇏", "⇔": "⇎"}
_BIG_CHARS = {char: limits for char, limits in symbols.BIG.values()}


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = _tokens(source)
        self.index = 0
        self.nodes = 0
        self.depth = 0

    # -- tiện ích --
    def peek(self, skip_space: bool = True) -> _Token:
        index = self.index
        while skip_space and self.tokens[index].kind == "space":
            index += 1
        return self.tokens[index]

    def take(self, skip_space: bool = True) -> _Token:
        while skip_space and self.tokens[self.index].kind == "space":
            self.index += 1
        token = self.tokens[self.index]
        if token.kind != "end":
            self.index += 1
        return token

    def count(self, node: Node) -> Node:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise MathError("Công thức quá dài. Hãy tách thành nhiều công thức nhỏ.")
        return node

    def fail(self, message: str) -> MathError:
        return MathError(message)

    # -- dòng --
    def row(self, stops: set[str]) -> list:
        """Đọc tới khi gặp một trong ``stops`` (tên lệnh như "right", "end", "\\\\", hoặc "close", "amp", "]", "end")."""
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise self.fail("Công thức lồng nhau quá sâu.")
        items: list = []
        while True:
            token = self.peek()
            if token.kind == "end" and "end" not in stops:
                break
            if self._stops(token, stops):
                break
            atom = self.atom(items)
            if atom is None:
                continue
            atom = self.scripts(atom)
            items.append(atom)
        self.depth -= 1
        return items

    @staticmethod
    def _stops(token: _Token, stops: set[str]) -> bool:
        if token.kind in stops:
            return True
        if token.kind == "cmd" and token.value in stops:
            return True
        if token.kind == "char" and token.value in stops:
            return True
        return False

    def group_or_token(self) -> list:
        """Tham số của một lệnh: {nhóm} hoặc một token."""
        token = self.peek()
        if token.kind == "open":
            self.take()
            body = self.row({"close"})
            if self.take().kind != "close":
                raise self.fail("Thiếu dấu } đóng nhóm.")
            return body
        if token.kind in {"end", "close"}:
            raise self.fail("Lệnh thiếu tham số (cần {…} sau lệnh).")
        if token.kind in {"sup", "sub", "amp"}:
            raise self.fail(f'Không đặt "{token.value}" ngay sau một lệnh; bọc tham số trong {{…}}.')
        atom = self.atom([])
        return [] if atom is None else [atom]

    def raw_group(self) -> str:
        """Chữ thô trong {…} (cho \\text, \\begin{…}, phần căn cột của array)."""
        token = self.take()
        if token.kind != "open":
            if token.kind in {"char", "cmd"}:
                return token.value
            raise self.fail("Cần {…} sau lệnh.")
        start = token.position + 1
        depth = 1
        position = start
        while position < len(self.source):
            char = self.source[position]
            if char == "\\":
                position += 2
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            position += 1
        if depth:
            raise self.fail("Thiếu dấu } đóng nhóm.")
        text = self.source[start:position]
        while self.tokens[self.index].position <= position and self.tokens[self.index].kind != "end":
            self.index += 1
        return text

    def optional(self) -> list | None:
        """Tham số tùy chọn [..] (\\sqrt[3]{x})."""
        token = self.peek()
        if token.kind == "char" and token.value == "[":
            self.take()
            body = self.row({"]"})
            closing = self.take()
            if not (closing.kind == "char" and closing.value == "]"):
                raise self.fail("Thiếu dấu ] đóng tham số tùy chọn.")
            return body
        return None

    # -- chỉ số --
    def scripts(self, atom: Node) -> Node:
        sub = sup = None
        while True:
            token = self.peek(skip_space=False)
            if token.kind == "space":
                following = self.peek()
                if following.kind not in {"sup", "sub"}:
                    break
                token = following
            if token.kind == "prime":
                primes = ""
                while self.peek(skip_space=False).kind == "prime":
                    self.take(skip_space=False)
                    primes += "′"
                sup = (sup or []) + [Sym(primes, "ord")]
                continue
            if token.kind not in {"sup", "sub"}:
                break
            self.take()
            argument = self.group_or_token()
            if token.kind == "sup":
                if sup is not None and not all(isinstance(item, Sym) and item.char.startswith("′") for item in sup):
                    raise self.fail("Hai chỉ số trên liền nhau (x^a^b). Bọc lại bằng {…}, ví dụ x^{ab}.")
                sup = (sup or []) + argument
            else:
                if sub is not None:
                    raise self.fail("Hai chỉ số dưới liền nhau (x_a_b). Bọc lại bằng {…}, ví dụ x_{ab}.")
                sub = argument
        if sub is None and sup is None:
            return atom
        if isinstance(atom, (BigOp, Func)) and atom.sub is None and atom.sup is None:
            atom.sub, atom.sup = sub, sup
            return atom
        if isinstance(atom, Accent) and atom.kind in {"overbrace", "underbrace"} and atom.label is None:
            label = sup if atom.kind == "overbrace" else sub
            other = sub if atom.kind == "overbrace" else sup
            atom.label = label
            if other is None:
                return atom
            return self.count(Scripts(atom, sub if atom.kind == "overbrace" else None,
                                      sup if atom.kind == "underbrace" else None))
        return self.count(Scripts(atom, sub, sup))

    # -- nguyên tử --
    def atom(self, items: list) -> Node | None:
        token = self.take()
        kind, value = token.kind, token.value
        if kind == "char":
            if value in _BIG_CHARS:
                return self.count(BigOp(value, default_limits=_BIG_CHARS[value]))
            return self.count(_char(value))
        if kind == "open":
            body = self.row({"close"})
            if self.take().kind != "close":
                raise self.fail("Thiếu dấu } đóng nhóm.")
            return self.count(Group(body))
        if kind == "close":
            raise self.fail("Thừa dấu } không có dấu { mở.")
        if kind in {"sup", "sub"}:
            # Chỉ số không có gốc (^2 đứng đầu): gốc rỗng, như LaTeX.
            self.index -= 1
            return self.scripts(Group([]))
        if kind == "amp":
            raise self.fail("Dấu & chỉ dùng trong \\begin{aligned}, \\begin{cases}, ma trận hay bảng.")
        if kind == "prime":
            return self.count(Sym("′", "ord"))
        if kind == "cmd":
            return self.command(value, items)
        return None

    def command(self, name: str, items: list) -> Node | None:
        if name in symbols.SPACES:
            return self.count(Space(symbols.SPACES[name]))
        if name == "nobreakspace":
            return self.count(Space(1 / 3))
        if name in {"\\"}:
            raise self.fail("Xuống dòng \\\\ chỉ dùng trong \\begin{aligned}, \\begin{cases} hay ma trận.")
        if name in symbols.IGNORED:
            if name in {"limits", "nolimits"} and items and isinstance(items[-1], (BigOp, Func)):
                items[-1].limits = name == "limits"
            if name in {"displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle"}:
                return self.count(Style(name))
            return None
        if name in symbols.IGNORED_WITH_ARG:
            self.raw_group()
            if name == "color" and self.peek().kind == "open":
                return self.count(Group(self.group_or_token()))
            return None
        if name in {"textcolor", "colorbox"}:
            self.raw_group()
            return self.count(Group(self.group_or_token()))
        if name in {"tag", "tag*"}:
            raise _Tag(self.raw_group())
        found = symbols.symbol(name)
        if found:
            char, cls = found
            if name in {"{", "lbrace"}:
                cls = "open"
            elif name in {"}", "rbrace"}:
                cls = "close"
            return self.count(Sym(char, cls))
        if name in symbols.BIG:
            char, limits = symbols.BIG[name]
            return self.count(BigOp(char, default_limits=limits))
        if name in symbols.FUNCTIONS:
            return self.count(Func(name, default_limits=name in symbols.LIMIT_FUNCTIONS))
        if name in {"operatorname", "operatorname*"}:
            text = self.raw_group().strip()
            if not text:
                raise self.fail("\\operatorname cần tên hàm, ví dụ \\operatorname{tg}.")
            return self.count(Func(text, default_limits=name.endswith("*")))
        if name in {"bmod", "mod"}:
            return self.count(Group([Space(4 / 18 if name == "bmod" else 1), Text("mod"), Space(4 / 18)], "bin"))
        if name == "pmod":
            argument = self.group_or_token()
            return self.count(Group([Space(1), Text("(mod"), Space(1 / 3)] + argument + [Text(")")]))
        if name in {"lvert", "lVert", "langle", "lfloor", "lceil", "lgroup", "llbracket"}:
            return self.count(Sym(symbols.DELIMITERS["\\" + name], "open"))
        if name in {"rvert", "rVert", "rangle", "rfloor", "rceil", "rgroup", "rrbracket"}:
            return self.count(Sym(symbols.DELIMITERS["\\" + name], "close"))
        if name in symbols.ACCENTS:
            return self.count(Accent(name, self.group_or_token()))
        if name in {"overline", "underline", "overbrace", "underbrace", "overparen", "wideparen", "underparen",
                    "cancel", "bcancel", "xcancel", "sout"}:
            kind = "overparen" if name == "wideparen" else name
            return self.count(Accent(kind, self.group_or_token()))
        if name in {"frac", "dfrac", "tfrac", "cfrac"}:
            numerator = self.group_or_token()
            denominator = self.group_or_token()
            size = {"dfrac": "display", "cfrac": "display", "tfrac": "text"}.get(name, "auto")
            return self.count(Frac(numerator, denominator, size=size))
        if name in {"binom", "dbinom", "tbinom"}:
            top = self.group_or_token()
            bottom = self.group_or_token()
            size = {"dbinom": "display", "tbinom": "text"}.get(name, "auto")
            return self.count(Frac(top, bottom, bar=False, size=size, left="(", right=")"))
        if name == "genfrac":
            left = self.raw_group().strip()
            right = self.raw_group().strip()
            thickness = self.raw_group().strip()
            self.raw_group()
            top = self.group_or_token()
            bottom = self.group_or_token()
            return self.count(Frac(top, bottom, bar=not thickness.startswith("0"),
                                   left=symbols.DELIMITERS.get(left, left), right=symbols.DELIMITERS.get(right, right)))
        if name == "sqrt":
            index = self.optional()
            return self.count(Sqrt(self.group_or_token(), index))
        if name in symbols.FONT_COMMANDS:
            return self._styled(self.group_or_token(), symbols.FONT_COMMANDS[name])
        if name in symbols.TEXT_COMMANDS:
            text = _text_content(self.raw_group())
            return self.count(Text(text, bold=name == "textbf", italic=name == "textit"))
        if name == "left":
            return self.delimited()
        if name in {"right", "middle"}:
            raise self.fail(f"\\{name} không có \\left đi trước.")
        base = name.rstrip("lrm")
        if base in _BIG_DELIMITERS:
            delimiter = self.delimiter()
            cls = {"l": "open", "r": "close", "m": "rel"}.get(name[len(base):], "ord")
            return self.count(BigDelim(delimiter, _BIG_DELIMITERS[base], cls))
        if name == "begin":
            return self.environment()
        if name == "end":
            raise self.fail("\\end không có \\begin đi trước.")
        if name in {"overset", "underset", "stackrel"}:
            mark = self.group_or_token()
            base_row = self.group_or_token()
            cls = "rel" if name == "stackrel" or _is_rel(base_row) else "ord"
            if name == "underset":
                return self.count(Over(base_row, under=mark, cls=cls))
            return self.count(Over(base_row, over=mark, cls=cls))
        if name in {"xrightarrow", "xleftarrow", "xRightarrow", "xLeftarrow", "xleftrightarrow", "xLeftrightarrow",
                    "xmapsto"}:
            below = self.optional()
            above = self.group_or_token()
            arrow = {"xrightarrow": "→", "xleftarrow": "←", "xRightarrow": "⇒", "xLeftarrow": "⇐",
                     "xleftrightarrow": "↔", "xLeftrightarrow": "⇔", "xmapsto": "↦"}[name]
            return self.count(Over([Sym(arrow, "rel")], over=above or None, under=below, cls="rel"))
        if name == "boxed":
            return self.count(Boxed(self.group_or_token()))
        if name in {"phantom", "hphantom", "vphantom"}:
            return self.count(Phantom(self.group_or_token(), horizontal=name != "vphantom",
                                      vertical=name != "hphantom"))
        if name == "not":
            following = self.atom([])
            if isinstance(following, Sym):
                negated = _NEGATIONS.get(following.char)
                return self.count(Sym(negated or following.char + "̸", following.cls))
            raise self.fail("\\not chỉ đi trước một ký hiệu, ví dụ \\not\\in.")
        if name == "substack":
            lines = [line for line in self.raw_group().split("\\\\") if line.strip()]
            rows = [[_Parser(line).row(set())] for line in lines[:12]]
            return self.count(Matrix(rows, "gathered", small=True))
        if name in {"hfill", "hfil"}:
            return self.count(Space(1))
        raise self.fail(f"Lệnh \\{name} chưa hỗ trợ trong tài liệu. Hãy viết cách khác (ký hiệu Unicode hoặc lệnh LaTeX thông dụng).")

    def _styled(self, body: list, font: str) -> Node:
        restyled = []
        for item in body:
            if isinstance(item, Sym) and (item.char.isalnum() or font in {"bold", "bold-italic"}):
                restyled.append(Sym(item.char, item.cls, font))
            elif isinstance(item, Group):
                restyled.append(Group([self._styled([inner], font) for inner in item.body], item.cls))
            elif isinstance(item, Scripts) and isinstance(item.base, Sym):
                restyled.append(Scripts(Sym(item.base.char, item.base.cls, font), item.sub, item.sup))
            else:
                restyled.append(item)
        return self.count(Group(restyled))

    def delimiter(self) -> str:
        token = self.take()
        if token.kind == "char":
            if token.value in symbols.DELIMITERS:
                return symbols.DELIMITERS[token.value]
            raise self.fail(f'"{token.value}" không phải dấu ngoặc dùng được sau \\left, \\right hay \\big.')
        if token.kind == "cmd":
            key = "\\" + token.value
            if key in symbols.DELIMITERS:
                return symbols.DELIMITERS[key]
            raise self.fail(f"\\{token.value} không phải dấu ngoặc dùng được sau \\left, \\right hay \\big.")
        raise self.fail("Thiếu dấu ngoặc sau \\left, \\right hay \\big (dùng \\left. nếu không cần ngoặc).")

    def delimited(self) -> Node:
        left = self.delimiter()
        parts, middles = [], []
        current = self.row({"right", "middle"})
        while True:
            token = self.take()
            if token.kind == "cmd" and token.value == "middle":
                parts.append(current)
                middles.append(self.delimiter())
                current = self.row({"right", "middle"})
                continue
            if token.kind == "cmd" and token.value == "right":
                parts.append(current)
                right = self.delimiter()
                return self.count(Delimited(left, right, parts, middles))
            raise self.fail("\\left thiếu \\right đóng lại.")

    def environment(self) -> Node:
        name = self.raw_group().strip()
        if name not in _ENVIRONMENTS:
            raise self.fail(f"Môi trường \\begin{{{name}}} chưa hỗ trợ. Dùng aligned, cases, matrix, pmatrix, bmatrix, "
                            "vmatrix hay array.")
        align = ""
        if name in {"array", "subarray", "alignat", "alignat*"}:
            align = "".join(char for char in self.raw_group() if char in "lcr")
        rows = self.table(name)
        kind = {"align": "aligned", "align*": "aligned", "split": "aligned", "alignat": "aligned",
                "alignat*": "aligned", "eqnarray": "aligned", "eqnarray*": "aligned", "gather": "gathered",
                "gather*": "gathered", "multline": "gathered", "multline*": "gathered", "dcases": "cases",
                "smallmatrix": "matrix", "subarray": "array", "equation": "gathered",
                "equation*": "gathered", "CD": "matrix"}.get(name, name)
        return self.count(Matrix(rows, kind, align, small=name in {"smallmatrix", "subarray"}))

    def table(self, name: str) -> list:
        rows: list = [[]]
        while True:
            cell = self.row({"amp", "\\", "end", "cr"})
            rows[-1].append(cell)
            token = self.take()
            if token.kind == "amp":
                continue
            if token.kind == "cmd" and token.value in {"\\", "cr"}:
                self.optional()
                rows.append([])
                continue
            if token.kind == "cmd" and token.value == "end":
                closing = self.raw_group().strip()
                if closing != name:
                    raise self.fail(f"\\begin{{{name}}} lại đóng bằng \\end{{{closing}}}.")
                break
            raise self.fail(f"\\begin{{{name}}} thiếu \\end{{{name}}}.")
        while rows and all(not cell for cell in rows[-1]):
            rows.pop()
        if len(rows) > 60 or any(len(row) > 20 for row in rows):
            raise self.fail("Ma trận hay hệ quá lớn (tối đa 60 hàng, 20 cột).")
        return rows


class _Tag(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


def _char(char: str) -> Sym:
    if char in symbols.CHAR_CLASS:
        cls = symbols.CHAR_CLASS[char]
        shown = {"-": "−", "*": "∗", "·": "⋅"}.get(char, char)
        return Sym(shown, cls)
    if char == "|":
        return Sym("|", "ord")
    return Sym(char, "ord")


def _is_rel(row: list) -> bool:
    return len(row) == 1 and isinstance(row[0], Sym) and row[0].cls == "rel"


def _text_content(raw: str) -> str:
    """Chữ trong \\text{…}: bỏ dấu $ của công thức lồng và dấu \\ trước ký tự đặc biệt."""
    out = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            following = raw[index + 1]
            if following in "{}%$&#_ ":
                out.append(following)
                index += 2
                continue
            end = index + 1
            while end < len(raw) and raw[end].isalpha():
                end += 1
            word = raw[index + 1:end]
            out.append({"textbackslash": "\\", "quad": " ", "qquad": "  "}.get(word, ""))
            index = end
            continue
        if char not in "${}":
            out.append(char)
        index += 1
    return "".join(out)


def _split_top(source: str) -> list[str] | None:
    """Tách công thức nhiều dòng viết thẳng (a &= b \\\\ &= c) ở mức ngoài cùng; None nếu chỉ một dòng."""
    depth = 0
    lines, start, index = [], 0, 0
    environment_depth = 0
    while index < len(source):
        if source.startswith("\\begin", index):
            environment_depth += 1
        elif source.startswith("\\end", index):
            environment_depth -= 1
        char = source[index]
        if char == "\\" and index + 1 < len(source):
            if source[index + 1] == "\\" and depth == 0 and environment_depth == 0:
                lines.append(source[start:index])
                index += 2
                start = index
                continue
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if not lines:
        return None
    lines.append(source[start:])
    return [line for line in lines if line.strip()]


# Như tildeNegation của khung chat (frontend/src/shared/markdown/mathMarkdown.ts): sách toán rời rạc viết phủ định là ~p,
# nhưng trong LaTeX ~ là khoảng trắng, nên chỉ ~ đứng ở chỗ một toán hạng mới thành ∼.
_OPERAND_START = re.compile(r"(?:^|[(\[{]|\\[{(]|\{\\sim\}|\\(?:lor|land|vee|wedge|to|rightarrow|leftarrow|leftrightarrow"
                            r"|Rightarrow|Leftarrow|Leftrightarrow|iff|implies|equiv|neg|lnot|oplus))$")


def tilde_negation(tex: str) -> str:
    result = ""
    for index, char in enumerate(tex):
        following = tex[index + 1] if index + 1 < len(tex) else ""
        if (char == "~" and (index == 0 or tex[index - 1] != "\\") and re.match(r"[A-Za-z(\\~\[]", following)
                and _OPERAND_START.search(result.rstrip())):
            result += "{\\sim}"
            continue
        result += char
    return result


def parse(source: str, display: bool = False) -> Formula:
    """Cây của một công thức. Lỗi là MathError có lời báo tiếng Việt."""
    source = tilde_negation(source.strip())
    if not source:
        raise MathError("Công thức trống.")
    if len(source) > MAX_FORMULA:
        raise MathError("Công thức quá dài (tối đa 4.000 ký tự). Hãy tách thành nhiều công thức.")
    tag = ""
    lines = _split_top(source)
    if lines is not None:
        # Viết nhiều dòng không có môi trường: coi như aligned (có &) hoặc gathered.
        aligned = any("&" in line for line in lines)
        source = ("\\begin{aligned}" if aligned else "\\begin{gathered}") + "\\\\".join(lines) + \
                 ("\\end{aligned}" if aligned else "\\end{gathered}")
    parser = _Parser(source)
    try:
        body = parser.row(set())
    except _Tag as found:
        tag = found.text.strip()
        rest = source[:source.find("\\tag")] + source[source.find("}", source.find("\\tag")) + 1:]
        body = _Parser(rest).row(set())
    leftover = parser.peek()
    if leftover.kind not in {"end"} and not tag:
        raise MathError("Công thức có phần thừa không đọc được.")
    return Formula(body, display, tag)


def check(source: str, display: bool = False) -> None:
    parse(source, display)
