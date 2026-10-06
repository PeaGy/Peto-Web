"""Đọc công thức Word (OMML, chèn bằng Alt+=) thành LaTeX, để Peto thấy được đề có công thức.

Trước 6/10/2026 bộ đọc Word chỉ lấy ``w:t``, nên mọi công thức Word biến mất: "Rút gọn A = (x+1)/(x²−1)" đến tay Peto
chỉ còn "Rút gọn biểu thức sau:". Ở đây mỗi cấu trúc OMML (phân số, căn, mũ, tổng, ma trận…) thành lệnh LaTeX
tương ứng; LaTeX là cách viết công thức Peto đọc và viết quen nhất.
"""
from __future__ import annotations

import re
import unicodedata

from features.documents.math import symbols

MATH_NAMESPACES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://purl.oclc.org/ooxml/officeDocument/math",
}
WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_CONTROL_WORD_END = re.compile(r"\\[A-Za-z]+$")
# Cấu trúc cao hơn một dòng chữ: ngoặc quanh chúng cần \left…\right.
_TALL = {"f", "nary", "m", "eqArr", "rad", "limLow", "limUpp", "groupChr", "borderBox"}
_ACCENT_NAMES = {
    "̂": "hat", "̌": "check", "̃": "tilde", "́": "acute", "̀": "grave", "̇": "dot",
    "̈": "ddot", "⃛": "dddot", "̆": "breve", "̅": "bar", "̄": "bar", "¯": "bar",
    "⃗": "vec", "⃖": "overleftarrow", "⃡": "overleftrightarrow", "̊": "mathring",
    "^": "hat", "~": "tilde", "→": "vec", "˙": "dot", "¨": "ddot", "ˇ": "check", "˘": "breve",
}
_WIDE = {"hat": "widehat", "tilde": "widetilde", "bar": "overline", "vec": "overrightarrow", "check": "widecheck"}
_DELIMITER_LATEX = {
    "(": "(", ")": ")", "[": "[", "]": "]", "{": "\\{", "}": "\\}", "|": "|", "‖": "\\|", "⟨": "\\langle",
    "〈": "\\langle", "⟩": "\\rangle", "〉": "\\rangle", "⌊": "\\lfloor", "⌋": "\\rfloor", "⌈": "\\lceil",
    "⌉": "\\rceil", "⟦": "\\llbracket", "⟧": "\\rrbracket",
}
_MATRIX_ENVIRONMENTS = {"(": "pmatrix", "[": "bmatrix", "{": "Bmatrix", "|": "vmatrix", "‖": "Vmatrix"}
_STYLE_COMMANDS = {
    "bold": "mathbf", "bold-italic": "boldsymbol", "double-struck": "mathbb", "script": "mathcal",
    "bold-script": "mathcal", "fraktur": "mathfrak", "bold-fraktur": "mathfrak", "sans-serif": "mathsf",
    "sans-serif-bold": "mathsf", "sans-serif-italic": "mathsf", "sans-serif-bold-italic": "mathsf",
    "monospace": "mathtt",
}
_SCRIPT_COMMANDS = {"double-struck": "mathbb", "script": "mathcal", "fraktur": "mathfrak", "sans-serif": "mathsf",
                    "monospace": "mathtt"}
_INVISIBLE = {"⁡", "⁢", "⁣", "⁤", "​", "‌", "‍", "﻿"}
_SPACE_LATEX = {" ": "\\quad ", " ": "\\enspace ", " ": "\\;", " ": "\\:", " ": "\\:",
                " ": "\\,", " ": "\\,", " ": "\\,", " ": "~"}


def local(element) -> tuple[str, str]:
    """(namespace, tên cục bộ) của một thẻ XML."""
    tag = element.tag if isinstance(element.tag, str) else ""
    if tag.startswith("{"):
        namespace, _, name = tag[1:].partition("}")
        return namespace, name
    return "", tag


def math_name(element) -> str:
    namespace, name = local(element)
    return name if namespace in MATH_NAMESPACES else ""


def _word_name(element) -> str:
    namespace, name = local(element)
    return name if namespace in WORD_NAMESPACES else ""


def _child(element, name: str):
    return next((child for child in element if math_name(child) == name), None)


def _children(element, name: str) -> list:
    return [child for child in element if math_name(child) == name]


def _value(element) -> str | None:
    """Giá trị m:val của một thẻ thuộc tính; thẻ có mặt mà không có val nghĩa là bật."""
    for key, value in element.attrib.items():
        if key.endswith("}val") or key == "val":
            return value
    return ""


def _prop(element, properties: str, name: str) -> str | None:
    holder = _child(element, properties)
    if holder is None:
        return None
    found = _child(holder, name)
    return None if found is None else _value(found)


