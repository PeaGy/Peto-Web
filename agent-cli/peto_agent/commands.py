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


COMMANDS = (
    Command("/moi", "Bắt đầu hội thoại mới"),
    Command("/resume", "Mở lại hội thoại gần nhất của thư mục này"),
    Command("/retry", "Thử lại bước bị gián đoạn kết nối"),
    Command("/diff", "Xem bản sửa tệp trực tiếp gần nhất đã lưu của dự án"),
    Command("/undo", "Hoàn tác bản sửa tệp trực tiếp gần nhất, kể cả sau khi đóng CLI"),
    Command("/compact", "Tóm tắt hội thoại dài (dùng một lượt gọi model)"),
    Command("/init", "Khảo sát dự án rồi viết AGENTS.md (dùng vài bước)"),
    Command("/permissions", "Xem quyền chạy lệnh đã ghi nhớ", (("clear", "Xóa mọi quyền ghi nhớ trong phiên"),)),
    # Lựa chọn thật theo quyền của tài khoản được đặt lại bằng use_models() sau khi hỏi máy chủ.
    Command("/model", "Xem hoặc đổi model", (("peto", "Peto · Mặc định"),)),
    Command("/effort", "Xem hoặc đổi mức suy nghĩ: thap, vua, cao",
            (("thap", "Nhanh, suy nghĩ ít"), ("vua", "Cân bằng giữa nhanh và kỹ"),
             ("cao", "Suy nghĩ kỹ hơn, mỗi bước tính 2 bước"))),
    Command("/usage", "Số bước và token đã dùng hôm nay"),
    Command("/help", "Xem các lệnh"),
    Command("/thoat", "Thoát peto"),
)


@dataclass(frozen=True)
class Suggestion:
    # Cả dòng lệnh khi chọn gợi ý này, ví dụ "/resume" hay "/effort cao".
    text: str
    # Chữ hiện ở cột đầu của bảng: tên lệnh, hoặc giá trị khi đang gõ phần sau lệnh.
    label: str
    description: str
    has_options: bool = False


def model_option(model: dict) -> tuple[str, str]:
    """("sol", "5.6 Sol · Mạnh nhất, của OpenAI · tính 4 bước") từ một model máy chủ trả trong /api/agent/me."""
    cost = int(model.get("step_cost") or 1)
    description = f"{model.get('label') or model['key']} · {model.get('description') or ''}".rstrip(" ·")
    return model["key"], description + (f" · tính {cost} bước" if cost > 1 else "")


def use_models(models: list[dict]) -> None:
    """Đặt lựa chọn của /model theo các model tài khoản này được dùng, để bảng gợi ý không mời chọn model bị cấm."""
    global COMMANDS
    options = tuple(model_option(model) for model in models)
    COMMANDS = tuple(replace(command, options=options) if command.name == "/model" else command
                     for command in COMMANDS)


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
        starts = [command for command in COMMANDS if fold(command.name).startswith(typed)]
        inside = [command for command in COMMANDS
                  if len(typed) > 1 and command not in starts and typed[1:] in fold(command.name)]
        return [Suggestion(command.name, command.name, command.description, bool(command.options))
                for command in starts + inside]
    command = next((command for command in COMMANDS if fold(command.name) == typed), None)
    value = rest.lstrip(" ")
    if command is None or not command.options or " " in value:
        return []
    return [Suggestion(f"{command.name} {option}", option, description)
            for option, description in command.options if fold(option).startswith(fold(value))]
