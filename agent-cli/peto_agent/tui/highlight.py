"""Tô màu code theo từng dòng bằng biểu thức chính quy: từ khóa, chuỗi, số, chú thích, tên hàm.

Không phân tích cú pháp thật (thư viện chuẩn không có); chuỗi hay chú thích kéo dài nhiều dòng chỉ được tô ở dòng mở.
"""

from __future__ import annotations

import re

from .text import S

_PY = "and as assert async await break class continue def del elif else except False finally for from global if " \
      "import in is lambda None nonlocal not or pass raise return True try while with yield match case self"
_JS = "async await break case catch class const continue debugger default delete do else export extends false " \
      "finally for from function if import in instanceof interface let new null of private public return static " \
      "super switch this throw true try type typeof undefined var void while yield enum implements readonly"
_C = "auto break case char class const continue default do double else enum extern false float for foreach goto if " \
     "in int interface internal long namespace new null object out override private protected public readonly ref " \
     "return sbyte sealed short signed sizeof static string struct switch this throw true try typedef typeof uint " \
     "unsigned using var virtual void volatile while bool async await get set record"
_SH = "if then else elif fi for in do done while case esac function return export local echo cd set exit"
_PS = "if else elseif foreach for in while do function return param begin process end try catch finally throw " \
      "switch break continue"
_CMD = "if else for in do goto call set echo exist not errorlevel rem cd setlocal endlocal exit"

LANGUAGES = {
    "python": (_PY, "#"), "javascript": (_JS, "//"), "c": (_C, "//"), "shell": (_SH, "#"),
    "powershell": (_PS, "#"), "cmd": (_CMD, "::"), "json": ("true false null", None), "css": ("", None),
    "html": ("", None),
}
ALIASES = {
    "py": "python", "python3": "python", "pyw": "python", "js": "javascript", "jsx": "javascript",
    "ts": "javascript", "tsx": "javascript", "typescript": "javascript", "mjs": "javascript", "cjs": "javascript",
    "cs": "c", "csharp": "c", "c#": "c", "cpp": "c", "c++": "c", "h": "c", "hpp": "c", "java": "c", "go": "c",
    "rs": "c", "rust": "c", "kt": "c", "sh": "shell", "bash": "shell", "zsh": "shell", "ps1": "powershell",
    "ps": "powershell", "pwsh": "powershell", "bat": "cmd", "batch": "cmd", "jsonc": "json", "scss": "css",
    "xml": "html", "htm": "html", "svg": "html", "vue": "html",
}


def language(name: str | None) -> str | None:
    """Ngôn ngữ từ nhãn khối code (```py) hay đuôi tệp (app.tsx); None khi không biết."""
    if not name:
        return None
    key = name.strip().lower().rsplit(".", 1)[-1] if "." in name else name.strip().lower()
    key = ALIASES.get(key, key)
    return key if key in LANGUAGES else None


def _pattern(lang: str) -> re.Pattern:
    words, comment = LANGUAGES[lang]
    parts = []
    if comment:
        parts.append(rf"(?P<comment>{re.escape(comment)}.*)")
    if lang in {"javascript", "c", "css"}:
        parts.append(r"(?P<comment2>/\*.*?(?:\*/|$))")
    if lang == "cmd":
        parts.append(r"(?P<comment3>(?i:^\s*rem\b.*))")
    if lang == "html":
        parts.append(r"(?P<comment4><!--.*?(?:-->|$))")
        parts.append(r"(?P<keyword></?[A-Za-z][\w:-]*|/?>)")
    parts.append(r"""(?P<string>'''.*?(?:'''|$)|\"\"\".*?(?:\"\"\"|$)|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|`[^`]*`?)""")
    if lang == "powershell" or lang == "shell":
        parts.append(r"(?P<variable>\$[\w:]+|\$\{[^}]*\})")
    if lang == "cmd":
        parts.append(r"(?P<variable>%[\w~]+%?)")
    parts.append(r"(?P<number>\b(?:0x[0-9A-Fa-f_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\b)")
    if words:
        parts.append(r"(?P<keyword2>\b(?:" + "|".join(re.escape(word) for word in words.split()) + r")\b)")
    if lang in {"python", "javascript", "c"}:
        parts.append(r"(?P<function>\b[A-Za-z_]\w*(?=\())")
    flags = re.IGNORECASE if lang in {"powershell", "cmd"} else 0
    return re.compile("|".join(parts), flags)


_PATTERNS: dict[str, re.Pattern] = {}
ROLES = {"comment": "comment", "comment2": "comment", "comment3": "comment", "comment4": "comment",
         "string": "string", "number": "number", "keyword": "keyword", "keyword2": "keyword",
         "function": "function", "variable": "info"}


def spans(code: str, lang: str | None, theme, bg: str | None = None) -> list:
    """Các đoạn chữ có màu của một dòng code; ngôn ngữ không biết thì giữ nguyên màu chữ."""
    if lang is None:
        return [S(code, theme.text, bg)]
    pattern = _PATTERNS.get(lang)
    if pattern is None:
        pattern = _PATTERNS[lang] = _pattern(lang)
    result, last = [], 0
    for match in pattern.finditer(code):
        if match.start() > last:
            result.append(S(code[last:match.start()], theme.text, bg))
        role = ROLES[match.lastgroup]
        result.append(S(match.group(), getattr(theme, role), bg, i=role == "comment"))
        last = match.end()
    if last < len(code):
        result.append(S(code[last:], theme.text, bg))
    return result
