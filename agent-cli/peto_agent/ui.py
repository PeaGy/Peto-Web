"""Hiển thị trong terminal: màu, dòng bước, dòng trạng thái tạm, Markdown tối thiểu, diff và câu hỏi đồng ý."""

from __future__ import annotations

import difflib
import os
import re
import sys

COLORS = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}
MAX_DIFF_LINES = 120
PERMISSION_QUESTION = "    Đồng ý? [y] có  [n] không  [a] có cho mọi bước trong yêu cầu này › "
# Về đầu dòng rồi xóa cả dòng: dùng để vẽ lại và xóa dòng trạng thái tạm.
CLEAR_LINE = "\r\033[2K"

# Markdown tối thiểu cho câu trả lời của Peto: chữ đậm, mã, tiêu đề, gạch đầu dòng, trích dẫn và khối code.
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
INLINE_CODE = re.compile(r"(`[^`\n]+`)")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def enable_colors(stream) -> bool:
    if os.environ.get("NO_COLOR") or not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name == "nt":
        # Bật xử lý mã màu ANSI cho cửa sổ console cũ; Windows Terminal thì vốn đã bật.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except (AttributeError, OSError):
            return False
    return True


def _plain(text: str) -> str:
    """Bỏ dấu Markdown trong đoạn sẽ được tô nguyên dòng (tiêu đề, trích dẫn)."""
    text = INLINE_CODE.sub(lambda match: match.group(1)[1:-1], text)
    return BOLD.sub(r"\1", LINK.sub(r"\1 (\2)", text))


class UI:
    def __init__(self, *, out=None, reader=input, colors: bool | None = None):
        self.out = out or sys.stdout
        self.reader = reader
        self.colors = enable_colors(self.out) if colors is None else colors
        self._status: str | None = None
        self._in_code = False

    def paint(self, text: str, color: str | None) -> str:
        if not color or not self.colors:
            return text
        return f"\033[{COLORS[color]}m{text}\033[0m"

    def write(self, text: str, color: str | None = None) -> None:
        if self._status is not None:
            self.out.write(CLEAR_LINE)
            self._status = None
        self.out.write(self.paint(text, color))
        self.out.flush()

    def line(self, text: str = "", color: str | None = None) -> None:
        self.write(text + "\n", color)

    def status(self, text: str) -> None:
        """Dòng trạng thái tạm như "… Peto đang nghĩ · 8s": vẽ đè tại chỗ, tự biến mất khi có gì khác được in.

        Chỉ hiện khi terminal hiểu mã điều khiển; output chuyển sang tệp hay ống dẫn thì bỏ qua.
        """
        if not self.colors or text == self._status:
            return
        self.out.write(CLEAR_LINE + self.paint(text, "dim"))
        self.out.flush()
        self._status = text

    def clear_status(self) -> None:
        if self._status is not None:
            self.out.write(CLEAR_LINE)
            self.out.flush()
            self._status = None

    def markdown(self, line: str) -> str:
        """Tô một dòng Markdown. Không có màu (output vào tệp, NO_COLOR) thì giữ nguyên chữ gốc."""
        if not self.colors:
            return line
        if FENCE.match(line):
            self._in_code = not self._in_code
            return self.paint(line, "dim")
        if self._in_code:
            return self.paint(line, "cyan")
        if RULE.match(line):
            return self.paint("─" * 40, "dim")
        if match := HEADING.match(line):
            return self.paint(_plain(match.group(1)), "bold")
        if match := QUOTE.match(line):
            return self.paint("│ " + _plain(match.group(1)), "dim")
        if match := BULLET.match(line):
            return f"{match.group(1)}• {self._inline(match.group(2))}"
        return self._inline(line)

    def end_markdown(self) -> None:
        """Hết một câu trả lời: khối code chưa đóng không được tô lan sang chữ in sau."""
        self._in_code = False

    def _inline(self, text: str) -> str:
        parts = []
        # Tách mã trước để dấu ** nằm trong mã không bị hiểu thành chữ đậm.
        for part in INLINE_CODE.split(text):
            if len(part) >= 3 and part.startswith("`") and part.endswith("`"):
                parts.append(self.paint(part[1:-1], "cyan"))
            else:
                part = LINK.sub(r"\1 (\2)", part)
                parts.append(BOLD.sub(lambda match: self.paint(match.group(1), "bold"), part))
        return "".join(parts)

    def step(self, text: str) -> None:
        self.line(f"  • {text}", "dim")

    def success(self, text: str) -> None:
        self.line(f"  ✓ {text}", "green")

    def failure(self, text: str) -> None:
        self.line(f"  ✗ {text}", "red")

    def diff(self, title: str, before: str, after: str) -> None:
        self.line(f"  ✎ {title}", "blue")
        lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=2))[2:]
        for text in lines[:MAX_DIFF_LINES]:
            color = "green" if text.startswith("+") else "red" if text.startswith("-") else "dim" if text.startswith("@@") else None
            self.line("    " + text, color)
        if len(lines) > MAX_DIFF_LINES:
            self.line(f"    … còn {len(lines) - MAX_DIFF_LINES} dòng diff nữa", "dim")

    def ask_permission(self) -> str:
        """Hỏi y/n/a. Hết đầu vào (EOF) thì coi như không đồng ý."""
        self.clear_status()
        while True:
            try:
                answer = self.reader(PERMISSION_QUESTION).strip().lower()
            except EOFError:
                self.line()
                return "n"
            if answer in {"y", "n", "a"}:
                return answer
            self.line("    Gõ y, n hoặc a nhé.", "yellow")

    def prompt(self) -> str:
        self.clear_status()
        return self.reader(self.paint("Bạn › ", "yellow"))
