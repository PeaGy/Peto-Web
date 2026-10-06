"""Dựng cây công thức (latex.py) thành công thức Word thật (OMML): mở tệp bằng Word là sửa được như công thức gõ bằng
Alt+=, chép sang tệp khác vẫn giữ nguyên.

Thứ tự thẻ con theo lược đồ OMML (m:nary: naryPr, sub, sup, e; m:rad: radPr, deg, e…), vì Word từ chối tệp sai thứ tự.
Căn thẳng hàng (aligned) và hệ (cases) dựng bằng ma trận m:m có căn cột, không dùng dấu & trong chữ.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from features.documents.math import latex as tree
from features.documents.math import symbols

MATH_FONT = "Cambria Math"
_SPACE_CHARS = [(2.0, "  "), (1.0, " "), (0.5, " "), (5 / 18, " "), (4 / 18, " "),
                (3 / 18, " "), (0.0, "")]
_ACCENT_CHARS = dict(symbols.ACCENTS)
_FONT_RUN = {
    "double-struck": '<m:scr m:val="double-struck"/><m:sty m:val="p"/>', "script": '<m:scr m:val="script"/>',
    "fraktur": '<m:scr m:val="fraktur"/>', "sans-serif": '<m:scr m:val="sans-serif"/><m:sty m:val="p"/>',
    "monospace": '<m:scr m:val="monospace"/><m:sty m:val="p"/>', "bold": '<m:sty m:val="b"/>',
    "bold-italic": '<m:sty m:val="bi"/>', "italic": '<m:sty m:val="i"/>', "upright": '<m:sty m:val="p"/>',
}
_MATRIX_DELIMITERS = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"), "vmatrix": ("|", "|"),
                      "Vmatrix": ("‖", "‖"), "cases": ("{", ""), "rcases": ("", "}")}


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


class _Writer:
    def __init__(self, text_font: str, display: bool):
        self.text_font = text_font
        self.display = display

    def run(self, text: str, math_props: str = "", text_font: bool = False, word_props: str = "") -> str:
        if not text:
            return ""
        font = self.text_font if text_font else MATH_FONT
        word = (f'<w:rPr><w:rFonts w:ascii="{_attr(font)}" w:hAnsi="{_attr(font)}" w:cs="{_attr(font)}"/>'
                f"{word_props}</w:rPr>")
        props = f"<m:rPr>{math_props}</m:rPr>" if math_props else ""
        return f'<m:r>{props}{word}<m:t xml:space="preserve">{escape(text)}</m:t></m:r>'

    def row(self, items: list) -> str:
        out: list[str] = []
        pending, pending_props = "", None
        index = 0
        while index < len(items):
            item = items[index]
            if isinstance(item, tree.Sym):
                props = _FONT_RUN.get(item.font or "", "")
                if pending and props != pending_props:
                    out.append(self.run(pending, pending_props or ""))
                    pending = ""
                pending += item.char
                pending_props = props
                index += 1
                continue
            if pending:
                out.append(self.run(pending, pending_props or ""))
                pending, pending_props = "", None
            if isinstance(item, tree.BigOp):
                # Phần toán tử tác động (m:e) là các mục sau nó tới dấu quan hệ kế tiếp, như Word tự gom khi gõ ∑.
                end = index + 1
                while end < len(items) and not _is_relation(items[end]):
                    end += 1
                out.append(self.big_operator(item, items[index + 1:end]))
                index = end
                continue
            if isinstance(item, tree.Func):
                end = _argument_end(items, index + 1)
                out.append(self.function(item, items[index + 1:end]))
                index = end
                continue
            out.append(self.node(item))
            index += 1
        if pending:
            out.append(self.run(pending, pending_props or ""))
        return "".join(out)

    def node(self, item) -> str:
        if isinstance(item, tree.Sym):
            return self.run(item.char, _FONT_RUN.get(item.font or "", ""))
        if isinstance(item, tree.Text):
            # m:nor (chữ thường) không đi cùng m:sty theo lược đồ: đậm, nghiêng đặt ở w:rPr.
            emphasis = "<w:b/>" if item.bold else "<w:i/>" if item.italic else ""
            return self.run(item.text, "<m:nor/>", text_font=True, word_props=emphasis)
        if isinstance(item, tree.Group):
            return self.row(item.body)
        if isinstance(item, tree.Space):
            return self.run(_space(item.em))
        if isinstance(item, tree.Style):
            return ""
        if isinstance(item, tree.Frac):
            fraction = (f'<m:f><m:fPr>{"" if item.bar else "<m:type m:val=" + chr(34) + "noBar" + chr(34) + "/>"}'
                        f'<m:ctrlPr/></m:fPr><m:num>{self.row(item.num)}</m:num><m:den>{self.row(item.den)}</m:den></m:f>')
            if item.left or item.right:
                return self.delimiters(item.left, item.right, [fraction])
            return fraction
        if isinstance(item, tree.Sqrt):
            if item.index:
                return f"<m:rad><m:radPr><m:ctrlPr/></m:radPr><m:deg>{self.row(item.index)}</m:deg><m:e>{self.row(item.body)}</m:e></m:rad>"
            return (f'<m:rad><m:radPr><m:degHide m:val="1"/><m:ctrlPr/></m:radPr><m:deg/>'
                    f"<m:e>{self.row(item.body)}</m:e></m:rad>")
        if isinstance(item, tree.Scripts):
            # Dấu phẩy trên (f′): ký tự ′ của phông toán đã nằm cao sẵn, nên viết liền như Word chứ không làm mũ.
            primes, rest = split_primes(item.sup)
            base = self.base(item.base) + (self.run(primes) if primes else "")
            return self.scripts(base, item.sub, rest)
        if isinstance(item, tree.BigOp):
            return self.big_operator(item, [])
        if isinstance(item, tree.Func):
            return self.function(item, [])
        if isinstance(item, tree.Accent):
            return self.accent(item)
        if isinstance(item, tree.Delimited):
            return self.delimiters(item.left, item.right, [self.row(part) for part in item.parts],
                                   item.middles[0] if item.middles else None)
        if isinstance(item, tree.BigDelim):
            return self.run(item.char)
        if isinstance(item, tree.Matrix):
            return self.matrix(item)
        if isinstance(item, tree.Over):
            inner = self.row(item.base)
            if item.over:
                inner = f"<m:limUpp><m:limUppPr><m:ctrlPr/></m:limUppPr><m:e>{inner}</m:e><m:lim>{self.row(item.over)}</m:lim></m:limUpp>"
            if item.under:
                inner = f"<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr><m:e>{inner}</m:e><m:lim>{self.row(item.under)}</m:lim></m:limLow>"
            return inner
        if isinstance(item, tree.Boxed):
            return f"<m:borderBox><m:borderBoxPr><m:ctrlPr/></m:borderBoxPr><m:e>{self.row(item.body)}</m:e></m:borderBox>"
        if isinstance(item, tree.Phantom):
            flags = ('<m:show m:val="0"/>' + ("" if item.horizontal else '<m:zeroWid m:val="1"/>')
                     + ("" if item.vertical else '<m:zeroAsc m:val="1"/><m:zeroDesc m:val="1"/>'))
            return f"<m:phant><m:phantPr>{flags}<m:ctrlPr/></m:phantPr><m:e>{self.row(item.body)}</m:e></m:phant>"
        return ""

    def base(self, item) -> str:
        return "" if item is None else self.node(item)

    def scripts(self, base: str, sub: list | None, sup: list | None) -> str:
        if sub is not None and sup is not None:
            return (f"<m:sSubSup><m:sSubSupPr><m:ctrlPr/></m:sSubSupPr><m:e>{base}</m:e>"
                    f"<m:sub>{self.row(sub)}</m:sub><m:sup>{self.row(sup)}</m:sup></m:sSubSup>")
        if sup is not None:
            return f"<m:sSup><m:sSupPr><m:ctrlPr/></m:sSupPr><m:e>{base}</m:e><m:sup>{self.row(sup)}</m:sup></m:sSup>"
        if sub is not None:
            return f"<m:sSub><m:sSubPr><m:ctrlPr/></m:sSubPr><m:e>{base}</m:e><m:sub>{self.row(sub)}</m:sub></m:sSub>"
        return base

    def big_operator(self, item: tree.BigOp, operand: list) -> str:
        limits = item.limits if item.limits is not None else (item.default_limits and self.display)
        props = [f'<m:chr m:val="{_attr(item.char)}"/>', f'<m:limLoc m:val="{"undOvr" if limits else "subSup"}"/>']
        if not item.sub:
            props.append('<m:subHide m:val="1"/>')
        if not item.sup:
            props.append('<m:supHide m:val="1"/>')
        return (f'<m:nary><m:naryPr>{"".join(props)}<m:ctrlPr/></m:naryPr><m:sub>{self.row(item.sub or [])}</m:sub>'
                f"<m:sup>{self.row(item.sup or [])}</m:sup><m:e>{self.row(operand)}</m:e></m:nary>")

    def function(self, item: tree.Func, argument: list) -> str:
        name = self.run(symbols.FUNCTION_TEXT.get(item.name, item.name), '<m:sty m:val="p"/>')
        limits = item.limits if item.limits is not None else (item.default_limits and self.display)
        if item.sub is not None and limits and item.sup is None:
            name = (f"<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr><m:e>{name}</m:e>"
                    f"<m:lim>{self.row(item.sub)}</m:lim></m:limLow>")
        elif item.sub is not None or item.sup is not None:
            name = self.scripts(name, item.sub, item.sup)
        return f"<m:func><m:funcPr><m:ctrlPr/></m:funcPr><m:fName>{name}</m:fName><m:e>{self.row(argument)}</m:e></m:func>"

    def accent(self, item: tree.Accent) -> str:
        body = self.row(item.body)
        if item.kind == "overline":
            return f'<m:bar><m:barPr><m:pos m:val="top"/><m:ctrlPr/></m:barPr><m:e>{body}</m:e></m:bar>'
        if item.kind == "underline":
            return f'<m:bar><m:barPr><m:pos m:val="bot"/><m:ctrlPr/></m:barPr><m:e>{body}</m:e></m:bar>'
        if item.kind in {"overbrace", "underbrace", "overparen", "underparen"}:
            top = item.kind.startswith("over")
            char = {"overbrace": "⏞", "underbrace": "⏟", "overparen": "⏜", "underparen": "⏝"}[item.kind]
            group = (f'<m:groupChr><m:groupChrPr><m:chr m:val="{char}"/><m:pos m:val="{"top" if top else "bot"}"/>'
                     f'<m:vertJc m:val="{"bot" if top else "top"}"/><m:ctrlPr/></m:groupChrPr><m:e>{body}</m:e></m:groupChr>')
            if item.label:
                kind = "limUpp" if top else "limLow"
                group = (f"<m:{kind}><m:{kind}Pr><m:ctrlPr/></m:{kind}Pr><m:e>{group}</m:e>"
                         f"<m:lim>{self.row(item.label)}</m:lim></m:{kind}>")
            return group
        if item.kind in {"cancel", "bcancel", "xcancel", "sout"}:
            strikes = {"cancel": '<m:strikeBLTR m:val="1"/>', "bcancel": '<m:strikeTLBR m:val="1"/>',
                       "xcancel": '<m:strikeBLTR m:val="1"/><m:strikeTLBR m:val="1"/>',
                       "sout": '<m:strikeH m:val="1"/>'}[item.kind]
            return (f'<m:borderBox><m:borderBoxPr><m:hideTop m:val="1"/><m:hideBot m:val="1"/><m:hideLeft m:val="1"/>'
                    f'<m:hideRight m:val="1"/>{strikes}<m:ctrlPr/></m:borderBoxPr><m:e>{body}</m:e></m:borderBox>')
        char = _ACCENT_CHARS.get(item.kind, "̂")
        return f'<m:acc><m:accPr><m:chr m:val="{_attr(char)}"/><m:ctrlPr/></m:accPr><m:e>{body}</m:e></m:acc>'

    def delimiters(self, left: str, right: str, parts: list[str], middle: str | None = None) -> str:
        props = f'<m:begChr m:val="{_attr(left)}"/><m:endChr m:val="{_attr(right)}"/>'
        if middle is not None:
            props = f'<m:begChr m:val="{_attr(left)}"/><m:sepChr m:val="{_attr(middle)}"/><m:endChr m:val="{_attr(right)}"/>'
        cells = "".join(f"<m:e>{part}</m:e>" for part in parts)
        return f"<m:d><m:dPr>{props}<m:ctrlPr/></m:dPr>{cells}</m:d>"

    def matrix(self, item: tree.Matrix) -> str:
        if item.kind == "gathered":
            rows = "".join(f"<m:e>{self.row(_flatten(row))}</m:e>" for row in item.rows)
            return f"<m:eqArr><m:eqArrPr><m:ctrlPr/></m:eqArrPr>{rows}</m:eqArr>"
        width = max((len(row) for row in item.rows), default=1)
        if item.kind == "aligned":
            justify = ["right" if column % 2 == 0 else "left" for column in range(width)]
        elif item.kind in {"cases", "rcases"}:
            justify = ["left"] * width
        elif item.kind == "array" and item.align:
            names = {"l": "left", "c": "center", "r": "right"}
            justify = [names[item.align[column]] if column < len(item.align) else "center" for column in range(width)]
        else:
            justify = ["center"] * width
        columns = "".join(f'<m:mc><m:mcPr><m:count m:val="1"/><m:mcJc m:val="{value}"/></m:mcPr></m:mc>'
                          for value in justify)
        body = ""
        for row in item.rows:
            cells = list(row) + [[] for _ in range(width - len(row))]
            body += "<m:mr>" + "".join(f"<m:e>{self.row(cell)}</m:e>" for cell in cells) + "</m:mr>"
        matrix = f'<m:m><m:mPr><m:baseJc m:val="center"/><m:mcs>{columns}</m:mcs><m:ctrlPr/></m:mPr>{body}</m:m>'
        if item.kind in _MATRIX_DELIMITERS:
            left, right = _MATRIX_DELIMITERS[item.kind]
            return self.delimiters(left, right, [matrix])
        return matrix


def split_primes(sup: list | None) -> tuple[str, list | None]:
    """Tách các dấu ′ đứng đầu chỉ số trên: (chuỗi dấu ′, phần còn lại hoặc None)."""
    if not sup:
        return "", sup
    primes = ""
    index = 0
    while index < len(sup) and isinstance(sup[index], tree.Sym) and set(sup[index].char) == {"′"}:
        primes += sup[index].char
        index += 1
    rest = sup[index:]
    return primes, (rest if rest else None) if primes else sup


def _flatten(row: list) -> list:
    out = []
    for index, cell in enumerate(row):
        if index:
            out.append(tree.Space(1.0))
        out.extend(cell)
    return out


def _is_relation(item) -> bool:
    return (isinstance(item, tree.Sym) and item.cls == "rel") or (isinstance(item, tree.Over) and item.cls == "rel")


def _argument_end(items: list, start: int) -> int:
    """Hết phần đối số của hàm (sin x): mục kế tiếp; nếu là dấu ngoặc mở thì tới dấu ngoặc đóng tương ứng."""
    if start >= len(items):
        return start
    first = items[start]
    while isinstance(first, tree.Space) and start + 1 < len(items):
        start += 1
        first = items[start]
    if isinstance(first, tree.Sym) and first.cls == "open":
        depth = 0
        for index in range(start, len(items)):
            item = items[index]
            if isinstance(item, tree.Sym) and item.cls == "open":
                depth += 1
            elif isinstance(item, tree.Sym) and item.cls == "close":
                depth -= 1
                if depth == 0:
                    return index + 1
        return len(items)
    if isinstance(first, (tree.Func, tree.BigOp)):
        return _argument_end(items, start + 1)
    return start + 1


def _space(em: float) -> str:
    for width, chars in _SPACE_CHARS:
        if em >= width - 1e-6:
            return chars
    return ""


def to_omml(formula: tree.Formula, text_font: str = "Times New Roman") -> str:
    """Chuỗi XML m:oMath (trong dòng) hoặc m:oMathPara (dòng riêng, căn giữa) của một công thức."""
    writer = _Writer(text_font, formula.display)
    body = writer.row(formula.body)
    if formula.tag:
        body += writer.run("  (" + formula.tag + ")")
    if formula.display:
        return (f'<m:oMathPara><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
                f"<m:oMath>{body}</m:oMath></m:oMathPara>")
    return f"<m:oMath>{body}</m:oMath>"
