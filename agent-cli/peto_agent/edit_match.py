"""Tìm đoạn cần sửa trong tệp cho edit_file, khớp gần đúng có kiểm soát (chủ web duyệt ngày 2026-10-12, theo OpenCode).

Model hay chép lệch chút: khoảng trắng cuối dòng, thụt lề khác, hoặc lỡ chép cả số dòng của read_file. Trước đây lệch
là lỗi và tốn thêm một bước. Thứ tự thử: khớp nguyên văn → bỏ số dòng → so từng dòng đã bỏ khoảng trắng hai đầu → so
từng dòng đã gộp khoảng trắng. Bước nào cũng phải khớp đúng một chỗ (trừ replace_all với khớp nguyên văn); khớp gần
đúng thì người dùng thấy ghi chú trong khung duyệt. Không có so khớp mờ theo khoảng cách chữ: lệch chữ là không khớp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "    12\t", "12: ", "12 | " ở đầu dòng: số dòng read_file in ra (cat -n) hoặc kiểu hay gặp khác.
LINE_NUMBER = re.compile(r"^\s*\d+(?:\t| ?[|:] )")
LABELS = {
    "numbers": "bỏ số dòng chép thừa",
    "trimmed": "bỏ qua khoảng trắng đầu và cuối dòng",
    "spaces": "bỏ qua khoảng trắng thừa trong dòng",
}


@dataclass
class Match:
    start: int
    end: int
    # Thụt lề trong old_text → thụt lề thật trong tệp, theo từng cặp dòng khớp: để new_text thụt theo tệp.
    indents: dict[str, str] | None = None


@dataclass
class Found:
    matches: list[Match]
    strategy: str  # "exact", "numbers", "trimmed", "spaces"
    old: str

    @property
    def label(self) -> str | None:
        return LABELS.get(self.strategy)


def _exact(text: str, old: str) -> list[Match]:
    matches, position = [], text.find(old)
    while position >= 0:
        matches.append(Match(position, position + len(old)))
        position = text.find(old, position + len(old))
    return matches


def _lines(text: str) -> list[tuple[int, int]]:
    """(đầu, cuối) của từng dòng, không tính ký tự xuống dòng."""
    spans, start = [], 0
    for line in text.split("\n"):
        spans.append((start, start + len(line)))
        start += len(line) + 1
    return spans


def _indent(line: str) -> str:
    return line[:len(line) - len(line.lstrip(" \t"))]


def _by_lines(text: str, old: str, normalize) -> list[Match]:
    """Các đoạn trọn dòng trong tệp mà từng dòng, sau ``normalize``, bằng từng dòng của old_text."""
    wanted = old.split("\n")
    trailing = wanted and wanted[-1] == ""
    if trailing:
        wanted = wanted[:-1]
    while wanted and not wanted[0].strip():
        wanted = wanted[1:]
    if not wanted:
        return []
    keys = [normalize(line) for line in wanted]
    if not any(keys):
        return []
    spans = _lines(text)
    rows = [text[start:end] for start, end in spans]
    normalized = [normalize(row) for row in rows]
    matches = []
    for index in range(len(rows) - len(keys) + 1):
        if normalized[index:index + len(keys)] == keys:
            start = spans[index][0]
            last = index + len(keys) - 1
            end = spans[last][1] + (1 if trailing and last + 1 < len(spans) else 0)
            matches.append(Match(start, end, _indent_map(wanted, rows[index:index + len(keys)])))
    return matches


def _indent_map(given: list[str], actual: list[str]) -> dict[str, str]:
    """Thụt lề từng dòng old_text ứng với thụt lề dòng tương ứng trong tệp; hai cách ứng khác nhau thì bỏ cả."""
    mapping: dict[str, str] = {}
    for old, real in zip(given, actual):
        if not old.strip():
            continue
        key, value = _indent(old), _indent(real)
        if mapping.setdefault(key, value) != value:
            return {}
    return mapping


def find(text: str, old: str) -> Found:
    matches = _exact(text, old)
    if matches:
        return Found(matches, "exact", old)
    lines = old.split("\n")
    numbered = [line for line in lines if line.strip()]
    if numbered and all(LINE_NUMBER.match(line) for line in numbered):
        stripped = "\n".join(LINE_NUMBER.sub("", line, count=1) for line in lines)
        matches = _exact(text, stripped)
        if matches:
            return Found(matches, "numbers", stripped)
        old = stripped
    matches = _by_lines(text, old, lambda line: line.strip())
    if matches:
        return Found(matches, "trimmed", old)
    matches = _by_lines(text, old, lambda line: " ".join(line.split()))
    return Found(matches, "spaces" if matches else "exact", old)


def reindent(new: str, match: Match) -> str:
    """Khớp gần đúng mà thụt lề trong old_text khác trong tệp: thụt từng dòng new_text theo tệp.

    Mỗi dòng dùng cách ứng của tiền tố thụt lề dài nhất đã biết, nên dòng sâu hơn trong new_text vẫn giữ phần thụt
    thêm của nó.
    """
    mapping = match.indents or {}
    if all(key == value for key, value in mapping.items()):
        return new
    rows = []
    for row in new.split("\n"):
        indent = _indent(row)
        known = max((key for key in mapping if indent.startswith(key)), key=len, default=None)
        if row.strip() and known is not None:
            row = mapping[known] + row[len(known):]
        rows.append(row)
    return "\n".join(rows)


def line_numbers(text: str, matches: list[Match]) -> list[int]:
    return [text.count("\n", 0, match.start) + 1 for match in matches]
