"""Markdown của câu trả lời, vẽ dần theo từng dòng nhận được.

Đoạn văn tự gập theo bề ngang terminal (bản cũ để terminal tự bẻ chữ), danh sách có dấu, bảng kẻ khung, khối code có
nền và tô màu. Bảng chỉ vẽ khi đã nhận hết bảng, vì độ rộng cột phụ thuộc mọi hàng. Công thức LaTeX đổi sang ký hiệu
Unicode như bản cũ (texmath).
"""

from __future__ import annotations

import re
import unicodedata

from .. import texmath
from . import highlight
from .text import Line, S, cells, fit, wrap

FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w#+.-]*)")
# Trích code kèm chỗ, kiểu ```21:24:src/main.c: model (Grok) hay viết vậy khi dẫn chứng; trước 0.19.1 nhãn chỉ còn "21".
CITATION = re.compile(r"^\s*(?:```+|~~~+)\s*(\d+):(\d+):(\S+)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
BULLET = re.compile(r"^(\s*)([-*+])\s+(\[[ xX]\]\s+)?(.*)$")
NUMBERED = re.compile(r"^(\s*)(\d{1,3}[.)])\s+(.*)$")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
INLINE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|\*\*(?P<bold>(?=\S).+?(?<=\S))\*\*"
    r"|__(?P<bold2>(?=\S).+?(?<=\S))__"
    r"|~~(?P<strike>(?=\S).+?(?<=\S))~~"
    r"|(?<![\w*])\*(?P<italic>(?=[^\s*])[^*\n]+?(?<=\S))\*(?![\w*])"
    r"|(?<![\w_])_(?P<italic2>(?=\S)[^_\n]+?(?<=\S))_(?![\w_])"
    r"|\[(?P<label>[^\]\n]+)\]\((?P<url>https?://[^)\s]+)\)"
    r"|(?P<path>(?<![\w/.-])(?:[\w.-]+[/\\])*[\w.-]+\.[A-Za-z]\w{0,7}:\d+(?:[-–]\d+)?)"
)
INDENT = 3


def _visible(text: str) -> str:
    return "".join(f"\\x{ord(char):02x}" if unicodedata.category(char) in {"Cc", "Cs"} else char
                   for char in text.expandtabs(4))


def inline(text: str, theme, base: dict | None = None) -> list:
    """Các đoạn chữ của một dòng: mã, đậm, nghiêng, gạch, link và tệp:dòng."""
    base = base or {}
    color = base.get("fg", theme.text)
    italic = base.get("i", False)
    result, last = [], 0
    for match in INLINE.finditer(text):
        if match.start() > last:
            result.append(S(text[last:match.start()], color, i=italic))
        kind = match.lastgroup
        if kind == "code":
            result.append(S(match.group("code")[1:-1], theme.inline_code))
        elif kind in {"bold", "bold2"}:
            result.append(S(match.group(kind), color, b=True, i=italic))
        elif kind == "strike":
            result.append(S(match.group("strike"), theme.muted, s=True))
        elif kind in {"italic", "italic2"}:
            result.append(S(match.group(kind), color, i=True))
        elif kind in {"label", "url"}:
            result.append(S(match.group("label"), theme.link, u=True))
            result.append(S(f" ({match.group('url')})", theme.muted))
        elif kind == "path":
            result.append(S(match.group("path"), theme.link, u=True))
        last = match.end()
    if last < len(text):
        result.append(S(text[last:], color, i=italic))
    return result


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row)]


