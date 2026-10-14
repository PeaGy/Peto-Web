"""Màu và ký hiệu của giao diện.

Màu lấy từ theme "opencode" của OpenCode (MIT License, Copyright (c) 2025 opencode,
https://github.com/anomalyco/opencode), màu chính cam đổi sang hồng của Peto Web (docs.css). Màu diff của bản sáng
được chỉnh tay cho đủ tương phản. Không vẽ nền chung: chỉ các khung (tin của bạn, khối công cụ, ô nhập) có nền riêng,
để nền của chính terminal hiện ra ở mọi chỗ khác (chủ web chọn ngày 2026-10-12).
"""

from __future__ import annotations

import os

DARK = {
    "primary": "#ee9cad", "on_primary": "#0a0a0a", "secondary": "#5c9cf5", "accent": "#9d7cd8",
    "error": "#e06c75", "warning": "#f5a742", "success": "#7fd88f", "info": "#56b6c2",
    "text": "#eeeeee", "muted": "#808080", "bg": "#0a0a0a", "panel": "#141414", "element": "#1e1e1e",
    "popup": "#262626", "border": "#484848", "hover": "#2c2c2c",
    "diff_added": "#4fd6be", "diff_removed": "#c53b53", "hunk": "#828bb8",
    "added_bg": "#20303b", "removed_bg": "#37222c", "line_number": "#8f8f8f",
    "added_number_bg": "#1b2b34", "removed_number_bg": "#2d1f26",
    "keyword": "#9d7cd8", "function": "#ee9cad", "string": "#7fd88f", "number": "#f5a742", "comment": "#808080",
    "inline_code": "#7fd88f", "link": "#ee9cad", "heading": "#9d7cd8", "quote": "#e5c07b",
}

LIGHT = {
    "primary": "#b3345b", "on_primary": "#ffffff", "secondary": "#7b5bb6", "accent": "#d68c27",
    "error": "#d1383d", "warning": "#b26b0e", "success": "#3d9a57", "info": "#318795",
    "text": "#1a1a1a", "muted": "#7a7a7a", "bg": "#ffffff", "panel": "#f4f4f4", "element": "#ebebeb",
    "popup": "#e2e2e2", "border": "#b8b8b8", "hover": "#dcdcdc",
    "diff_added": "#1e725c", "diff_removed": "#c53b53", "hunk": "#5a6098",
    "added_bg": "#d5ece4", "removed_bg": "#f7dde0", "line_number": "#7a7a7a",
    "added_number_bg": "#c5e2d8", "removed_number_bg": "#efcdd2",
    "keyword": "#7b5bb6", "function": "#b3345b", "string": "#3d9a57", "number": "#b26b0e", "comment": "#7a7a7a",
    "inline_code": "#3d9a57", "link": "#b3345b", "heading": "#7b5bb6", "quote": "#8a6d1f",
}

# Ký hiệu. Cửa sổ console cổ (conhost với Consolas) thiếu chữ Braille và vài ký hiệu, nên dùng bộ dự phòng.
RICH = {"spinner": "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "search": "✱", "web": "◈", "warn": "△", "done": "▣", "tool": "⚙", "write": "✎",
        "scan_on": "■", "scan_off": "⬝"}
PLAIN = {"spinner": "-\\|/", "search": "*", "web": "@", "warn": "!", "done": "■", "tool": "#", "write": ">",
         "scan_on": "■", "scan_off": "·"}


def blend(color: str, background: str, alpha: float) -> str:
    """Màu ``color`` phủ lên ``background`` với độ đục ``alpha``: dùng cho chữ mờ đi như "+ Đã nghĩ"."""
    a = [int(color[index:index + 2], 16) for index in (1, 3, 5)]
    b = [int(background[index:index + 2], 16) for index in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(alpha * x + (1 - alpha) * y) for x, y in zip(a, b))


def rich_terminal() -> bool:
    """Windows Terminal và VS Code tự vẽ ký tự khối, chữ Braille; cửa sổ console cổ thì không chắc."""
    return bool(os.environ.get("WT_SESSION")) or os.environ.get("TERM_PROGRAM") == "vscode" or os.name != "nt"


class Theme:
    def __init__(self, name: str = "dark", *, colors: bool = True, rich: bool | None = None):
        self.name = name if name in {"dark", "light"} else "dark"
        self.colors = colors
        self._values = dict(LIGHT if self.name == "light" else DARK)
        self.glyphs = RICH if (rich_terminal() if rich is None else rich) else PLAIN
        self._values["thought"] = blend(self._values["warning"], self._values["bg"], 0.6)
        self._values["dim_text"] = blend(self._values["text"], self._values["bg"], 0.8)
        # Vùng chữ đang chọn bằng chuột ở màn hình toàn phần: hồng nhạt, chữ vẫn đọc rõ.
        self._values["selection"] = blend(self._values["primary"], self._values["bg"],
                                          0.25 if self.name == "light" else 0.35)

    def __getattr__(self, name: str) -> str | None:
        values = self.__dict__.get("_values")
        if values is None or name not in values:
            raise AttributeError(name)
        # NO_COLOR: không màu chữ, không màu nền; thanh và ký hiệu vẫn còn.
        return values[name] if self.__dict__["colors"] else None


def load(*, colors: bool = True) -> Theme:
    """Theme theo PETO_AGENT_THEME (dark hoặc light); mặc định tối."""
    return Theme(os.environ.get("PETO_AGENT_THEME", "dark").strip().lower(), colors=colors)