def _on(value: str | None) -> bool:
    return value is not None and value.lower() not in {"0", "off", "false"}


def join(parts: list[str]) -> str:
    """Nối các mảnh LaTeX; chèn khoảng trắng sau lệnh chữ (\\alpha x chứ không phải \\alphax)."""
    out = ""
    for part in parts:
        if not part:
            continue
        if _CONTROL_WORD_END.search(out) and part[0].isalpha():
            out += " "
        out += part
    return out


def _alphanumeric(char: str) -> tuple[str, str] | None:
    """Chữ trong khối Mathematical Alphanumeric Symbols: (kiểu, chữ gốc), ví dụ 𝑥 → ("italic", "x")."""
    code = ord(char)
    if char == "ℎ":
        return "italic", "h"
    if not 0x1D400 <= code <= 0x1D7FF:
        return None
    try:
        name = unicodedata.name(char)
    except ValueError:
        return None
    match = re.fullmatch(r"MATHEMATICAL ((?:[A-Z-]+ )*?)(CAPITAL|SMALL|DIGIT) ([A-Z]+(?: SYMBOL)?)", name)
    if not match:
        return None
    style = match.group(1).strip().lower().replace(" ", "-") or "upright"
    kind, letter = match.group(2), match.group(3)
    if kind == "DIGIT":
        digits = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "SIX": "6",
                  "SEVEN": "7", "EIGHT": "8", "NINE": "9"}
        return style, digits.get(letter, "")
    if len(letter) == 1:
        return style, letter if kind == "CAPITAL" else letter.lower()
    greek = letter.lower().replace(" symbol", "")
    greek_name = greek.capitalize() if kind == "CAPITAL" else greek
    if greek_name in symbols.GREEK:
        return style, "\\" + greek_name
    return None


