"""Chân cố định (chủ web chọn ngày 2026-10-12, như Claude Code): ô nhập luôn nằm ở đáy, kể cả lúc Peto đang làm.

Hội thoại vẫn in vào lịch sử cuộn của terminal như trước. Mỗi lần có chữ mới: xóa phần chân đang vẽ, in chữ, vẽ lại
chân. Không dùng vùng cuộn (DECSTBM): dòng trôi ra khỏi vùng cuộn có lề trên bị console bỏ đi, không vào lịch sử cuộn.

Một luồng riêng đọc phím suốt phiên, nên gõ được tin tiếp theo trong lúc Peto làm (Enter thì tin chờ tới khi yêu cầu
xong). Ctrl+C lúc Peto đang làm dừng yêu cầu; Esc hai lần cũng vậy. Ctrl+C lúc ô trống mà Peto rảnh thì thoát, như
trước. Câu hỏi quyền thay chỗ ô nhập cho tới khi được trả lời.
"""

from __future__ import annotations

import queue
import signal
import threading
import time
from collections.abc import Callable

from ..line_editor import INTERRUPT, SUBMIT, EditorState, Key
from .. import images as image_files
from ..ui import terminal_size
from .text import Line, S, cells, clip, render

SYNC_ON, SYNC_OFF = "\x1b[?2026h", "\x1b[?2026l"
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
# Esc lần hai trong ngần này giây thì dừng yêu cầu.
ESC_WINDOW = 3.0
# Phím tới trong ngần này giây sau khi khung duyệt hiện chưa được tính: đó thường là phím gõ cho ô nhập.
PANEL_GUARD = 0.3
TICK_MS = 100
BUSY_PLACEHOLDER = "Gõ tin tiếp theo; Peto gửi khi làm xong việc này…"


class Panel:
    """Một câu hỏi đang chờ trả lời ở chỗ ô nhập (quyền, đăng nhập trình duyệt)."""

    def __init__(self, render_lines: Callable[[], list[Line]], handle: Callable[[Key], str | None]):
        self.render_lines = render_lines
        self.handle = handle
        self.opened = time.monotonic()
        self.answer: str | None = None
        self.done = threading.Event()


