"""Dòng có kiểu chữ: các đoạn (chữ, kiểu), đo bề ngang theo ô terminal, gập, cắt và đổi thành mã SGR."""

from __future__ import annotations

import re
import unicodedata

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")


def cell(char: str) -> int:
    if unicodedata.combining(char) or unicodedata.category(char) in {"Mn", "Me", "Cf"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def cells(text: str) -> int:
    return sum(cell(char) for char in text)


def S(text: str, fg: str | None = None, bg: str | None = None, *, b: bool = False, i: bool = False,
      u: bool = False, s: bool = False) -> tuple[str, dict]:
    """Một đoạn chữ với màu chữ, màu nền (#rrggbb hoặc None) và đậm, nghiêng, gạch chân, gạch ngang."""
    return text, {"fg": fg, "bg": bg, "b": b, "i": i, "u": u, "s": s}


class Line:
    """Một hàng: các đoạn chữ nối tiếp nhau."""

    __slots__ = ("spans",)

    def __init__(self, spans=None):
        self.spans = [span for span in (spans or []) if span[0]]

    def width(self) -> int:
        return sum(cells(text) for text, _ in self.spans)

    def text(self) -> str:
        return "".join(text for text, _ in self.spans)

    def __add__(self, other: "Line") -> "Line":
        return Line(self.spans + other.spans)

    def __repr__(self) -> str:
        return f"Line({self.text()!r})"


def _rgb(color: str) -> str:
    return f"{int(color[1:3], 16)};{int(color[3:5], 16)};{int(color[5:7], 16)}"


def sgr(style: dict, colors: bool = True) -> str:
    codes = ["0"]
    if style.get("b"):
        codes.append("1")
    if style.get("d"):
        codes.append("2")
    if style.get("r"):
        codes.append("7")
    if style.get("i"):
        codes.append("3")
    if style.get("u"):
        codes.append("4")
    if style.get("s"):
        codes.append("9")
    if colors and style.get("c16"):
        codes.append(style["c16"])
    if colors and style.get("fg"):
        codes.append("38;2;" + _rgb(style["fg"]))
    if colors and style.get("bg"):
        codes.append("48;2;" + _rgb(style["bg"]))
    return "\x1b[" + ";".join(codes) + "m"


def render(line: Line, colors: bool = True) -> str:
    """Mã terminal của một hàng, luôn trả kiểu chữ về mặc định ở cuối."""
    if not line.spans:
        return ""
    return "".join(sgr(style, colors) + text for text, style in line.spans) + "\x1b[0m"


def fit(line: Line, width: int, bg: str | None = None) -> Line:
    """Cắt hoặc đệm một hàng cho đúng ``width`` ô; phần đệm mang màu nền ``bg``."""
    spans, used = [], 0
    for text, style in line.spans:
        kept = []
        for char in text:
            size = cell(char)
            if used + size > width:
                break
            kept.append(char)
            used += size
        if kept:
            spans.append(("".join(kept), style))
        if used >= width or len(kept) < len(text):
            break
    if used < width:
        spans.append(S(" " * (width - used), bg=bg))
    return Line(spans)


def clip(text: str, width: int) -> str:
    if cells(text) <= width:
        return text
    kept, used = [], 0
    for char in text:
        used += cell(char)
        if used > width - 1:
            break
        kept.append(char)
    return "".join(kept) + "…"


def indent(line: Line, columns: int, bg: str | None = None) -> Line:
    return Line([S(" " * columns, bg=bg)] + line.spans) if columns else line


SGR = re.compile(r"\x1b\[([0-9;]*)m")


def parse_ansi(text: str) -> Line:
    """Một dòng chữ đã có mã màu (đầu phiên, thông báo in thẳng) thành ``Line``, để màn hình toàn phần gập lại được khi
    cửa sổ đổi cỡ. Hiểu các mã ``render`` và ``UI.paint`` sinh ra; mã điều khiển khác bị bỏ."""
    spans, style, position = [], {}, 0
    for match in ANSI.finditer(text):
        if match.start() > position:
            spans.append((text[position:match.start()], dict(style)))
        position = match.end()
        code = SGR.fullmatch(match.group(0))
        if code is None:
            continue
        numbers = [int(part) if part else 0 for part in code.group(1).split(";")]
        index = 0
        while index < len(numbers):
            number = numbers[index]
            if number == 0:
                style = {}
            elif number in (1, 2, 3, 4, 7, 9):
                style[{1: "b", 2: "d", 3: "i", 4: "u", 7: "r", 9: "s"}[number]] = True
            elif number == 22:
                style.pop("b", None)
                style.pop("d", None)
            elif number in (23, 24, 27, 29):
                style.pop({23: "i", 24: "u", 27: "r", 29: "s"}[number], None)
            elif number in (38, 48) and index + 4 < len(numbers) and numbers[index + 1] == 2:
                color = "#%02x%02x%02x" % tuple(max(0, min(255, value)) for value in numbers[index + 2:index + 5])
                style["fg" if number == 38 else "bg"] = color
                if number == 38:
                    style.pop("c16", None)
                index += 4
            elif 30 <= number <= 37 or 90 <= number <= 97:
                style["c16"] = str(number)
                style.pop("fg", None)
            elif number == 39:
                style.pop("fg", None)
                style.pop("c16", None)
            elif number == 49:
                style.pop("bg", None)
            index += 1
    if position < len(text):
        spans.append((text[position:], dict(style)))
    return Line(spans)


def crop(line: Line, width: int) -> Line:
    """Cắt một hàng còn ``width`` ô, không đệm thêm."""
    if line.width() <= width:
        return line
    spans, used = [], 0
    for text, style in line.spans:
        kept = []
        for char in text:
            if used + cell(char) > width:
                break
            kept.append(char)
            used += cell(char)
        if kept:
            spans.append(("".join(kept), style))
        if len(kept) < len(text):
            break
    return Line(spans)


def _split(line: Line, columns: list[int]) -> list[list]:
    """Các đoạn của hàng tách ở những cột cho trước; trả từng nhóm đoạn giữa hai cột liền nhau."""
    groups: list[list] = [[] for _ in range(len(columns) + 1)]
    used = 0
    for text, style in line.spans:
        for char in text:
            group = sum(1 for column in columns if used >= column)
            target = groups[group]
            if target and target[-1][1] is style:
                target[-1] = (target[-1][0] + char, style)
            else:
                target.append((char, style))
            used += cell(char)
    return groups


def highlight(line: Line, start: int, end: int, fg: str | None, bg: str | None) -> Line:
    """Tô ô ``start``..``end`` (không tính ``end``) bằng màu vùng chọn; hàng ngắn hơn thì tô cả phần trống.

    Không có màu (NO_COLOR) thì đảo màu chữ và nền."""
    if line.width() < end:
        line = Line(line.spans + [(" " * (end - line.width()), {})])
    before, middle, after = _split(line, [start, end])
    chosen = [(text, {**style, "fg": fg, "bg": bg, "c16": None, "d": False, "r": not (fg or bg)})
              for text, style in middle]
    return Line(before + chosen + after)


def text_between(line: Line, start: int, end: int) -> str:
    """Chữ thuần nằm trong ô ``start``..``end`` của hàng."""
    return "".join(text for text, _ in _split(line, [start, end])[1])


def wrap(spans: list, width: int, *, hard: bool = False) -> list[list]:
    """Gập các đoạn chữ thành hàng không quá ``width`` ô, giữ kiểu của từng đoạn.

    Bình thường ngắt ở khoảng trắng và bỏ khoảng trắng đầu hàng; ``hard`` cho code: cắt đúng ở mép, giữ mọi khoảng
    trắng. Một từ dài hơn cả hàng thì bị cắt.
    """
    width = max(1, width)
    rows: list[list] = [[]]
    used = 0
    if hard:
        for text, style in spans:
            piece = []
            for char in text:
                size = cell(char)
                if used + size > width and used:
                    if piece:
                        rows[-1].append(("".join(piece), style))
                        piece = []
                    rows.append([])
                    used = 0
                piece.append(char)
                used += size
            if piece:
                rows[-1].append(("".join(piece), style))
        return rows
    words = []
    for text, style in spans:
        for piece in re.split(r"(\s+)", text):
            if piece:
                words.append((piece, style))
    for piece, style in words:
        size = cells(piece)
        if piece.isspace():
            if used and used + size <= width:
                rows[-1].append((piece, style))
                used += size
            continue
        if used + size > width and used:
            while rows[-1] and rows[-1][-1][0].isspace():
                rows[-1].pop()
            rows.append([])
            used = 0
        while size > width:
            # Từ dài hơn cả hàng (đường dẫn, URL): cắt thành nhiều hàng.
            head, rest, taken = [], piece, 0
            for index, char in enumerate(piece):
                if taken + cell(char) > width - used:
                    rest = piece[index:]
                    break
                head.append(char)
                taken += cell(char)
            rows[-1].append(("".join(head), style))
            rows.append([])
            used = 0
            piece, size = rest, cells(rest)
        if piece:
            rows[-1].append((piece, style))
            used += size
    return rows
