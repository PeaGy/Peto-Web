"""Bảng ký hiệu dùng chung: lệnh LaTeX ↔ ký tự Unicode, kèm loại ký hiệu để giãn cách như TeX.

Loại ký hiệu: ``ord`` (chữ, số, ký hiệu thường), ``op`` (toán tử lớn như ∑ ∫), ``bin`` (phép toán hai ngôi),
``rel`` (quan hệ và mũi tên), ``open``/``close`` (ngoặc), ``punct`` (dấu câu).
"""
from __future__ import annotations

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "varkappa": "ϰ", "lambda": "λ",
    "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο", "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ",
    "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "ϕ", "varphi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω", "digamma": "ϝ",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ",
    "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

ORD = {
    "infty": "∞", "partial": "∂", "nabla": "∇", "forall": "∀", "exists": "∃", "nexists": "∄", "emptyset": "∅",
    "varnothing": "∅", "neg": "¬", "lnot": "¬", "angle": "∠", "measuredangle": "∡", "sphericalangle": "∢",
    "triangle": "△", "square": "□", "Box": "□", "blacksquare": "■", "Diamond": "◇", "lozenge": "◊",
    "prime": "′", "hbar": "ℏ", "hslash": "ℏ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "beth": "ℶ",
    "wp": "℘", "top": "⊤", "bot": "⊥", "degree": "°", "ldots": "…", "dots": "…", "dotsc": "…", "dotsb": "⋯",
    "cdots": "⋯", "vdots": "⋮", "ddots": "⋱", "checkmark": "✓", "clubsuit": "♣", "diamondsuit": "♢",
    "heartsuit": "♡", "spadesuit": "♠", "flat": "♭", "natural": "♮", "sharp": "♯", "surd": "√", "S": "§",
    "P": "¶", "dagger": "†", "ddagger": "‡", "imath": "ı", "jmath": "ȷ", "mho": "℧", "complement": "∁",
    "backprime": "‵", "infin": "∞", "backslash": "\\", "vert": "|", "Vert": "‖", "|": "‖",
    "%": "%", "#": "#", "&": "&", "$": "$", "_": "_", "{": "{", "}": "}", "lbrace": "{", "rbrace": "}",
    "copyright": "©", "pounds": "£", "euro": "€", "yen": "¥", "circledS": "Ⓢ", "Finv": "Ⅎ", "Game": "⅁",
    "eth": "ð",
}

BIN = {
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "⋅", "cdotp": "⋅", "ast": "∗", "star": "⋆",
    "circ": "∘", "bullet": "∙", "oplus": "⊕", "ominus": "⊖", "otimes": "⊗", "oslash": "⊘", "odot": "⊙",
    "cup": "∪", "cap": "∩", "sqcup": "⊔", "sqcap": "⊓", "vee": "∨", "lor": "∨", "wedge": "∧", "land": "∧",
    "setminus": "∖", "smallsetminus": "∖", "wr": "≀", "diamond": "⋄", "bigtriangleup": "△",
    "bigtriangledown": "▽", "triangleleft": "◃", "triangleright": "▹", "lhd": "⊲", "rhd": "⊳",
    "unlhd": "⊴", "unrhd": "⊵", "uplus": "⊎", "amalg": "⨿", "barwedge": "⊼", "veebar": "⊻",
    "boxplus": "⊞", "boxminus": "⊟", "boxtimes": "⊠", "boxdot": "⊡", "divideontimes": "⋇", "ltimes": "⋉",
    "rtimes": "⋊", "dotplus": "∔", "intercal": "⊺", "centerdot": "⋅", "circledast": "⊛",
    "circledcirc": "⊚", "circleddash": "⊝", "Cap": "⋒", "Cup": "⋓", "curlyvee": "⋎", "curlywedge": "⋏",
    "xor": "⊕",
}

