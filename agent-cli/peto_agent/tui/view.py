"""Giao diện terminal kiểu OpenCode cho Peto Agent (chủ web chọn từ bản mô phỏng ngày 2026-10-12).

Vẫn là dòng nối tiếp như trước: mọi thứ in vào lịch sử cuộn của terminal. Khác bản cũ:

- Tin của bạn là khung có thanh ┃ hồng; chữ của Peto thụt vào, tự gập dòng, có bảng và khối code tô màu.
- Mỗi công cụ là một dòng mờ ("→ Đọc app.py:1-40"); các lần đọc, tìm liền nhau gộp thành "→ Đã xem: …".
- Sửa tệp và chạy lệnh là khối nền nhạt: diff có cột số dòng, lệnh có phần cuối output và kết quả.
- Câu hỏi quyền là khung tạm ở cuối màn hình, chọn bằng ←/→ và Enter (phím y/a/s/l/n vẫn dùng được); trả lời xong
  khung biến mất, kết quả nằm ở khối của công cụ.
- Suy nghĩ của model chỉ hiện một dòng "+ Đã nghĩ: … · 3,2s"; cuối yêu cầu là "▣ Peto · model · thời gian · …".
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta

from .. import patch as patch_text, transcript
from ..events import Permission, RequestEnd, ToolCall, ToolDone
from ..formats import format_duration, format_tokens
from ..ui import (CLEAR_LINE, READ_ONLY_LINES, REFUSED_LINES, UI, _count, _page_details, _seconds, _viewport_label,
                  _where, action_details, output_lines, page_notes, visible)
from . import prompt as prompt_view
from .diff import Diff
from .markdown import Markdown
from ..line_editor import Key
from .text import Line, S, Target, clickable, clip, fit, parse_ansi, render, wrap
from .theme import load as load_theme

PAD = 2
# Đọc, liệt kê, tìm liền nhau thì gộp thành một dòng "Đã xem" như OpenCode.
EXPLORE: dict[str, Callable[[dict], str]] = {
    "read_file": lambda args: f"Đang đọc {args.get('path', '')}",
    "list_files": lambda args: f"Đang xem thư mục {args.get('path', '.')}",
    "search_files": lambda args: f'Đang tìm "{args.get("pattern", "")}"',
    "find_files": lambda args: f'Đang tìm tệp "{args.get("pattern", "")}"',
    "read_output": lambda args: f"Đang đọc output {args.get('output_id', '')}",
    "read_history": lambda args: "Đang tra lịch sử trước tóm tắt",
}
# Số hàng diff tối đa trong khối sửa tệp; cả diff đã hiện ở khung duyệt, và /diff xem đủ.
BLOCK_DIFF_ROWS = 40
OUTPUT_TAIL = 10
HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"
COLOR_ROLES = {"dim": "muted", "yellow": "warning", "red": "error", "green": "success", "blue": "secondary",
               "cyan": "info"}
LETTERS_HINT = "phím tắt"


def thought_title(text: str) -> str:
    """Tiêu đề ngắn cho phần suy nghĩ: tiêu đề **in đậm** cuối cùng, không có thì đoạn cuối."""
    heads = re.findall(r"\*\*(.+?)\*\*", text)
    if heads:
        return heads[-1].strip().rstrip(":")
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    return paragraphs[-1] if paragraphs else ""


class Option:
    def __init__(self, key: str, label: str):
        self.key, self.label = key, label


class SavedText:
    """Tin đã lưu, vẽ lại thành khung tin như ``prompt.Sent``: chữ đã gõ, nhãn ảnh ở cuối. Tin quá dài (thường là đoạn
    dán) chỉ giữ phần đầu, như lúc gửi đoạn dán dài chỉ hiện một nhãn."""

    LINES = 12

    def __init__(self, text: str, images=()):
        lines = text.split("\n")
        if len(lines) > self.LINES:
            lines = lines[:self.LINES - 2] + [f"… (còn {len(lines) - self.LINES + 2} dòng)"]
        self.text = "\n".join(lines) + "".join(" " + label for label in images)

    def is_paste(self, char: str) -> bool:
        return False

    def is_image(self, char: str) -> bool:
        return False

    def label(self, char: str) -> str:
        return char


class TerminalUI(UI):
    def bind_runtime(self, admit, pending):
        self.runtime_admit, self.runtime_pending = admit, pending

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme = load_theme(colors=self.colors)
        self._group: list[tuple[str, str]] = []
        self._last: str | None = None
        self._preview: tuple[str, dict] | None = None
        self._static_diff = False
        self.thinking_title: str | None = None
        # /thinking: in cả phần tóm tắt suy nghĩ dưới dòng "+ Đã nghĩ" (mặc định tắt như OpenCode).
        self.show_thoughts = False
        # Màn hình toàn phần (screen.py), hoặc chân cố định (footer.py) khi PETO_AGENT_UI=inline: bật khi phiên có ô
        # nhập đọc phím thô; None thì in nối tiếp như 0.16.
        self.engine = None
        # Khung trên màn hình của từng tin người dùng trong hội thoại, theo id của mục (giữ cả mục để id không bị dùng
        # lại): /timeline nhảy tới (CLI 0.22.0). Lệnh gạch chéo cũng thành khung tin nhưng không phải mục nào.
        self._user_entries: dict[int, tuple[dict, object]] = {}
        self._last_user_entry = None
        self._header: tuple | None = None

    def toggle_thoughts(self) -> bool:
        self.show_thoughts = not self.show_thoughts
        return self.show_thoughts

    # ---- Màn hình toàn phần, chân cố định

    @property
    def fullscreen(self) -> bool:
        return self.engine is not None and getattr(self.engine, "fullscreen", False)

    def start_footer(self) -> None:
        """Bật màn hình toàn phần như Claude Code (ô nhập ghim ở đáy, thoát ra terminal sạch như trước); gõ được cả lúc
        Peto đang làm. ``PETO_AGENT_UI=inline`` giữ kiểu chân cố định in vào lịch sử cuộn của 0.17."""
        if self.editor is None or self.engine is not None:
            return
        if os.environ.get("PETO_AGENT_UI", "").strip().lower() == "inline":
            from .footer import FooterEngine as Engine
        else:
            from .screen import ScreenEngine as Engine
        engine = Engine(self, self.editor, size=self.editor.size)
        try:
            engine.start()
        except OSError:
            return
        self.engine = engine

    @contextlib.contextmanager
    def suspended(self, message: str = ""):
        """Nhường terminal cho trình soạn của /editor (CLI 0.23.0); không có màn hình của Peto thì chỉ in ``message``."""
        if self.engine is None:
            with super().suspended(message):
                yield
            return
        with self.engine.suspended(message):
            yield

    def stop_footer(self) -> None:
        if self.engine is not None:
            engine, self.engine = self.engine, None
            engine.stop()

    def write(self, text: str, color: str | None = None) -> None:
        if self.engine is not None:
            self.engine.commit(self.paint(text, color))
            return
        super().write(text, color)

    def commit_user(self, sent, *, steer: bool = False) -> None:
        """Tin vừa gửi nằm lại trong hội thoại thành khung có thanh ┃ (``sent`` là ``prompt.Sent``). Tin nhắn thêm lúc
        Peto đang làm có thêm một dòng mờ nói nó được chèn giữa chừng."""
        self._flush_group()
        if self._last not in {None, "blank"}:
            self._out(lambda: [Line()], pad=False)
        holder: dict = {}

        def build() -> list[Line]:
            lines = prompt_view.user_panel(sent, self.theme, self.width)
            if holder.get("item") is None:
                return lines
            # Chỉ tin đã vào hội thoại mới bấm được (lệnh gạch chéo cũng hiện thành khung tin nhưng không có gì để làm).
            target = Target(("message", id(holder)), lambda: self._message_clicked(holder), look="bg")
            return [Line([(text, {**style, "act": target}) if style.get("bg") else (text, style)
                          for text, style in line.spans]) for line in lines]

        self._last_user_entry = self._out(build, pad=False)
        self._last_user_holder = holder
        if steer:
            self._out(lambda: [Line([S("   ↳ nhắn thêm lúc Peto đang làm", self.theme.muted)])])
        self._last = "user"

    def link_user_entry(self, item: dict | None) -> None:
        """Mục vừa thêm vào hội thoại là tin trong khung vừa vẽ (gửi, nhắn thêm, hay vẽ lại khi /resume)."""
        if item is not None and self._last_user_entry is not None:
            self._user_entries[id(item)] = (item, self._last_user_entry)
            holder = getattr(self, "_last_user_holder", None)
            if holder is not None:
                holder["item"] = item
                self._last_user_entry.changed()
                if self.engine is not None:
                    self.engine.changed()
        self._last_user_entry = None
        self._last_user_holder = None

    def _message_clicked(self, holder: dict) -> None:
        """Bấm vào tin của bạn (CLI 0.24.0, như opencode): Peto rảnh thì mở menu Chép / Tách hội thoại từ đây qua vòng
        lệnh (/timeline); Peto đang làm thì chỉ chép, vì tách hội thoại phải đợi việc đang làm xong."""
        item, engine = holder.get("item"), self.engine
        if item is None or engine is None:
            return None
        if engine.busy or engine.panel is not None:
            copied = self.copy(transcript.typed_text(item))
            engine.notify("✓ Đã chép tin · tách hội thoại được khi Peto làm xong" if copied
                          else "Không chép được vào clipboard")
            return None
        self.clicked_message = item
        engine.busy = True
        engine.status = None
        engine.submitted.put(("/timeline", []))
        return None

    def take_clicked(self) -> dict | None:
        """Tin vừa được bấm (cho /timeline mở thẳng menu của nó); lấy ra là hết."""
        item, self.clicked_message = getattr(self, "clicked_message", None), None
        return item

    def jump_to(self, item: dict) -> bool:
        """/timeline "Nhảy tới": cuộn tới khung của tin này. False khi không có màn hình toàn phần hay không còn khung."""
        pair = self._user_entries.get(id(item))
        if not self.fullscreen or pair is None or pair[0] is not item:
            return False
        return self.engine.jump(pair[1])

    def prefill(self, text: str) -> None:
        """/fork: chữ của tin được chọn nằm sẵn trong ô nhập để sửa rồi gửi lại."""
        if self.engine is None:
            super().prefill(text)
            return
        with self.engine.lock:
            self.engine.state.clear()
            self.engine.state.insert(text)
        self.engine.refresh()

    def copy(self, text: str) -> bool:
        # Màn hình toàn phần có hàm chép riêng (test thay được, không đụng clipboard thật).
        if self.engine is not None and callable(getattr(self.engine, "copy", None)):
            return bool(self.engine.copy(text))
        from .clipboard import copy_text

        return copy_text(text)

    def take_steers(self) -> list[tuple[str, list]]:
        """Tin người dùng nhắn thêm lúc Peto đang làm, để vòng làm việc chèn vào bước kế tiếp (CLI 0.20.0)."""
        if self.engine is None:
            return []
        taken = self.engine.take_steers()
        for _, _, sent in taken:
            self.commit_user(sent, steer=True)
        # Runtime mới đã lưu ở lúc Enter; chỉ xóa phần hiển thị, không nhận lại cùng tin lần hai.
        return [] if getattr(self, 'runtime_admit', None) else [(text, images) for text, images, _ in taken]

    def toggle_mode(self) -> str:
        """Đổi qua lại chế độ làm việc và Lập kế hoạch (Shift+Tab hay /plan); vẽ lại ô nhập ngay."""
        self.mode = "build" if self.mode == "plan" else "plan"
        if self.engine is not None:
            self.engine.refresh()
        return self.mode

    def set_session_title(self, title: str | None) -> None:
        """Tên hội thoại cho thanh trên cùng; luồng nền đặt tên cũng gọi được (vẽ lại trong khóa của màn hình)."""
        super().set_session_title(title)
        if self.engine is not None:
            self.engine.refresh()

    def bell(self) -> None:
        if self.engine is not None:
            if self.terminal and not os.environ.get("PETO_AGENT_NO_BELL"):
                self.engine.raw_write("\a")
            return
        super().bell()

    def title(self, text: str) -> None:
        if self.engine is not None:
            self._title = text
            if self.terminal:
                self.engine.raw_write(f"\033]0;{visible(text)}\033\\")
            return
        super().title(text)

    def session_header(self, version: str, directory: str, *, model: str, effort: str) -> None:
        """Màn hình toàn phần: đầu phiên là khối đầu của hội thoại, chọn lại cỡ mascot mỗi khi cửa sổ đổi cỡ."""
        self._header = (version, directory, model, effort)
        if not self.fullscreen:
            super().session_header(version, directory, model=model, effort=effort)
            return
        self._out(lambda: [parse_ansi(text) for text in self.header_lines(version, directory, model=model,
                                                                           effort=effort)], pad=False)
        self._last = "blank"

    def clear_conversation(self) -> bool:
        """/new, /resume, /fork: xóa hội thoại trên màn hình, chỉ để lại đầu phiên (CLI 0.22.0, như opencode mở hẳn
        hội thoại khác). Kiểu in nối tiếp không xóa được gì: trả về False."""
        self._group = []
        self._user_entries, self._last_user_entry = {}, None
        if not self.fullscreen:
            return False
        self.engine.clear()
        self._last = None
        if self._header is not None:
            version, directory, model, effort = self._header
            self.session_header(version, directory, model=model, effort=effort)
        return True

    @property
    def animated(self) -> bool:
        return len(self.theme.glyphs["spinner"]) > 4

    def spinner_frame(self) -> str:
        glyphs = self.theme.glyphs["spinner"]
        return glyphs[int(time.monotonic() * 10) % len(glyphs)] if self.animated else "…"

    def status_body(self, body: str) -> str:
        """Chữ của dòng trạng thái: "Peto đang nghĩ" kèm tiêu đề suy nghĩ khi có."""
        if self.thinking_title and body.startswith("Peto đang nghĩ"):
            return f"Đang nghĩ: {self.thinking_title}" + body[len("Peto đang nghĩ"):]
        if body.startswith("Peto đang "):
            return "Đang " + body[len("Peto đang "):]
        return body

    # ---- In ra lịch sử cuộn

    @property
    def content_width(self) -> int:
        return max(20, self.width - PAD)

    def _out(self, build, *, pad: bool = True, now: list[Line] | None = None):
        """Đưa một khối ra màn hình. Màn hình toàn phần giữ hàm vẽ ``build`` để vẽ lại theo bề ngang mới; kiểu nối tiếp
        in ngay các hàng (``now`` nếu đã vẽ sẵn)."""
        if self.fullscreen:
            return self.engine.add(build, pad=pad)
        lines = build() if now is None else now
        prefix = " " * PAD if pad else ""
        self.write("".join(prefix + render(line, self.colors) + "\n" if line.spans else "\n" for line in lines))
        return None

    def _write_lines(self, lines: list[Line]) -> None:
        self._out(lambda: lines, now=lines)

    def _emit(self, lines, kind: str):
        """In các hàng của một phần; giữa các phần khác loại có một dòng trống như OpenCode.

        ``lines`` là các hàng, hoặc hàm vẽ chúng theo bề ngang hiện tại (màn hình toàn phần gọi lại khi đổi cỡ)."""
        self._flush_group()
        build = lines if callable(lines) else (lambda: lines)
        drawn = build()
        skip = 0
        while skip < len(drawn) and not drawn[skip].spans and self._last in {None, "blank"}:
            skip += 1
        drawn = drawn[skip:]
        if not drawn:
            return None
        if self._last not in {None, "blank"} and drawn[0].spans and not (kind == self._last and kind in {"row", "text"}):
            self._write_lines([Line()])
        entry = self._out((lambda: build()[skip:]) if skip else build, now=drawn)
        self._last = "blank" if not drawn[-1].spans else kind
        return entry

    def _toggle(self, state: dict) -> None:
        """Mở hay thu một khối (suy nghĩ, nhóm Đã xem, diff hay output bị cắt): vẽ lại đúng khối đó."""
        state["open"] = not state.get("open")
        entry = state.get("entry")
        if entry is not None:
            entry.changed()
        if self.engine is not None:
            self.engine.changed()

    def _opener(self, state: dict | None) -> Target | None:
        """Chỗ bấm mở/thu của một khối; chỉ màn hình toàn phần bấm được."""
        if state is None or not self.fullscreen:
            return None
        return Target(("open", id(state)), lambda: self._toggle(state))

    def _cut(self, rows: list[Line], limit: int, state: dict | None) -> list[Line]:
        """Diff dài quá ``limit`` hàng thì cắt, kèm một dòng bấm vào để mở hết; mở rồi thì dòng cuối thu lại. Kiểu in
        nối tiếp không bấm được nên vẫn chỉ đường /diff như cũ."""
        theme = self.theme
        if len(rows) <= limit:
            return rows
        target = self._opener(state)
        if target is not None and state.get("open"):
            return rows + [Line(clickable([S("▴ thu gọn", theme.muted, theme.panel)], target))]
        hidden = len(rows) - limit
        label = f"… còn {hidden} dòng · " + ("bấm để xem đủ" if target else "/diff để xem đủ")
        return rows[:limit] + [Line(clickable([S(label, theme.muted, theme.panel)], target))]

    def _row(self, icon: str, spans: list, icon_color: str | None = None) -> list[Line]:
        """Một dòng công cụ: biểu tượng rồi chữ, dòng dài gập thẳng hàng với chữ."""
        rows = wrap(spans, self.content_width - 5)
        head = [S("   "), S(icon + " ", icon_color or self.theme.muted)]
        return [Line((head if index == 0 else [S("     ")]) + row) for index, row in enumerate(rows)]

    def _detail(self, text: str, color: str | None = None) -> list[Line]:
        return [Line([S("     ")] + row) for row in wrap([S(visible(text), color or self.theme.muted)],
                                                          self.content_width - 5)]

    def _block(self, header: list, body: list[Line]) -> list[Line]:
        """Khối nền panel: một cột trống, rồi nền nhạt; đệm trên dưới một hàng, trái hai cột."""
        theme = self.theme
        panel, width = theme.panel, self.content_width
        blank = fit(Line([S(" "), S(" ", bg=panel)]), width, panel)
        # Tiêu đề dài (lệnh dài, đường dẫn sâu) xuống hàng thay vì bị cắt: đó là thứ người dùng cần đọc đủ.
        out = [blank] + [fit(Line([S(" "), S("  ", bg=panel)] + row), width, panel)
                         for row in wrap(header, width - 4, hard=True)]
        if body:
            out.append(blank)
            out += [fit(Line([S(" "), S("  ", bg=panel)] + line.spans), width, panel) for line in body]
        out.append(blank)
        return out

    def line(self, text: str = "", color: str | None = None) -> None:
        """Chữ chung của lệnh gạch chéo và thông báo phiên, tô theo theme."""
        self._flush_group()
        if not text:
            self.write("\n")
            self._last = "blank"
            return
        role = COLOR_ROLES.get(color or "")
        style = {"fg": getattr(self.theme, role) if role else self.theme.text, "b": color == "bold"}
        if self.fullscreen:
            # Gập theo bề ngang hiện tại; hàng sau thụt như hàng đầu (danh sách của /help, /permissions…).
            body = text.lstrip(" ")
            # Thẳng cột với tin trả lời và dòng công cụ (lề chung + 3), giữ phần thụt riêng của câu (danh sách /help).
            indent = " " * (PAD + 3 + len(text) - len(body))
            self._out(lambda: [Line([S(indent)] + row) for row in wrap([(body, style)], self.width - len(indent))],
                      pad=False)
        else:
            self.write(render(Line([(text, style)]), self.colors) + "\n")
        self._last = "row"

    def step(self, text: str) -> None:
        self._emit(lambda: self._row("↳", [S(visible(text), self.theme.muted)]), "row")

    def success(self, text: str) -> None:
        self._emit(lambda: self._row("✓", [S(visible(text), self.theme.text)], self.theme.success), "row")

    def failure(self, text: str) -> None:
        self._emit(lambda: self._row("✗", [S(visible(text), self.theme.error)], self.theme.error), "row")

    def item(self, text: str) -> None:
        self._emit(lambda: self._detail(text), "row")

    def notice(self, text: str, level: str = "dim") -> None:
        color = self.theme.warning if level == "yellow" else self.theme.muted
        self._emit(lambda: self._row("·", [S(visible(text), color)], color), "row")

    def plan(self, steps: list[dict]) -> None:
        theme = self.theme
        panel = theme.panel
        body = []
        for step in steps:
            title = visible(str(step.get("title", "")))
            if step.get("status") == "done":
                body.append(Line([S("[✓] ", theme.success, panel), S(title, theme.muted, panel)]))
            elif step.get("status") == "running":
                body.append(Line([S("[•] ", theme.warning, panel), S(title, theme.text, panel, b=True)]))
            else:
                body.append(Line([S("[ ] ", theme.muted, panel), S(title, theme.text, panel)]))
        self._emit(lambda: self._block([S("# ", theme.muted, panel), S("Việc cần làm", theme.muted, panel)], body),
                   "block")
        if self.engine is not None:
            # Việc đang làm hiện ngay trên ô nhập trong lúc Peto làm, thay cho sidebar của bản toàn màn hình.
            running = next(((index, step) for index, step in enumerate(steps) if step.get("status") == "running"), None)
            self.engine.plan_line = (f"{visible(str(running[1].get('title', '')))} ({running[0] + 1}/{len(steps)})"
                                     if running else None)

    # ---- Dòng trạng thái tạm

    def status(self, text: str) -> None:
        if not self.terminal:
            return
        if self.engine is not None:
            self.engine.set_status(clip(visible(text), self.content_width - 6))
            return
        theme = self.theme
        spin = self.spinner_frame()
        body = self.status_body(text.removeprefix("… "))
        line = Line([S("   "), S(spin + " ", theme.primary), S(clip(visible(body), self.content_width - 5), theme.muted)])
        rendered = " " * PAD + render(line, self.colors)
        if rendered == self._status:
            return
        self.out.write(CLEAR_LINE + rendered)
        self.out.flush()
        self._status = rendered

    # ---- Công cụ

    def tool_started(self, call: ToolCall) -> None:
        self._preview = None
        self._static_diff = False
        label = EXPLORE.get(call.name)
        if label is None:
            self._flush_group()
            return
        self.status("… " + label(call.args))

    def explore_progress(self, text: str) -> None:
        """Agent con explore (CLI 0.27.0): việc nó đang làm hiện ở dòng trạng thái."""
        self.status(f"… Khám phá · {text}")

    def tool_progress(self, call_id: str, seconds: float, output: str) -> None:
        command = (self._preview[1].get("command", "") if self._preview else "").split("\n")[0]
        label = f"… $ {clip(command, 40)} · {int(seconds)}s · Ctrl+C dừng lệnh"
        lines = output_lines(output)
        if lines and self.width > 70:
            label += " │ " + lines[-1]
        self.status(label)

    def preview(self, kind: str, body: dict) -> None:
        """Ghi lại thứ công cụ sắp làm: khung duyệt dùng nó, và khối của công cụ khi đã được cho phép sẵn."""
        self._preview = (kind, body)

    def search(self, state: str) -> None:
        if state == "searching":
            self._emit(lambda: self._row(self.theme.glyphs["web"], [S("Tìm trên web", self.theme.muted)]), "row")

    def _explore_label(self, name: str, args: dict, result: dict, meta: dict) -> tuple[str, str]:
        if name == "read_history":
            return "read", f'lịch sử trước tóm tắt · {len(result.get("entries") or [])} mục'
        if name == "read_output":
            # Output đầy đủ của một lệnh dài mà CLI đã lưu (CLI 0.25.0).
            if args.get("pattern"):
                return "search", (f'"{args["pattern"]}" {result.get("total_matches", 0)} kết quả trong output '
                                  f'{result.get("output_id", "")}')
            return "read", f'output {result.get("output_id", "")}:{result.get("start_line")}-{result.get("end_line")}'
        if name == "read_file":
            if not result.get("total_lines"):
                return "read", f"{result['path']} (trống)"
            return "read", f"{result['path']}:{result['start_line']}-{result['end_line']}"
        if name == "list_files":
            path = result["path"]
            return "list", ("./" if path == "." else path.rstrip("/") + "/")
        where = meta.get("base", ".")
        if name == "find_files":
            return "find", (f'"{args.get("pattern", "")}" {result.get("total", 0)} tệp'
                            + (f" trong {where}" if where != "." else ""))
        count = result.get("total", len(result.get("matches") or []))
        return "search", (f'"{args.get("pattern", "")}" {count}{"+" if result.get("truncated") else ""} kết quả'
                          + (f" trong {where}" if where != "." else ""))

    def _flush_group(self) -> None:
        if not self._group:
            return
        group, self._group = self._group, []
        if self._last not in {None, "blank", "row"}:
            self._write_lines([Line()])
        state: dict = {}
        state["entry"] = self._out(lambda: self._group_lines(group, state))
        self._last = "row"

    def _explore_lines(self, args: dict, result: dict, meta: dict, state: dict) -> list[Line]:
        """Khối của agent con explore: một dòng tóm tắt, bấm để mở từng việc nó làm và kết luận nó trả về."""
        theme = self.theme
        target = self._opener(state)
        opened = target is not None and state.get("open")
        task = " ".join(str(args.get("task", "")).split())
        task = task if len(task) <= 70 else task[:69] + "…"
        where = f" · {result.get('steps', 0)} bước · đọc {len(result.get('files_read') or [])} tệp"
        failed = bool(result.get("error"))
        icon = ("▾" if opened else "◇") if target else "◇"
        lines = self._row(icon, clickable([S("Khám phá ", theme.muted), S(visible(task), theme.dim_text),
                                           S(where + (" · chưa xong" if failed else ""),
                                             theme.error if failed else theme.muted)], target),
                          theme.error if failed else None)
        if not opened:
            return lines
        for action in meta.get("actions") or []:
            lines += [Line([S("     ")] + row) for row in wrap([S(visible(action), theme.muted)],
                                                                 self.content_width - 5)]
        summary = [line for line in str(result.get("error") or result.get("summary") or "").split("\n")]
        for text in summary[:30]:
            lines += [Line([S("     ")] + row) for row in wrap([S(visible(text), theme.dim_text)],
                                                                 self.content_width - 5)] or [Line()]
        if len(summary) > 30:
            lines.append(Line([S("     "), S(f"… còn {len(summary) - 30} dòng", theme.muted)]))
        return lines

    def _group_lines(self, group: list[tuple[str, str]], state: dict | None = None) -> list[Line]:
        theme = self.theme
        if len(group) == 1:
            kind, label = group[0]
            verb = {"read": "Đọc ", "list": "Xem thư mục ", "search": "Tìm ", "find": "Tìm tệp "}[kind]
            icon = theme.glyphs["search"] if kind in {"search", "find"} else "→"
            lines = self._row(icon, [S(verb, theme.muted), S(visible(label), theme.dim_text)])
        else:
            kinds = ("read", "list", "search", "find")
            counts = {kind: sum(1 for item, _ in group if item == kind) for kind in kinds}
            names = {"read": "lần đọc", "list": "thư mục", "search": "lần tìm", "find": "lần tìm tệp"}
            summary = ", ".join(f"{counts[kind]} {names[kind]}" for kind in kinds if counts[kind])
            # Bấm "Đã xem" thì hiện từng lần đọc, tìm trên một dòng; bấm lần nữa thu lại (CLI 0.24.0, như opencode).
            target = self._opener(state)
            opened = target is not None and state.get("open")
            lines = self._row("▾" if opened else "→", clickable([S("Đã xem: ", theme.muted), S(summary, theme.muted)],
                                                                target))
            if opened:
                verbs = {"read": "Đọc ", "list": "Xem thư mục ", "search": "Tìm ", "find": "Tìm tệp "}
                for kind, label in group:
                    lines += [Line([S("     ")] + row) for row in wrap(
                        [S(verbs[kind], theme.muted), S(visible(label), theme.dim_text)], self.content_width - 5)]
                return lines
            labels = [label for _, label in group]
            rows = wrap([S(visible(" · ".join(labels)), theme.dim_text)], self.content_width - 5)
            if len(rows) > 2:
                rows = rows[:2]
                rows[-1] = rows[-1] + clickable([S(" …", theme.muted)], target)
            lines += [Line([S("     ")] + row) for row in rows]
        return lines

    def tool_finished(self, done: ToolDone) -> None:
        name, args, result, meta = done.name, done.args, done.result, done.meta
        theme = self.theme
        if meta.get("stopped"):
            return
        if name in EXPLORE and not meta.get("raised") and "error" not in result:
            self._group.append(self._explore_label(name, args, result, meta))
            return
        self._flush_group()
        if meta.get("raised") == "guide":
            self.step(meta["message"])
            return
        if name == "explore" and not meta.get("raised"):
            state: dict = {}
            state["entry"] = self._emit(lambda: self._explore_lines(args, result, meta, state), "row")
            return
        if meta.get("raised") == "unread":
            # Sửa tệp chưa đọc (CLI 0.25.0): không phải lỗi, nội dung đã gửi cho Peto để sửa ở bước sau.
            self.notice(meta["message"], "yellow")
            return
        if meta.get("raised"):
            self.failure(meta["message"])
            return
        if meta.get("refused"):
            self.failure(REFUSED_LINES[name].format(path=meta.get("path", "")))
            return
        if meta.get("read_only"):
            self.failure(READ_ONLY_LINES.get(name, "Trang ngoài chỉ xem: mở link bằng địa chỉ của nó."))
            return
        if name == "browser_login" and "done" in meta:
            where = (f'"{result["title"]}" · ' if result.get("title") else "") + _where(result.get("url") or "")
            if meta["done"]:
                self.success(f"Đã đăng nhập · {where}")
            else:
                self.failure(f"Bạn bỏ qua đăng nhập · {where}")
            return
        preview, static = self._preview, self._static_diff
        if name in {"run_command", "run_python"} and "exit_code" in result:
            shell: dict = {}
            shell["entry"] = self._emit(lambda: self._shell_block(result, preview, shell), "block")
            return
        if "error" in result:
            self._emit(lambda: self._row("·", [S(clip(visible(str(result["error"])), 300), theme.muted)]), "row")
            return
        if name in {"edit_file", "write_file", "delete_file"}:
            edit: dict = {}
            edit["entry"] = self._emit(lambda: self._edit_block(name, result, preview, static, edit), "block")
        elif name == "apply_patch":
            files = preview[1]["files"] if preview and preview[0] == "patch" else []
            for index, item in enumerate(result["files"]):
                source = files[index] if index < len(files) and not static else None
                cut: dict = {}
                cut["entry"] = self._emit(lambda item=item, source=source, cut=cut: self._patch_block(item, source, cut),
                                          "block")
        elif name == "ask_user":
            for item in result.get("answers") or []:
                self._emit(lambda item=item: self._row("?", [S(visible(item["question"]) + " ", theme.muted),
                                                             S(visible(", ".join(item["answer"]) or "(trống)"),
                                                               theme.text)], theme.secondary), "row")
            if result.get("dismissed"):
                self._emit(lambda: self._row("?", [S("Bạn bỏ qua câu hỏi của Peto", theme.muted)]), "row")
        elif name == "update_plan":
            self.plan(meta["plan"])
        elif name == 'record_acceptance':
            row = result.get('acceptance', {})
            labels = {'passed': 'Đạt trong phạm vi đã kiểm', 'failed': 'Chưa đạt', 'unverified': 'Chưa xác minh'}
            self._emit(lambda: self._row('✓' if row.get('status') == 'passed' else '·',
                       [S(labels.get(row.get('status'), 'Nghiệm thu') + ': ', theme.muted),
                        S(visible(row.get('criterion', '')), theme.text)]), 'row')
        elif name == "move_file":
            self._emit(lambda: self._row("→", [S("Đổi tên ", theme.muted),
                                               S(f"{result['moved_from']} → {result['path']}", theme.dim_text)]), "row")
        elif name == "start_command":
            where = result.get("cwd", ".")
            self._emit(lambda: self._row("$", [S(f"Chạy nền #{result['id']} ", theme.muted),
                                               S(visible(result["command"]), theme.dim_text),
                                               S(f" · trong {where}" if where != "." else "", theme.muted)]), "row")
        elif name == "read_command_output":
            state = "đang chạy" if result.get("running") else f"đã dừng, mã thoát {result.get('exit_code')}"
            self._emit(lambda: self._row("→", [S(f"Đọc output lệnh nền #{result['id']} ({state})", theme.muted)]),
                       "row")
        elif name == "stop_command":
            self._emit(lambda: self._row("■", [S(f"Đã dừng lệnh nền #{result['id']}: ", theme.muted),
                                               S(visible(result["command"]), theme.dim_text)]), "row")
        elif name == "browser_open":
            self.page(f"Xem trang {result['url']} · {_viewport_label(result['viewport'])}", _page_details(result),
                      result.get("problems") or [])
        elif name == "browser_screenshot":
            label = _viewport_label(result["viewport"]) + (" · cả trang" if result.get("full_page") else "")
            if result.get("cut"):
                label += f" (cắt ở {result['height']}px)"
            self.page(f"Chụp trang · {label}", " · ".join(page_notes(result)), result.get("problems") or [],
                      path=meta.get("path"))
        elif name == "browser_read":
            what = f"Đọc chữ trong {args['selector']}" if args.get("selector") else "Đọc chữ trên trang"
            self.page(f"{what} ({_count(result.get('chars', 0))} ký tự)", " · ".join(page_notes(result)),
                      result.get("problems") or [])
        elif name in {"browser_click", "browser_type", "browser_press"}:
            title = result["action"][:1].upper() + result["action"][1:]
            self.page(title, action_details(name.removeprefix("browser_"), result), result.get("problems") or [])
        elif name == "load_skill":
            self._emit(lambda: self._row("→", [S("Nạp skill ", theme.muted), S(f'"{args.get("name")}"', theme.dim_text)]),
                       "row")
        elif name == "mcp_call_tool":
            self._emit(lambda: self._row(theme.glyphs["tool"], [S("MCP ", theme.muted),
                                                                S(f"{args.get('server')} → {args.get('tool')}",
                                                                  theme.dim_text)]), "row")
        elif name == "mcp_list_tools":
            self._emit(lambda: self._row(theme.glyphs["tool"], [S(f"Xem công cụ MCP {args.get('server')}", theme.muted)]),
                       "row")

    # ---- Vẽ lại hội thoại đã lưu (/resume, /fork; CLI 0.22.0, theo opencode)

    def replay(self, items: list[dict]) -> None:
        """Vẽ lại cả hội thoại bằng đúng các hàm vẽ lúc đang làm, để /resume thấy lại mọi thứ chứ không chỉ tin cuối.
        Suy nghĩ của model và ảnh chụp trang không được lưu nên không có."""
        for event in transcript.events(items):
            if event.kind in {"user", "steer"}:
                self.commit_user(SavedText(event.text, event.images), steer=event.kind == "steer")
                self.link_user_entry(event.item)
                for path in event.files:
                    self.step(f"Đính kèm {path}")
            elif event.kind == "summary":
                self.notice("Phần trước của hội thoại đã được tóm tắt")
            elif event.kind == "note":
                self.notice(event.text)
            elif event.kind == "reply":
                writer = self.reply()
                writer.feed(event.text)
                writer.finish()
            elif event.result is not None:
                self._replay_tool(event)
        self._flush_group()
        self._preview = None
        if self.engine is not None:
            self.engine.plan_line = None

    def _replay_tool(self, event) -> None:
        name, args, result = event.name, event.args, event.result
        meta: dict = {}
        preview = None
        if name == "edit_file":
            # Kết quả không lưu số dòng của tệp: diff chỉ là đoạn bị thay, không số dòng.
            preview = ("file", {"before": str(args.get("old_text") or ""), "after": str(args.get("new_text") or ""),
                                "snippet": True})
        elif name == "write_file" and result.get("created"):
            preview = ("file", {"before": "", "after": str(args.get("content") or "")})
        elif name == "apply_patch" and result.get("files"):
            try:
                ops = patch_text.parse(str(args.get("patch_text") or ""))
            except patch_text.PatchError:
                ops = []
            files = []
            for op in ops:
                if op.kind == "add":
                    files.append({"before": "", "after": op.contents})
                elif op.kind == "update":
                    files.append({"before": "\n".join(line for chunk in op.chunks for line in chunk.old),
                                  "after": "\n".join(line for chunk in op.chunks for line in chunk.new), "snippet": True})
                else:
                    files.append({"before": "", "after": ""})
            preview = ("patch", {"files": files}) if len(files) == len(result["files"]) else None
        elif name in {"run_command", "start_command"}:
            preview = ("command", {"command": str(args.get("command") or ""), "shell": args.get("shell") or "cmd"})
        elif name == "run_python":
            preview = ("command", {"command": str(args.get("code") or ""), "shell": "python"})
        elif name == "update_plan":
            steps = args.get("steps")
            if not isinstance(steps, list) or "error" in result:
                return
            meta["plan"] = [step for step in steps if isinstance(step, dict)]
        self._preview, self._static_diff = preview, False
        self.tool_finished(ToolDone("", name, args, result, meta))

    def page(self, title: str, details: str, problems: list[str], *, path: str | None = None) -> None:
        """Một lần Peto xem hay thao tác trên trang: dòng chính, dòng chi tiết, tối đa 5 lỗi, đường dẫn ảnh."""
        theme = self.theme

        def build() -> list[Line]:
            lines = self._row("%", [S(visible(title), theme.muted)])
            if details:
                lines += self._detail(details)
            for problem in problems[:5]:
                lines += [Line([S("     "), S("✗ ", theme.error)] + row)
                          for row in wrap([S(visible(problem), theme.error)], self.content_width - 7)]
            if len(problems) > 5:
                lines += self._detail(f"… còn {len(problems) - 5} lỗi")
            return lines

        self._emit(build, "row")
        if path:
            # In liền một dòng, không gập, để terminal VS Code nhận ra đường dẫn và cho Ctrl+Click mở ảnh. Màn hình toàn
            # phần không viết quá bề ngang, nên đường dẫn dài hơn cả hàng mới bị bẻ.
            line = Line([S("     ảnh: ", theme.muted), S(visible(path), theme.muted)])
            if self.fullscreen:
                self._out(lambda: [Line(row) for row in wrap(line.spans, self.content_width, hard=True)])
            else:
                self.write(" " * PAD + render(line, self.colors) + "\n")

    def _edit_block(self, name: str, result: dict, preview: tuple[str, dict] | None = None,
                    static: bool = False, state: dict | None = None) -> list[Line]:
        theme = self.theme
        panel = theme.panel
        rel = result["path"]
        verb = {"edit_file": "Sửa", "delete_file": "Xóa"}.get(name, "Tạo" if result.get("created") else "Ghi đè")
        header = [S("← ", theme.muted, panel), S(verb + " ", theme.text, panel, b=True), S(rel, theme.text, panel)]
        if result.get("added_lines"):
            header.append(S(f"  +{result['added_lines']}", theme.diff_added, panel))
        if result.get("removed_lines"):
            header.append(S(f"  −{result['removed_lines']}", theme.diff_removed, panel))
        if (result.get("replacements") or 1) > 1:
            header.append(S(f"  · {result['replacements']} chỗ", theme.muted, panel))
        if result.get("match"):
            header.append(S(f"  · khớp gần đúng: {result['match']}", theme.warning, panel))
        body: list[Line] = []
        if name != "delete_file" and not static and preview and preview[0] == "file":
            rows = Diff(preview[1]["before"], preview[1]["after"], path=rel,
                        numbered=not preview[1].get("snippet")).rows(theme, self.content_width - 3)
            body = self._cut(rows, BLOCK_DIFF_ROWS, state)
        return self._block(header, body)

    def _patch_block(self, item: dict, source: dict | None, state: dict | None = None) -> list[Line]:
        """Một tệp của bản patch: như khối sửa tệp, kèm diff khi có bản xem trước."""
        theme = self.theme
        panel = theme.panel
        verb = {"add": "Tạo", "delete": "Xóa"}.get(item["op"], "Sửa")
        where = f"{item['moved_from']} → {item['path']}" if item.get("moved_from") else item["path"]
        header = [S("← ", theme.muted, panel), S(verb + " ", theme.text, panel, b=True), S(where, theme.text, panel)]
        if item.get("added_lines"):
            header.append(S(f"  +{item['added_lines']}", theme.diff_added, panel))
        if item.get("removed_lines"):
            header.append(S(f"  −{item['removed_lines']}", theme.diff_removed, panel))
        body: list[Line] = []
        if source is not None and item["op"] != "delete":
            rows = Diff(source["before"], source["after"], path=item["path"],
                        numbered=not source.get("snippet")).rows(theme, self.content_width - 3)
            body = self._cut(rows, BLOCK_DIFF_ROWS, state)
        return self._block(header, body)

    def _shell_block(self, result: dict, preview: tuple[str, dict] | None = None,
                     state: dict | None = None) -> list[Line]:
        theme = self.theme
        panel = theme.panel
        body = preview[1] if preview and preview[0] in {"command", "background"} else {}
        command = str(body.get("command") or result.get("command") or "")
        powershell = (body.get("shell") or result.get("shell")) == "powershell"
        first, *more = command.split("\n")
        header = [S("PS> " if powershell else "$ ", theme.muted, panel), S(visible(first), theme.text, panel)]
        if more:
            header.append(S(f"  (+{len(more)} dòng)", theme.muted, panel))
        if result.get("cwd"):
            header.append(S(f"  trong {result['cwd']}", theme.muted, panel))
        lines = output_lines(str(result.get("output") or ""))
        # Mỗi dòng output có thể gập thành vài hàng: cắt theo dòng output, rồi mới gập.
        opened = self._opener(state) is not None and state.get("open")
        kept = lines if opened or len(lines) <= OUTPUT_TAIL else lines[-OUTPUT_TAIL:]
        rows: list[Line] = []
        for text in kept:
            rows += [Line(row) for row in wrap([S(text, theme.muted, panel)], self.content_width - 5, hard=True)]
        if len(lines) > OUTPUT_TAIL:
            target = self._opener(state)
            if opened:
                rows.append(Line(clickable([S("▴ thu gọn", theme.muted, panel)], target)))
            else:
                label = f"({len(lines) - OUTPUT_TAIL} dòng trước đó" + (" · bấm để xem đủ)" if target else ")")
                rows.insert(0, Line(clickable([S(label, theme.muted, panel)], target)))
        seconds = result.get("seconds")
        took = _seconds(seconds) if isinstance(seconds, (int, float)) else f"{seconds} giây"
        classification = result.get("classification")
        if classification == "no_match":
            status = [S("· ", theme.muted, panel), S(f"không tìm thấy kết quả · {took}", theme.muted, panel)]
        elif classification == "environment_error":
            status = [S("✗ ", theme.error, panel),
                      S(f"có dấu hiệu lỗi môi trường; chưa xác minh được code · {took}", theme.error, panel)]
        elif classification == "no_tests":
            status = [S("! ", theme.warning, panel),
                      S(f"không thu thập được bài kiểm thử; chưa xác minh được code · {took}", theme.warning, panel)]
        elif result.get("error"):
            status = [S("✗ ", theme.error, panel), S(f"{visible(str(result['error']))} · {took}", theme.error, panel)]
        elif result.get("exit_code") == 0:
            status = [S("✓ ", theme.success, panel), S(f"xong · {took}", theme.muted, panel)]
        else:
            status = [S("✗ ", theme.error, panel), S(f"mã thoát {result.get('exit_code')} · {took}", theme.error, panel)]
        # Ảnh chụp dự án (CLI 0.26.0) biết lệnh đã đổi tệp nào; /diff xem đủ, /undo trả lại được.
        changed = result.get("files_changed_total") or len(result.get("files_changed") or [])
        if changed:
            status.append(S(f" · đổi {changed} tệp", theme.muted, panel))
        if rows:
            rows.append(Line([S("", bg=panel)]))
        rows.append(Line(status))
        return self._block(header, rows)

    # ---- Câu hỏi quyền

    def _options(self, permission: Permission) -> list[Option]:
        kind, body = permission.kind, permission.body
        if kind in {"mcp", "mcp_enable"}:
            return [Option("y", "Cho phép"), Option("n", "Từ chối")]
        if kind == "undo":
            return [Option("y", "Hoàn tác"), Option("n", "Thôi")]
        if kind == "loop":
            return [Option("y", "Cho gọi tiếp"), Option("n", "Dừng lại")]
        if kind == "site" and body.get("unusual"):
            return [Option("y", "Mở đúng địa chỉ này"), Option("a", "Mọi bước trong yêu cầu"), Option("n", "Từ chối")]
        first = {"page": "Trang này tới hết yêu cầu", "site": f"{body.get('site', '')} tới hết yêu cầu"}.get(kind,
                                                                                                         "Cho phép")
        options = [Option("y", first), Option("a", "Cả yêu cầu này")]
        if permission.allow_session:
            label = {"command": "Nhớ lệnh trong phiên", "background": "Nhớ lệnh trong phiên",
                     "page": "Cả phiên"}.get(kind, permission.session_label)
            options.append(Option("s", label))
        if permission.allow_always:
            options.append(Option("l", "Luôn ở dự án"))
        options.append(Option("n", "Từ chối"))
        return options

    def _permission_parts(self, permission: Permission, width: int) -> tuple[list, list[Line]]:
        """Dòng tiêu đề và các hàng nội dung của khung duyệt."""
        theme = self.theme
        kind, body = permission.kind, permission.body
        if kind == "file":
            rel = body.get("path", "")
            diff = Diff(body.get("before", ""), body.get("after", ""), path=rel)
            verb = "Xóa" if body.get("deleted") else "Tạo" if body.get("created") else (
                "Ghi đè" if body.get("title", "").startswith("Muốn ghi đè") else "Sửa")
            header = [S("← ", theme.muted), S(verb + " ", theme.text, b=True), S(rel, theme.text)]
            if diff.added:
                header.append(S(f"  +{diff.added}", theme.diff_added))
            if diff.removed:
                header.append(S(f"  −{diff.removed}", theme.diff_removed))
            if body.get("match"):
                header.append(S(f"  · khớp gần đúng: {body['match']}", theme.warning))
            rows = diff.rows(theme, width) if not diff.empty else [Line([S("Nội dung không đổi.", theme.muted)])]
            return header, rows
        if kind == "patch":
            files = body.get("files") or []
            added = removed = 0
            rows: list[Line] = []
            for item in files:
                diff = Diff(item.get("before", ""), item.get("after", ""), path=item["path"])
                added, removed = added + diff.added, removed + diff.removed
                verb = {"add": "Tạo", "delete": "Xóa"}.get(item["op"], "Sửa")
                where = item["path"] + (f" → {item['new_path']}" if item.get("new_path") else "")
                if rows:
                    rows.append(Line())
                rows.append(Line([S(verb + " ", theme.text, b=True), S(where, theme.text),
                                  S(f"  +{diff.added}", theme.diff_added), S(f"  −{diff.removed}", theme.diff_removed)]))
                if item["op"] != "delete":
                    rows += diff.rows(theme, width) if not diff.empty else [Line([S("Nội dung không đổi.", theme.muted)])]
            header = [S("← ", theme.muted), S(f"Áp bản patch · {len(files)} tệp", theme.text, b=True),
                      S(f"  +{added}", theme.diff_added), S(f"  −{removed}", theme.diff_removed)]
            return header, rows
        if kind == "move":
            return [S("→ ", theme.muted), S("Đổi tên ", theme.text, b=True),
                    S(f"{body['old']} → {body['new']}", theme.text)], [Line([S("Nội dung giữ nguyên.", theme.muted)])]
        if kind in {"command", "background"}:
            powershell = body.get("shell") == "powershell"
            where = body.get("directory", "")
            note = ("chạy tiếp sau khi yêu cầu xong" if kind == "background"
                    else f"tối đa {body.get('timeout', 0)} giây")
            header = [S("# ", theme.muted), S("Chạy lệnh nền" if kind == "background" else "Chạy lệnh", theme.text, b=True),
                      S(" bằng PowerShell" if powershell else "", theme.text), S(f"   {note}", theme.muted)]
            rows = [Line([S(visible(where), theme.muted)])] if where else []
            for part in str(body.get("command", "")).split("\n"):
                rows += [Line(([S("PS> " if powershell else "$ ", theme.muted)] if index == 0 else [S("  ")]) + row)
                         for index, row in enumerate(wrap([S(visible(part.expandtabs(4)), theme.text)], width - 4,
                                                           hard=True))]
            return header, rows
        if kind == "page":
            return ([S("% ", theme.muted), S("Bấm, gõ trên ", theme.text, b=True), S(visible(body["origin"]), theme.text)],
                    [Line(row) for row in wrap([S(f"Trước tiên: {visible(body['action'])}", theme.text)], width)]
                    + [Line(row) for row in wrap([S("Đây là thao tác thật trên app đang chạy: có thể gửi form, xóa dữ "
                                                    "liệu hay gọi dịch vụ thật như bạn bấm.", theme.muted)], width)])
        if kind == "site":
            unusual = body.get("unusual")
            rows = [Line(row) for row in wrap([S(visible(body["url"]), theme.text)], width, hard=True)]
            note = (f"Phần sau tên miền dài có thể đang mang dữ liệu của bạn tới {body['site']}: xem kỹ rồi hãy đồng ý."
                    if unusual else "Trình duyệt riêng, không cookie hay đăng nhập nào; Peto chỉ xem.")
            rows += [Line(row) for row in wrap([S(note, theme.warning if unusual else theme.muted)], width)]
            return [S("% ", theme.muted), S("Mở trang ngoài", theme.text, b=True),
                    S(" (địa chỉ dài bất thường)" if unusual else "", theme.warning)], rows
        if kind == "mcp":
            text = json.dumps(body.get("arguments", {}), ensure_ascii=False)
            return ([S(theme.glyphs["tool"] + " ", theme.muted), S("Gọi công cụ MCP ", theme.text, b=True),
                     S(f"{body['server']} → {body['tool']}", theme.text)],
                    [Line(row) for row in wrap([S(visible(text), theme.muted)], width, hard=True)])
        if kind == "mcp_enable":
            text = json.dumps(body.get("spec", {}), ensure_ascii=False)
            return ([S(theme.glyphs["tool"] + " ", theme.muted), S("Bật MCP ", theme.text, b=True),
                     S(str(body.get("name", "")), theme.text)],
                    [Line(row) for row in wrap([S(visible(text), theme.muted)], width, hard=True)]
                    + [Line(row) for row in wrap([S("MCP cục bộ chạy với quyền tài khoản máy; không nằm trong giới hạn "
                                                    "công cụ tệp của Peto.", theme.warning)], width)])
        if kind == "loop":
            text = json.dumps(body.get("arguments", {}), ensure_ascii=False)
            return ([S("⟳ ", theme.warning), S("Peto gọi lặp lại", theme.text, b=True)],
                    [Line(row) for row in wrap([S(f"{body['name']} y hệt {body['count']} lần liền mà không có tệp nào "
                                                  "đổi. Dừng lại thì Peto phải đổi cách làm.", theme.text)], width)]
                    + [Line(row) for row in wrap([S(visible(clip(text, 400)), theme.muted)], width, hard=True)])
        if kind == "undo":
            files = body.get("files") or []
            return ([S("↶ ", theme.muted), S(f"Hoàn tác {len(files)} tệp", theme.text, b=True)],
                    [Line([S(visible(name), theme.muted)]) for name in files])
        return [S(visible(permission.question.strip().removesuffix("›").strip()), theme.text)], []

    def _panel(self, permission: Permission, options: list[Option], selected: int, offset: int,
               budget: int, pick: Callable[[int], Target] | None = None) -> tuple[list[Line], int]:
        """Các hàng của khung duyệt và số hàng nội dung còn ẩn phía sau."""
        theme = self.theme
        width = self.content_width
        panel, element = theme.panel, theme.element
        inner = width - 4
        header, rows = self._permission_parts(permission, inner)
        bar = S("┃", theme.primary, panel)

        def row(spans: list, bg=panel) -> Line:
            return fit(Line([S("┃", theme.primary, bg), S("   ", bg=bg)] + spans), width, bg)

        top = [fit(Line([bar, S(" "), S(theme.glyphs["warn"] + " ", theme.warning, panel),
                         S("Cần bạn duyệt", theme.text, panel, b=True)]), width, panel),
               row([(text, {**style, "bg": style.get("bg") or panel}) for text, style in header])]
        choices = [S("┃", theme.primary, element), S("  ", bg=element)]
        for index, option in enumerate(options):
            target = pick(index) if pick is not None else None
            if index == selected:
                choices += clickable([S(f" {option.label} ", theme.on_primary, theme.primary, b=True)], target)
            else:
                choices += clickable([S(f" {option.label} ", theme.muted, element)], target)
            choices.append(S(" ", bg=element))
        letters = "/".join(option.key for option in options)
        hint = [S("┃", theme.primary, element), S("  ", bg=element), S("←→", theme.text, element),
                S(" chọn  ", theme.muted, element), S("enter", theme.text, element), S(" đồng ý  ", theme.muted, element),
                S("esc", theme.text, element), S(" từ chối  ", theme.muted, element), S(letters, theme.text, element),
                S(f" {LETTERS_HINT}", theme.muted, element)]
        bottom = [row([]), fit(Line(choices), width, element), fit(Line(hint), width, element),
                  Line([S("╹", theme.primary), S("▀" * (width - 1), element)])]
        room = max(1, budget - len(top) - len(bottom) - 2)
        hidden = 0
        shown = rows[offset:offset + room]
        if len(rows) - offset > room:
            shown = rows[offset:offset + room - 1]
            hidden = len(rows) - offset - len(shown)
        body = [row([]) if rows else None]
        body = [line for line in body if line is not None]
        body += [row([(text, {**style, "bg": style.get("bg") or panel}) for text, style in line.spans]) for line in shown]
        if hidden:
            body.append(row([S(f"… còn {hidden} dòng · v hoặc PgDn xem tiếp", theme.muted, panel)]))
        return top + body + bottom, hidden

    @staticmethod
    def _pick(state: dict, field: str, index, press: Key) -> Target:
        """Chỗ bấm của một dòng hay nút trong khung chọn: rê qua là chọn nó (như opencode), bấm là chọn rồi bấm phím
        ``press`` (thường là Enter), đi đúng đường của bàn phím."""
        def select() -> None:
            state[field] = index

        def run() -> Key:
            select()
            return press

        return Target(("pick", id(state), index), run, hover=select, look="")

    @staticmethod
    def _press(state: dict, key: Key, name: str) -> Target:
        """Chỗ bấm của một gợi ý phím ở chân khung ("esc thôi", "c chép"): bấm là bấm phím đó."""
        return Target(("press", id(state), name), lambda: key)

    def ask(self, permission: Permission) -> str:
        self._flush_group()
        self.clear_status()
        waiting = self._title
        self.title("Peto · cần bạn duyệt")
        self.bell()
        options = self._options(permission)
        try:
            if self.engine is not None:
                render_lines, handle = self._chooser(permission, options, max(8, self.height - 1))
                return self.engine.ask(render_lines, handle)
            console = getattr(self.editor, "console", None) if self.editor is not None else None
            if console is not None:
                try:
                    return self._ask_keys(console, permission, options)
                except OSError:
                    self.editor = None
            return self._ask_typed(permission, options)
        finally:
            self.title(waiting)

    def _chooser(self, permission: Permission, options: list[Option], budget: int):
        """Khung duyệt và cách nó nhận phím: ←/→ chọn, Enter đồng ý, Esc từ chối, phím chữ chọn thẳng, v/PgDn xem
        tiếp diff dài. Trả hàm vẽ và hàm nhận phím (trả câu trả lời khi xong, None khi chưa)."""
        state = {"selected": 0, "offset": 0, "hidden": 0}
        letters = {option.key for option in options}

        def pick(index: int) -> Target:
            return self._pick(state, "selected", index, Key("enter"))

        def render_lines() -> list[Line]:
            lines, state["hidden"] = self._panel(permission, options, state["selected"], state["offset"], budget, pick)
            return lines

        def handle(key) -> str | None:
            text = key.text.lower() if key.name == "char" else ""
            if key.name in {"left", "up"}:
                state["selected"] = (state["selected"] - 1) % len(options)
            elif key.name in {"right", "down", "tab"}:
                state["selected"] = (state["selected"] + 1) % len(options)
            elif key.name == "enter":
                return options[state["selected"]].key
            elif key.name == "escape":
                return "n" if "n" in letters else options[-1].key
            elif key.name == "pagedown" or text == "v":
                if state["hidden"]:
                    state["offset"] += max(1, budget - 12)
            elif key.name == "pageup":
                state["offset"] = max(0, state["offset"] - max(1, budget - 12))
            elif text in letters:
                return text
            return None

        return render_lines, handle

    def _draw(self, lines: list[Line], drawn: int) -> int:
        parts = [HIDE_CURSOR]
        if drawn > 1:
            parts.append(f"\033[{drawn - 1}A")
        parts.append("\r\033[J")
        parts.append("\r\n".join(" " * PAD + render(line, self.colors) for line in lines))
        self.out.write("".join(parts))
        self.out.flush()
        return len(lines)

    def _erase(self, drawn: int) -> None:
        self.out.write((f"\033[{drawn - 1}A" if drawn > 1 else "") + "\r\033[J" + SHOW_CURSOR)
        self.out.flush()

    def _ask_keys(self, console, permission: Permission, options: list[Option]) -> str:
        """Khung duyệt tạm ở cuối màn hình khi chưa có chân cố định."""
        render_lines, handle = self._chooser(permission, options, max(8, self.height - 1))
        if self._last not in {None, "blank"}:
            self.write("\n")
            self._last = "blank"
        opened = time.monotonic()
        answer = None
        drawn = 0
        with console.raw():
            try:
                drawn = self._draw(render_lines(), drawn)
                while answer is None:
                    keys = console.keys()
                    if time.monotonic() - opened < 0.3:
                        # Phím gõ trước khi khung hiện (Enter của tin trước…) không được thành câu trả lời.
                        continue
                    for key in keys:
                        if key.name == "interrupt":
                            raise KeyboardInterrupt
                        answer = handle(key)
                        if answer is not None:
                            break
                    if answer is None:
                        drawn = self._draw(render_lines(), drawn)
            finally:
                self._erase(drawn)
        return answer

    def _ask_typed(self, permission: Permission, options: list[Option]) -> str:
        """Không đọc được phím thô (ống dẫn, input()): in khung đứng yên rồi hỏi bằng chữ như trước."""
        lines, _ = self._panel(permission, options, -1, 0, 10_000)
        self._emit(lines[:-3] + lines[-1:], "block")
        self._static_diff = permission.kind == "file"
        choices = [option.key for option in options]
        listing = "  ".join(f"[{option.key}] {option.label}" for option in options)
        self.line("     " + listing, "dim")
        while True:
            try:
                answer = self.reader("     Chọn › ").strip().lower()
            except EOFError:
                self.line()
                return "n"
            if answer in choices:
                return answer
            self.line(f"     Gõ {', '.join(choices[:-1])} hoặc {choices[-1]} nhé.", "yellow")

    def questions(self, questions: list[dict]) -> list[list[str]] | None:
        """Câu hỏi của Peto (ask_user, CLI 0.21.0) ở chỗ ô nhập, từng câu một: ↑/↓ chọn, Enter chọn, phím số chọn
        nhanh, Space đánh dấu khi chọn nhiều, dòng cuối "Tự trả lời…" mở ô gõ ngay trong khung, Esc bỏ qua."""
        if self.engine is None:
            return super().questions(questions)
        self._flush_group()
        self.clear_status()
        waiting = self._title
        self.title("Peto · hỏi bạn")
        self.bell()
        answers = []
        try:
            for index, question in enumerate(questions):
                render_lines, handle = self._question_chooser(question, index, len(questions), max(10, self.height - 1))
                answer = self.engine.ask(render_lines, handle)
                if not answer:
                    return None
                answers.append(json.loads(answer))
        finally:
            self.title(waiting)
        return answers

    def _question_chooser(self, question: dict, index: int, total: int, budget: int):
        options = question["options"]
        multiple = question["multiple"]
        custom = len(options)
        state = {"selected": 0, "checked": set(), "typing": False, "text": ""}
        theme = self.theme

        def render_lines() -> list[Line]:
            width = self.content_width
            panel, element = theme.panel, theme.element

            def row(spans: list, bg=panel) -> Line:
                return fit(Line([S("┃", theme.secondary, bg), S("  ", bg=bg)] + spans), width, bg)

            lines = [row([S("? ", theme.secondary, panel), S(visible(question["header"]) or "Peto hỏi", theme.text,
                                                               panel, b=True),
                          S(f"  {index + 1}/{total}" if total > 1 else "", theme.muted, panel)])]
            lines += [row(spans) for spans in wrap([S(visible(question["question"]), theme.text, panel)], width - 4)]
            lines.append(row([]))
            for number, option in enumerate(options):
                chosen = number == state["selected"]
                bg = element if chosen else panel
                mark = ("[x] " if number in state["checked"] else "[ ] ") if multiple else f"{number + 1} "
                spans = [S("› " if chosen else "  ", theme.secondary, bg), S(mark, theme.muted, bg),
                         S(visible(option["label"]), theme.text, bg, b=chosen)]
                if option["description"]:
                    spans.append(S("  " + visible(option["description"]), theme.muted, bg))
                # Câu nhiều đáp án: bấm là đánh dấu (như Space); câu một đáp án: bấm là chọn luôn.
                press = Key("char", " ") if multiple else Key("enter")
                lines.append(Line(clickable(row(spans, bg).spans, self._pick(state, "selected", number, press))))
            chosen = state["selected"] == custom
            bg = element if chosen else panel
            if state["typing"]:
                lines.append(row([S("› ", theme.secondary, bg), S(theme.glyphs["write"] + " ", theme.muted, bg),
                                  S(state["text"] + "▏", theme.text, bg)], bg))
            else:
                lines.append(Line(clickable(row([S("› " if chosen else "  ", theme.secondary, bg),
                                                 S(theme.glyphs["write"] + " Tự trả lời…", theme.muted, bg, b=chosen)],
                                                bg).spans, self._pick(state, "selected", custom, Key("enter")))))
            if state["typing"]:
                hint = [("gõ câu trả lời  ", theme.muted), ("enter", theme.text), (" gửi  ", theme.muted),
                        ("esc", theme.text), (" quay lại", theme.muted)]
            elif multiple:
                hint = [("↑↓", theme.text), (" chọn  ", theme.muted), ("space", theme.text), (" đánh dấu  ", theme.muted),
                        ("enter", theme.text), (" xong  ", theme.muted), ("esc", theme.text), (" bỏ qua", theme.muted)]
            else:
                hint = [("↑↓", theme.text), (" chọn  ", theme.muted), ("enter", theme.text), (" chọn  ", theme.muted),
                        (f"1–{len(options)}", theme.text), (" chọn nhanh  ", theme.muted), ("esc", theme.text),
                        (" bỏ qua", theme.muted)]
            keys = {"enter": Key("enter"), "esc": Key("escape")}
            spans = []
            for position, (text, color) in enumerate(hint):
                # "enter" và "esc" ở chân khung bấm được, kèm chữ ngay sau chúng ("enter xong", "esc bỏ qua").
                name = text if text in keys else hint[position - 1][0] if position and hint[position - 1][0] in keys \
                    else None
                target = self._press(state, keys[name], name) if name else None
                spans += clickable([S(text, color, element)], target)
            lines += [row([]), fit(Line([S("┃", theme.secondary, element), S("  ", bg=element)] + spans), width, element),
                      Line([S("╹", theme.secondary), S("▀" * (width - 1), element)])]
            return lines

        def handle(key) -> str | None:
            if state["typing"]:
                if key.name in {"char", "paste"}:
                    state["text"] += " ".join(key.text.split()) if key.name == "paste" else key.text
                elif key.name == "backspace":
                    state["text"] = state["text"][:-1]
                elif key.name == "escape":
                    state["typing"] = False
                elif key.name == "enter" and state["text"].strip():
                    # Câu nhiều đáp án: chữ tự gõ đi cùng các mục đã đánh dấu.
                    picked = [options[number]["label"] for number in sorted(state["checked"])] if multiple else []
                    return json.dumps([*picked, state["text"].strip()], ensure_ascii=False)
                return None
            if key.name in {"up", "left"}:
                state["selected"] = (state["selected"] - 1) % (custom + 1)
            elif key.name in {"down", "right", "tab"}:
                state["selected"] = (state["selected"] + 1) % (custom + 1)
            elif key.name == "escape":
                return ""
            elif key.name == "enter":
                if state["selected"] == custom:
                    state["typing"] = True
                    return None
                if multiple:
                    picked = sorted(state["checked"]) or [state["selected"]]
                    return json.dumps([options[number]["label"] for number in picked], ensure_ascii=False)
                return json.dumps([options[state["selected"]]["label"]], ensure_ascii=False)
            elif key.name == "char" and key.text == " " and multiple and state["selected"] < custom:
                state["checked"] ^= {state["selected"]}
            elif key.name == "char" and key.text.isdigit() and 1 <= int(key.text) <= len(options):
                if multiple:
                    state["checked"] ^= {int(key.text) - 1}
                    state["selected"] = int(key.text) - 1
                else:
                    return json.dumps([options[int(key.text) - 1]["label"]], ensure_ascii=False)
            return None

        return render_lines, handle

    # ---- /btw: câu hỏi bên lề (CLI 0.23.0, theo hộp trả lời /btw của opencode)

    def ask_aside(self, question: str, run: Callable[[], tuple[str, bool]]) -> None:
        """Hỏi bên lề ở luồng riêng, kể cả lúc Peto đang làm: câu hỏi hiện "⠋ /btw …" trên ô nhập tới khi có trả lời,
        rồi hộp trả lời hiện ở chỗ ô nhập. ``run`` trả (chữ, lỗi?) và không được ném lỗi. Gọi được trong khóa màn hình."""
        engine = self.engine
        with engine.lock:
            engine.side_pending.append(question)

        def worker() -> None:
            try:
                answer, failed = run()
            except Exception:  # noqa: BLE001 - luồng nền không được chết lặng lẽ mà để dòng chờ treo mãi
                answer, failed = "Không hỏi được câu này.", True
            finally:
                with engine.lock:
                    if question in engine.side_pending:
                        engine.side_pending.remove(question)
                    engine._draw()
            self.side_answer(question, answer, failed=failed)

        threading.Thread(target=worker, name="peto-btw", daemon=True).start()

    def side_answer(self, question: str, answer: str, *, failed: bool = False) -> None:
        """Hộp trả lời /btw ở chỗ ô nhập: cao tối đa 60% màn hình, ↑/↓ PgUp/PgDn cuộn, c chép, Esc hay Enter đóng.
        Khung khác đang mở (câu hỏi quyền) thì hộp chờ nó đóng. Ctrl+C trong hộp chỉ đóng hộp, không dừng Peto."""
        if self.engine is None:
            super().side_answer(question, answer, failed=failed)
            return
        render_lines, handle = self._side_box(question, answer, failed)
        self.engine.ask(render_lines, handle, on_interrupt="")

    def _side_box(self, question: str, answer: str, failed: bool):
        theme = self.theme
        state = {"top": 0, "copied": None}

        def body(width: int) -> list[Line]:
            if failed:
                return [Line(row) for row in wrap([S(visible(answer), theme.error)], width)]
            markdown = Markdown(theme, width)
            lines: list[Line] = []
            for line in answer.split("\n"):
                lines += markdown.feed(line)
            lines += markdown.flush()
            while lines and not lines[0].spans:
                lines.pop(0)
            while lines and not lines[-1].spans:
                lines.pop()
            return lines

        def room() -> int:
            return max(4, int(self.height * 0.6) - 5)

        def render_lines() -> list[Line]:
            width = self.content_width
            panel, element = theme.panel, theme.element

            def row(spans: list, bg=panel) -> Line:
                # Chữ Markdown không có nền riêng: tô nền khung để hộp liền một khối.
                spans = [(text, {**style, "bg": style.get("bg") or bg}) for text, style in spans]
                return fit(Line([S("┃", theme.secondary, bg), S("  ", bg=bg)] + spans), width, bg)

            lines = body(max(10, width - 4))
            view = room()
            state["top"] = max(0, min(state["top"], len(lines) - view))
            top = state["top"]
            head = [S("/btw", theme.text, panel, b=True),
                    S("  " + clip(" ".join(question.split()), max(10, width - 16)), theme.muted, panel)]
            out = [row(head), row([])]
            out += [row(line.spans) for line in lines[top:top + view]]
            if state["copied"] is True:
                hint = [S("✓ Đã chép câu trả lời", theme.success, element)]
            elif state["copied"] is False:
                hint = [S("Không chép được vào clipboard", theme.warning, element)]
            else:
                hint = clickable([S("c", theme.text, element), S(" chép", theme.muted, element)],
                                 self._press(state, Key("char", "c"), "copy")) + [S("  ", bg=element)]
            if len(lines) > view:
                hint += [S("↑↓ pgup pgdn", theme.text, element),
                         S(f" cuộn · dòng {top + 1}–{min(top + view, len(lines))}/{len(lines)}  ", theme.muted, element)]
            hint += clickable([S("esc", theme.text, element), S(" đóng", theme.muted, element)],
                              self._press(state, Key("escape"), "close"))
            hint += [S(" · không thêm vào hội thoại", theme.muted, element)]
            out += [row([]), fit(Line([S("┃", theme.secondary, element), S("  ", bg=element)] + hint), width, element),
                    Line([S("╹", theme.secondary), S("▀" * (width - 1), element)])]
            return out

        def handle(key) -> str | None:
            step = room()
            if key.name in {"escape", "enter"} or (key.name == "char" and key.text in {"q", "Q"}):
                return ""
            if key.name == "up":
                state["top"] -= 1
            elif key.name == "down":
                state["top"] += 1
            elif key.name == "pageup":
                state["top"] -= step
            elif key.name == "pagedown":
                state["top"] += step
            elif key.name == "home":
                state["top"] = 0
            elif key.name == "end":
                state["top"] = 10 ** 9
            elif key.name == "char" and key.text in {"c", "C"}:
                state["copied"] = bool(self.copy(answer))
            state["top"] = max(0, state["top"])
            return None

        return render_lines, handle

    def choose(self, title: str, rows: list[tuple[str, str]]) -> int | None:
        """Bảng chọn dạng danh sách dọc ở chỗ ô nhập (/resume): ↑/↓, Enter mở, phím số chọn nhanh, Esc thôi. Không có
        màn hình toàn phần hay chân cố định thì hỏi bằng chữ như bản cũ."""
        if self.engine is None:
            return super().choose(title, rows)
        self._flush_group()
        self.clear_status()
        render_lines, handle = self._list_chooser(title, rows, max(8, self.height - 1))
        answer = self.engine.ask(render_lines, handle)
        return int(answer) if answer else None

    # ---- Khung nổi kiểu OpenCode (/models, /connect; CLI 0.32.0)

    def dialog(self, dialog):
        """Mở một khung của ``tui.dialog`` giữa màn hình (chân cố định thì ở chỗ ô nhập) rồi chờ kết quả. Esc, bấm ra
        ngoài khung hay Ctrl+C đều là đóng."""
        from .dialog import Result

        self._flush_group()
        self.clear_status()
        dialog.result = None
        self.engine.ask(lambda: dialog.render(self.theme, self.width - 2, self.height), dialog.handle,
                        on_interrupt="", overlay=True, guard=False)
        return dialog.result or Result("close")

    @contextlib.contextmanager
    def dialog_busy(self, dialog, on_key=None):
        """Giữ khung trên màn hình trong lúc nơi gọi làm việc chậm (kiểm khóa API, chờ đăng nhập ChatGPT). Phím chỉ tới
        ``on_key`` (chạy ở luồng đọc phím, không được chờ), khung không tự đóng; Ctrl+C ngắt việc đó như ngắt một yêu
        cầu. Trả hàm vẽ lại, cho nơi gọi đổi chữ trong khung."""
        from .footer import Panel

        engine = self.engine

        def handle(key):
            if on_key is not None:
                on_key(key)
            return None

        panel = Panel(lambda: dialog.render(self.theme, self.width - 2, self.height), handle, overlay=True, guard=False)
        while True:
            with engine.lock:
                if engine.panel is None:
                    engine.panel = panel
                    engine._draw()
                    break
            time.sleep(0.05)

        def redraw() -> None:
            with engine.lock:
                engine._draw()

        try:
            yield redraw
        finally:
            with engine.lock:
                if engine.panel is panel:
                    engine.panel = None
                engine._draw()

    def _list_chooser(self, title: str, rows: list[tuple[str, str]], budget: int):
        state = {"selected": 0}
        theme = self.theme

        def render_lines() -> list[Line]:
            width = self.content_width
            panel, element = theme.panel, theme.element

            def row(spans: list, bg=panel) -> Line:
                return fit(Line([S("┃", theme.primary, bg), S("  ", bg=bg)] + spans), width, bg)

            room = max(1, budget - 6)
            selected = state["selected"]
            start = min(max(0, selected - room + 1), max(0, len(rows) - room))
            lines = [row([S(title, theme.text, panel, b=True),
                          S(f"  {len(rows)} mục" if len(rows) > room else "", theme.muted, panel)]), row([])]
            for index in range(start, min(len(rows), start + room)):
                label, detail = rows[index]
                chosen = index == selected
                bg = element if chosen else panel
                number = f"{index + 1:>2} " if index < 9 else "   "
                spans = [S("› " if chosen else "  ", theme.primary, bg), S(number, theme.muted, bg),
                         S(clip(visible(label), max(10, width - 30)), theme.text, bg, b=chosen)]
                if detail:
                    spans.append(S("  " + visible(detail), theme.muted, bg))
                lines.append(Line(clickable(row(spans, bg).spans, self._pick(state, "selected", index, Key("enter")))))
            hint = [S("↑↓", theme.text, element), S(" chọn  ", theme.muted, element), S("enter", theme.text, element),
                    S(" mở  ", theme.muted, element)]
            hint += clickable([S("esc", theme.text, element), S(" thôi", theme.muted, element)],
                              self._press(state, Key("escape"), "close"))
            hint += [S("  ", bg=element), S("1–9", theme.text, element), S(" chọn nhanh", theme.muted, element)]
            lines += [row([]), fit(Line([S("┃", theme.primary, element), S("  ", bg=element)] + hint), width, element),
                      Line([S("╹", theme.primary), S("▀" * (width - 1), element)])]
            return lines

        def handle(key) -> str | None:
            if key.name in {"up", "left"}:
                state["selected"] = (state["selected"] - 1) % len(rows)
            elif key.name in {"down", "right", "tab"}:
                state["selected"] = (state["selected"] + 1) % len(rows)
            elif key.name == "pageup":
                state["selected"] = max(0, state["selected"] - max(1, budget - 6))
            elif key.name == "pagedown":
                state["selected"] = min(len(rows) - 1, state["selected"] + max(1, budget - 6))
            elif key.name == "enter":
                return str(state["selected"])
            elif key.name == "escape":
                return ""
            elif key.name == "char" and key.text.isdigit() and 1 <= int(key.text) <= min(9, len(rows)):
                return str(int(key.text) - 1)
            return None

        return render_lines, handle

    def choose_session(self, sessions: list, current: str | None, *, rename, delete):
        """Bảng /resume như opencode (``dialog-session-list.tsx``; CLI 0.22.0): gõ để tìm theo tên (không phân biệt
        dấu), nhóm Hôm nay / Hôm qua / theo ngày, Ctrl+R đổi tên ngay trên dòng, Ctrl+D bấm hai lần để xóa. Không xóa
        được hội thoại đang mở. ``rename(id, tên)`` và ``delete(id) -> bool`` ghi vào đĩa."""
        if self.engine is None:
            return super().choose_session(sessions, current, rename=rename, delete=delete)
        self._flush_group()
        self.clear_status()
        items = list(sessions)
        render_lines, handle = self._session_chooser(items, current, rename, delete, max(10, self.height - 1))
        answer = self.engine.ask(render_lines, handle)
        # Tìm trong danh sách của bảng: hội thoại vừa đổi tên mở ra với tên mới.
        return next((saved for saved in items if saved.id == answer), None)

    def _session_chooser(self, sessions: list, current: str | None, rename, delete, budget: int):
        from ..commands import fold

        theme = self.theme
        state = {"query": "", "selected": 0, "renaming": None, "text": "", "deleting": None, "message": None}
        # ``sessions`` là danh sách của riêng bảng này: đổi tên và xóa sửa thẳng trong nó.
        items = sessions

        def shown() -> list:
            query = fold(state["query"].strip())
            return [saved for saved in items if not query or query in fold(saved.title)]

        def day(saved) -> str:
            moment = datetime.fromtimestamp(saved.saved_at)
            today = date.today()
            if moment.date() == today:
                return "Hôm nay"
            if moment.date() == today - timedelta(days=1):
                return "Hôm qua"
            return f"{moment:%d/%m}" if moment.year == today.year else f"{moment:%d/%m/%Y}"

        def render_lines() -> list[Line]:
            width = self.content_width
            panel, element = theme.panel, theme.element

            def row(spans: list, bg=panel) -> Line:
                return fit(Line([S("┃", theme.primary, bg), S("  ", bg=bg)] + spans), width, bg)

            visible_items = shown()
            state["selected"] = min(state["selected"], max(0, len(visible_items) - 1))
            body: list[tuple[Line, bool]] = []
            group = None
            for index, saved in enumerate(visible_items):
                label = day(saved)
                if label != group:
                    group = label
                    body.append((row([S(label, theme.accent, panel, b=True)]), False))
                chosen = index == state["selected"]
                bg = element if chosen else panel
                spans = [S("› " if chosen else "  ", theme.primary, bg)]
                target = None if state["renaming"] or state["deleting"] else self._pick(state, "selected", index,
                                                                                      Key("enter"))
                if chosen and state["renaming"] == saved.id:
                    spans += [S(state["text"] + "▏", theme.text, bg, b=True),
                              S("  enter lưu · esc thôi", theme.muted, bg)]
                elif chosen and state["deleting"] == saved.id:
                    spans += [S(clip(visible(saved.title), max(10, width - 44)), theme.text, bg, b=True),
                              S("  bấm ctrl+d lần nữa để xóa", theme.warning, bg)]
                else:
                    detail = f"{datetime.fromtimestamp(saved.saved_at):%H:%M} · {saved.message_count} tin"
                    if saved.interrupted:
                        detail += " · bị ngắt"
                    if saved.id == current:
                        detail += " · đang mở"
                    spans += [S(clip(visible(saved.title), max(10, width - 34)), theme.text, bg, b=chosen),
                              S("  " + detail, theme.muted, bg)]
                body.append((Line(clickable(row(spans, bg).spans, target)), chosen))
            if not visible_items:
                body.append((row([S("Không có hội thoại nào khớp", theme.muted, panel)]), False))
            room = max(3, budget - 7)
            focus = next((index for index, (_, chosen) in enumerate(body) if chosen), 0)
            start = min(max(0, focus - room + 1), max(0, len(body) - room))
            query = state["query"]
            search = ([S("Tìm: ", theme.muted, panel), S(query + "▏", theme.text, panel)] if query
                      else [S("Gõ để tìm theo tên", theme.muted, panel)])
            lines = [row([S("Hội thoại", theme.text, panel, b=True),
                          S(f" của {self.folder_name}" if self.folder_name else "", theme.muted, panel)]),
                     row(search), row([])]
            lines += [line for line, _ in body[start:start + room]]
            if state["message"]:
                lines += [row([]), row([S(state["message"], theme.warning, panel)])]
            hint = [S("enter", theme.text, element), S(" mở  ", theme.muted, element), S("ctrl+r", theme.text, element),
                    S(" đổi tên  ", theme.muted, element), S("ctrl+d", theme.text, element),
                    S(" xóa  ", theme.muted, element)]
            hint += clickable([S("esc", theme.text, element), S(" thôi", theme.muted, element)],
                              self._press(state, Key("escape"), "close"))
            lines += [row([]), fit(Line([S("┃", theme.primary, element), S("  ", bg=element)] + hint), width, element),
                      Line([S("╹", theme.primary), S("▀" * (width - 1), element)])]
            return lines

        def handle(key) -> str | None:
            visible_items = shown()
            selected = visible_items[state["selected"]] if visible_items else None
            if state["renaming"] is not None:
                if key.name in {"char", "paste"}:
                    state["text"] += " ".join(key.text.split()) if key.name == "paste" else key.text
                elif key.name == "backspace":
                    state["text"] = state["text"][:-1]
                elif key.name == "escape":
                    state["renaming"] = None
                elif key.name == "enter":
                    title = " ".join(state["text"].split())
                    if title and selected is not None:
                        rename(selected.id, title)
                        items[items.index(selected)] = replace(selected, title=title)
                    state["renaming"] = None
                return None
            armed, state["deleting"], state["message"] = state["deleting"], None, None
            if key.name == "up" and visible_items:
                state["selected"] = (state["selected"] - 1) % len(visible_items)
            elif key.name == "down" and visible_items:
                state["selected"] = (state["selected"] + 1) % len(visible_items)
            elif key.name == "pageup":
                state["selected"] = max(0, state["selected"] - max(1, budget - 7))
            elif key.name == "pagedown" and visible_items:
                state["selected"] = min(len(visible_items) - 1, state["selected"] + max(1, budget - 7))
            elif key.name == "enter" and selected is not None:
                return selected.id
            elif key.name == "escape":
                return ""
            elif key.name == "ctrl" and key.text == "r" and selected is not None:
                state["renaming"], state["text"] = selected.id, selected.title
            elif key.name == "ctrl" and key.text == "d" and selected is not None:
                if selected.id == current:
                    state["message"] = "Đang mở hội thoại này nên không xóa được."
                elif armed == selected.id:
                    if delete(selected.id):
                        items.remove(selected)
                    else:
                        state["message"] = "Không xóa được hội thoại này."
                else:
                    state["deleting"] = selected.id
            elif key.name in {"char", "paste"}:
                state["query"] += " ".join(key.text.split()) if key.name == "paste" else key.text
                state["selected"] = 0
            elif key.name == "backspace":
                state["query"] = state["query"][:-1]
                state["selected"] = 0
            return None

        return render_lines, handle

    def ask_permission(self, *, allow_session: bool = False, allow_always: bool = False,
                       session_label: str = "nhớ lệnh này trong phiên", question: str = "") -> str:
        """Lối cũ (vài lệnh gạch chéo gọi thẳng): hỏi như một câu quyền chung."""
        permission = Permission("other", {}, allow_session, allow_always, session_label,
                                question or "Đồng ý?")
        return self.ask(permission)

    def wait_for_user(self) -> bool:
        """Chờ người dùng đăng nhập xong trong cửa sổ trình duyệt: khung ở chỗ ô nhập khi có chân cố định."""
        if self.engine is None:
            return super().wait_for_user()
        waiting = self._title
        self.title("Peto · cần bạn")
        self.bell()
        try:
            permission = Permission("login", {}, question="Đăng nhập xong trong cửa sổ trình duyệt chưa?")
            options = [Option("y", "Xong rồi"), Option("n", "Bỏ qua")]
            render_lines, handle = self._chooser(permission, options, max(8, self.height - 1))
            return self.engine.ask(render_lines, handle) == "y"
        finally:
            self.title(waiting)

    def clear_status(self) -> None:
        if self.engine is not None:
            self.engine.set_status(None)
            return
        super().clear_status()

    def review_diff(self, title: str, before: str, after: str) -> None:
        """/diff và /undo: khối diff đầy đủ của một tệp, xem tiếp từng trang bằng v. Có chân cố định thì in hết: diff
        nằm trong lịch sử cuộn, kéo lên xem như mọi chữ khác."""
        theme = self.theme
        panel = theme.panel
        diff = Diff(before, after, path=title.split(" ")[0])
        header = [S("← ", theme.muted, panel), S(visible(title), theme.text, panel, b=True),
                  S(f"  +{diff.added}", theme.diff_added, panel), S(f"  −{diff.removed}", theme.diff_removed, panel)]
        if self.fullscreen:
            self._emit(lambda: self._block(header, diff.rows(theme, self.content_width - 3) if not diff.empty else [
                Line([S("Nội dung không đổi.", theme.muted, panel)])]), "block")
            return
        rows = diff.rows(theme, self.content_width - 3) if not diff.empty else [
            Line([S("Nội dung không đổi.", theme.muted, panel)])]
        page = 2000 if self.engine is not None else 120
        shown = rows[:page]
        self._emit(self._block(header, shown), "block")
        position = len(shown)
        while position < len(rows):
            try:
                if self.reader(f"     Còn {len(rows) - position} dòng · [v] xem tiếp · Enter bỏ qua › ").strip().lower() != "v":
                    break
            except EOFError:
                break
            shown = rows[position:position + page]
            self._emit(self._block([S("… tiếp", theme.muted, panel)], shown), "block")
            position += len(shown)

    # ---- Câu trả lời và cuối yêu cầu

    def reply(self) -> "TerminalReply":
        return TerminalReply(self)

    def request_finished(self, end: RequestEnd) -> None:
        theme = self.theme
        if end.outcome == "done":
            spans = [S(theme.glyphs["done"] + " ", theme.primary), S("Peto", theme.primary)]
            if end.model:
                spans.append(S(f" · {end.model}", theme.muted))
            spans.append(S(f" · {format_duration(end.seconds)}", theme.muted))
        else:
            label = {"stopped": "Đã dừng sau", "error": "Dừng vì lỗi sau", "limit": "Tạm dừng sau"}[end.outcome]
            color = theme.error if end.outcome == "error" else theme.warning
            spans = [S("■ ", color), S(f"{label} {format_duration(end.seconds)}", color)]
        parts = []
        if end.changes:
            parts.append(f"sửa {len(end.changes)} tệp")
        if end.commands:
            failed = sum(1 for command in end.commands
                         if command.get("classification") not in {"passed", "success", "no_match"})
            parts.append(f"chạy {len(end.commands)} lệnh" + (f" ({failed} lỗi)" if failed else ""))
        if end.command_files:
            parts.append(f"lệnh đổi {end.command_files} tệp")
        if end.background_jobs:
            parts.append(f"đang chạy {end.background_jobs} lệnh nền")
        if end.plan_left:
            parts.append(f"còn {end.plan_left} việc chưa xong")
        if end.context_tokens:
            parts.append(f"{format_tokens(end.context_tokens)} token")
        if end.context_share is not None:
            parts.append(f"{min(100, round(end.context_share * 100))}% tới lúc tự tóm tắt")
        for part in parts:
            spans.append(S(f" · {part}", theme.muted))
        self._emit(lambda: [Line([S("   ")] + row) for row in wrap(spans, self.content_width - 3)], "footer")

    # ---- Ô nhập

    def prompt(self, *, footer: str = "", status: str = "") -> str:
        self._flush_group()
        self.clear_status()
        self.attached = []
        meta = ["Peto"] + [part.strip() for part in status.removeprefix("◉").split("·") if part.strip()]
        if self.engine is not None:
            self.engine.idle(meta, footer)
            text, images = self.engine.take()
            self.attached = list(images)
            return text
        if self.editor is not None:
            if self._last not in {None, "blank"}:
                self.write("\n")
            try:
                text = self.editor.read("› ", boxed=True, frame=lambda state, width, height: prompt_view.frame(
                    state, self.theme, width=width, height=height, meta=meta, footer=footer, colors=self.colors))
                self.attached = list(self.editor.last_images)
                self._last = "user" if text.strip() else "blank"
                return text
            except OSError:
                # Console không cho đọc phím thô nữa: quay về input() cho hết phiên.
                self.editor = None
                self.write("\n")
        text = self.reader(render(Line([S("› ", self.theme.primary)]), self.colors))
        self._last = "user"
        return text


class TerminalReply:
    """Câu trả lời của một bước: Markdown vẽ dần từng dòng, phần dở dang hiện ở dòng trạng thái."""

    def __init__(self, ui: TerminalUI):
        self.ui = ui
        self.pending = ""
        self.started = False
        self.markdown = Markdown(ui.theme, ui.content_width)
        # Màn hình toàn phần: cả câu trả lời là một khối, vẽ lại từ nguồn mỗi khi có chữ mới hay cửa sổ đổi cỡ.
        self.source = ""
        self.entry = None
        self._thought: list[str] = []
        self._think_started: float | None = None
        self._think_ended: float | None = None
        self._thought_done = False

    def think(self, text: str) -> None:
        if self._think_started is None:
            self._think_started = time.monotonic()
        self._thought.append(text)
        title = thought_title("".join(self._thought))
        self.ui.thinking_title = clip(title, 60) if title else None

    def _commit_thought(self) -> None:
        if self._thought_done or self._think_started is None:
            return
        self._thought_done = True
        seconds = (self._think_ended or time.monotonic()) - self._think_started
        title = thought_title("".join(self._thought))
        text = f"+ Đã nghĩ: {clip(title, 60)} · {_seconds(seconds).replace(' giây', 's')}" if title else \
            f"+ Đã nghĩ · {_seconds(seconds).replace(' giây', 's')}"
        self.ui.thinking_title = None
        thought = "".join(self._thought)
        ui = self.ui
        state: dict = {}
        # Bấm dòng "+ Đã nghĩ" thì toàn văn hiện ngay dưới, như opencode (CLI 0.24.0); /thinking mở tất cả.
        target = ui._opener(state) if thought.strip() else None

        def build() -> list[Line]:
            opened = bool(thought.strip()) and (ui.show_thoughts or state.get("open"))
            label = "− " + text[2:] if opened and target is not None else text
            lines = [Line([S("   ")] + clickable([S(visible(label), ui.theme.thought)], target))]
            for paragraph in thought.split("\n") if opened else []:
                spans = [S(visible(paragraph.replace("**", "")), ui.theme.muted, i=True)]
                lines += [Line([S("     ")] + row) for row in wrap(spans, ui.content_width - 5)]
            return lines

        state["entry"] = self.ui._emit(build, "row")

    def _render(self) -> list[Line]:
        """Cả câu trả lời tới lúc này, vẽ theo bề ngang hiện tại; dòng đang viết dở cũng hiện luôn."""
        markdown = Markdown(self.ui.theme, self.ui.content_width)
        lines: list[Line] = []
        for line in self.source.split("\n"):
            lines += markdown.feed(line)
        lines += markdown.flush()
        while lines and not lines[0].spans:
            lines.pop(0)
        while lines and not lines[-1].spans:
            lines.pop()
        return lines

    def feed(self, text: str) -> None:
        if text and not self.started:
            self._think_ended = time.monotonic()
            self._commit_thought()
        self.started = self.started or bool(text)
        if self.ui.fullscreen:
            self.source += text
            if self.entry is not None:
                self.entry.changed()
                self.ui.engine.changed()
            elif self.source.strip():
                self.ui.clear_status()
                self.entry = self.ui._emit(self._render, "text")
            return
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._emit(self.markdown.feed(line))
        if self.pending.strip():
            self.ui.status(f"… {visible(self.pending.rstrip(chr(13)).expandtabs(4))[-(self.ui.content_width - 10):]}")

    def finish(self) -> None:
        self._commit_thought()
        if self.ui.fullscreen:
            self.ui.thinking_title = None
            return
        if self.pending:
            self._emit(self.markdown.feed(self.pending))
            self.pending = ""
        self._emit(self.markdown.flush())
        self.ui.thinking_title = None

    def _emit(self, lines: list[Line]) -> None:
        if lines:
            self.ui.clear_status()
            self.ui._emit(lines, "text")
