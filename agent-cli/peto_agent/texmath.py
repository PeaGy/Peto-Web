"""Công thức LaTeX trong câu trả lời, đổi sang ký hiệu Unicode để đọc được trong terminal.

Terminal không vẽ được LaTeX: "\\lnot A \\lor B" hiện nguyên văn, kèm cả "\\[", "\\begin{align*}" và dấu "&", rất khó
đọc. Chỉ phần nằm trong dấu phân cách công thức ($…$, $$…$$, \\(…\\), \\[…\\]) mới bị đổi; chữ thường và code giữ
nguyên. Đây chỉ là cách hiển thị: hội thoại gửi lại cho model vẫn là chữ gốc.
"""

from __future__ import annotations

import re

SYMBOLS = {
    # Logic
    "lnot": "¬", "neg": "¬", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨", "oplus": "⊕",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "gets": "←", "leftrightarrow": "↔", "mapsto": "↦",
    "Rightarrow": "⇒", "implies": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "iff": "⇔",
    "equiv": "≡", "top": "⊤", "bot": "⊥", "vdash": "⊢", "models": "⊨",
    "forall": "∀", "exists": "∃", "nexists": "∄", "therefore": "∴", "because": "∵",
    # Quan hệ
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠", "approx": "≈", "sim": "∼",
    "simeq": "≃", "cong": "≅", "propto": "∝", "ll": "≪", "gg": "≫", "perp": "⊥", "parallel": "∥",
    # Tập hợp
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅", "varnothing": "∅", "mid": "∣",
    "bigcup": "⋃", "bigcap": "⋂",
    # Phép tính và dấu
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "ast": "∗", "circ": "∘",
    "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮", "partial": "∂", "nabla": "∇",
    "infty": "∞", "ldots": "…", "dots": "…", "cdots": "⋯", "vdots": "⋮", "prime": "′", "degree": "°",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉",
    "lbrace": "{", "rbrace": "}", "vert": "|", "Vert": "‖",
    # Chữ Hy Lạp
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
    # Khoảng trắng
    "quad": "  ", "qquad": "    ",
}
# Lệnh chỉ đổi kiểu chữ: giữ nguyên phần chữ bên trong.
TEXT_COMMANDS = {"text", "textrm", "textbf", "textit", "mathrm", "mathbf", "mathit", "mathsf", "mathtt",
                 "operatorname", "mbox", "boldsymbol"}
# Lệnh đổi cỡ ngoặc: \left( chỉ là (.
SIZING = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr",
          "displaystyle", "textstyle", "limits", "nolimits"}
BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ"}
# Dấu đứng ngay trước toán hạng của nó, không cách ra.
PREFIX = {"lnot", "neg"}
SUPERSCRIPT = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
OVERLINE = "\u0305"

# \(…\) và \[…\] trên cùng một dòng, $$…$$ trên cùng một dòng, và $…$.
INLINE = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$|(?<![\\$\w])\$(?=\S)([^$\n]+?)(?<=\S)\$(?![\w$])")
CODE_SPAN = re.compile(r"(`+[^`]*`+)")


def _group(tex: str, index: int) -> tuple[str, int]:
    """Đối số của một lệnh bắt đầu ở ``index``: nội dung trong {…}, hoặc một ký tự hay một lệnh đứng một mình."""
    while index < len(tex) and tex[index] == " ":
        index += 1
    if index >= len(tex):
        return "", index
    if tex[index] == "{":
        depth, start = 0, index + 1
        while index < len(tex):
            char = tex[index]
            if char == "\\":
                index += 2
                continue
            depth += char == "{"
            depth -= char == "}"
            if depth == 0:
                return tex[start:index], index + 1
            index += 1
        return tex[start:], len(tex)
    if tex[index] == "\\":
        end = index + 1
        while end < len(tex) and tex[end].isalpha():
            end += 1
        return tex[index:max(end, index + 2)], max(end, index + 2)
    return tex[index], index + 1


def _wrap(text: str) -> str:
    """Tử hay mẫu nhiều ký tự thì thêm ngoặc: \\frac{a+1}{2} thành (a+1)/2."""
    return text if len(text) == 1 or text.isalnum() else f"({text})"


