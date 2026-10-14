"""Diff kiểu OpenCode: cột số dòng, dấu + −, nền xanh hay đỏ cho dòng thêm, xóa; rộng thì hai cột cũ và mới."""

from __future__ import annotations

import difflib
import unicodedata

from . import highlight
from .text import Line, S, fit, wrap

# Rộng hơn ngần này ô thì diff chia hai cột (OpenCode: hơn 120).
SPLIT_WIDTH = 120
CONTEXT = 2


def _visible(text: str) -> str:
    """Ký tự điều khiển trong tệp hiện thành chữ, để nội dung tệp không vẽ đè được câu hỏi duyệt."""
    return "".join(f"\\x{ord(char):02x}" if unicodedata.category(char) in {"Cc", "Cs"} else char
                   for char in text.expandtabs(4))


class Diff:
    """Các dòng đổi giữa hai bản; ``rows(width)`` dựng các hàng có màu cho một bề ngang.

    ``numbered=False`` cho hai đoạn cắt ra từ tệp (đoạn sửa của edit_file khi /resume vẽ lại hội thoại): số dòng của
    đoạn không phải số dòng của tệp, nên không in số, và đoạn không có xuống dòng ở cuối cũng không bị nhắc."""

    def __init__(self, before: str, after: str, *, path: str | None = None, context: int = CONTEXT,
                 numbered: bool = True):
        self.numbered = numbered
        if not numbered:
            before, after = (text if not text or text.endswith("\n") else text + "\n" for text in (before, after))
        self.old = before.splitlines(keepends=True)
        self.new = after.splitlines(keepends=True)
        self.groups = list(difflib.SequenceMatcher(None, self.old, self.new, autojunk=False)
                           .get_grouped_opcodes(context))
        self.added = sum(j2 - j1 for group in self.groups for tag, _, _, j1, j2 in group if tag in {"insert", "replace"})
        self.removed = sum(i2 - i1 for group in self.groups for tag, i1, i2, _, _ in group
                           if tag in {"delete", "replace"})
        self.lang = highlight.language(path)
        self.digits = max(3, len(str(max(len(self.old), len(self.new), 1)))) if numbered else 0

    @property
    def empty(self) -> bool:
        return not self.groups

    def _side(self, theme, number: int | None, sign: str, text: str | None, kind: str, width: int) -> list[Line]:
        """Một dòng của một cột; dòng dài được gập, các hàng sau để trống cột số."""
        bg = {"del": theme.removed_bg, "add": theme.added_bg}.get(kind, theme.panel)
        number_bg = {"del": theme.removed_number_bg, "add": theme.added_number_bg}.get(kind, theme.panel)
        sign_color = {"del": theme.diff_removed, "add": theme.diff_added}.get(kind, theme.line_number)
        gutter = self.digits + 3
        if text is None:
            return [fit(Line([S("", bg=theme.panel)]), width, theme.panel)]
        body = text.rstrip("\n")
        code = highlight.spans(_visible(body), self.lang, theme, bg)
        rows = wrap(code, max(1, width - gutter), hard=True)
        lines = []
        for index, row in enumerate(rows):
            head = ([S(f"{number:>{self.digits}}" if number and self.numbered else " " * self.digits, theme.line_number,
                       number_bg),
                     S(f" {sign} ", sign_color, number_bg)] if index == 0
                    else [S(" " * gutter, bg=number_bg)])
            lines.append(fit(Line(head + row), width, bg))
        if not text.endswith("\n") and kind != "ctx":
            lines.append(fit(Line([S(" " * gutter, bg=number_bg),
                                   S("↳ không có ký tự xuống dòng ở cuối tệp", theme.muted, bg)]), width, bg))
        return lines

    def rows(self, theme, width: int, *, split: bool | None = None) -> list[Line]:
        split = width > SPLIT_WIDTH if split is None else split
        rows: list[Line] = []
        for number, group in enumerate(self.groups):
            if number:
                where = f" @@ dòng {group[0][1] + 1} → {group[0][3] + 1} @@" if self.numbered else " ⋯"
                rows.append(fit(Line([S(where, theme.hunk, theme.panel)]), width, theme.panel))
            for tag, i1, i2, j1, j2 in group:
                if not split:
                    if tag == "equal":
                        for index in range(i2 - i1):
                            rows += self._side(theme, j1 + index + 1, " ", self.old[i1 + index], "ctx", width)
                        continue
                    for index in range(i1, i2):
                        rows += self._side(theme, index + 1, "−", self.old[index], "del", width)
                    for index in range(j1, j2):
                        rows += self._side(theme, index + 1, "+", self.new[index], "add", width)
                    continue
                half = (width - 1) // 2
                for index in range(max(i2 - i1, j2 - j1)):
                    if tag == "equal":
                        left = self._side(theme, i1 + index + 1, " ", self.old[i1 + index], "ctx", half)
                        right = self._side(theme, j1 + index + 1, " ", self.new[j1 + index], "ctx", width - half - 1)
                    else:
                        left = (self._side(theme, i1 + index + 1, "−", self.old[i1 + index], "del", half)
                                if i1 + index < i2 else self._side(theme, None, "", None, "fill", half))
                        right = (self._side(theme, j1 + index + 1, "+", self.new[j1 + index], "add", width - half - 1)
                                 if j1 + index < j2 else self._side(theme, None, "", None, "fill", width - half - 1))
                    for row in range(max(len(left), len(right))):
                        a = left[row] if row < len(left) else fit(Line([S("", bg=theme.panel)]), half, theme.panel)
                        b = right[row] if row < len(right) else fit(Line([S("", bg=theme.panel)]), width - half - 1,
                                                                     theme.panel)
                        rows.append(Line(a.spans + [S(" ", bg=theme.panel)] + b.spans))
        return rows