class _Writer:
    def __init__(self):
        self.array_depth = 0
        self.function_depth = 0

    def sequence(self, parent) -> str:
        return join([self.node(child) for child in parent])

    def node(self, element) -> str:
        name = math_name(element)
        if not name:
            word = _word_name(element)
            if word == "r":
                text = "".join(child.text or "" for child in element.iter() if _word_name(child) == "t")
                return "\\text{" + _text_mode(text) + "}" if text.strip() else ""
            return self.sequence(element) if len(element) else ""
        handler = getattr(self, "_" + name, None)
        if handler is not None:
            return handler(element)
        if name.endswith("Pr"):
            return ""
        return self.sequence(element)

    def part(self, element, name: str) -> str:
        found = _child(element, name)
        return "" if found is None else self.sequence(found)

    # ---- chữ ----
    def _r(self, element) -> str:
        properties = _child(element, "rPr")
        normal = properties is not None and _on(_prop(element, "rPr", "nor"))
        plain = (_prop(element, "rPr", "sty") or "") if properties is not None else ""
        script = (_prop(element, "rPr", "scr") or "") if properties is not None else ""
        align = properties is not None and _child(properties, "aln") is not None
        text = ""
        for child in element:
            child_name = math_name(child) or _word_name(child)
            if child_name == "t":
                text += child.text or ""
            elif child_name == "sym":
                code = next((value for key, value in child.attrib.items() if key.endswith("}char")), "")
                try:
                    text += symbols.symbol_font_char(int(code, 16))
                except ValueError:
                    pass
            elif child_name == "tab":
                text += " "
        if normal:
            body = "\\text{" + _text_mode(text) + "}" if text else ""
        elif self.function_depth and text.strip() in symbols.FUNCTIONS:
            body = "\\" + text.strip()
        elif self.function_depth and text.strip().isalpha() and len(text.strip()) > 1:
            body = "\\operatorname{" + text.strip() + "}"
        else:
            body = self.math_text(text)
            command = _SCRIPT_COMMANDS.get(script)
            if command is None and plain in {"b", "bi"}:
                command = "mathbf" if plain == "b" else "boldsymbol"
            elif command is None and plain == "p" and any(char.isalpha() for char in text):
                command = "mathrm"
            if command and body:
                body = "\\" + command + "{" + body + "}"
        return ("&" if align else "") + body

    def math_text(self, text: str) -> str:
        out: list[str] = []
        index = 0
        while index < len(text):
            char = text[index]
            following = text[index + 1] if index + 1 < len(text) else ""
            accent = _ACCENT_NAMES.get(following) if following and unicodedata.combining(following) else None
            if accent:
                out.append("\\" + accent + "{" + self.char(char) + "}")
                index += 2
                continue
            out.append(self.char(char))
            index += 1
        return join(out)

    def char(self, char: str) -> str:
        if char in _INVISIBLE:
            return ""
        if char in _SPACE_LATEX:
            return _SPACE_LATEX[char]
        styled = _alphanumeric(char)
        if styled:
            style, base = styled
            command = _STYLE_COMMANDS.get(style)
            return "\\" + command + "{" + base + "}" if command else base
        if char in symbols.TO_LATEX:
            return "\\" + symbols.TO_LATEX[char]
        simple = {"−": "-", "∗": "*", "′": "'", "″": "''", "‴": "'''", "{": "\\{", "}": "\\}", "%": "\\%",
                  "#": "\\#", "$": "\\$", "_": "\\_", "\\": "\\backslash ", "~": "\\sim ", "^": "\\wedge "}
        if char in simple:
            return simple[char]
        if char == "&":
            return "&" if self.array_depth else "\\&"
        if unicodedata.combining(char):
            return ""
        return char

    # ---- cấu trúc ----
    def _f(self, element) -> str:
        kind = _prop(element, "fPr", "type") or "bar"
        numerator, denominator = self.part(element, "num"), self.part(element, "den")
        if kind in {"lin", "skw"}:
            return _group(numerator) + "/" + _group(denominator)
        if kind == "noBar":
            return "\\genfrac{}{}{0pt}{}{" + numerator + "}{" + denominator + "}"
        return "\\frac{" + numerator + "}{" + denominator + "}"

    def _scripted(self, element) -> str:
        base = _child(element, "e")
        text = "" if base is None else self.sequence(base)
        if base is not None and _single_structure(base):
            return text
        return text if _single_token(text) else "{" + text + "}"

    def _sSup(self, element) -> str:
        return self._scripted(element) + "^{" + self.part(element, "sup") + "}"

    def _sSub(self, element) -> str:
        return self._scripted(element) + "_{" + self.part(element, "sub") + "}"

    def _sSubSup(self, element) -> str:
        return self._scripted(element) + "_{" + self.part(element, "sub") + "}^{" + self.part(element, "sup") + "}"

    def _sPre(self, element) -> str:
        return "{}_{" + self.part(element, "sub") + "}^{" + self.part(element, "sup") + "}" + self._scripted(element)

    def _rad(self, element) -> str:
        degree = self.part(element, "deg")
        body = self.part(element, "e")
        if _on(_prop(element, "radPr", "degHide")) or not degree.strip():
            return "\\sqrt{" + body + "}"
        return "\\sqrt[" + degree + "]{" + body + "}"

    def _d(self, element) -> str:
        begin = _prop(element, "dPr", "begChr")
        end = _prop(element, "dPr", "endChr")
        separator = _prop(element, "dPr", "sepChr")
        begin = "(" if begin is None else begin
        end = ")" if end is None else end
        separator = "|" if separator is None else separator
        items = _children(element, "e")
        only = _only_structure(items[0]) if len(items) == 1 else None
        if only is not None and math_name(only) == "eqArr" and begin == "{" and not end:
            self.array_depth += 1
            rows = [self.sequence(row) for row in _children(only, "e")]
            self.array_depth -= 1
            return "\\begin{cases} " + " \\\\ ".join(rows) + " \\end{cases}"
        if only is not None and math_name(only) == "m" and begin in _MATRIX_ENVIRONMENTS:
            return self._matrix(only, _MATRIX_ENVIRONMENTS[begin])
        if only is not None and math_name(only) == "f" and begin == "(" and end == ")" \
                and _prop(only, "fPr", "type") == "noBar":
            return "\\binom{" + self.part(only, "num") + "}{" + self.part(only, "den") + "}"
        between = " \\mid " if separator == "|" else (separator if separator in {",", ";"} else
                                                      _DELIMITER_LATEX.get(separator, separator))
        inner = between.join(self.sequence(item) for item in items)
        tall = any(math_name(node) in _TALL for item in items for node in item.iter())
        left, right = _DELIMITER_LATEX.get(begin, begin), _DELIMITER_LATEX.get(end, end)
        if tall:
            return "\\left" + (left or ".") + " " + inner + " \\right" + (right or ".")
        return left + inner + right

    def _nary(self, element) -> str:
        char = _prop(element, "naryPr", "chr") or "∫"
        name = symbols.TO_LATEX.get(char)
        out = "\\" + name if name in symbols.BIG else char
        if not _on(_prop(element, "naryPr", "subHide")):
            lower = self.part(element, "sub")
            if lower:
                out += "_{" + lower + "}"
        if not _on(_prop(element, "naryPr", "supHide")):
            upper = self.part(element, "sup")
            if upper:
                out += "^{" + upper + "}"
        body = self.part(element, "e")
        return out + (" " + body if body else "")

    def _func(self, element) -> str:
        self.function_depth += 1
        name = self.part(element, "fName")
        self.function_depth -= 1
        argument = self.part(element, "e")
        return join([name, " " + argument if argument else ""])

    def _limLow(self, element) -> str:
        base, limit = self.part(element, "e"), self.part(element, "lim")
        if re.fullmatch(r"\\(?:lim|liminf|limsup|max|min|sup|inf|det|gcd|Pr|argmax|argmin)|lim|max|min", base.strip()):
            command = base.strip() if base.strip().startswith("\\") else "\\" + base.strip()
            return command + "_{" + limit + "}"
        return "\\underset{" + limit + "}{" + base + "}"

    def _limUpp(self, element) -> str:
        return "\\overset{" + self.part(element, "lim") + "}{" + self.part(element, "e") + "}"

    def _acc(self, element) -> str:
        char = _prop(element, "accPr", "chr")
        name = _ACCENT_NAMES.get("̂" if char is None else char, "hat")
        body = self.part(element, "e")
        if not _single_token(body) and name in _WIDE:
            name = _WIDE[name]
        return "\\" + name + "{" + body + "}"

    def _bar(self, element) -> str:
        top = (_prop(element, "barPr", "pos") or "bot") == "top"
        return ("\\overline{" if top else "\\underline{") + self.part(element, "e") + "}"

    def _groupChr(self, element) -> str:
        char = _prop(element, "groupChrPr", "chr") or "⏟"
        top = (_prop(element, "groupChrPr", "pos") or "bot") == "top"
        body = self.part(element, "e")
        if char == "⏟":
            return "\\underbrace{" + body + "}"
        if char == "⏞":
            return "\\overbrace{" + body + "}"
        mark = self.math_text(char)
        return ("\\overset{" if top else "\\underset{") + mark + "}{" + body + "}"

    def _box(self, element) -> str:
        return self.part(element, "e")

    def _borderBox(self, element) -> str:
        return "\\boxed{" + self.part(element, "e") + "}"

    def _phant(self, element) -> str:
        shown = _prop(element, "phantPr", "show")
        return "" if shown is not None and not _on(shown) else self.part(element, "e")

    def _m(self, element) -> str:
        return self._matrix(element, "matrix")

    def _matrix(self, element, environment: str) -> str:
        self.array_depth += 1
        rows = [" & ".join(self.sequence(cell) for cell in _children(row, "e")) for row in _children(element, "mr")]
        self.array_depth -= 1
        return "\\begin{" + environment + "} " + " \\\\ ".join(rows) + " \\end{" + environment + "}"

    def _eqArr(self, element) -> str:
        self.array_depth += 1
        rows = [self.sequence(row) for row in _children(element, "e")]
        self.array_depth -= 1
        environment = "aligned" if any("&" in row for row in rows) else "gathered"
        return "\\begin{" + environment + "} " + " \\\\ ".join(rows) + " \\end{" + environment + "}"


