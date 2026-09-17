"""Khung nhập có nền riêng và bảng gợi ý lệnh khi gõ "/", đọc từng phím trong console Windows.

input() chỉ trả chữ về khi người dùng bấm Enter, nên muốn hiện gợi ý ngay lúc gõ thì phải tự đọc phím. Mô-đun chỉ dùng
thư viện chuẩn và chia ba phần:

- ``EditorState``: chữ đang gõ, con trỏ, lịch sử và gợi ý. Thuần Python nên test được.
- ``layout``: xếp chữ thành các hàng vừa khung terminal, thêm bảng gợi ý và tính chỗ đặt con trỏ. Cũng thuần Python.
- ``WindowsConsole``: đọc phím bằng ``ReadConsoleInputW``, nhận ra lúc dán, bật và trả lại chế độ console.

Bộ gõ tiếng Việt như Unikey, EVKey sửa chữ bằng cách gửi phím xóa rồi gửi ký tự mới, nên ô nhập xóa đúng một ký tự
Unicode mỗi lần xóa, như các ô nhập khác của Windows. Không phải console Windows (ống dẫn, tệp, hệ điều hành khác) hoặc
đặt ``PETO_AGENT_SIMPLE_INPUT=1`` thì phiên dùng lại input() như cũ.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from . import images as image_files
from .commands import Suggestion, suggestions

SUBMIT, INTERRUPT = "submit", "interrupt"
MAX_ITEMS = 8
# Từ 3 phím chữ trở lên tới cùng một lúc là đang dán, hoặc bộ gõ gửi cả cụm chữ: gom lại chèn một lần.
PASTE_MIN_KEYS = 3
# Đoạn dán từ 4 dòng hoặc dài hơn 1000 ký tự thì chỉ hiện "[Đã dán N dòng]"; lúc gửi vẫn gửi đủ.
COLLAPSE_LINES = 4
COLLAPSE_CHARS = 1000
# Mỗi đoạn dán thu gọn, và mỗi ảnh gửi kèm, là một ký tự trong vùng dùng riêng U+100000 trở đi: đoạn dán ở nửa đầu,
# ảnh ở nửa sau. Chữ gõ hay dán vào bị bỏ ký tự vùng này.
PASTE_BASE = 0x100000
IMAGE_BASE = 0x108000
MAX_PASTES = IMAGE_BASE - PASTE_BASE
MAX_IMAGES = 0x10FFFE - IMAGE_BASE
READING_IMAGE = "Đang đọc ảnh…"
TEXT_KEYS = {"char": "", "enter": "\r", "newline": "\n", "tab": "\t"}

HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"
INPUT_PLACEHOLDER = "Nhờ Peto làm gì đó…"


@dataclass(frozen=True)
class Key:
    """Một phím đã hiểu nghĩa.

    ``name`` là char, paste, enter, newline, tab, backspace, delete, left, right, up, down, home, end, escape hoặc
    interrupt (Ctrl+C). ``text`` là chữ của char và paste.
    """

    name: str
    text: str = ""
    ctrl: bool = False


def clean(text: str, keep: str = "") -> str:
    """Bỏ ký tự điều khiển, nửa cặp surrogate lẻ và ký tự vùng dùng làm đại diện đoạn dán."""
    return "".join(char for char in text if char in keep
                   or (unicodedata.category(char) not in ("Cc", "Cs") and ord(char) < PASTE_BASE))


def char_width(char: str) -> int:
    if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def display_width(text: str) -> int:
    return sum(char_width(char) for char in text)


def clip(text: str, width: int) -> str:
    """Cắt chữ cho vừa ``width`` cột, thêm "…" khi phải cắt."""
    if display_width(text) <= width:
        return text
    kept, used = [], 0
    for char in text:
        used += char_width(char)
        if used > width - 1:
            break
        kept.append(char)
    return "".join(kept) + "…"


def wrap(text: str, width: int) -> list[str]:
    """Ngắt chữ thành các dòng không quá ``width`` cột, ngắt ở dấu cách; một từ dài hơn cả dòng thì bị cắt."""
    lines, current = [], ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and display_width(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return [clip(line, width) for line in lines]


class EditorState:
    def __init__(self, suggest: Callable[[str], list[Suggestion]] = suggestions):
        self.suggest = suggest
        self.pastes: list[str] = []
        # Ảnh đã dán trong phiên, đánh số [Ảnh 1], [Ảnh 2]… theo thứ tự dán như Claude Code.
        self.images: list[image_files.Image] = []
        self.history: list[str] = []
        self.clear()

    def clear(self) -> None:
        self.text = ""
        self.cursor = 0
        # Gợi ý đang chọn; None khi chưa chọn gì, lúc đó Enter gửi đúng chữ đã gõ.
        self.selected: int | None = None
        self.dismissed = False
        self.finished = False
        # Dòng nhắc màu vàng dưới ô nhập, như "Clipboard chưa có ảnh"; phím kế tiếp là mất.
        self.notice: str | None = None
        self._browsing: int | None = None
        self._draft = ""

    def items(self) -> list[Suggestion]:
        if self.dismissed or self.finished:
            return []
        return self.suggest(self.text)

    def is_paste(self, char: str) -> bool:
        return PASTE_BASE <= ord(char) < PASTE_BASE + len(self.pastes)

    def is_image(self, char: str) -> bool:
        return IMAGE_BASE <= ord(char) < IMAGE_BASE + len(self.images)

    def label(self, char: str) -> str:
        """Chữ hiện thay cho ký tự đại diện: "[Đã dán 42 dòng]" hay "[Ảnh 1]"."""
        if self.is_image(char):
            return f"[Ảnh {ord(char) - IMAGE_BASE + 1}]"
        text = self.pastes[ord(char) - PASTE_BASE]
        lines = text.count("\n") + 1
        return f"[Đã dán {lines} dòng]" if lines > 1 else f"[Đã dán {len(text)} ký tự]"

    def expanded(self) -> str:
        """Chữ sẽ gửi: đoạn dán được trả lại đủ, ảnh thành nhãn [Ảnh N] để Peto biết người dùng nhắc tới ảnh nào."""
        return "".join(self.pastes[ord(char) - PASTE_BASE] if self.is_paste(char)
                       else self.label(char) if self.is_image(char) else char for char in self.text)

    def attached(self) -> list[tuple[int, image_files.Image]]:
        """Các ảnh còn nằm trong ô nhập, theo thứ tự xuất hiện, kèm số của ảnh."""
        found: list[tuple[int, image_files.Image]] = []
        for char in self.text:
            if self.is_image(char):
                number = ord(char) - IMAGE_BASE + 1
                if all(number != known for known, _ in found):
                    found.append((number, self.images[number - 1]))
        return found

    def insert_images(self, images: list[image_files.Image]) -> None:
        markers = []
        for image in images:
            if len(self.images) >= MAX_IMAGES:
                break
            self.images.append(image)
            markers.append(chr(IMAGE_BASE + len(self.images) - 1) + " ")
        self._insert("".join(markers))

    def handle(self, key: Key) -> tuple[str, str] | None:
        """Xử lý một phím. Trả ("submit", chữ) khi gửi, ("interrupt", "") khi bấm Ctrl+C lúc ô trống, còn lại None."""
        name = key.name
        self.notice = None
        items = self.items()
        if name == "interrupt":
            if not self.text:
                return INTERRUPT, ""
            self._edit("", 0, len(self.text))
        elif name == "char":
            self._insert(clean(key.text))
        elif name == "paste":
            self._insert(self._paste(key.text))
        elif name == "newline":
            self._insert("\n")
        elif name == "enter":
            if items and self.selected is not None:
                self._edit(items[self.selected].text, 0, len(self.text))
            return self._submit()
        elif name == "tab":
            if items:
                choice = items[self.selected or 0]
                self._edit(choice.text + (" " if choice.has_options else ""), 0, len(self.text))
        elif name == "escape":
            if items:
                self.dismissed = True
            elif self.text:
                self._edit("", 0, len(self.text))
        elif name in ("up", "down"):
            step = -1 if name == "up" else 1
            if self._browsing is not None:
                self._recall(step)
            elif items:
                if self.selected is None:
                    self.selected = 0 if step > 0 else len(items) - 1
                else:
                    self.selected = (self.selected + step) % len(items)
            elif not self._move_line(step):
                self._recall(step)
        elif name == "left":
            self.cursor = self._word_start() if key.ctrl else max(0, self.cursor - 1)
        elif name == "right":
            self.cursor = self._word_end() if key.ctrl else min(len(self.text), self.cursor + 1)
        elif name == "home":
            self.cursor = self.text.rfind("\n", 0, self.cursor) + 1
        elif name == "end":
            end = self.text.find("\n", self.cursor)
            self.cursor = len(self.text) if end < 0 else end
        elif name == "backspace":
            if self.cursor:
                self._edit("", self._word_start() if key.ctrl else self.cursor - 1, self.cursor)
        elif name == "delete":
            if self.cursor < len(self.text):
                self._edit("", self.cursor, self._word_end() if key.ctrl else self.cursor + 1)
        return None

    def _insert(self, text: str) -> None:
        if text:
            self._edit(text, self.cursor, self.cursor)

    def _edit(self, new: str, start: int, end: int) -> None:
        self.text = self.text[:start] + new + self.text[end:]
        self.cursor = start + len(new)
        # Sửa chữ thì thôi duyệt lịch sử: mũi tên lại dùng cho bảng gợi ý và cho các dòng.
        self._browsing = None
        self._changed()

    def _show(self, text: str) -> None:
        self.text, self.cursor = text, len(text)
        self._changed()

    def _changed(self) -> None:
        self.dismissed = False
        # Chưa gõ gì sau "/" hay sau "/effort " thì chưa chọn sẵn, để Enter không chạy lệnh người dùng chưa chọn.
        self.selected = None if self.text == "/" or self.text.endswith(" ") else 0

    def _submit(self) -> tuple[str, str]:
        if self.text.strip() and (not self.history or self.history[-1] != self.text):
            self.history.append(self.text)
        self.finished = True
        self.cursor = len(self.text)
        return SUBMIT, self.expanded()

    def _paste(self, text: str) -> str:
        text = clean(text.replace("\r\n", "\n").replace("\r", "\n"), keep="\n\t").rstrip("\n")
        long = text.count("\n") + 1 >= COLLAPSE_LINES or len(text) > COLLAPSE_CHARS
        if long and len(self.pastes) < MAX_PASTES:
            self.pastes.append(text)
            return chr(PASTE_BASE + len(self.pastes) - 1)
        return text

    def _recall(self, step: int) -> None:
        if self._browsing is None:
            if step > 0 or not self.history:
                return
            self._draft = self.text
            index = len(self.history) - 1
        else:
            index = max(0, self._browsing + step)
        if index >= len(self.history):
            self._browsing = None
            self._show(self._draft)
            return
        self._browsing = index
        self._show(self.history[index])

    def _move_line(self, step: int) -> bool:
        start = self.text.rfind("\n", 0, self.cursor) + 1
        column = self.cursor - start
        if step < 0:
            if not start:
                return False
            previous = self.text.rfind("\n", 0, start - 1) + 1
            self.cursor = min(previous + column, start - 1)
            return True
        end = self.text.find("\n", self.cursor)
        if end < 0:
            return False
        following = self.text.find("\n", end + 1)
        self.cursor = min(end + 1 + column, len(self.text) if following < 0 else following)
        return True

    def _word_start(self) -> int:
        index = self.cursor
        while index and self.text[index - 1].isspace():
            index -= 1
        while index and not self.text[index - 1].isspace():
            index -= 1
        return index

    def _word_end(self) -> int:
        index, size = self.cursor, len(self.text)
        while index < size and self.text[index].isspace():
            index += 1
        while index < size and not self.text[index].isspace():
            index += 1
        return index


@dataclass
class Frame:
    lines: list[str]
    cursor_row: int
    cursor_col: int


def _no_paint(text: str, color: str | None) -> str:
    return text


def layout(state: EditorState, *, prompt: str, width: int, height: int, paint=_no_paint,
           boxed: bool = False, footer: str = "", placeholder: str = INPUT_PLACEHOLDER) -> Frame:
    """Các hàng cần vẽ và chỗ đặt con trỏ. Hàng nối tiếp thụt vào bằng độ rộng dấu nhắc."""
    # Không bao giờ viết vào cột cuối, để khỏi phụ thuộc cách từng terminal tự xuống dòng.
    usable = max(width, 8) - 1
    # Khi gửi/hủy, khung và các dòng phụ biến mất; chỉ tin đã nhập nằm trong lịch sử cuộn.
    boxed = boxed and not state.finished
    prompt = clip(prompt, max(1, usable - 2))
    indent = display_width(prompt)

    def input_paint(text: str, color: str | None = None) -> str:
        if boxed:
            return paint(text, "input_marker" if color == "cyan" else "input")
        return paint(text, color)

    rows: list[list[str]] = [[input_paint(prompt, "yellow")]]
    row_widths = [indent]
    column = indent
    cursor: tuple[int, int] | None = None
    for index, char in enumerate(state.text):
        if index == state.cursor:
            cursor = (len(rows) - 1, column)
        if char == "\n":
            rows.append([input_paint(" " * indent)])
            row_widths.append(indent)
            column = indent
            continue
        color = None
        if state.is_paste(char) or state.is_image(char):
            glyph, color = clip(state.label(char), usable - indent), "cyan"
        else:
            glyph = "    " if char == "\t" else char
        size = display_width(glyph)
        if column + size > usable and column > indent:
            rows.append([input_paint(" " * indent)])
            row_widths.append(indent)
            column = indent
            if index == state.cursor:
                cursor = (len(rows) - 1, column)
        rows[-1].append(input_paint(glyph, color))
        column += size
        row_widths[-1] = column
    if cursor is None:
        cursor = (len(rows) - 1, column)
    if boxed and not state.text:
        hint = clip(placeholder, usable - indent)
        rows[0].append(paint(hint, "input_hint"))
        row_widths[0] += display_width(hint)

    popup = []
    if state.notice and not state.finished:
        popup.extend(paint(f"  {line}", "yellow") for line in wrap(state.notice, usable - 2))
    notice_rows = len(popup)
    items = state.items()
    if items:
        label_width = max(display_width(item.label) for item in items)
        for index, item in enumerate(items):
            chosen = index == state.selected
            head = clip(f"  {'❯' if chosen else ' '} {item.label}{' ' * (label_width - display_width(item.label))}  ",
                        usable)
            description = clip(item.description, usable - display_width(head))
            popup.append(paint(head, "cyan" if chosen else None) + (paint(description, "dim") if description else ""))

    # Dành chỗ cho padding, footer và ít nhất một dòng nhập. Popup không được đẩy con trỏ khỏi màn hình thấp.
    budget = max(1, height - 1)
    padding = 2 if boxed and budget >= 4 + bool(popup) else 0
    footer_lines = ([paint("  " + clip(clean(footer), usable - 2), "dim")]
                    if boxed and footer and budget >= padding + 2 else [])
    popup_space = min(MAX_ITEMS + notice_rows, max(0, budget - padding - len(footer_lines) - 1))
    selected_row = notice_rows + (state.selected or 0) if items else 0
    popup_top = min(max(0, selected_row - popup_space + 1), max(0, len(popup) - popup_space))
    popup = popup[popup_top:popup_top + popup_space]
    available = max(1, budget - padding - len(footer_lines) - len(popup))
    top = 0
    if len(rows) > available:
        top = min(max(0, cursor[0] - available + 1), len(rows) - available)
    lines = []
    for index in range(top, min(len(rows), top + available)):
        row = "".join(rows[index])
        if boxed:
            row += paint(" " * max(0, usable - row_widths[index]), "input")
        lines.append(row)
    if padding:
        blank = paint(" " * usable, "input")
        lines = [blank, *lines, blank]
    return Frame(lines + popup + footer_lines, cursor[0] - top + padding // 2, cursor[1])


def group_paste(keys: list[Key]) -> list[Key]:
    """Gom các phím chữ tới cùng lúc thành một lần dán.

    Enter nằm giữa đoạn dán là xuống dòng. Enter đứng cuối vẫn là gửi, trừ khi đoạn đó đã có Enter khác (dán nhiều dòng):
    bộ gõ gửi chữ vừa gõ kèm Enter trong cùng một lúc thì người dùng vẫn gửi được.
    """
    submit = None
    if keys and keys[-1].name == "enter" and not any(key.name in ("enter", "newline") for key in keys[:-1]):
        submit, keys = keys[-1], keys[:-1]
    grouped: list[Key] = []
    run: list[Key] = []

    def flush() -> None:
        if len(run) >= PASTE_MIN_KEYS:
            grouped.append(Key("paste", "".join(key.text or TEXT_KEYS[key.name] for key in run)))
        else:
            grouped.extend(Key("newline") if key.name == "enter" else key for key in run)
        run.clear()

    for key in keys:
        if key.name in TEXT_KEYS:
            run.append(key)
        else:
            flush()
            grouped.append(key)
    flush()
    if submit is not None:
        grouped.append(submit)
    return grouped


# --- Console Windows --------------------------------------------------------

KEY_EVENT = 0x0001
VK_BACK, VK_TAB, VK_RETURN, VK_MENU, VK_ESCAPE, VK_V = 0x08, 0x09, 0x0D, 0x12, 0x1B, 0x56
NAVIGATION = {0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x2E: "delete"}
RIGHT_ALT, LEFT_ALT, RIGHT_CTRL, LEFT_CTRL, SHIFT = 0x01, 0x02, 0x04, 0x08, 0x10
# Tắt Ctrl+C thành tín hiệu, nhập theo dòng, tự in phím, sự kiện cửa sổ và chuột, và mã VT cho phím.
RAW_MODE_OFF = 0x0001 | 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0200
READ_CHUNK = 512
PASTE_GRACE_MS = 15
MAX_PASTE_KEYS = 400_000
WAIT_OBJECT_0 = 0


def translate(vk: int, char: str, state: int) -> Key | None:
    """Một lần nhấn phím của console thành ``Key``; None với phím không dùng (Shift, F1…)."""
    ctrl = bool(state & (LEFT_CTRL | RIGHT_CTRL))
    if vk == VK_RETURN or char in ("\r", "\n"):
        return Key("newline") if char == "\n" or state & (SHIFT | LEFT_CTRL | RIGHT_CTRL) else Key("enter")
    if vk == VK_BACK or char in ("\b", "\x7f"):
        return Key("backspace", ctrl=ctrl)
    if vk == VK_TAB or char == "\t":
        return Key("tab")
    if vk == VK_ESCAPE or char == "\x1b":
        return Key("escape")
    if vk in NAVIGATION and char < " ":
        return Key(NAVIGATION[vk], ctrl=ctrl)
    if char == "\x03":
        return Key("interrupt")
    if state & (LEFT_ALT | RIGHT_ALT) and not ctrl and (vk == VK_V or char in ("v", "V")):
        # Alt+V dán ảnh trong clipboard như Claude Code trên Windows: Ctrl+V đã bị terminal giữ để dán chữ.
        # AltGr là Ctrl+Alt phải, nên bàn phím dùng AltGr+V để gõ ký tự không bị nhầm.
        return Key("image")
    if char == "\x17":
        # Ctrl+W, và là thứ terminal của VS Code gửi khi bấm Ctrl+Backspace.
        return Key("backspace", ctrl=True)
    if char >= " " and char != "\x7f":
        return Key("char", char)
    return None


class WindowsConsole:
    """Đọc phím thô từ console Windows. Tạo không được (stdin không phải console) thì ném OSError."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class KeyEvent(ctypes.Structure):
            _fields_ = [("key_down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vk", wintypes.WORD),
                        ("scan", wintypes.WORD), ("char", wintypes.WCHAR), ("state", wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("key", KeyEvent), ("raw", ctypes.c_byte * 16)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("type", wintypes.WORD), ("event", Event)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle, dword, count = wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
        signatures = {
            "GetStdHandle": ([dword], handle),
            "GetConsoleMode": ([handle, count], wintypes.BOOL),
            "SetConsoleMode": ([handle, dword], wintypes.BOOL),
            "ReadConsoleInputW": ([handle, ctypes.POINTER(InputRecord), dword, count], wintypes.BOOL),
            "GetNumberOfConsoleInputEvents": ([handle, count], wintypes.BOOL),
            "WaitForSingleObject": ([handle, dword], dword),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel32, name)
            function.argtypes, function.restype = arguments, result
        self._ctypes, self._dword = ctypes, dword
        self._kernel32 = kernel32
        self._handle = kernel32.GetStdHandle(-10 & 0xFFFFFFFF)
        self._buffer = (InputRecord * READ_CHUNK)()
        self._high = ""
        self._mode()

    def _check(self, ok) -> None:
        if not ok:
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def _mode(self) -> int:
        mode = self._dword()
        self._check(self._handle and self._kernel32.GetConsoleMode(self._handle, self._ctypes.byref(mode)))
        return mode.value

    @contextlib.contextmanager
    def raw(self):
        original = self._mode()
        self._check(self._kernel32.SetConsoleMode(self._handle, original & ~RAW_MODE_OFF))
        try:
            yield
        finally:
            self._kernel32.SetConsoleMode(self._handle, original)

    def keys(self) -> list[Key]:
        """Chờ tới khi có phím, rồi lấy luôn mọi phím đang chờ; đoạn dán được gom lại."""
        keys = self._read() + self._drain()
        # Sau Enter, hay giữa một cụm chữ, chờ thêm chút: phần còn lại của đoạn dán thường tới ngay sau đó.
        if keys and (keys[-1].name == "enter" or sum(key.name in TEXT_KEYS for key in keys) >= PASTE_MIN_KEYS):
            keys += self._drain(grace=True)
        return group_paste(keys)

    def _pending(self) -> int:
        count = self._dword()
        self._check(self._kernel32.GetNumberOfConsoleInputEvents(self._handle, self._ctypes.byref(count)))
        return count.value

    def _drain(self, grace: bool = False) -> list[Key]:
        keys: list[Key] = []
        signaled = False
        while len(keys) < MAX_PASTE_KEYS:
            if self._pending():
                keys += self._read()
                signaled = False
            elif (not grace or signaled
                  or self._kernel32.WaitForSingleObject(self._handle, PASTE_GRACE_MS) != WAIT_OBJECT_0):
                break
            else:
                signaled = True
        return keys

    def _read(self) -> list[Key]:
        count = self._dword()
        self._check(self._kernel32.ReadConsoleInputW(self._handle, self._buffer, READ_CHUNK,
                                                     self._ctypes.byref(count)))
        keys: list[Key] = []
        for record in self._buffer[:count.value]:
            if record.type != KEY_EVENT:
                continue
            event = record.event.key
            char = event.char
            # Gõ Alt + số trên bàn phím số thì ký tự tới lúc nhả Alt; các lần nhả phím khác bỏ qua.
            if not event.key_down and not (event.vk == VK_MENU and char >= " "):
                continue
            if "\ud800" <= char <= "\udbff":
                self._high = char
                continue
            if "\udc00" <= char <= "\udfff":
                if not self._high:
                    continue
                char = (self._high + char).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
                self._high = ""
            key = translate(event.vk, char, event.state)
            if key is not None:
                keys.extend([key] * max(1, event.repeat))
        return keys


class LineEditor:
    def __init__(self, console, out, *, size: Callable[[], tuple[int, int]] = shutil.get_terminal_size,
                 suggest: Callable[[str], list[Suggestion]] = suggestions,
                 clipboard: Callable[[], list[image_files.Image]] | None = None,
                 files: Callable[[list], list[image_files.Image]] | None = None):
        self.console = console
        self.out = out
        self.size = size
        self.state = EditorState(suggest)
        self.clipboard = clipboard or image_files.from_clipboard
        self.files = files or image_files.from_files
        # Ảnh gửi kèm lượt nhập vừa xong: (số ảnh, ảnh).
        self.last_images: list[tuple[int, image_files.Image]] = []
        # Hàng đang có con trỏ, tính từ hàng dấu nhắc, để lần vẽ sau quay về đúng chỗ.
        self._row = 0
        self._pending: list[Key] = []
        self._boxed = False
        self._footer = ""

    def read(self, prompt: str, paint=_no_paint, *, boxed: bool = False, footer: str = "") -> str:
        """Đọc một lượt nhập. Ctrl+C lúc ô trống ném KeyboardInterrupt như input()."""
        state = self.state
        state.clear()
        self.last_images = []
        self._row = 0
        self._boxed, self._footer = boxed, footer
        result = None
        try:
            with self.console.raw():
                self._draw(prompt, paint)
                while result is None:
                    keys, self._pending = self._pending or self.console.keys(), []
                    for position, key in enumerate(keys):
                        if key.name == "image":
                            self._attach(prompt, paint, self.clipboard)
                            continue
                        # Kéo thả tệp ảnh vào terminal thì terminal dán đường dẫn tệp: đổi thành ảnh gửi kèm.
                        if key.name == "paste" and (paths := image_files.dropped_paths(key.text)):
                            self._attach(prompt, paint, lambda: self.files(paths))
                            continue
                        result = state.handle(key)
                        if result is not None:
                            self._pending = keys[position + 1:]
                            break
                    if keys and result is None:
                        self._draw(prompt, paint)
                state.finished = True
                self._draw(prompt, paint)
        except BaseException:
            # Lỗi đọc phím không được để nền ô nhập hoặc con trỏ ẩn ảnh hưởng phần trả lời tiếp theo.
            if boxed:
                state.finished = True
                with contextlib.suppress(OSError):
                    self._draw(prompt, paint)
                    self.out.write("\033[0m" + SHOW_CURSOR)
                    self.out.flush()
            raise
        kind, text = result
        if kind == INTERRUPT:
            raise KeyboardInterrupt
        self.last_images = state.attached()
        self.out.write("\r\n")
        self.out.flush()
        return text

    def _attach(self, prompt: str, paint, load: Callable[[], list[image_files.Image]]) -> None:
        state = self.state
        # Thu nhỏ ảnh lớn mất một lúc: báo trước để người dùng không tưởng peto bị treo.
        state.notice = READING_IMAGE
        self._draw(prompt, paint)
        try:
            found = load()
        except image_files.ImageError as err:
            state.notice = err.message
            return
        state.notice = None
        state.insert_images(found)

    def _draw(self, prompt: str, paint) -> None:
        columns, lines = self.size()
        frame = layout(self.state, prompt=prompt, width=columns, height=lines, paint=paint,
                       boxed=self._boxed, footer=self._footer)
        parts = [HIDE_CURSOR]
        if self._row:
            parts.append(f"\033[{self._row}A")
        parts.append("\r\033[J")
        parts.append("\r\n".join(frame.lines))
        if up := len(frame.lines) - 1 - frame.cursor_row:
            parts.append(f"\033[{up}A")
        parts.append("\r")
        if frame.cursor_col:
            parts.append(f"\033[{frame.cursor_col}C")
        parts.append(SHOW_CURSOR)
        self.out.write("".join(parts))
        self.out.flush()
        self._row = frame.cursor_row


def simple_input_requested() -> bool:
    return os.environ.get("PETO_AGENT_SIMPLE_INPUT", "").strip() not in ("", "0")


def create(out, enable_vt: Callable[[object], bool]) -> LineEditor | None:
    """Ô nhập có gợi ý khi chạy trong console Windows; None thì phiên dùng input() như cũ."""
    if os.name != "nt" or simple_input_requested():
        return None
    if not (hasattr(out, "isatty") and out.isatty() and sys.stdin is not None and sys.stdin.isatty()):
        return None
    if not enable_vt(out):
        return None
    try:
        return LineEditor(WindowsConsole(), out)
    except OSError:
        return None
