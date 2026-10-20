"""Màn hình toàn phần, như Claude Code và opencode (chủ web chọn ngày 2026-10-12 sau khi xem cả hai).

Peto vẽ trên màn hình phụ của terminal (alternate screen, như ``vim``): đầu phiên và hội thoại ở trên, ô nhập ghim ở
đáy, thoát ra thì terminal trở lại y như trước khi gõ ``peto``. Hội thoại không nằm trong lịch sử cuộn của terminal nữa
nên Peto tự cuộn: lăn chuột, PgUp/PgDn (nửa màn hình), Ctrl+Home/Ctrl+End. Kéo chuột chọn chữ thì thả tay là chép;
giữ Shift khi kéo để chọn kiểu terminal.

Mỗi khối hội thoại giữ hàm vẽ của nó chứ không giữ chữ đã vẽ, nên đổi cỡ cửa sổ thì vẽ lại cả màn hình theo bề ngang
mới: không còn mảnh khung cũ sót lại như chân cố định ở VS Code. Mỗi lần vẽ chỉ ghi lại các hàng đổi, mỗi hàng ghi trọn
từ cột đầu rồi xóa tới cuối hàng (ConPTY gộp sai những lần ghi lẻ từng ô, Claude Code gặp ở Windows Terminal).
"""

from __future__ import annotations

import bisect
import os
import re
import threading
import time
from collections.abc import Callable

from .clipboard import copy_text
from ..line_editor import Key
from .footer import HIDE_CURSOR, SCAN_TICK_MS, SHOW_CURSOR, SYNC_OFF, SYNC_ON, TICK_MS, FooterEngine
from .text import (Line, S, Target, _split, cells, clickable, clip, crop, highlight, parse_ansi, render, target_at,
                   text_between, wrap)
from .theme import blend

ENTER_SCREEN, LEAVE_SCREEN = "\x1b[?1049h", "\x1b[?1049l"
PAD = 2
WHEEL_LINES = 3
TOAST_SECONDS = 2.5
# Đường dẫn hay địa chỉ dưới con trỏ khi Ctrl+bấm chuột.
LINK = re.compile(r"https?://\S+|[A-Za-z]:\\[^\s:*?\"<>|]+")


class Entry:
    """Một khối hội thoại: hàm vẽ ra các hàng theo bề ngang hiện tại, kèm bản vẽ gần nhất."""

    __slots__ = ("build", "pad", "_width", "_lines")

    def __init__(self, build: Callable[[], list[Line]], pad: bool = True):
        self.build = build
        self.pad = pad
        self._width: int | None = None
        self._lines: list[Line] = []

    def lines(self, width: int) -> list[Line]:
        if self._width != width:
            lines = self.build()
            if self.pad:
                lines = [Line([S(" " * PAD)] + line.spans) if line.spans else line for line in lines]
            self._lines, self._width = lines, width
        return self._lines

    def changed(self) -> None:
        self._width = None


class TextEntry(Entry):
    """Chữ in thẳng (đã có mã màu): gập lại theo bề ngang mới. Dòng chưa xong thì lần in sau viết tiếp vào."""

    __slots__ = ("text", "width")

    def __init__(self, width: Callable[[], int]):
        super().__init__(self._render, pad=False)
        self.text = ""
        self.width = width

    def _render(self) -> list[Line]:
        text = self.text[:-1] if self.text.endswith("\n") else self.text
        width = self.width()
        lines = []
        for raw in text.split("\n"):
            line = parse_ansi(raw.replace("\r", ""))
            lines += [Line(row) for row in wrap(line.spans, width, hard=True)] if line.spans else [Line()]
        return lines


