"""Chân cố định (chủ web chọn ngày 2026-10-12, như Claude Code): ô nhập luôn nằm ở đáy, kể cả lúc Peto đang làm.

Hội thoại vẫn in vào lịch sử cuộn của terminal như trước. Mỗi lần có chữ mới: xóa phần chân đang vẽ, in chữ, vẽ lại
chân. Không dùng vùng cuộn (DECSTBM): dòng trôi ra khỏi vùng cuộn có lề trên bị console bỏ đi, không vào lịch sử cuộn.

Một luồng riêng đọc phím suốt phiên, nên gõ được tin tiếp theo trong lúc Peto làm (Enter thì tin chờ tới khi yêu cầu
xong). Ctrl+C lúc Peto đang làm dừng yêu cầu; Esc hai lần cũng vậy. Ctrl+C lúc ô trống mà Peto rảnh thì thoát, như
trước. Câu hỏi quyền thay chỗ ô nhập cho tới khi được trả lời.
"""

from __future__ import annotations

import contextlib
import queue
import signal
import threading
import time
from collections.abc import Callable

from ..line_editor import INTERRUPT, SUBMIT, EditorState, Key
from .. import images as image_files
from ..ui import terminal_size
from . import scanner
from .text import Line, S, clip, hovered, render

SYNC_ON, SYNC_OFF = "\x1b[?2026h", "\x1b[?2026l"
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
# Esc lần hai trong ngần này giây thì dừng yêu cầu.
ESC_WINDOW = 3.0
# Phím tới trong ngần này giây sau khi khung duyệt hiện chưa được tính: đó thường là phím gõ cho ô nhập.
PANEL_GUARD = 0.3
TICK_MS = 100
# Lúc bận, màn hình toàn phần vẽ lại theo nhịp của hoạt ảnh Knight Rider (scanner.FRAME_MS) để không khung nào bị bỏ.
SCAN_TICK_MS = scanner.FRAME_MS
BUSY_PLACEHOLDER = "Nhắn thêm cho Peto; tin được chèn vào bước kế tiếp…"