def _text_mode(text: str) -> str:
    replaced = text.replace("\\", "\\textbackslash ").replace("{", "\\{").replace("}", "\\}")
    return re.sub(r"([%#$&_])", r"\\\1", replaced)


def _group(text: str) -> str:
    return text if _single_token(text) else "{" + text + "}"


def _single_token(text: str) -> bool:
    text = text.strip()
    return bool(re.fullmatch(r"\\[A-Za-z]+|\\.|[^\s\\{}]|\d+(?:[.,]\d+)?", text)) or (
        text.startswith("{") and _balanced_group(text))


def _balanced_group(text: str) -> bool:
    depth = 0
    for index, char in enumerate(text):
        if char == "{" and (index == 0 or text[index - 1] != "\\"):
            depth += 1
        elif char == "}" and text[index - 1] != "\\":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return False
    return depth == 0


def _only_structure(element):
    """Cấu trúc duy nhất trong một m:e (bỏ qua thẻ thuộc tính), hoặc None."""
    nodes = [child for child in element if not math_name(child).endswith("Pr")]
    return nodes[0] if len(nodes) == 1 and math_name(nodes[0]) not in {"", "r"} else None


def _single_structure(element) -> bool:
    return _only_structure(element) is not None


def omml_to_latex(element) -> str:
    """LaTeX của một m:oMath."""
    return _Writer().sequence(element).strip()


def math_paragraph(element) -> list[str]:
    """Các công thức của một m:oMathPara (mỗi công thức một dòng riêng)."""
    return [latex for latex in (omml_to_latex(child) for child in element if math_name(child) == "oMath") if latex]
