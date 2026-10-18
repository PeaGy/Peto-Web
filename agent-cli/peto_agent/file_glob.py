"""Một cú pháp glob cho cả tìm tên và tìm nội dung; mở rộng ngoặc có giới hạn."""
from __future__ import annotations

import re

from .workspace import WorkspaceError

MAX_ALTERNATIVES = 64


def _expand(pattern: str, depth: int = 0) -> list[str]:
    if depth > 8:
        raise WorkspaceError("Mẫu glob lồng ngoặc quá sâu (tối đa 8 tầng).")
    opening = None
    nesting = 0
    in_class = False
    cuts = []
    for index, char in enumerate(pattern):
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        if in_class:
            continue
        if char == "{":
            if opening is None:
                opening = index
            nesting += 1
        elif char == "}":
            if not nesting:
                raise WorkspaceError("Mẫu glob có ngoặc } không có ngoặc mở.")
            nesting -= 1
            if nesting == 0:
                assert opening is not None
                if not cuts:
                    raise WorkspaceError("Ngoặc glob cần danh sách như {py,json}; không hỗ trợ dải số {1..3}.")
                points = [opening, *cuts, index]
                expanded = []
                for left, right in zip(points, points[1:]):
                    expanded.extend(_expand(pattern[:opening] + pattern[left + 1:right] + pattern[index + 1:], depth + 1))
                    if len(expanded) > MAX_ALTERNATIVES:
                        raise WorkspaceError("Mẫu glob mở rộng quá 64 lựa chọn; thu hẹp mẫu tìm.")
                return expanded
        elif char == "," and nesting == 1:
            cuts.append(index)
    if nesting:
        raise WorkspaceError("Mẫu glob thiếu ngoặc đóng }.")
    return [pattern]


def _translate(pattern: str) -> str:
    parts, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
            continue
        if pattern.startswith("**", index):
            parts.append(".*")
            index += 2
            continue
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        elif char == "[" and (close := pattern.find("]", index + 1)) > index:
            inside = pattern[index + 1:close].replace("\\", "\\\\")
            parts.append("[" + ("^" + inside[1:] if inside.startswith("!") else inside) + "]")
            index = close + 1
            continue
        else:
            parts.append(re.escape(char))
        index += 1
    return "".join(parts)


def glob_regex(pattern: str) -> re.Pattern:
    pattern = pattern.strip().replace("\\", "/")
    if not pattern:
        raise WorkspaceError("Mẫu tìm tệp đang trống, ví dụ **/*.py.")
    try:
        return re.compile("(?:" + "|".join(_translate(item) for item in _expand(pattern)) + ")", re.IGNORECASE)
    except re.error as err:
        raise WorkspaceError(f"Mẫu glob không hợp lệ: {err}.") from None