REL = {
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "equiv": "≡", "approx": "≈",
    "sim": "∼", "simeq": "≃", "cong": "≅", "propto": "∝", "asymp": "≍", "doteq": "≐", "ll": "≪", "gg": "≫",
    "lll": "⋘", "ggg": "⋙", "prec": "≺", "succ": "≻", "preceq": "⪯", "succeq": "⪰", "subset": "⊂",
    "supset": "⊃", "subseteq": "⊆", "supseteq": "⊇", "subsetneq": "⊊", "supsetneq": "⊋", "in": "∈",
    "notin": "∉", "ni": "∋", "owns": "∋", "perp": "⊥", "parallel": "∥", "nparallel": "∦", "mid": "∣",
    "nmid": "∤", "vdash": "⊢", "dashv": "⊣", "models": "⊨", "vDash": "⊨", "Vdash": "⊩", "to": "→",
    "rightarrow": "→", "leftarrow": "←", "gets": "←", "leftrightarrow": "↔", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "Leftrightarrow": "⇔", "implies": "⟹", "impliedby": "⟸", "iff": "⟺",
    "longrightarrow": "⟶", "longleftarrow": "⟵", "longleftrightarrow": "⟷", "Longrightarrow": "⟹",
    "Longleftarrow": "⟸", "Longleftrightarrow": "⟺", "mapsto": "↦", "longmapsto": "⟼", "uparrow": "↑",
    "downarrow": "↓", "updownarrow": "↕", "Uparrow": "⇑", "Downarrow": "⇓", "Updownarrow": "⇕",
    "nearrow": "↗", "searrow": "↘", "swarrow": "↙", "nwarrow": "↖", "hookrightarrow": "↪",
    "hookleftarrow": "↩", "rightleftharpoons": "⇌", "leftrightharpoons": "⇋", "rightharpoonup": "⇀",
    "rightharpoondown": "⇁", "leftharpoonup": "↼", "leftharpoondown": "↽", "leadsto": "⇝",
    "rightrightarrows": "⇉", "leftleftarrows": "⇇", "twoheadrightarrow": "↠", "nless": "≮", "ngtr": "≯",
    "nleq": "≰", "ngeq": "≱", "nsim": "≁", "ncong": "≇", "nequiv": "≢", "nsubseteq": "⊈", "nsupseteq": "⊉",
    "sqsubseteq": "⊑", "sqsupseteq": "⊒", "sqsubset": "⊏", "sqsupset": "⊐", "approxeq": "≊",
    "lesssim": "≲", "gtrsim": "≳", "leqslant": "⩽", "geqslant": "⩾", "lessgtr": "≶", "gtrless": "≷",
    "coloneqq": "≔", "eqqcolon": "≕", "triangleq": "≜", "therefore": "∴", "because": "∵", "smile": "⌣",
    "frown": "⌢", "bowtie": "⋈", "Join": "⋈", "vartriangleleft": "⊲", "vartriangleright": "⊳",
    "trianglelefteq": "⊴", "trianglerighteq": "⊵", "nvdash": "⊬", "nvDash": "⊭",
    "circeq": "≗", "bumpeq": "≏", "Bumpeq": "≎", "risingdotseq": "≓", "fallingdotseq": "≒",
    "thicksim": "∼", "thickapprox": "≈", "backsim": "∽", "eqsim": "≂",
}

PUNCT = {"colon": ":", "ldotp": "."}

# Toán tử lớn: tên → ký tự; ``True`` nếu chỉ số đặt trên/dưới khi hiển thị riêng dòng (∑), ``False`` nếu đặt bên phải (∫).
BIG = {
    "sum": ("∑", True), "prod": ("∏", True), "coprod": ("∐", True), "int": ("∫", False), "iint": ("∬", False),
    "iiint": ("∭", False), "oint": ("∮", False), "oiint": ("∯", False), "bigcup": ("⋃", True),
    "bigcap": ("⋂", True), "bigvee": ("⋁", True), "bigwedge": ("⋀", True), "bigoplus": ("⨁", True),
    "bigotimes": ("⨂", True), "bigodot": ("⨀", True), "biguplus": ("⨄", True), "bigsqcup": ("⨆", True),
}

