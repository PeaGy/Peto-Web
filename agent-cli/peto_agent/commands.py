"""Các lệnh gạch chéo trong phiên peto: dùng chung cho /help và bảng gợi ý hiện ra khi gõ "/"."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    # Giá trị đi sau lệnh, ví dụ mức của /effort: (giá trị, mô tả).
    options: tuple[tuple[str, str], ...] = ()
    # Lệnh cần gõ thêm chữ (/btw <câu hỏi>, /remember <ghi chú>): bấm chuột vào gợi ý thì điền lệnh, chưa chạy.
    takes_text: bool = False


# Shared with the web guide; runtime model/effort options are still supplied by the server.
from .catalog import commands as catalog_commands

COMMANDS = tuple(Command(item['name'], item['description'], tuple(tuple(option) for option in item['options']),
                         "<" in item.get("usage", ""))
                 for item in catalog_commands())
# Tên tiếng Việt cũ (/moi, /thoat, /nho…) vẫn gõ được nhưng không hiện trong gợi ý: chủ web chọn tên tiếng Anh cho
# quen tay từ CLI 0.20.0.
ALIASES = {alias: item['name'] for item in catalog_commands() for alias in item.get('aliases', [])}


def canonical(name: str) -> str:
    """Tên lệnh chính của một tên cũ ("/moi" thành "/new"); tên khác giữ nguyên."""
    return ALIASES.get(name, name)

@dataclass(frozen=True)
class Suggestion:
    # Cả dòng lệnh khi chọn gợi ý này, ví dụ "/resume" hay "/effort cao".
    text: str
    # Chữ hiện ở cột đầu của bảng: tên lệnh, hoặc giá trị khi đang gõ phần sau lệnh.
    label: str
    description: str
    has_options: bool = False
    takes_text: bool = False


def model_option(model: dict) -> tuple[str, str]:
    """("sol", "6 Sol · Mạnh nhất, của OpenAI · tính 4 bước") từ một model máy chủ trả trong /api/agent/me."""
    cost = int(model.get("step_cost") or 1)
    description = f"{model.get('label') or model['key']} · {model.get('description') or ''}".rstrip(" ·")
    return model["key"], description + (f" · tính {cost} bước" if cost > 1 else "")


def use_models(models: list[dict]) -> None:
    """Đặt lựa chọn của /model theo các model tài khoản này được dùng, để bảng gợi ý không mời chọn model bị cấm."""
    global COMMANDS
    options = tuple(model_option(model) for model in models)
    COMMANDS = tuple(replace(command, options=options) if command.name == "/model" else command
                     for command in COMMANDS)


def use_efforts(efforts: list[str]) -> None:
    """Chỉ gợi ý mức máy chủ hỗ trợ cho model đang chọn."""
    global COMMANDS
    choices = {"none": ("none", "Không suy luận"), "low": ("low", "Nhanh, suy nghĩ ít"),
               "medium": ("medium", "Cân bằng giữa nhanh và kỹ"), "high": ("high", "Cao · nhân đôi số bước"),
               "xhigh": ("xhigh", "Rất cao · nhân đôi số bước"), "max": ("max", "Tối đa · nhân đôi số bước")}
    options = tuple(choices[value] for value in efforts if value in choices)
    COMMANDS = tuple(replace(command, options=options,
                             description="Xem hoặc đổi mức suy nghĩ: " + ", ".join(value for value, _ in options))
                     if command.name == "/effort" else command for command in COMMANDS)


def fold(text: str) -> str:
    """Chữ thường không dấu, để gõ "/thoát" bằng bộ gõ tiếng Việt vẫn khớp "/thoat"."""
    decomposed = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def suggestions(text: str) -> list[Suggestion]:
    """Gợi ý cho dòng đang gõ; danh sách rỗng khi dòng đó không phải lệnh."""
    if not text.startswith("/") or "\n" in text:
        return []
    name, space, rest = text.partition(" ")
    typed = fold(name)
    if not space:
        # Gõ tên cũ (/nhớ, /thoát) thì gợi ý tên mới, để người quen tay vẫn tìm ra.
        starts = [command for command in COMMANDS if fold(command.name).startswith(typed)
                  or any(alias.startswith(typed) for alias, name in ALIASES.items() if name == command.name)]
        inside = [command for command in COMMANDS
                  if len(typed) > 1 and command not in starts and typed[1:] in fold(command.name)]
        return [Suggestion(command.name, command.name, command.description, bool(command.options), command.takes_text)
                for command in starts + inside]
    command = next((command for command in COMMANDS if fold(command.name) == typed), None)
    value = rest.lstrip(" ")
    if command is None or not command.options or " " in value:
        return []
    return [Suggestion(f"{command.name} {option}", option, description)
            for option, description in command.options if fold(option).startswith(fold(value))]