class ScreenEngine(FooterEngine):
    fullscreen = True

    def __init__(self, ui, editor, *, size=None, interrupt=None, copy: Callable[[str], bool] = copy_text):
        kwargs = {"interrupt": interrupt}
        if size is not None:
            kwargs["size"] = size
        super().__init__(ui, editor, **kwargs)
        self.copy = copy
        self.entries: list[Entry] = []
        # Bám cuối hội thoại (chữ mới tới thì cuộn theo), hay đứng yên ở (khối, hàng trong khối) người dùng cuộn tới.
        self.follow = True
        self.anchor = (0, 0)
        # Vùng chọn: ((hàng, cột), (hàng, cột)) theo hàng của cả hội thoại; điểm bắt đầu kéo.
        self.selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self._drag: tuple[int, int] | None = None
        self.toast: tuple[str, float] | None = None
        self.full_repaint = os.environ.get("PETO_AGENT_FULL_REPAINT", "").strip() not in {"", "0"}
        self._version = 0
        self._layout_key: tuple | None = None
        self._lines: list[Line] = []
        self._starts: list[int] = []
        self._frame: list[str] = []
        self._size = (0, 0)
        self._full = True
        self._top = 0
        self._view = 0
        # Số hàng cố định trên cùng (thanh tên hội thoại, CLI 0.22.0); hội thoại bắt đầu ngay dưới.
        self._head = 0
        self._saved_size = (ui._width, ui._height)
        # Hàng đã vẽ ở từng hàng màn hình (None: không có chỗ bấm), để biết chuột đang ở chỗ bấm nào (CLI 0.24.0).
        self._hits: list[Line | None] = []
        # Chỗ bấm dưới nút chuột lúc nhấn, và ô nhấn: thả tại đó mới là bấm, kéo đi là chọn chữ như cũ.
        self._press_target: Target | None = None
        self._press_cell: tuple[int, int] | None = None

    # ---- Vòng đời

    def start(self) -> None:
        if hasattr(self.console, "mouse"):
            self.console.mouse = True
        try:
            self._raw = self.console.raw()
            self._raw.__enter__()
        except BaseException:
            if hasattr(self.console, "mouse"):
                self.console.mouse = False
            raise
        self._write(ENTER_SCREEN + HIDE_CURSOR + "\x1b[0m\x1b[H\x1b[2J")
        self._full = True
        self._thread = threading.Thread(target=self._run, name="peto-input", daemon=True)
        self._thread.start()
        with self.lock:
            self._draw()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self.lock:
            # Xóa màn hình phụ trước khi rời: trình vẽ WebGL của xterm.js (phát lại headless ngày 2026-10-12) có lúc
            # giữ nền các khung cũ trên màn hình chính dù ô đã trống.
            self._write("\x1b[0m\x1b[H\x1b[2J" + SHOW_CURSOR + LEAVE_SCREEN)
            self._rows = []
        if self._raw is not None:
            self._raw.__exit__(None, None, None)
            self._raw = None
        if hasattr(self.console, "mouse"):
            self.console.mouse = False
        self.ui._width, self.ui._height = self._saved_size

    # ---- Hội thoại

    def add(self, build: Callable[[], list[Line]], pad: bool = True) -> Entry:
        entry = Entry(build, pad)
        with self.lock:
            self.entries.append(entry)
            self.changed()
        return entry

    def commit(self, text: str) -> None:
        """Chữ in thẳng (lệnh gạch chéo, thông báo): nối vào khối chữ cuối nếu dòng trước chưa xong."""
        if not text:
            return
        with self.lock:
            last = self.entries[-1] if self.entries else None
            if not (isinstance(last, TextEntry) and not last.text.endswith("\n")):
                last = TextEntry(lambda: self.ui.width)
                self.entries.append(last)
            last.text += text
            last.changed()
            self.changed()

    def clear(self) -> None:
        """Xóa hội thoại trên màn hình (/new, /resume, /fork): bám cuối lại, bỏ vùng chọn."""
        with self.lock:
            self.entries = []
            self.follow, self.anchor = True, (0, 0)
            self.selection, self._drag = None, None
            self._full = True
            self.changed()

    def jump(self, entry: Entry) -> bool:
        """Cuộn tới một khối (/timeline "Nhảy tới"). Khối gần cuối thì vẫn bám cuối như khi tự cuộn tới đó."""
        with self.lock:
            if entry not in self.entries:
                return False
            self.follow, self.anchor = False, (self.entries.index(entry), 0)
            self._draw()
        return True

    def changed(self) -> None:
        """Có khối mới hay khối vừa đổi: vẽ lại."""
        with self.lock:
            self._version += 1
            self._draw()

    def _layout(self, width: int) -> tuple[list[Line], list[int]]:
        key = (width, self._version, len(self.entries))
        if key != self._layout_key:
            lines: list[Line] = []
            starts: list[int] = []
            for entry in self.entries:
                starts.append(len(lines))
                lines.extend(entry.lines(width))
            self._lines, self._starts, self._layout_key = lines, starts, key
        return self._lines, self._starts

    # ---- Vẽ

    def _draw(self, committed: str = "") -> None:
        if self._suspended:
            return
        columns, height = self.size()
        columns, height = max(columns, 20), max(height, 6)
        if (columns, height) != self._size:
            # Đổi cỡ: vẽ lại hết từ đầu, vùng chọn theo hàng cũ không còn đúng.
            self._full = True
            self.selection = None
            self._drag = None
        rows, cursor = self._compose(columns, height)
        full = self._full or len(rows) != len(self._frame)
        parts = [SYNC_ON, HIDE_CURSOR]
        if full:
            parts.append("\x1b[0m\x1b[H\x1b[2J")
        for index, row in enumerate(rows):
            if full or self.full_repaint or self._frame[index] != row:
                parts.append(f"\x1b[{index + 1};1H{row}\x1b[0m\x1b[K")
        parts.append(f"\x1b[{cursor[0] + 1};{cursor[1] + 1}H")
        if self.panel is None:
            parts.append(SHOW_CURSOR)
        parts.append(SYNC_OFF)
        self._write("".join(parts))
        self._frame, self._size, self._full = rows, (columns, height), False
        self._columns = columns
        self._last_draw = time.monotonic()
        self._drawn_status = self.status

    def _compose(self, columns: int, height: int) -> tuple[list[str], tuple[int, int]]:
        ui = self.ui
        # Mọi khối vẽ theo bề ngang ui.width (= cột - 1, không bao giờ chạm cột cuối).
        ui._width, ui._height = columns, height
        overlay = self.panel if self._overlaid() else None
        if overlay is not None:
            # Khung nổi: phía sau vẫn là ô nhập như lúc chờ gõ, chỉ tối đi.
            self.panel = None
            try:
                source, cursor = self._footer_source(columns, height)
            finally:
                self.panel = overlay
        else:
            source, cursor = self._footer_source(columns, height)
        if len(source) > height - 1:
            cut = len(source) - (height - 1)
            source = source[cut:]
            cursor = (max(0, cursor[0] - cut), cursor[1])
        footer = [render(self._paint(line), ui.colors) for line in source]
        width = columns - 1
        head_lines = self._title_lines(width) if height - len(footer) > 3 else []
        head = [render(line, ui.colors) for line in head_lines]
        view = height - len(footer) - len(head)
        lines, starts = self._layout(ui.width)
        total = len(lines)
        top = self._resolve_top(total, view, starts)
        self._top, self._view, self._head = top, view, len(head)
        rows = []
        hits: list[Line | None] = [None] * len(head)
        for index in range(view):
            number = top + index
            if number >= total:
                rows.append("")
                hits.append(None)
                continue
            line = crop(lines[number], width)
            hits.append(line)
            if self.selection is not None:
                line = self._highlight(line, number, width)
            rows.append(render(self._paint(line), ui.colors))
        more = self._overlay(total, top, view, width)
        if more is not None and view:
            rows[-1] = render(self._paint(more), ui.colors)
            hits[-1] = more
        if overlay is not None:
            return self._float(overlay, head_lines, hits[len(head):], source, columns, height)
        self._hits = hits + source
        return head + rows + footer, (len(head) + view + cursor[0], cursor[1])

    def _float(self, panel, head: list[Line], view: list[Line | None], footer: list[Line], columns: int,
               height: int) -> tuple[list[str], tuple[int, int]]:
        """Khung nổi như OpenCode: mọi hàng phía sau tối đi dưới lớp đen độ đục 150/255, khung canh giữa, cách đỉnh
        một phần tư màn hình. Bấm ra ngoài khung là đóng (Esc)."""
        from .dialog import BACKDROP

        ui = self.ui
        theme = ui.theme
        width = columns - 1
        shade = 1 - BACKDROP
        base = blend(theme.bg, "#000000", shade)
        outside = Target(("dialog-backdrop", id(panel)), lambda: Key("escape"), look="")

        def dim(line: Line | None) -> Line:
            spans = []
            for text, style in (line.spans if line is not None else []):
                faded = {key: value for key, value in style.items() if key not in {"act", "c16", "d"}}
                faded["fg"] = blend(style.get("fg") or theme.text, "#000000", shade)
                faded["bg"] = blend(style["bg"], "#000000", shade) if style.get("bg") else base
                faded["act"] = outside
                spans.append((text, faded))
            used = sum(cells(text) for text, _ in spans)
            if used < width:
                spans.append((" " * (width - used), {"bg": base, "act": outside}))
            return crop(Line(spans), width)

        rows = [dim(line) for line in head + list(view) + footer]
        rows = (rows + [dim(None)] * height)[:height]
        dialog = panel.render_lines()
        size = max((line.width() for line in dialog), default=0)
        left = max(0, (width - size) // 2)
        top = max(0, min(height // 4, height - len(dialog)))
        for offset, line in enumerate(dialog[:height]):
            row = top + offset
            before, _, after = _split(rows[row], [left, left + size])
            rows[row] = Line(before + crop(line, width - left).spans + after)
        self._hits = list(rows)
        return [render(self._paint(line), ui.colors) for line in rows], (height - 1, 0)

    def _title_rows(self, width: int) -> list[str]:
        return [render(line, self.ui.colors) for line in self._title_lines(width)]

    def _title_lines(self, width: int) -> list[Line]:
        """Thanh trên cùng như opencode: tên hội thoại đậm bên trái, thư mục mờ bên phải; chưa có tên thì không có."""
        ui = self.ui
        title = getattr(ui, "session_title", None)
        if not title:
            return []
        theme = ui.theme
        folder = getattr(ui, "folder_name", "") or ""
        right = f"  {folder} " if folder and width > 50 else " "
        left = Line([S(" " * PAD + " ", bg=theme.panel), S(clip(" ".join(title.split()), width - len(right) - PAD - 2),
                                                             theme.text, theme.panel, b=True)])
        gap = max(0, width - left.width() - len(right))
        row = Line(left.spans + [S(" " * gap, bg=theme.panel), S(right, theme.muted, theme.panel)])
        return [crop(row, width)]

    def _resolve_top(self, total: int, view: int, starts: list[int]) -> int:
        bottom = max(0, total - view)
        if self.follow or not starts:
            return bottom
        entry, offset = self.anchor
        entry = min(entry, len(starts) - 1)
        end = starts[entry + 1] if entry + 1 < len(starts) else total
        top = min(starts[entry] + offset, max(starts[entry], end - 1))
        if top >= bottom:
            self.follow = True
            return bottom
        return max(0, top)

    def _overlay(self, total: int, top: int, view: int, width: int) -> Line | None:
        """Hàng cuối khung hội thoại: còn bao nhiêu dòng bên dưới khi đang cuộn lên, hoặc thông báo ngắn (đã chép)."""
        theme = self.ui.theme
        if self.toast is not None:
            text, until = self.toast
            if time.monotonic() < until:
                return crop(Line([S("   "), S(text, theme.success)]), width)
            self.toast = None
        below = total - (top + view)
        if self.follow or below <= 0:
            return None
        # Bấm vào dòng này là về cuối, như "Jump to latest ↓" của opencode (CLI 0.24.0).
        latest = Target(("latest",), self._to_latest)
        spans = [S("   ")] + clickable([S(f" ↓ còn {below} dòng bên dưới ", theme.text, theme.element),
                                       S("  ctrl+end", theme.text), S(" hoặc bấm vào đây để về cuối", theme.muted)],
                                      latest)
        return crop(Line(spans), width)

    def _to_latest(self) -> None:
        self.follow = True
        self.hover_key = None

    def notify(self, message: str) -> None:
        """Thông báo ngắn ở hàng cuối khung hội thoại (đã chép…)."""
        with self.lock:
            self.toast = (message, time.monotonic() + TOAST_SECONDS)
            self._draw()

    def _highlight(self, line: Line, number: int, width: int) -> Line:
        (first_row, first_col), (last_row, last_col) = self.selection
        if not first_row <= number <= last_row:
            return line
        start = first_col if number == first_row else 0
        end = last_col + 1 if number == last_row else max(line.width(), start + 1)
        end = min(end, width)
        if end <= start:
            return line
        theme = self.ui.theme
        return highlight(line, start, end, theme.text if theme.selection else None, theme.selection)

    def _tick(self) -> None:
        with self.lock:
            size = self.size()
            animated = (self.busy or bool(self.side_pending)) and self.panel is None
            esc_expired = self._esc_until and time.monotonic() >= self._esc_until
            if esc_expired:
                self._esc_until = 0.0
            toast_expired = self.toast is not None and time.monotonic() >= self.toast[1]
            if (animated or esc_expired or toast_expired or self.status != self._drawn_status
                    or (max(size[0], 20), max(size[1], 6)) != self._size):
                self._draw()

    def _wait_ms(self) -> int:
        # Chỉ hàng đã đổi được ghi lại (thường chỉ hàng chân), nên vẽ theo từng khung của hoạt ảnh không tốn gì mấy.
        return SCAN_TICK_MS if self.busy and self.panel is None else TICK_MS

    # ---- Phím và chuột

    def _submitted(self) -> None:
        self.follow = True

    def ask(self, render_lines, handle, *, on_interrupt: str | None = None, overlay: bool = False,
            guard: bool = True) -> str:
        # Câu hỏi quyền nằm ở đáy; hội thoại về cuối để thấy Peto vừa làm gì trước khi hỏi. Hộp /btw (Ctrl+C chỉ đóng
        # hộp) không kéo màn hình đi: người dùng có thể đang cuộn lên đọc.
        if on_interrupt is None:
            with self.lock:
                self.follow = True
        return super().ask(render_lines, handle, on_interrupt=on_interrupt, overlay=overlay, guard=guard)

    def _overlaid(self) -> bool:
        return self.panel is not None and getattr(self.panel, "overlay", False)

    def _key(self, key) -> bool | None:
        name = key.name
        if self._overlaid() and name == "wheel":
            # Khung nổi đang mở: con lăn cuộn danh sách của khung, không cuộn hội thoại phía sau.
            return super()._key(key)
        if name == "wheel":
            self._scroll(-WHEEL_LINES if key.text == "up" else WHEEL_LINES)
            # Hội thoại vừa trôi dưới con trỏ: chỗ đang tô không còn nằm dưới chuột nữa.
            self.hover_key = None
            return
        if name == "mouse":
            return self._mouse(key)
        if name in {"resize", "redraw"}:
            self._full = True
            return
        if self.panel is None and name in {"pageup", "pagedown"}:
            step = max(1, self._view // 2)
            self._scroll(-step if name == "pageup" else step)
            return
        if self.panel is None and key.ctrl and name in {"home", "end"}:
            if name == "end":
                self.follow = True
            else:
                self.follow, self.anchor = False, (0, 0)
            return
        if self.selection is not None:
            if name == "interrupt":
                # Đang chọn chữ thì Ctrl+C là chép (như Claude Code), không dừng Peto.
                self._copy_selection()
                self.selection = None
                return
            self.selection = None
        super()._key(key)

    def _scroll(self, delta: int) -> None:
        lines, starts = self._layout(self.ui.width)
        total = len(lines)
        bottom = max(0, total - self._view)
        top = max(0, min(self._top + delta, bottom))
        if top >= bottom:
            self.follow = True
            return
        self.follow = False
        entry = max(0, bisect.bisect_right(starts, top) - 1)
        self.anchor = (entry, top - starts[entry]) if starts else (0, 0)
        self._top = top

    def _position(self, key) -> tuple[int, int] | None:
        """Hàng (của cả hội thoại) và cột dưới con trỏ chuột; None khi chuột nằm ở ô nhập."""
        y = key.y - self._head
        if not 0 <= y < self._view:
            return None
        return self._top + y, max(0, key.x)

    def _hit(self, x: int, y: int) -> Target | None:
        """Chỗ bấm được ở ô (x, y) của màn hình."""
        return target_at(self._hits[y], x) if 0 <= y < len(self._hits) else None

    def _hover(self, target: Target | None) -> bool:
        """Chuột sang chỗ khác: tô chỗ mới (khung chọn thì chuyển lựa chọn tới đó). False khi không có gì đổi."""
        key = target.key if target is not None else None
        if key == self.hover_key:
            return False
        self.hover_key = key
        if target is not None and target.hover is not None:
            target.hover()
        return True

    def _click(self, target: Target) -> None:
        result = target.run()
        if isinstance(result, Key):
            # Khung chọn trả phím của bàn phím (chọn dòng rồi Enter…): đi đúng đường đó, kể cả thời gian bỏ qua phím
            # ngay khi khung vừa hiện.
            self._key(result)

    def _mouse(self, key) -> bool | None:
        if key.text == "move":
            return self._hover(self._hit(key.x, key.y))
        if key.text == "release":
            target, self._press_target = self._press_target, None
            if self._drag is not None and self.selection is not None:
                self._copy_selection()
            elif target is not None:
                released = self._hit(key.x, key.y)
                if released is not None and released.key == target.key:
                    self._click(target)
            self._drag = None
            return
        if key.text == "drag":
            if self._press_cell is not None and (key.x, key.y) != self._press_cell:
                # Kéo khỏi chỗ vừa nhấn: là chọn chữ, không còn là bấm.
                self._press_target = None
            if self._drag is None:
                return
            y = key.y - self._head
            if y <= 0:
                self._scroll(-1)
            elif y >= self._view - 1:
                self._scroll(1)
            row = self._top + max(0, min(y, self._view - 1))
            point = (row, max(0, key.x))
            self.selection = tuple(sorted([self._drag, point]))
            return
        position = self._position(key)
        self.selection = None
        self._press_target, self._press_cell = self._hit(key.x, key.y), (key.x, key.y)
        if position is None or self._overlaid():
            # Khung nổi đang mở: chỉ bấm, không chọn chữ của hội thoại phía sau.
            self._drag = None
            return
        if key.ctrl and self._open_link(*position):
            self._drag = None
            self._press_target = None
            return
        if key.text == "double" and self._press_target is None:
            self._select_word(*position)
            self._drag = None
            return
        # Lần nhấn thứ hai của bấm đúp lên chỗ bấm được cũng chỉ là một lần bấm, không chọn từ.
        self._drag = position

    def _line(self, number: int) -> Line | None:
        lines, _ = self._layout(self.ui.width)
        return lines[number] if 0 <= number < len(lines) else None

    def _select_word(self, number: int, column: int) -> None:
        line = self._line(number)
        if line is None:
            return
        cells_of: list[tuple[int, str]] = []
        used = 0
        for char in line.text():
            cells_of.append((used, char))
            used += cells(char)
        index = next((position for position, (start, _) in enumerate(cells_of) if start >= column), len(cells_of))
        if index >= len(cells_of) or cells_of[index][1].isspace():
            return
        first = last = index
        while first > 0 and not cells_of[first - 1][1].isspace():
            first -= 1
        while last + 1 < len(cells_of) and not cells_of[last + 1][1].isspace():
            last += 1
        end = cells_of[last][0] + cells(cells_of[last][1]) - 1
        self.selection = ((number, cells_of[first][0]), (number, end))
        self._copy_selection()

    def _open_link(self, number: int, column: int) -> bool:
        """Ctrl+bấm vào địa chỉ web hay đường dẫn tệp thì mở nó. Terminal của VS Code tự mở link khi Ctrl+bấm."""
        if os.environ.get("TERM_PROGRAM") == "vscode" or os.name != "nt":
            return False
        line = self._line(number)
        if line is None:
            return False
        text = line.text()
        for match in LINK.finditer(text):
            if cells(text[:match.start()]) <= column < cells(text[:match.end()]):
                target = match.group(0).rstrip(".,;)")
                if target.startswith("http") or os.path.exists(target):
                    try:
                        os.startfile(target)  # noqa: S606 - người dùng tự Ctrl+bấm vào đúng chỗ này
                    except OSError:
                        return False
                    return True
        return False

    def selected_text(self) -> str:
        if self.selection is None:
            return ""
        (first_row, first_col), (last_row, last_col) = self.selection
        parts = []
        for number in range(first_row, last_row + 1):
            line = self._line(number)
            if line is None:
                continue
            start = first_col if number == first_row else 0
            end = last_col + 1 if number == last_row else max(line.width(), start)
            parts.append(text_between(line, start, end).rstrip())
        return "\n".join(parts).strip("\n")

    def _copy_selection(self) -> None:
        text = self.selected_text()
        if not text.strip():
            return
        copied = self.copy(text)
        message = f"✓ Đã chép {len(text)} ký tự" if copied else "Không chép được vào clipboard"
        self.toast = (message, time.monotonic() + TOAST_SECONDS)