# Hàm viết chữ đứng (sin x). tg, cotg, arctg là cách viết của sách Việt Nam.
FUNCTIONS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "arccot", "sinh", "cosh", "tanh",
    "coth", "log", "ln", "lg", "exp", "lim", "liminf", "limsup", "max", "min", "sup", "inf", "det", "gcd",
    "lcm", "deg", "dim", "ker", "arg", "hom", "Pr", "tg", "cotg", "arctg", "arccotg", "sh", "ch", "th",
    "cth", "sgn", "rank", "tr", "Var", "Cov", "argmax", "argmin",
}
# Hàm có chỉ số đặt dưới khi hiển thị riêng dòng (lim x→0).
LIMIT_FUNCTIONS = {"lim", "liminf", "limsup", "max", "min", "sup", "inf", "det", "gcd", "Pr", "argmax", "argmin"}
FUNCTION_TEXT = {"liminf": "lim inf", "limsup": "lim sup", "argmax": "arg max", "argmin": "arg min"}

# Dấu trên chữ: tên → ký tự kết hợp Word dùng trong m:acc. ``widehat`` và bạn bè giãn theo bề rộng.
ACCENTS = {
    "hat": "̂", "widehat": "̂", "check": "̌", "widecheck": "̌", "tilde": "̃",
    "widetilde": "̃", "acute": "́", "grave": "̀", "dot": "̇", "ddot": "̈",
    "dddot": "⃛", "breve": "̆", "bar": "̅", "vec": "⃗", "mathring": "̊",
    "overrightarrow": "⃗", "overleftarrow": "⃖", "overleftrightarrow": "⃡",
}
WIDE_ACCENTS = {"widehat", "widecheck", "widetilde", "overrightarrow", "overleftarrow", "overleftrightarrow"}

# Ngoặc dùng được sau \left, \right, \big…: tên hoặc ký tự → ký tự Unicode ("" là không có ngoặc, như \left.).
DELIMITERS = {
    "(": "(", ")": ")", "[": "[", "]": "]", "\\{": "{", "\\}": "}", "\\lbrace": "{", "\\rbrace": "}",
    "|": "|", "\\|": "‖", "\\vert": "|", "\\Vert": "‖", "\\lvert": "|", "\\rvert": "|", "\\lVert": "‖",
    "\\rVert": "‖", "\\langle": "⟨", "\\rangle": "⟩", "\\lfloor": "⌊", "\\rfloor": "⌋", "\\lceil": "⌈",
    "\\rceil": "⌉", ".": "", "/": "/", "\\backslash": "\\", "\\uparrow": "↑", "\\downarrow": "↓",
    "\\updownarrow": "↕", "\\Uparrow": "⇑", "\\Downarrow": "⇓", "\\lgroup": "⟮", "\\rgroup": "⟯",
    "\\llbracket": "⟦", "\\rrbracket": "⟧", "<": "⟨", ">": "⟩", "⟨": "⟨", "⟩": "⟩", "‖": "‖",
}

# Khoảng trắng: tên → bề rộng theo em (TeX: \, = 3/18 em, \: = 4/18, \; = 5/18).
SPACES = {
    ",": 3 / 18, "thinspace": 3 / 18, ":": 4 / 18, ">": 4 / 18, "medspace": 4 / 18, ";": 5 / 18,
    "thickspace": 5 / 18, "!": -3 / 18, "negthinspace": -3 / 18, " ": 1 / 3, "space": 1 / 3,
    "enspace": 1 / 2, "quad": 1.0, "qquad": 2.0,
}