class Panel:
    """Một câu hỏi đang chờ trả lời ở chỗ ô nhập (quyền, đăng nhập trình duyệt), hoặc hộp trả lời /btw.

    ``on_interrupt``: Ctrl+C trả lời khung bằng giá trị này thay vì dừng Peto (hộp /btw chỉ đóng lại)."""

    def __init__(self, render_lines: Callable[[], list[Line]], handle: Callable[[Key], str | None],
                 on_interrupt: str | None = None):
        self.render_lines = render_lines
        self.handle = handle
        self.on_interrupt = on_interrupt
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
        # Gõ trong lúc Peto đang làm (theo opencode, CLI 0.20.0): tin thường chèn vào bước kế tiếp để lái việc đang làm
        # (steers), lệnh gạch chéo chờ yêu cầu xong mới chạy (queued). Mỗi mục là (chữ, ảnh, bản chụp tin để vẽ khung).
        self.steers: list[tuple[str, list, object]] = []
        self.queued: list[tuple[str, list, object]] = []
        # /btw (CLI 0.23.0): ``side`` nhận chữ vừa gửi, trả None nếu không phải /btw, "" nếu đã nhận câu hỏi, hay một
        # lời nhắc giữ chữ lại trong ô. Gọi trong khóa của màn hình nên chỉ được mở luồng rồi trả về ngay.
        # ``side_pending`` là các câu hỏi bên lề đang chờ trả lời, hiện ngay trên ô nhập.
        self.side: Callable[[str], str | None] | None = None
        self.side_pending: list[str] = []
        # Chỗ bấm được đang có chuột rê trên nó (``Target.key``, CLI 0.24.0); chỉ màn hình toàn phần bắt chuột.
        self.hover_key = None
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
        # /editor đang nhường terminal cho trình soạn: không vẽ gì, khung /btw tới lúc đó chờ tới khi quay lại.
        self._suspended = False

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

    @contextlib.contextmanager
    def suspended(self, message: str = ""):
        """Nhường cả terminal cho chương trình khác (trình soạn của /editor, CLI 0.23.0), rồi bật lại như cũ: tắt luồng
        phím và chế độ phím thô, rời màn hình của Peto, in ``message``; xong thì vẽ lại toàn bộ."""
        self._suspended = True
        self.stop()
        if message:
            self.out.write(message + "\r\n")
            self.out.flush()
        try:
            yield
        finally:
            self._stop.clear()
            self._suspended = False
            self.start()

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

    def _paint(self, line: Line) -> Line:
        """Tô chỗ bấm đang có chuột rê trên nó."""
        if self.hover_key is None:
            return line
        theme = self.ui.theme
        # Nền khi rê chuột đậm hơn nền ô nhập: khung tin của bạn sáng hẳn lên chứ không chỉ nhích một chút.
        return hovered(line, self.hover_key, text=theme.text, bg=theme.hover)

    def _footer_lines(self, width: int, height: int):
        """Các hàng của phần chân đã đổi thành mã terminal, bề ngang từng hàng và chỗ con trỏ."""
        lines, cursor = self._footer_source(width, height)
        return ([render(self._paint(line), self.ui.colors) for line in lines], [line.width() for line in lines], cursor)

    def _footer_source(self, width: int, height: int) -> tuple[list[Line], tuple[int, int]]:
        """Các hàng của phần chân và chỗ con trỏ: khung duyệt nếu đang hỏi, không thì dòng trạng thái và ô nhập."""
        from . import prompt as prompt_view

        ui = self.ui
        theme = ui.theme
        if self.panel is not None:
            rows = self.panel.render_lines()
            return [Line([S("  ")]) + line for line in rows], (len(rows) - 1, 0)
        above: list[Line] = []
        for label, waiting in (("Nhắn thêm: ", self.steers), ("Chờ chạy: ", self.queued)):
            for text, _, _ in waiting:
                above.append(Line([S("   ↳ ", theme.muted), S(label, theme.muted),
                                   S(clip(" ".join(text.split()), 200), theme.dim_text)]))
        for question in self.side_pending:
            above.append(Line([S("   "), S(ui.spinner_frame() + " ", theme.secondary), S("/btw ", theme.text),
                               S(clip(" ".join(question.split()), 200), theme.muted)]))
        if self.busy:
            spin = ui.spinner_frame()
            body = (self.status or "… Peto đang làm").removeprefix("… ")
            body = ui.status_body(body)
            above.append(Line([S("   "), S(spin + " ", theme.primary), S(body, theme.muted)]))
            if self.plan_line:
                above.append(Line([S("   "), S("▶ ", theme.warning), S(self.plan_line, theme.muted)]))
        footer_line = None
        planning = getattr(ui, "mode", "build") == "plan"
        if self.busy:
            # Dãy Knight Rider như opencode, tô theo chế độ đang dùng (CLI 0.22.0); vòng quay trên vẫn giữ.
            scan = scanner.spans(theme, theme.secondary if planning else theme.primary) + [S("  ")]
            if time.monotonic() < self._esc_until:
                footer_line = Line(scan + [S("esc", theme.warning, b=True), S(" lần nữa để dừng yêu cầu", theme.warning)])
            else:
                footer_line = Line(scan + [S("esc esc", theme.text), S(" hoặc ", theme.muted), S("ctrl+c", theme.text),
                                           S(" dừng · Enter nhắn thêm cho Peto", theme.muted)])
        placeholder = BUSY_PLACEHOLDER if self.busy else prompt_view.PLACEHOLDER
        meta, accent = self.meta, None
        if planning:
            # Chế độ Lập kế hoạch: nhãn thay chữ "Peto" ở hàng thông tin, thanh đổi màu, dòng chân nói cách quay lại.
            meta, accent = ["Lập kế hoạch", *self.meta[1:]], theme.secondary
            if footer_line is None:
                footer_line = Line([S("shift+tab", theme.text), S(" hoặc ", theme.muted), S("/plan", theme.text),
                                    S(" về chế độ làm việc", theme.muted)]
                                   + ([S(" · " + self.footer, theme.muted)] if self.footer else []))
        frame = prompt_view.frame(self.state, theme, width=width, height=height, meta=meta, footer=self.footer,
                                  colors=ui.colors, footer_line=footer_line, above=above, placeholder=placeholder,
                                  accent=accent)
        return frame.source, (frame.cursor_row, frame.cursor_col)

    def _draw(self, committed: str = "") -> None:
        if self._suspended:
            return
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

    def raw_write(self, text: str) -> None:
        """Mã không vẽ gì (tiêu đề cửa sổ, chuông): ghi trong khóa để không chen vào giữa một lần vẽ."""
        with self.lock:
            self._write(text)

    def _submitted(self) -> None:
        """Vừa gửi một tin (gửi ngay hay để chờ)."""

    def take_steers(self) -> list[tuple[str, list, object]]:
        """Các tin nhắn thêm đang chờ chèn vào bước kế tiếp; lấy ra là hết."""
        with self.lock:
            steers, self.steers = self.steers, []
            if steers:
                self._draw()
        return steers

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
            if self.steers or self.queued:
                # Yêu cầu xong trước khi kịp chèn tin nhắn thêm: tin đó thành yêu cầu kế tiếp.
                text, images, sent = (self.steers or self.queued).pop(0)
                self.busy = True
                try:
                    self.ui.commit_user(sent)
                except Exception:
                    pass  # Tin đã lưu; lỗi vẽ không được làm mất lần nhận.
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

    def ask(self, render_lines: Callable[[], list[Line]], handle: Callable[[Key], str | None], *,
            on_interrupt: str | None = None) -> str:
        """Hiện một khung ở chỗ ô nhập rồi chờ trả lời. Khung khác đang mở (câu hỏi quyền, hộp /btw tới từ luồng
        khác) thì chờ nó đóng trước; phiên đã dừng thì trả chuỗi rỗng."""
        panel = Panel(render_lines, handle, on_interrupt)
        while True:
            with self.lock:
                if self.panel is None and not self._suspended:
                    self.panel = panel
                    # Thời gian bỏ qua phím tính từ lúc khung thật sự hiện, không từ lúc nó bắt đầu chờ.
                    panel.opened = time.monotonic()
                    self._draw()
                    break
            if self._stop.is_set() and not self._suspended:
                return ""
            time.sleep(0.05)
        try:
            while not panel.done.wait(0.1):
                if self._stop.is_set() and not self._suspended:
                    break
        finally:
            with self.lock:
                if self.panel is panel:
                    self.panel = None
                self._draw()
        return panel.answer

    # ---- Luồng đọc phím

    def _wait_ms(self) -> int:
        """Chờ phím bao lâu trước khi vẽ lại hoạt ảnh. Chân cố định vẽ lại cả phần chân mỗi lần nên giữ nhịp 0,1 giây."""
        return TICK_MS

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
                if not self.console.wait(self._wait_ms()):
                    self._tick()
                    continue
                keys = self.console.keys()
                if not keys:
                    # Chuột lướt qua (không bấm) cũng đánh thức console mà không thành phím nào: không vẽ lại vì nó,
                    # nhưng vẫn giữ nhịp vòng quay khi chuột cứ di mãi.
                    if time.monotonic() - self._last_draw >= self._wait_ms() / 1000:
                        self._tick()
                    continue
                with self.lock:
                    # Chuột rê qua mà không sang chỗ bấm khác thì không có gì đổi: khỏi vẽ lại, chỉ giữ nhịp hoạt ảnh.
                    redraw = False
                    for key in keys:
                        redraw = self._key(key) is not False or redraw
                    if redraw:
                        self._draw()
                if not redraw and time.monotonic() - self._last_draw >= self._wait_ms() / 1000:
                    self._tick()
            except Exception:  # noqa: BLE001 - luồng phím không được chết lặng lẽ, nhưng cũng không làm sập phiên
                time.sleep(0.2)

    def _tick(self) -> None:
        """Mỗi 0,1 giây khi không có phím: vẽ lại vòng quay, cỡ cửa sổ mới, hoặc gỡ lời nhắc Esc đã hết hạn."""
        with self.lock:
            columns, _ = self.size()
            animated = (self.busy or bool(self.side_pending)) and self.panel is None
            esc_expired = self._esc_until and time.monotonic() >= self._esc_until
            if esc_expired:
                self._esc_until = 0.0
            if animated or columns != self._columns or esc_expired or self.status != self._drawn_status:
                self._draw()

    def _key(self, key: Key) -> None:
        if self.panel is not None:
            if key.name == "interrupt":
                if self.panel.on_interrupt is not None:
                    self.panel.answer = self.panel.on_interrupt
                    self.panel.done.set()
                    self.panel = None
                    return
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
        if key.name == "backtab":
            # Shift+Tab đổi chế độ làm việc ↔ Lập kế hoạch, như Claude Code; áp dụng từ bước kế tiếp.
            toggle = getattr(self.ui, "toggle_mode", None)
            if toggle is not None:
                toggle()
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
        if kind == SUBMIT and text.strip() and self.side is not None:
            # /btw không vào hội thoại: câu hỏi chạy ở luồng riêng, kể cả lúc Peto đang làm (theo opencode).
            note = self.side(text)
            if note is not None:
                state.clear()
                if note:
                    # Chưa có câu hỏi: giữ "/btw " trong ô để gõ tiếp, kèm lời nhắc.
                    state.insert(text.strip() + " ")
                    state.notice = note
                return
        if kind == SUBMIT and text.strip():
            from . import prompt as prompt_view
            sent = prompt_view.Sent(state)
            admit = getattr(self.ui, 'runtime_admit', None)
            if admit:
                try:
                    admit(text, images, delivery='queue' if self.busy and text.lstrip().startswith('/')
                          else 'steer' if self.busy else 'input')
                except Exception:
                    state.notice = 'Chưa lưu được tin nhắn. Nội dung vẫn ở ô nhập; kiểm tra runtime rồi thử lại.'
                    return
            if self.busy:
                (self.queued if text.lstrip().startswith("/") else self.steers).append((text, images, sent))
            else:
                self.busy = True
                self.status = None
                try:
                    self.ui.commit_user(sent)
                except Exception:
                    pass  # Runtime giữ receipt, không phụ thuộc khung tin được vẽ hay chưa.
                self.submitted.put((text, images))
            state.clear()
            self._submitted()
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
