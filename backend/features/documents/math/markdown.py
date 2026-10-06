"""Tách công thức ($…$, $$…$$, \\(…\\), \\[…\\]) khỏi Markdown trước khi phân tích, thay bằng dấu giữ chỗ.

Phải tách trước: công thức dòng riêng hay có dòng bắt đầu bằng "+ " hoặc "- " (vế tiếp của một tổng dài), mà
Markdown đọc dòng đó thành gạch đầu dòng; còn \\( \\[ bị Markdown đọc thành ký tự thoát. Mã trong `…` và khối ``` giữ
nguyên. Quy tắc dấu $ như Pandoc: sau $ mở không là khoảng trắng, trước $ đóng không là khoảng trắng và sau nó không là
chữ số, nên "giá $5 và $10" không thành công thức.
"""
from __future__ import annotations

import re

# Ký tự riêng (Private Use) làm dấu giữ chỗ; người dùng gõ các ký tự này thì bị bỏ trước khi tách.
DISPLAY_OPEN, DISPLAY_CLOSE, INLINE_OPEN, INLINE_CLOSE = "", "", "", ""
PLACEHOLDER = re.compile("(|)(\\d+)(?:|)")
_FENCE = re.compile(r"[ \t]{0,3}(`{3,}|~{3,})")


def extract(content: str) -> tuple[str, list[tuple[str, bool]]]:
    """(Markdown đã thay công thức bằng dấu giữ chỗ, danh sách (LaTeX, dòng riêng))."""
    content = re.sub("[-]", "", content)
    formulas: list[tuple[str, bool]] = []
    out: list[str] = []
    index = 0
    length = len(content)
    fence: str | None = None

    def keep(latex: str, display: bool) -> str:
        formulas.append((latex.strip(), display))
        number = len(formulas) - 1
        return f"{DISPLAY_OPEN}{number}{DISPLAY_CLOSE}" if display else f"{INLINE_OPEN}{number}{INLINE_CLOSE}"

    while index < length:
        if index == 0 or content[index - 1] == "\n":
            end_of_line = content.find("\n", index)
            end_of_line = length if end_of_line < 0 else end_of_line
            line = content[index:end_of_line]
            match = _FENCE.match(line)
            if fence is not None:
                if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                        and not line[match.end():].strip():
                    fence = None
                out.append(content[index:end_of_line + 1])
                index = end_of_line + 1
                continue
            if match:
                fence = match.group(1)
                out.append(content[index:end_of_line + 1])
                index = end_of_line + 1
                continue
        char = content[index]
        if char == "`":
            run = len(content[index:]) - len(content[index:].lstrip("`"))
            ticks = content[index:index + run]
            closing = content.find(ticks, index + run)
            while closing >= 0 and closing + run < length and content[closing + run] == "`":
                closing = content.find(ticks, closing + run + 1)
            if closing < 0:
                out.append(ticks)
                index += run
                continue
            out.append(content[index:closing + run])
            index = closing + run
            continue
        if char == "\\" and index + 1 < length:
            following = content[index + 1]
            if following in "([":
                closing = content.find("\\)" if following == "(" else "\\]", index + 2)
                if closing >= 0 and (following == "[" or "\n\n" not in content[index:closing]):
                    out.append(keep(content[index + 2:closing], following == "["))
                    index = closing + 2
                    continue
            out.append(content[index:index + 2])
            index += 2
            continue
        if char == "$":
            if content.startswith("$$", index):
                closing = _closing(content, "$$", index + 2)
                if closing >= 0 and content[index + 2:closing].strip():
                    out.append(keep(content[index + 2:closing], True))
                    index = closing + 2
                    continue
                out.append("$$")
                index += 2
                continue
            closing = _inline_closing(content, index)
            if closing >= 0:
                out.append(keep(content[index + 1:closing], False))
                index = closing + 1
                continue
        out.append(char)
        index += 1
    return "".join(out), formulas


def _closing(content: str, marker: str, start: int) -> int:
    position = start
    while True:
        found = content.find(marker, position)
        if found < 0:
            return -1
        if content[found - 1] != "\\":
            return found
        position = found + 1


def _inline_closing(content: str, start: int) -> int:
    """Vị trí $ đóng của công thức trong dòng mở ở ``start``, hoặc -1 khi đó chỉ là dấu $ thường."""
    following = content[start + 1] if start + 1 < len(content) else ""
    if not following or following.isspace() or following == "$":
        return -1
    position = start + 1
    while position < len(content):
        char = content[position]
        if char == "\\":
            position += 2
            continue
        if char == "\n" and content[position + 1:position + 2] == "\n":
            return -1
        if char == "$":
            before = content[position - 1]
            after = content[position + 1] if position + 1 < len(content) else ""
            if not before.isspace() and not after.isdigit():
                return position
            return -1
        position += 1
    return -1


def split(text: str, formulas: list[tuple[str, bool]]) -> list:
    """Chữ đã có dấu giữ chỗ → danh sách chuỗi và (LaTeX, dòng riêng)."""
    parts: list = []
    last = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > last:
            parts.append(text[last:match.start()])
        number = int(match.group(2))
        if number < len(formulas):
            parts.append(formulas[number])
        last = match.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


def restore(text: str, formulas: list[tuple[str, bool]]) -> str:
    """Dấu giữ chỗ → lại thành $…$ / $$…$$ (cho chữ thường như mục lục, tên đề mục)."""
    def back(match: re.Match) -> str:
        number = int(match.group(2))
        if number >= len(formulas):
            return ""
        latex, display = formulas[number]
        return f"$${latex}$$" if display else f"${latex}$"
    return PLACEHOLDER.sub(back, text)