# Kiểu chữ: \mathbb{R} → chữ khối kép… Tên kiểu theo khối Mathematical Alphanumeric Symbols của Unicode.
FONT_COMMANDS = {
    "mathbb": "double-struck", "mathbf": "bold", "boldsymbol": "bold-italic", "bm": "bold-italic",
    "mathcal": "script", "mathscr": "script", "mathfrak": "fraktur", "mathsf": "sans-serif",
    "mathtt": "monospace", "mathit": "italic", "mathrm": "upright", "mathup": "upright",
}
TEXT_COMMANDS = {"text", "textrm", "textnormal", "mbox", "textit", "textbf", "textsf", "texttt", "hbox"}

# Lệnh không vẽ gì (kiểu cỡ chữ, nhãn) thì bỏ qua; lệnh có một tham số bỏ qua cùng tham số.
IGNORED = {"displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle", "limits", "nolimits", "notag",
           "nonumber", "hline", "allowbreak", "relax", "strut", "mathstrut", "nobreak", "protect"}
IGNORED_WITH_ARG = {"label", "color", "hspace", "vspace", "hspace*", "vspace*", "kern", "mkern", "mspace",
                    "hskip", "htmlClass", "htmlId", "cline"}


def symbol(name: str) -> tuple[str, str] | None:
    """Ký tự và loại của một lệnh ký hiệu (không gồm toán tử lớn, hàm, dấu trên chữ)."""
    if name in GREEK:
        return GREEK[name], "ord"
    if name in ORD:
        return ORD[name], "ord"
    if name in BIN:
        return BIN[name], "bin"
    if name in REL:
        return REL[name], "rel"
    if name in PUNCT:
        return PUNCT[name], "punct"
    return None


# Loại của ký tự gõ thẳng trong công thức.
CHAR_CLASS = {
    "+": "bin", "-": "bin", "−": "bin", "*": "bin", "±": "bin", "∓": "bin", "×": "bin", "÷": "bin", "⋅": "bin",
    "·": "bin", "∘": "bin", "∗": "bin", "∪": "bin", "∩": "bin", "∧": "bin", "∨": "bin", "⊕": "bin", "⊗": "bin",
    "⊙": "bin", "∖": "bin",
    "=": "rel", "<": "rel", ">": "rel", ":": "rel", "≤": "rel", "≥": "rel", "≠": "rel", "≈": "rel", "≡": "rel",
    "∼": "rel", "≃": "rel", "≅": "rel", "∝": "rel", "→": "rel", "←": "rel", "↔": "rel", "⇒": "rel", "⇐": "rel",
    "⇔": "rel", "⟹": "rel", "⟺": "rel", "∈": "rel", "∉": "rel", "∋": "rel", "⊂": "rel", "⊃": "rel",
    "⊆": "rel", "⊇": "rel", "⊥": "rel", "∥": "rel", "∣": "rel", "↦": "rel", "≪": "rel", "≫": "rel",
    ",": "punct", ";": "punct",
    "(": "open", "[": "open", "{": "open", "⟨": "open", "⌊": "open", "⌈": "open",
    ")": "close", "]": "close", "}": "close", "⟩": "close", "⌋": "close", "⌉": "close", "!": "close",
    "?": "close",
}

# Chiều ngược lại cho bộ đọc Word: ký tự trong công thức → lệnh LaTeX dễ đọc nhất (trùng nghĩa thì lấy tên thường gặp).
_PREFERRED = {"≤": "le", "≥": "ge", "≠": "ne", "→": "to", "←": "leftarrow", "¬": "neg", "∧": "wedge",
              "∨": "vee", "∅": "emptyset", "ε": "varepsilon", "φ": "varphi", "ϕ": "phi", "…": "ldots",
              "∋": "ni", "⊥": "perp", "∣": "mid", "⟹": "implies", "⟺": "iff", "□": "square", "‖": "|",
              "⋅": "cdot", "ℏ": "hbar", "∼": "sim", "≈": "approx"}
TO_LATEX: dict[str, str] = {}
for _table in (GREEK, ORD, BIN, REL):
    for _name, _char in _table.items():
        if len(_char) == 1 and _name.isalpha() and _char not in TO_LATEX:
            TO_LATEX[_char] = _name
