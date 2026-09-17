"""Hiển thị trong terminal: màu, dòng bước, diff và câu hỏi đồng ý."""

from __future__ import annotations

import difflib
import os
import sys

COLORS = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}
MAX_DIFF_LINES = 120
PERMISSION_QUESTION = "    Đồng ý? [y] có  [n] không  [a] có cho mọi bước trong yêu cầu này › "


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


class UI:
    def __init__(self, *, out=None, reader=input, colors: bool | None = None):
        self.out = out or sys.stdout
        self.reader = reader
        self.colors = enable_colors(self.out) if colors is None else colors

    def paint(self, text: str, color: str | None) -> str:
        if not color or not self.colors:
            return text
        return f"\033[{COLORS[color]}m{text}\033[0m"

    def write(self, text: str, color: str | None = None) -> None:
        self.out.write(self.paint(text, color))
        self.out.flush()

    def line(self, text: str = "", color: str | None = None) -> None:
        self.write(text + "\n", color)

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
        return self.reader(self.paint("Bạn › ", "yellow"))