class FooterEngine:
    def __init__(self, ui, editor, *, size: Callable[[], tuple[int, int]] = terminal_size,
                 interrupt: Callable[[], None] | None = None):
        self.ui = ui
        self.editor = editor
        self.console = editor.console
        self.out = ui.out
        self.state: EditorState = editor.state
        self.size = size
        self.interrupt = interrupt or (lambda: signal.raise_signal(signal.SIGINT))
        self.lock = threading.RLock()
        self.submitted: queue.Queue = queue.Queue()
        # Tin gõ trong lúc Peto đang làm: (chữ, ảnh, các hàng khung tin).
        self.queued: list[tuple[str, list, list[Line]]] = []
        self.busy = False
        self.panel: Panel | None = None
        self.status: str | None = None
        self.meta: list[str] = []
        self.footer = ""
        self.plan_line: str | None = None
        self._esc_until = 0.0
        # Bề rộng (ô) của từng hàng chân đang vẽ, và hàng có con trỏ: để xóa đúng chỗ, kể cả khi cửa sổ vừa hẹp lại.
        self._rows: list[int] = []
        self._cursor = (0, 0)
        self._columns = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._raw = None
        self._last_draw = 0.0
        self._drawn_status: str | None = None

    # ---- Vòng đời

    def start(self) -> None:
        self._raw = self.console.raw()
        self._raw.__enter__()
        self._thread = threading.Thread(target=self._run, name="peto-input", daemon=True)
        self._thread.start()
        with self.lock:
            self._draw()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self.lock:
            self._write(self._erase() + SHOW_CURSOR)
            self._rows = []
        if self._raw is not None:
            self._raw.__exit__(None, None, None)
            self._raw = None

    # ---- Vẽ

    def _write(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()

    def _erase(self) -> str:
        """Lùi con trỏ lên hàng đầu của phần chân rồi xóa tới cuối màn hình.

        Cửa sổ hẹp lại thì Windows Terminal, VS Code và console mới tự xuống dòng các hàng cũ: tính lại số hàng thật
        theo bề rộng mới để không xóa nhầm chữ đã in phía trên.
        """
        if not self._rows:
            return ""
        row, _ = self._cursor
        # Mỗi hàng chân tính là một dòng, kể cả khi cửa sổ vừa hẹp lại. Terminal nào tự xuống dòng các hàng cũ thì có
        # thể còn sót một mảnh chân cũ phía trên; còn tính theo kiểu tự xuống dòng mà terminal không làm vậy (ConPTY,
        # thử ngày 2026-10-12) thì xóa mất chữ đã in, tệ hơn nhiều.
        return (f"\x1b[{row}A" if row else "") + "\r\x1b[J"

    def _footer_lines(self, width: int, height: int):
        """Các hàng của phần chân và chỗ con trỏ: khung duyệt nếu đang hỏi, không thì dòng trạng thái và ô nhập."""
        from . import prompt as prompt_view

        ui = self.ui
        theme = ui.theme
        if self.panel is not None:
            rows = self.panel.render_lines()
            return ([" " * 2 + render(line, ui.colors) for line in rows], [2 + line.width() for line in rows],
                    (len(rows) - 1, 0))
        above: list[Line] = []
        for text, _, _ in self.queued:
            above.append(Line([S("   ↳ ", theme.muted), S("Chờ gửi: ", theme.muted),
                               S(clip(" ".join(text.split()), 200), theme.dim_text)]))
        if self.busy:
            spin = ui.spinner_frame()
            body = (self.status or "… Peto đang làm").removeprefix("… ")
            body = ui.status_body(body)
            above.append(Line([S("   "), S(spin + " ", theme.primary), S(body, theme.muted)]))
            if self.plan_line:
                above.append(Line([S("   "), S("▶ ", theme.warning), S(self.plan_line, theme.muted)]))
        footer_line = None
        if self.busy:
            if time.monotonic() < self._esc_until:
                footer_line = Line([S("esc", theme.warning, b=True), S(" lần nữa để dừng yêu cầu", theme.warning)])
            else:
                footer_line = Line([S("esc esc", theme.text), S(" hoặc ", theme.muted), S("ctrl+c", theme.text),
                                    S(" dừng · Enter gửi tin chờ Peto làm xong", theme.muted)])
        placeholder = BUSY_PLACEHOLDER if self.busy else prompt_view.PLACEHOLDER
        frame = prompt_view.frame(self.state, theme, width=width, height=height, meta=self.meta, footer=self.footer,
                                  colors=ui.colors, footer_line=footer_line, above=above, placeholder=placeholder)
        widths = [cells(_plain(line)) for line in frame.lines]
        return frame.lines, widths, (frame.cursor_row, frame.cursor_col)

    def _draw(self, committed: str = "") -> None:
        columns, height = self.size()
        lines, widths, cursor = self._footer_lines(columns, height)
        parts = [SYNC_ON, HIDE_CURSOR, self._erase(), committed]
        parts.append("\r\n".join(lines))
        if up := len(lines) - 1 - cursor[0]:
            parts.append(f"\x1b[{up}A")
        parts.append("\r")
        if cursor[1]:
            parts.append(f"\x1b[{cursor[1]}C")
        parts.append(SHOW_CURSOR + SYNC_OFF)
        self._write("".join(parts))
        self._rows, self._cursor, self._columns = widths, cursor, columns
        self._last_draw = time.monotonic()
        self._drawn_status = self.status

    def commit(self, text: str) -> None:
        """In chữ vào lịch sử cuộn, phía trên phần chân."""
        if not text:
            return
        with self.lock:
            self._draw(text.replace("\r\n", "\n").replace("\n", "\r\n"))

    def refresh(self) -> None:
        with self.lock:
            self._draw()

    def set_status(self, text: str | None) -> None:
        with self.lock:
            if text == self.status:
                return
            self.status = text
            # Vòng quay vẽ lại 10 lần mỗi giây trong _tick; ở đây chỉ vẽ ngay khi chữ thật sự đổi.
            if time.monotonic() - self._last_draw > 0.05 or text is None:
                self._draw()

    # ---- Ô nhập và câu hỏi

    def idle(self, meta: list[str], footer: str) -> None:
        with self.lock:
            self.busy = False
            self.status = None
            self.plan_line = None
            self.meta, self.footer = meta, footer
            self._draw()

    def take(self) -> tuple[str, list]:
        """Tin kế tiếp: tin đã gõ trong lúc Peto làm, hoặc chờ người dùng gửi. Ctrl+C lúc ô trống thì thoát."""
        with self.lock:
            if self.queued:
                text, images, panel = self.queued.pop(0)
                self.busy = True
                self.ui.commit_user(panel)
                return text, images
        while True:
            try:
                item = self.submitted.get(timeout=0.2)
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                # Ctrl+C rơi đúng lúc tin vừa gửi mà yêu cầu chưa bắt đầu: không vì thế mà thoát peto.
                if self.busy:
                    continue
                raise
            if item is INTERRUPT:
                raise KeyboardInterrupt
            return item

    def ask(self, render_lines: Callable[[], list[Line]], handle: Callable[[Key], str | None]) -> str:
        panel = Panel(render_lines, handle)
        with self.lock:
            self.panel = panel
            self._draw()
        try:
            while not panel.done.wait(0.1):
                pass
        finally:
            with self.lock:
                if self.panel is panel:
                    self.panel = None
                self._draw()
        return panel.answer

    # ---- Luồng đọc phím

    def _run(self) -> None:
        last_mode_check = 0.0
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if now - last_mode_check > 1:
                    last_mode_check = now
                    ensure = getattr(self.console, "ensure_raw", None)
                    if ensure is not None:
                        ensure()
                if not self.console.wait(TICK_MS):
                    self._tick()
                    continue
                keys = self.console.keys()
                with self.lock:
                    for key in keys:
                        self._key(key)
                    self._draw()
            except Exception:  # noqa: BLE001 - luồng phím không được chết lặng lẽ, nhưng cũng không làm sập phiên
                time.sleep(0.2)

    def _tick(self) -> None:
        """Mỗi 0,1 giây khi không có phím: vẽ lại vòng quay, cỡ cửa sổ mới, hoặc gỡ lời nhắc Esc đã hết hạn."""
        with self.lock:
            columns, _ = self.size()
            animated = self.busy and self.panel is None and self.ui.animated
            esc_expired = self._esc_until and time.monotonic() >= self._esc_until
            if esc_expired:
                self._esc_until = 0.0
            if animated or columns != self._columns or esc_expired or self.status != self._drawn_status:
                self._draw()

    def _key(self, key: Key) -> None:
        if self.panel is not None:
            if key.name == "interrupt":
                self.interrupt()
                return
            if time.monotonic() - self.panel.opened < PANEL_GUARD:
                return
            answer = self.panel.handle(key)
            if answer is not None:
                self.panel.answer = answer
                self.panel.done.set()
                self.panel = None
            return
        state = self.state
        if key.name == "interrupt":
            if self.busy:
                self._esc_until = 0.0
                self.interrupt()
            elif state.text:
                state.handle(key)
            else:
                self.submitted.put(INTERRUPT)
            return
        if key.name == "escape" and self.busy and not state.items():
            if time.monotonic() < self._esc_until:
                self._esc_until = 0.0
                self.interrupt()
            else:
                self._esc_until = time.monotonic() + ESC_WINDOW
            return
        if key.name == "image":
            self._attach(self.editor.clipboard)
            return
        if key.name == "paste" and (paths := image_files.dropped_paths(key.text)):
            self._attach(lambda: self.editor.files(paths))
            return
        result = state.handle(key)
        if result is None:
            return
        kind, text = result
        images = state.attached()
        if kind == SUBMIT and text.strip():
            from . import prompt as prompt_view
            panel = prompt_view.user_panel(state, self.ui.theme, self.size()[0] - 1)
            if self.busy:
                self.queued.append((text, images, panel))
            else:
                self.busy = True
                self.status = None
                self.ui.commit_user(panel)
                self.submitted.put((text, images))
        state.clear()

    def _attach(self, load) -> None:
        state = self.state
        state.notice = "Đang đọc ảnh…"
        self._draw()
        try:
            found = load()
        except image_files.ImageError as err:
            state.notice = err.message
            return
        state.notice = None
        state.insert_images(found)


def _plain(text: str) -> str:
    from .text import ANSI
    return ANSI.sub("", text)