for _name, (_char, _limits) in BIG.items():
    TO_LATEX.setdefault(_char, _name)
TO_LATEX.update(_PREFERRED)
for _plain in ("{", "}", "|", "&", "%", "#", "$", "_"):
    TO_LATEX.pop(_plain, None)
TO_LATEX.pop("°", None)
TO_LATEX.pop("′", None)
TO_LATEX.update({"·": "cdot", "∙": "cdot", "⋯": "cdots", "⋮": "vdots", "⋱": "ddots",
                 "ℝ": "mathbb{R}", "ℕ": "mathbb{N}", "ℤ": "mathbb{Z}", "ℚ": "mathbb{Q}", "ℂ": "mathbb{C}",
                 "ℙ": "mathbb{P}"})

# Phông Symbol của Word (tệp cũ gõ chữ Hy Lạp và ký hiệu toán bằng phông này): mã 0x20–0xFE → Unicode.
SYMBOL_FONT = {
    0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2A: "∗", 0x2D: "−", 0x40: "≅", 0x5C: "∴", 0x5E: "⊥", 0x60: "‾",
    0x7E: "∼", 0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄", 0xA5: "∞", 0xA6: "ƒ", 0xA7: "♣", 0xA8: "♦",
    0xA9: "♥", 0xAA: "♠", 0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→", 0xAF: "↓", 0xB0: "°", 0xB1: "±",
    0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝", 0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠", 0xBA: "≡",
    0xBB: "≈", 0xBC: "…", 0xBD: "|", 0xBE: "—", 0xBF: "↵", 0xC0: "ℵ", 0xC1: "ℑ", 0xC2: "ℜ", 0xC3: "℘",
    0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪", 0xC9: "⊃", 0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂",
    0xCD: "⊆", 0xCE: "∈", 0xCF: "∉", 0xD0: "∠", 0xD1: "∇", 0xD2: "®", 0xD3: "©", 0xD4: "™", 0xD5: "∏",
    0xD6: "√", 0xD7: "⋅", 0xD8: "¬", 0xD9: "∧", 0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑", 0xDE: "⇒",
    0xDF: "⇓", 0xE0: "◊", 0xE1: "⟨", 0xE2: "®", 0xE3: "©", 0xE4: "™", 0xE5: "∑", 0xE6: "⎛", 0xE7: "⎜",
    0xE8: "⎝", 0xE9: "⎡", 0xEA: "⎢", 0xEB: "⎣", 0xEC: "⎧", 0xED: "⎨", 0xEE: "⎩", 0xEF: "⎪", 0xF1: "⟩",
    0xF2: "∫", 0xF3: "⌠", 0xF4: "⎮", 0xF5: "⌡", 0xF6: "⎞", 0xF7: "⎟", 0xF8: "⎠", 0xF9: "⎤", 0xFA: "⎥",
    0xFB: "⎦", 0xFC: "⎫", 0xFD: "⎬", 0xFE: "⎭",
}
_SYMBOL_LETTERS = "ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ"
_SYMBOL_SMALL = "αβχδεφγηιϕκλμνοπθρστυϖωξψζ"
for _index, _char in enumerate(_SYMBOL_LETTERS):
    SYMBOL_FONT[0x41 + _index] = _char
for _index, _char in enumerate(_SYMBOL_SMALL):
    SYMBOL_FONT[0x61 + _index] = _char


def symbol_font_char(code: int) -> str:
    """Ký tự Unicode của một mã trong phông Symbol; Word lưu mã đó dạng 0xF0xx hoặc chữ ASCII trong lượt chữ Symbol."""
    if 0xF000 <= code <= 0xF0FF:
        code -= 0xF000
    if code in SYMBOL_FONT:
        return SYMBOL_FONT[code]
    return chr(code) if 0x20 <= code < 0x7F else ""
