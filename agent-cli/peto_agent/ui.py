"""Hiển thị trong terminal: màu, dòng bước, dòng trạng thái tạm, Markdown tối thiểu, diff và câu hỏi đồng ý."""

from __future__ import annotations

import difflib
import os
import re
import shutil
import sys
import unicodedata

from . import texmath

COLORS = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}
COLORS.update(input="48;5;236;38;5;252", input_hint="48;5;236;38;5;245", input_marker="48;5;236;38;5;117")
MAX_DIFF_LINES = 120
MAX_OUTPUT_LINES = 8
PERMISSION_QUESTION = "    Đồng ý? [y] có  [n] không  [a] có cho mọi bước trong yêu cầu này › "
# Về đầu dòng rồi xóa cả dòng: dùng để vẽ lại và xóa dòng trạng thái tạm.
CLEAR_LINE = "\r\033[2K"

# Markdown tối thiểu cho câu trả lời của Peto: chữ đậm, mã, tiêu đề, gạch đầu dòng, trích dẫn và khối code.
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
INLINE_CODE = re.compile(r"(`[^`\n]+`)")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")


def cell_width(char: str) -> int:
    if unicodedata.combining(char) or unicodedata.category(char) in {"Mn", "Me", "Cf"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def visible(text: str) -> str:
    """Hiện ký tự điều khiển thành chữ, để nội dung tệp không thể vẽ đè câu hỏi đồng ý."""
    return "".join(f"\\x{ord(char):02x}" if unicodedata.category(char) in {"Cc", "Cs"} else char for char in text)


def wrap_cells(text: str, width: int, *, words: bool = False) -> list[str]:
    """Ngắt theo cột terminal, giữ đủ chữ và khoảng trắng của code, kể cả tiếng Việt dấu tổ hợp."""
    lines, current, used = [], "", 0
    for char in text:
        size = cell_width(char)
        if current and used + size > width:
            split = current.rfind(" ") if words else -1
            if split > 0:
                lines.append(current[:split])
                current = current[split + 1:]
                used = sum(map(cell_width, current))
            else:
                lines.append(current)
                current, used = "", 0
        current += char
        used += size
    return [*lines, current]


def clip_cells(text: str, width: int) -> str:
    if sum(map(cell_width, text)) <= width:
        return text
    return wrap_cells(text, max(1, width - 1))[0] + "…"


def output_lines(text: str) -> list[str]:
    return [visible(line.expandtabs(4)) for line in ANSI.sub("", text).splitlines() if line.strip()]


def enable_vt(stream) -> bool:
    """Bật mã điều khiển ANSI (màu, di chuyển con trỏ) cho terminal; False khi output không phải terminal."""
    if not hasattr(stream, "isatty") or not stream.isatty():
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
            if not kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                return False
        except (AttributeError, OSError):
            return False
    return os.environ.get("TERM") != "dumb"


def enable_colors(stream) -> bool:
    return "NO_COLOR" not in os.environ and enable_vt(stream)


def _plain(text: str) -> str:
    """Bỏ dấu Markdown trong đoạn sẽ được tô nguyên dòng (tiêu đề, trích dẫn)."""
    text = INLINE_CODE.sub(lambda match: match.group(1)[1:-1], text)
    return BOLD.sub(r"\1", LINK.sub(r"\1 (\2)", text))


class UI:
    def __init__(self, *, out=None, reader=input, colors: bool | None = None, width: int | None = None):
        self.out = out or sys.stdout
        self.reader = reader
        self.terminal = enable_vt(self.out) if colors is not True else True
        self.colors = (self.terminal and "NO_COLOR" not in os.environ) if colors is None else colors
        self._width = width
        self._status: str | None = None
        self._in_code = False
        self._in_math = False
        self._diff_rows: list[tuple[str, str, str | None]] = []
        self._diff_position = 0
        # Tiêu đề cửa sổ đang đặt, để hỏi quyền xong thì trả lại trạng thái trước đó.
        self._title = ""
        # Ô nhập có gợi ý lệnh (line_editor); None thì dấu nhắc dùng reader như input().
        self.editor = None
        # Ảnh gửi kèm lượt nhập vừa xong: (số ảnh, ảnh). Chỉ ô nhập mới dán được ảnh.
        self.attached: list = []

    @property
    def width(self) -> int:
        # Chừa một cột để dòng trạng thái không tự xuống hàng ở mép phải.
        return max(20, (self._width or shutil.get_terminal_size((100, 24)).columns) - 1)

    def _wrapped(self, prefix: str, text: str, color: str | None = None, *, code: bool = False) -> None:
        continuation = " " * max(0, len(prefix) - 2) + "│ " if code else " " * len(prefix)
        for index, part in enumerate(wrap_cells(text, max(1, self.width - len(prefix)), words=not code)):
            self.line((prefix if index == 0 else continuation) + part, color)

    def _rule(self) -> None:
        if self.terminal:
            self.line("  " + "─" * max(1, self.width - 4), "dim")

    def reply(self) -> ReplyWriter:
        return ReplyWriter(self)

    def session_header(self, version: str, directory: str, account: str, effort: str, quota: str, hint: str, *,
                       model: str = "Peto") -> None:
        if not self.terminal:
            self.line(f"Peto Agent {version} · {os.path.basename(directory)} · {account} · {model} · mức {effort} · "
                      f"hôm nay còn {quota} bước")
            self.line(hint, "dim")
            return
        self.line()
        self.line(self.paint("  Peto Agent", "cyan") + self.paint(f"  {version}", "dim"))
        self._rule()
        self._wrapped("  ", visible(directory))
        self._wrapped("  ", f"{visible(account)} · {model} · mức {effort} · còn {quota} bước", "dim")
        self._rule()
        self._wrapped("  ", hint, "dim")
        self.line()

    def paint(self, text: str, color: str | None) -> str:
        if not color or not self.colors:
            return text
        return f"\033[{COLORS[color]}m{text}\033[0m"

    def write(self, text: str, color: str | None = None) -> None:
        if self._status is not None:
            self.out.write(CLEAR_LINE)
            self._status = None
        self.out.write(self.paint(text, color))
        self.out.flush()

    def line(self, text: str = "", color: str | None = None) -> None:
        self.write(text + "\n", color)

    def status(self, text: str) -> None:
        """Dòng trạng thái tạm như "… Peto đang nghĩ · 8s": vẽ đè tại chỗ, tự biến mất khi có gì khác được in.

        Chỉ hiện khi terminal hiểu mã điều khiển; output chuyển sang tệp hay ống dẫn thì bỏ qua.
        """
        text = clip_cells(visible(text), self.width)
        if not self.terminal or text == self._status:
            return
        self.out.write(CLEAR_LINE + self.paint(text, "dim"))
        self.out.flush()
        self._status = text

    def clear_status(self) -> None:
        if self._status is not None:
            self.out.write(CLEAR_LINE)
            self.out.flush()
            self._status = None

    def markdown(self, line: str) -> str | None:
        """Một dòng Markdown của câu trả lời.

        Công thức LaTeX được đổi sang ký hiệu Unicode vì terminal không vẽ được LaTeX, kể cả khi không có màu; phần
        tô màu chỉ làm khi terminal có màu. Trả None cho dòng chỉ là dấu mở hay đóng công thức (\\[, \\], $$,
        \\begin{align*}…), để khỏi in những dòng trống thừa.
        """
        if FENCE.match(line):
            self._in_code = not self._in_code
            return self.paint(line, "dim") if self.colors else line
        if self._in_code:
            return self.paint(line, "cyan") if self.colors else line
        stripped = line.strip()
        if self._in_math:
            if stripped.endswith("\\]") or stripped == "$$":
                self._in_math = False
                stripped = stripped[:-2]
            text = texmath.convert(stripped)
            return f"    {text}" if text else None
        if stripped in ("\\[", "$$") or (stripped.startswith("\\[") and "\\]" not in stripped):
            self._in_math = True
            text = texmath.convert(stripped[2:])
            return f"    {text}" if text else None
        if (formula := texmath.display_line(line)) is not None:
            return f"    {formula}"
        line = texmath.inline(line)
        if not self.colors:
            return line
        if RULE.match(line):
            return self.paint("─" * 40, "dim")
        if match := HEADING.match(line):
            return self.paint(_plain(match.group(1)), "bold")
        if match := QUOTE.match(line):
            return self.paint("│ " + _plain(match.group(1)), "dim")
        if match := BULLET.match(line):
            return f"{match.group(1)}• {self._inline(match.group(2))}"
        return self._inline(line)

    def end_markdown(self) -> None:
        """Hết một câu trả lời: khối code hay công thức chưa đóng không được lan sang chữ in sau."""
        self._in_code = False
        self._in_math = False

    def _inline(self, text: str) -> str:
        parts = []
        # Tách mã trước để dấu ** nằm trong mã không bị hiểu thành chữ đậm.
        for part in INLINE_CODE.split(text):
            if len(part) >= 3 and part.startswith("`") and part.endswith("`"):
                parts.append(self.paint(part[1:-1], "cyan"))
            else:
                part = LINK.sub(r"\1 (\2)", part)
                parts.append(BOLD.sub(lambda match: self.paint(match.group(1), "bold"), part))
        return "".join(parts)

    def plan(self, steps: list[dict]) -> None:
        """Danh sách việc của yêu cầu dài, in lại mỗi lần Peto cập nhật để thấy đang tới đâu."""
        marks = {"done": ("☑ ", "dim"), "running": ("▶ ", "blue")}
        self.line()
        for step in steps:
            mark, color = marks.get(step.get("status"), ("☐ ", None))
            self._wrapped("  " + mark, visible(str(step.get("title", ""))), color)

    def bell(self) -> None:
        """Kêu một tiếng khi Peto cần người dùng hoặc vừa xong việc lâu. Tắt bằng PETO_AGENT_NO_BELL=1."""
        if self.terminal and not os.environ.get("PETO_AGENT_NO_BELL"):
            self.out.write("\a")
            self.out.flush()

    def title(self, text: str) -> None:
        """Đổi tiêu đề cửa sổ terminal, để liếc thanh tác vụ là biết Peto xong chưa."""
        self._title = text
        if self.terminal:
            # Kết thúc bằng ST (ESC \) chứ không phải BEL, để tiếng chuông chỉ vang khi Peto thật sự gọi.
            self.out.write(f"\033]0;{visible(text)}\033\\")
            self.out.flush()

    def step(self, text: str) -> None:
        self.line(f"  • {text}", "dim")

    def success(self, text: str) -> None:
        self.line(f"  ✓ {text}", "green")

    def failure(self, text: str) -> None:
        self.line(f"  ✗ {text}", "red")

    def diff(self, title: str, before: str, after: str) -> None:
        old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
        groups = list(difflib.SequenceMatcher(None, old, new).get_grouped_opcodes(2))
        added = sum(j2 - j1 for group in groups for tag, _, _, j1, j2 in group if tag in {"insert", "replace"})
        removed = sum(i2 - i1 for group in groups for tag, i1, i2, _, _ in group if tag in {"delete", "replace"})
        self.line()
        self._wrapped("  ✎ ", visible(title), "blue")
        self.line(f"    +{added} thêm · −{removed} xóa", "dim")
        self._rule()
        digits = max(3, len(str(max(len(old), len(new)))))
        self.line(f"    {'Cũ':>{digits}} {'Mới':>{digits}} │", "dim")
        self._diff_rows = []
        self._diff_position = 0
        for group in groups:
            self._diff_rows.append(("    ", f"@@ dòng {group[0][1] + 1} → {group[0][3] + 1} @@", "dim"))
            for tag, i1, i2, j1, j2 in group:
                if tag in {"equal", "delete", "replace"}:
                    for index in range(i1, i2):
                        equal = tag == "equal"
                        self._diff_row(index + 1, j1 + index - i1 + 1 if equal else None,
                                       " " if equal else "−", old[index], digits, None if equal else "red")
                if tag in {"insert", "replace"}:
                    for index in range(j1, j2):
                        self._diff_row(None, index + 1, "+", new[index], digits, "green")
        if not self._diff_rows:
            self.line("    Nội dung không đổi.", "dim")
        self._show_diff_page()

    def review_diff(self, title: str, before: str, after: str) -> None:
        self.diff(title, before, after)
        while self._diff_position < len(self._diff_rows):
            try:
                if self.reader("    [v] xem tiếp · Enter bỏ qua › ").strip().lower() != "v":
                    break
            except EOFError:
                break
            self._show_diff_page()
        self._diff_rows = []

    def _diff_row(self, old: int | None, new: int | None, sign: str, text: str, digits: int,
                  color: str | None) -> None:
        prefix = f"    {str(old or ''):>{digits}} {str(new or ''):>{digits}} │ {sign} "
        self._diff_rows.append((prefix, visible(text.rstrip("\n").expandtabs(4)), color))
        if not text.endswith("\n"):
            self._diff_rows.append(("    ", "↳ Dòng này không có ký tự xuống dòng ở cuối tệp.", "dim"))

    def _show_diff_page(self) -> None:
        end = min(len(self._diff_rows), self._diff_position + MAX_DIFF_LINES)
        for prefix, text, color in self._diff_rows[self._diff_position:end]:
            self._wrapped(prefix, text, color, code=True)
        self._diff_position = end
        self._rule()
        if end < len(self._diff_rows):
            self._wrapped("    ", f"Còn {len(self._diff_rows) - end} dòng · gõ v để xem tiếp trước khi quyết định.", "dim")

    def command(self, command: str, directory: str, timeout: int, *, shell: str = "cmd",
                background: bool = False) -> None:
        powershell = shell == "powershell"
        self._diff_rows = []
        self.line()
        self.line(("  ▶ Muốn chạy lệnh nền" if background else "  ▶ Muốn chạy lệnh")
                  + (" bằng PowerShell" if powershell else ""), "blue")
        self._wrapped("    ", visible(directory), "dim")
        self._wrapped("    ", "Chạy tiếp sau khi yêu cầu xong, tới khi Peto dừng hoặc bạn đóng peto" if background
                      else f"Giới hạn {timeout} giây · Ctrl+C dừng lệnh", "dim")
        self._rule()
        for line in command.split("\n"):
            self._wrapped("    PS> " if powershell else "    $ ", visible(line.expandtabs(4)), code=True)
        self._rule()

    def command_progress(self, seconds: float, output: str) -> None:
        label = f"… Đang chạy lệnh · {int(seconds)}s · Ctrl+C dừng"
        lines = output_lines(output)
        if lines and self.width > 60:
            label += " │ " + lines[-1]
        self.status(label)

    def command_result(self, result: dict) -> None:
        self.clear_status()
        lines = output_lines(str(result.get("output") or ""))
        if len(lines) > MAX_OUTPUT_LINES:
            self.line(f"    … {len(lines) - MAX_OUTPUT_LINES} dòng trước được thu gọn", "dim")
        for line in lines[-MAX_OUTPUT_LINES:]:
            self._wrapped("    │ ", line, "dim", code=True)
        summary = f"{result['seconds']} giây"
        if result.get("classification") == "no_match":
            self.line(f"  {summary} · không tìm thấy kết quả", "dim")
            return
        if result.get("classification") == "environment_error":
            self.failure(f"{summary} · có dấu hiệu lỗi môi trường; chưa xác minh được code")
            return
        if result.get("classification") == "no_tests":
            self.line(f"  {summary} · không thu thập được bài kiểm thử; chưa xác minh được code", "yellow")
            return
        if result.get("error"):
            self.failure(f"{summary} · {result['error']}")
        elif result["exit_code"] == 0:
            self.success(f"{summary} · xong")
        else:
            self.failure(f"{summary} · mã thoát {result['exit_code']}")

    def ask_permission(self, *, allow_session: bool = False) -> str:
        """Hỏi y/n/a. Hết đầu vào (EOF) thì coi như không đồng ý."""
        self.clear_status()
        waiting = self._title
        self.title("Peto · cần bạn duyệt")
        self.bell()
        try:
            return self._ask(allow_session)
        finally:
            self.title(waiting)

    def _ask(self, allow_session: bool) -> str:
        while True:
            try:
                question = PERMISSION_QUESTION
                if allow_session:
                    question = "    [s] nhớ đúng lệnh này trong phiên · " + question.strip()
                if self._diff_position < len(self._diff_rows):
                    question = "    [v] xem thêm diff · " + question.strip()
                if self.terminal:
                    self._wrapped("    ", question.strip().removesuffix(" ›"), "dim")
                    question = "    Chọn › "
                answer = self.reader(question).strip().lower()
            except EOFError:
                self._diff_rows = []
                self.line()
                return "n"
            if answer == "v" and self._diff_position < len(self._diff_rows):
                self._show_diff_page()
                continue
            if answer in ({"y", "n", "a", "s"} if allow_session else {"y", "n", "a"}):
                self._diff_rows = []
                return answer
            self.line("    Gõ y, n, a hoặc s nhé." if allow_session else "    Gõ y, n hoặc a nhé.", "yellow")

    def prompt(self, *, footer: str = "") -> str:
        self.clear_status()
        self.attached = []
        if self.editor is not None:
            try:
                text = self.editor.read("› ", self.paint, boxed=True, footer=footer)
                self.attached = list(self.editor.last_images)
                return text
            except OSError:
                # Console không cho đọc phím thô nữa: quay về input() cho hết phiên.
                self.editor = None
                self.line()
        return self.reader(self.paint("› ", "yellow"))


class ReplyWriter:
    """Markdown theo dòng, kèm dòng chữ tạm để câu dài vẫn hiện trong lúc đang nhận."""

    def __init__(self, ui: UI):
        self.ui = ui
        self.pending = ""
        self.started = False
        self._emitted = False

    def feed(self, text: str) -> None:
        self.started = self.started or bool(text)
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._emit(line)
        if self.pending:
            # Cả câu vẫn được in đủ khi xong; dòng tạm giữ phần cuối để thấy chữ đang tới.
            part = visible(self.pending.rstrip("\r").expandtabs(4))
            if sum(map(cell_width, part)) > self.ui.width - 9:
                part = "…" + wrap_cells(part, max(1, self.ui.width - 10))[-1]
            self.ui.status("Peto › " + part)

    def finish(self) -> None:
        if self.pending:
            self._emit(self.pending)
            self.pending = ""
        self.ui.end_markdown()

    def _emit(self, line: str) -> None:
        rendered = self.ui.markdown(visible(line.rstrip("\r").expandtabs(4)))
        if rendered is None:
            # Dòng chỉ là dấu mở hay đóng công thức: không in, và nhãn "Peto ›" để dành cho dòng có chữ đầu tiên.
            return
        label = "" if self._emitted else self.ui.paint("Peto › ", "cyan")
        self._emitted = True
        self.ui.line(label + rendered)