def _script(text: str, table: dict, mark: str) -> str:
    if text and all(ord(char) in table for char in text):
        return text.translate(table)
    return mark + (text if len(text) == 1 else f"({text})")


def convert(tex: str) -> str:
    """Một công thức LaTeX (không kèm dấu phân cách) thành chữ Unicode."""
    out: list[str] = []
    index = 0
    while index < len(tex):
        char = tex[index]
        if char == "\\":
            following = tex[index + 1:index + 2]
            if not following.isalpha():
                # \\ xuống dòng trong align (mỗi dòng đã in riêng), \, \; \! là khoảng trắng, \{ \} là ngoặc thật.
                out.append(following if following in "{}_$%&#|" else " " if following in ", ;:\\" else "")
                index += 2
                continue
            end = index + 1
            while end < len(tex) and tex[end].isalpha():
                end += 1
            name, index = tex[index + 1:end], end
            if name in ("begin", "end"):
                _, index = _group(tex, index)
            elif name in SIZING:
                if tex[index:index + 1] == ".":
                    index += 1
            elif name in TEXT_COMMANDS:
                body, index = _group(tex, index)
                out.append(body)
            elif name == "mathbb":
                body, index = _group(tex, index)
                out.append("".join(BLACKBOARD.get(letter, letter) for letter in body))
            elif name in ("frac", "dfrac", "tfrac"):
                top, index = _group(tex, index)
                bottom, index = _group(tex, index)
                out.append(f"{_wrap(convert(top))}/{_wrap(convert(bottom))}")
            elif name == "sqrt":
                body, index = _group(tex, index)
                inner = convert(body)
                out.append("√" + (inner if len(inner) == 1 else f"({inner})"))
            elif name in ("overline", "bar"):
                body, index = _group(tex, index)
                out.append("".join(letter + OVERLINE if not letter.isspace() else letter for letter in convert(body)))
            elif name in ("hat", "widehat", "tilde", "widetilde", "vec", "dot", "ddot"):
                body, index = _group(tex, index)
                out.append(convert(body))
            else:
                # Lệnh lạ như \sin, \log, \max: bỏ dấu gạch chéo là đọc được.
                out.append(SYMBOLS.get(name, name))
                if name in PREFIX:
                    # "\lnot A" là ¬A: dấu cách sau tên lệnh chỉ để kết thúc tên lệnh, không phải khoảng trắng.
                    while index < len(tex) and tex[index] == " ":
                        index += 1
            continue
        if char in "^_":
            body, index = _group(tex, index + 1)
            text = convert(body)
            out.append(_script(text, SUPERSCRIPT, "^") if char == "^" else _script(text, SUBSCRIPT, "_"))
            continue
        if char not in "{}&":
            out.append(char)
        index += 1
    return re.sub(r"(?<=\S) {2,}(?=\S)", " ", "".join(out)).strip()


def _looks_like_tex(body: str) -> bool:
    # $5 và $10 hay $HOME không phải công thức; chỉ đổi khi bên trong có lệnh, số mũ hay chỉ số.
    return bool(re.search(r"\\[A-Za-z]|[\^_{]", body))


def inline(line: str) -> str:
    """Đổi các công thức nằm gọn trong một dòng; phần trong dấu ` (code) giữ nguyên."""
    def replace(match: re.Match) -> str:
        body = next(group for group in match.groups() if group is not None)
        if match.group(4) is not None and not _looks_like_tex(body):
            return match.group(0)
        return convert(body)

    parts = CODE_SPAN.split(line)
    return "".join(part if index % 2 else INLINE.sub(replace, part) for index, part in enumerate(parts))


def display_line(line: str) -> str | None:
    """Dòng chỉ gồm một công thức hiển thị riêng (\\[…\\] hay $$…$$): trả phần đã đổi, không phải thì None."""
    match = re.fullmatch(r"\s*(?:\\\[(.+)\\\]|\$\$(.+)\$\$)\s*", line)
    if match is None:
        return None
    return convert(match.group(1) or match.group(2))
