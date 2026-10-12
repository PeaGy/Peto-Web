"""Terminal ảo tối giản cho test: đủ mã điều khiển mà Peto dùng để kiểm lịch sử cuộn và phần chân cố định.

Hiểu: chữ (đo ô như terminal), CR, LF (dòng trôi lên lịch sử cuộn khi chạm đáy), CSI n A/B/C/D, CSI J, CSI K, và bỏ qua
SGR, ?25, ?2026, OSC. Không tự xuống dòng ở cột cuối: Peto không bao giờ viết vào cột cuối, nên chạm cột cuối là lỗi.
"""

from __future__ import annotations

import re
import unicodedata

TOKEN = re.compile(r"\x1b\[([?0-9;]*)([A-Za-z])|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.|[\r\n\x07]|[^\x1b\r\n\x07]")


def width(char: str) -> int:
    if unicodedata.combining(char) or unicodedata.category(char) in {"Mn", "Me", "Cf"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


class Terminal:
    def __init__(self, columns: int, rows: int):
        self.columns, self.rows = columns, rows
        self.screen = [[] for _ in range(rows)]
        self.scrollback: list[str] = []
        self.row = self.col = 0

    def _line(self, index: int) -> list:
        line = self.screen[index]
        if len(line) < self.columns:
            line.extend([" "] * (self.columns - len(line)))
        return line

    def feed(self, data: str) -> None:
        for match in TOKEN.finditer(data):
            text = match.group(0)
            if match.group(2):
                self._csi(match.group(1), match.group(2))
            elif text.startswith("\x1b"):
                continue
            elif text == "\r":
                self.col = 0
            elif text == "\n":
                self._down()
            elif text == "\x07":
                continue
            else:
                size = width(text)
                if size == 0:
                    line = self._line(self.row)
                    if self.col:
                        line[self.col - 1] += text
                    continue
                if self.col + size > self.columns - 1:
                    raise AssertionError(f"viết vào cột cuối ở hàng {self.row}: {self.text(self.row)!r}{text!r}")
                line = self._line(self.row)
                line[self.col] = text
                if size == 2:
                    line[self.col + 1] = ""
                self.col += size

    def _down(self) -> None:
        if self.row == self.rows - 1:
            self.scrollback.append(self.text(0))
            self.screen = self.screen[1:] + [[]]
        else:
            self.row += 1

    def _csi(self, params: str, final: str) -> None:
        if params.startswith("?"):
            return
        number = int(params) if params.isdigit() else 0
        if final == "A":
            self.row = max(0, self.row - max(1, number))
        elif final == "B":
            self.row = min(self.rows - 1, self.row + max(1, number))
        elif final == "C":
            self.col = min(self.columns - 1, self.col + max(1, number))
        elif final == "D":
            self.col = max(0, self.col - max(1, number))
        elif final == "J" and number == 0:
            line = self._line(self.row)
            self.screen[self.row] = line[:self.col]
            for index in range(self.row + 1, self.rows):
                self.screen[index] = []
        elif final == "K" and number == 0:
            self.screen[self.row] = self._line(self.row)[:self.col]

    def text(self, index: int) -> str:
        return "".join(self.screen[index]).rstrip()

    def lines(self) -> list[str]:
        """Lịch sử cuộn rồi màn hình, bỏ các hàng trống ở cuối màn hình."""
        screen = [self.text(index) for index in range(self.rows)]
        while screen and not screen[-1]:
            screen.pop()
        return self.scrollback + screen