class Markdown:
    """Nhận từng dòng nguồn, trả các hàng đã vẽ; ``flush`` trả phần còn giữ (bảng, khối code chưa đóng)."""

    def __init__(self, theme, width: int):
        self.theme = theme
        self.width = max(20, width)
        self.code: str | None = None
        self.lang: str | None = None
        self.math = False
        self.table: list[str] = []
        self._blank = True

    def _text_width(self) -> int:
        return max(10, self.width - INDENT)

    def _para(self, spans: list, first: str = "", rest: str | None = None, marker: list | None = None) -> list[Line]:
        """Gập một đoạn; ``first`` là phần thụt của hàng đầu (sau dấu danh sách), ``rest`` của các hàng sau."""
        rest = " " * cells(first) if rest is None else rest
        rows = wrap(spans, self._text_width() - cells(first))
        lines = []
        for index, row in enumerate(rows):
            lead = [S(" " * INDENT)] + ((marker or [S(first)]) if index == 0 else [S(rest)])
            lines.append(Line(lead + row))
        return lines

    def feed(self, raw: str) -> list[Line]:
        theme = self.theme
        line = _visible(raw.rstrip("\r"))
        out: list[Line] = []
        if self.table and not (TABLE_ROW.match(line) or TABLE_RULE.match(line)):
            out += self._table()
        fence = FENCE.match(line)
        if self.code is not None:
            if fence and fence.group(1)[0] == self.code[0] and len(fence.group(1)) >= len(self.code):
                self.code = None
                self._blank = True
                return out + [self._code_row([], label=False), Line()]
            return out + self._code_line(line)
        if fence:
            self._blank = False
            self.code, self.lang = fence.group(1), highlight.language(fence.group(2))
            label = fence.group(2).strip()
            if cited := CITATION.match(line):
                start, end, path = cited.groups()
                self.lang = highlight.language(path)
                label = f"{path}:{start}" + (f"-{end}" if end != start else "")
            return out + [self._code_row([S(label, theme.muted, theme.panel)] if label else [], label=True)]
        stripped = line.strip()
        if self.math:
            if stripped.endswith("\\]") or stripped == "$$":
                self.math = False
                stripped = stripped[:-2]
            text = texmath.convert(stripped)
            return out + ([Line([S(" " * (INDENT + 4)), S(text, theme.text)])] if text else [])
        if stripped in ("\\[", "$$") or (stripped.startswith("\\[") and "\\]" not in stripped):
            self.math = True
            text = texmath.convert(stripped[2:])
            return out + ([Line([S(" " * (INDENT + 4)), S(text, theme.text)])] if text else [])
        if (formula := texmath.display_line(line)) is not None:
            return out + [Line([S(" " * (INDENT + 4)), S(formula, theme.text)])]
        if TABLE_ROW.match(line):
            self.table.append(line)
            return out
        if not stripped:
            if self._blank:
                return out
            self._blank = True
            return out + [Line()]
        self._blank = False
        line = texmath.inline(line)
        if RULE.match(line):
            return out + [Line([S(" " * INDENT), S("─" * min(40, self._text_width()), theme.border)])]
        if match := HEADING.match(line):
            spans = inline(match.group(2), theme, {"fg": theme.heading})
            spans = [(text, {**style, "b": True}) for text, style in spans]
            return out + self._para(spans)
        if match := QUOTE.match(line):
            return out + self._para(inline(match.group(1), theme, {"fg": theme.quote, "i": True}), "│ ", "│ ",
                                    marker=[S("│ ", theme.border)])
        if match := BULLET.match(line):
            depth = len(match.group(1).expandtabs(4)) // 2
            box = match.group(3)
            if box:
                done = box.strip()[1] in "xX"
                mark = [S("  " * depth), S("[✓] " if done else "[ ] ", theme.success if done else theme.muted)]
                first = "  " * depth + "[ ] "
            else:
                mark = [S("  " * depth), S("• ", theme.primary)]
                first = "  " * depth + "• "
            return out + self._para(inline(match.group(4), theme), first, marker=mark)
        if match := NUMBERED.match(line):
            depth = len(match.group(1).expandtabs(4)) // 2
            first = "  " * depth + match.group(2) + " "
            return out + self._para(inline(match.group(3), theme), first,
                                    marker=[S("  " * depth), S(match.group(2) + " ", theme.primary)])
        return out + self._para(inline(line.strip(), theme))

    def flush(self) -> list[Line]:
        out = self._table() if self.table else []
        if self.code is not None:
            self.code = None
            out.append(self._code_row([], label=False))
        self.math = False
        return out

    # Khối code: nền panel, thụt như chữ, hàng dài cắt xuống hàng.
    def _code_row(self, spans: list, *, label: bool) -> Line:
        theme = self.theme
        width = self._text_width()
        return Line([S(" " * INDENT)] + fit(Line([S("  ", bg=theme.panel)] + spans), width, theme.panel).spans)

    def _code_line(self, line: str) -> list[Line]:
        theme = self.theme
        width = self._text_width()
        spans = highlight.spans(line, self.lang, theme, theme.panel)
        return [Line([S(" " * INDENT)] + fit(Line([S("  ", bg=theme.panel)] + row), width, theme.panel).spans)
                for row in wrap(spans, width - 3, hard=True)]

    def _table(self) -> list[Line]:
        theme = self.theme
        rows = [_cells(row) for row in self.table if not TABLE_RULE.match(row)]
        self.table = []
        self._blank = False
        if not rows:
            return []
        columns = max(len(row) for row in rows)
        rows = [row + [""] * (columns - len(row)) for row in rows]
        # Mỗi ô gập theo cột; cột quá rộng so với màn hình thì thu hẹp cột rộng nhất trước.
        widths = [max(cells(row[index]) for row in rows) or 1 for index in range(columns)]
        room = self._text_width() - (3 * columns + 1)
        while sum(widths) > room and max(widths) > 6:
            widest = widths.index(max(widths))
            widths[widest] -= 1
        border = theme.border

        def edge(left: str, middle: str, right: str) -> Line:
            return Line([S(" " * INDENT), S(left + middle.join("─" * (width + 2) for width in widths) + right, border)])

        lines = [edge("┌", "┬", "┐")]
        for number, row in enumerate(rows):
            wrapped = [wrap(inline(cell, theme), widths[index]) for index, cell in enumerate(row)]
            for part in range(max(len(cell) for cell in wrapped)):
                spans = [S(" " * INDENT), S("│", border)]
                for index, cell in enumerate(wrapped):
                    content = cell[part] if part < len(cell) else []
                    if number == 0:
                        content = [(text, {**style, "b": True}) for text, style in content]
                    spans += [S(" ")] + fit(Line(content), widths[index]).spans + [S(" "), S("│", border)]
                lines.append(Line(spans))
            if number == 0 and len(rows) > 1:
                lines.append(edge("├", "┼", "┤"))
        lines.append(edge("└", "┴", "┘"))
        return lines
