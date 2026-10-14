"""Hiển thị trong terminal: màu, dòng bước, dòng trạng thái tạm, Markdown tối thiểu, diff và câu hỏi đồng ý."""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import sys
import unicodedata
from urllib.parse import urlsplit

from . import mascot, texmath
from .events import PERMISSION_QUESTION, Permission, RequestEnd, ToolCall, ToolDone
from .formats import format_duration, format_tokens

COLORS = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}
# Chừa ít nhất ngần này cột cho ba dòng chữ bên phải mascot; cửa sổ hẹp hơn thì bỏ hình, chỉ in chữ.
HEADER_TEXT_MIN = 30
# Số dòng cần ngoài hình: hai dòng trống quanh đầu phiên và năm dòng của ô nhập (trạng thái, hai đường kẻ, dòng nhập,
# dòng dưới). Dòng lệnh vừa gõ được phép trôi lên. Cửa sổ thấp hơn thì dùng cỡ hình nhỏ hơn, để lúc mở không trôi mất
# phần trên của hình: bảng terminal chừng 13 dòng của VS Code vừa đủ cho quả lê 6×6.
HEADER_SPARE_ROWS = 7
# Terminal của VS Code che khoảng hai cột sát mép phải (ngày 2026-09-22 chủ web thấy mất chữ cuối của dòng trạng thái
# canh phải ở VS Code 1.138; đo trên hai cỡ bảng 157 và 168 cột đều hụt chừng 2,2 cột), nên ở đó chừa thêm chừng ấy cột.
VSCODE_COVERED_COLUMNS = 2
MAX_DIFF_LINES = 120
# Số lỗi trang in dưới mỗi lần Peto xem trang; Peto vẫn nhận đủ.
MAX_PAGE_PROBLEMS = 5
MAX_OUTPUT_LINES = 8
OUTCOME_LABELS = {"done": "Xong trong", "stopped": "Đã dừng sau", "error": "Dừng vì lỗi sau", "limit": "Tạm dừng sau"}
OUTCOME_MARKS = {"done": "✓", "stopped": "■", "error": "✗", "limit": "■"}
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


def terminal_size() -> tuple[int, int]:
    """Cỡ terminal (cột, dòng) dùng được để vẽ: đã trừ các cột sát mép phải mà terminal che mất.

    VS Code tự đặt ``TERM_PROGRAM=vscode`` cho terminal tích hợp của nó.
    """
    columns, lines = shutil.get_terminal_size((100, 24))
    covered = VSCODE_COVERED_COLUMNS if os.environ.get("TERM_PROGRAM") == "vscode" else 0
    return max(1, columns - covered), lines


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


def _seconds(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " giây"


def _count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _viewport_label(viewport: str) -> str:
    from .browser import viewport_label
    return viewport_label(viewport)


def page_notes(result: dict) -> list[str]:
    """Hộp thoại và việc Peto chặn (trang ngoài, tab mới, tải tệp) cho dòng chi tiết. Hộp thoại in ở dòng mờ chứ không
    thành dòng lỗi đỏ: hộp thoại không phải lỗi."""
    dialogs = ["hộp thoại " + "; ".join(result["dialogs"])] if result.get("dialogs") else []
    return dialogs + list(result.get("notes") or [])


def _where(url: str) -> str:
    """localhost:5173/admin: địa chỉ gọn cho dòng tổng kết."""
    parts = urlsplit(url or "")
    return f"{parts.netloc}{parts.path if parts.path != '/' else ''}" or url


def _page_details(page: dict) -> str:
    details = [f"Tải xong {_seconds(page['seconds'])}" if page.get("loaded")
               else f"Chưa tải xong sau {_seconds(page['seconds'])}"]
    if page.get("status") and page["status"] >= 400:
        details.append(f"HTTP {page['status']}")
    details.append(f"\"{page['title']}\"" if page.get("title") else "không có tiêu đề")
    details.append(f"{len(page['problems'])} lỗi" if page.get("problems") else "không lỗi")
    return " · ".join(details + page_notes(page))


def action_details(kind: str, result: dict) -> str:
    """Dòng chi tiết dưới một thao tác (bản phác chủ web chọn ngày 2026-09-23): trang chuyển tới đâu, chữ mới hiện, hộp
    thoại, việc bị chặn, số lỗi. Gõ mà không có gì mới thì không in dòng này."""
    parts = []
    if result.get("new_page") or result.get("moved"):
        parts.append(f"Chuyển tới {urlsplit(result['url']).path or '/'}"
                     + (f' · "{result["title"]}"' if result.get("title") else ""))
    elif result.get("appeared"):
        more = len(result["appeared"]) - 1
        parts.append(f'Hiện thêm: "{_clip(result["appeared"][0], 80)}"' + (f" (+{more} dòng)" if more else ""))
    elif kind == "click" and not result.get("elements") and not page_notes(result):
        parts.append("Chữ trên trang không đổi")
    parts += page_notes(result)
    if parts or result.get("problems"):
        parts.append(f"{len(result['problems'])} lỗi" if result.get("problems") else "không lỗi")
    return " · ".join(parts)


# Dòng báo khi người dùng từ chối, theo công cụ.
REFUSED_LINES = {
    "edit_file": "Không sửa {path}", "write_file": "Không ghi {path}", "delete_file": "Không xóa {path}",
    "move_file": "Không đổi tên {path}", "start_command": "Không chạy lệnh nền", "run_command": "Không chạy lệnh",
    "browser_open": "Không mở trang ngoài", "browser_click": "Không thao tác trên trang",
    "browser_type": "Không thao tác trên trang", "browser_press": "Không thao tác trên trang",
    "apply_patch": "Không áp bản patch (từ {path})",
}
READ_ONLY_LINES = {
    "browser_login": "Trang ngoài chỉ xem: Peto không nhờ đăng nhập trên trang ngoài.",
}


class UI:
    def __init__(self, *, out=None, reader=input, colors: bool | None = None, width: int | None = None,
                 height: int | None = None):
        self.out = out or sys.stdout
        self.reader = reader
        self.terminal = enable_vt(self.out) if colors is not True else True
        self.colors = (self.terminal and "NO_COLOR" not in os.environ) if colors is None else colors
        self._width = width
        self._height = height
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
        # Chế độ làm việc ("build") hay Lập kế hoạch ("plan", CLI 0.20.0): Tools chặn sửa tệp khi đang lập kế hoạch.
        self.mode = "build"

    @property
    def width(self) -> int:
        # Chừa một cột để dòng trạng thái không tự xuống hàng ở mép phải.
        return max(20, (self._width or terminal_size()[0]) - 1)

    @property
    def height(self) -> int:
        return self._height or terminal_size()[1]

    def _wrapped(self, prefix: str, text: str, color: str | None = None, *, code: bool = False) -> None:
        continuation = " " * max(0, len(prefix) - 2) + "│ " if code else " " * len(prefix)
        for index, part in enumerate(wrap_cells(text, max(1, self.width - len(prefix)), words=not code)):
            self.line((prefix if index == 0 else continuation) + part, color)

    def page(self, title: str, details: str, problems: list[str], *, path: str | None = None) -> None:
        """Một lần Peto xem trang (chủ web chọn ngày 2026-09-23): dòng chính, dòng chi tiết, tối đa 5 lỗi Peto thấy.

        Đường dẫn ảnh in liền một dòng, không tự ngắt, để terminal VS Code còn nhận ra và cho Ctrl+Click mở ảnh.
        """
        self.step(visible(title))
        if details:
            self._wrapped("    ", visible(details), "dim")
        for problem in problems[:MAX_PAGE_PROBLEMS]:
            self._wrapped("    ✗ ", visible(problem), "red")
        if len(problems) > MAX_PAGE_PROBLEMS:
            self.line(f"    … còn {len(problems) - MAX_PAGE_PROBLEMS} lỗi", "dim")
        if path:
            self.line(f"    ảnh: {visible(path)}", "dim")

    def page_permission(self, origin: str, action: str) -> None:
        """Lần đầu Peto bấm, gõ trên một trang (chủ web chọn ngày 2026-09-23: hỏi một lần mỗi trang)."""
        self._diff_rows = []
        self.line()
        self._wrapped("  ▶ ", f"Muốn bấm và gõ trên {visible(origin)}", "blue")
        self._wrapped("    ", f"Trước tiên: {visible(action)}", "dim")
        self._wrapped("    ", "Đây là thao tác thật trên app đang chạy: có thể gửi form, xóa dữ liệu hay gọi dịch vụ "
                              "thật như bạn bấm.", "dim")

    def site_permission(self, url: str, site: str, unusual: bool = False) -> None:
        """Lần đầu Peto mở một tên miền ngoài máy (chủ web chọn ngày 2026-09-24: hỏi mỗi tên miền, kèm đủ địa chỉ)."""
        self._diff_rows = []
        self.line()
        self.line("  ▶ Muốn mở trang ngoài" + (" (địa chỉ dài bất thường)" if unusual else ""), "blue")
        self._wrapped("    ", visible(url), code=True)
        if unusual:
            self._wrapped("    ", f"Phần sau tên miền dài có thể đang mang dữ liệu của bạn tới {visible(site)}: xem kỹ "
                                  "rồi hãy đồng ý. Đồng ý chỉ mở đúng địa chỉ này.", "yellow")
        else:
            self._wrapped("    ", "Trình duyệt riêng, không cookie hay đăng nhập nào; Peto chỉ xem.", "dim")

    def hand_over(self, reason: str) -> None:
        """Peto nhờ người dùng tự đăng nhập trong cửa sổ trình duyệt; mật khẩu không đi qua Peto."""
        self.line()
        self._wrapped("  ▶ ", f"Peto nhờ bạn: {visible(reason)}", "blue")
        self._wrapped("    ", "Cửa sổ trình duyệt của Peto đang mở trang này. Đăng nhập xong thì quay lại đây bấm "
                              "Enter; gõ n để bỏ qua.", "dim")
        self._wrapped("    ", "Peto không thấy mật khẩu bạn gõ.", "dim")

    def wait_for_user(self) -> bool:
        """Chờ người dùng làm xong trong cửa sổ trình duyệt: Enter là xong, n là bỏ qua; hết đầu vào là bỏ qua."""
        self.clear_status()
        waiting = self._title
        self.title("Peto · cần bạn")
        self.bell()
        try:
            while True:
                try:
                    answer = self.reader("    Xong chưa? › ").strip().lower()
                except EOFError:
                    self.line()
                    return False
                if answer in {"", "y", "ok", "xong", "rồi", "roi"}:
                    return True
                if answer in {"n", "no", "không", "khong", "bỏ", "bo"}:
                    return False
                self.line("    Bấm Enter khi xong, hoặc gõ n để bỏ qua.", "yellow")
        finally:
            self.title(waiting)

    def questions(self, questions: list[dict]) -> list[list[str]] | None:
        """Câu hỏi có lựa chọn của Peto (ask_user, CLI 0.21.0): in lựa chọn đánh số, gõ số (chọn nhiều thì cách nhau
        bằng dấu phẩy) hoặc tự gõ câu trả lời; Enter trống hay hết đầu vào là bỏ qua cả lượt hỏi."""
        self.bell()
        answers = []
        for question in questions:
            self.line()
            self.line(f"  ? {question['header']}: {question['question']}", "blue")
            options = question["options"]
            for number, option in enumerate(options, 1):
                self.line(f"    {number}. {option['label']}" + (f" · {option['description']}" if option["description"]
                                                                  else ""))
            hint = "các số, cách nhau bằng dấu phẩy" if question["multiple"] else "một số"
            try:
                answer = self.reader(f"    Gõ {hint}, hoặc tự trả lời; Enter để bỏ qua › ").strip()
            except EOFError:
                self.line()
                return None
            if not answer:
                return None
            picks = [part.strip() for part in answer.split(",")] if question["multiple"] else [answer]
            if all(part.isdigit() and 1 <= int(part) <= len(options) for part in picks):
                answers.append([options[int(part) - 1]["label"] for part in picks])
            else:
                answers.append([answer])
        return answers

    def choose(self, title: str, rows: list[tuple[str, str]]) -> int | None:
        """Chọn một mục trong danh sách (như /resume): in danh sách đánh số rồi hỏi số; Enter trống hay hết đầu vào
        là thôi. ``rows`` là các cặp (tên, chi tiết mờ)."""
        self.line(f"  {title}:")
        for number, (label, detail) in enumerate(rows, 1):
            self.line(f"    {number}. {label}" + (f" · {detail}" if detail else ""))
        while True:
            try:
                answer = self.reader(f"    Chọn 1–{len(rows)}, Enter để thôi › ").strip()
            except EOFError:
                self.line()
                return None
            if not answer:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(rows):
                return int(answer) - 1
            self.line(f"    Gõ một số từ 1 tới {len(rows)}.", "yellow")

    def clear_conversation(self) -> bool:
        """/new, /resume, /fork: in nối tiếp thì không xóa được gì (màn hình toàn phần xóa và vẽ lại đầu phiên)."""
        return False

    def replay(self, items: list[dict]) -> None:
        """Mở lại một hội thoại: bản in chữ chỉ nhắc tin cuối của bạn và câu trả lời cuối; màn hình toàn phần vẽ lại cả
        hội thoại (CLI 0.22.0)."""
        from . import history

        for who, text in history.recap(items):
            self.line(f"    {who} › {text}", "dim")

    def link_user_entry(self, item: dict | None) -> None:
        """Màn hình toàn phần nhớ khung của từng tin để /timeline nhảy tới; bản in chữ không cuộn được nên bỏ qua."""

    def jump_to(self, item: dict) -> bool:
        return False

    def prefill(self, text: str) -> None:
        """/fork: không đặt sẵn chữ vào input() được, nên in ra để chép lại."""
        self.line("  Chữ của tin đó (chép lại để gửi):", "dim")
        self.line("    " + text.replace("\n", "\n    "))

    def copy(self, text: str) -> bool:
        return False

    def choose_session(self, sessions: list, current: str | None, *, rename, delete):
        """Bảng /resume: chọn một hội thoại đã lưu (``history.Saved``), hoặc None. Bản chữ chỉ có danh sách đánh số;
        màn hình toàn phần thêm tìm kiếm, nhóm theo ngày, đổi tên và xóa (CLI 0.22.0)."""
        from . import history

        rows = [(saved.title, f"{history.when(saved.saved_at)} · {saved.message_count} tin"
                 + (" · bị ngắt giữa chừng" if saved.interrupted else "")
                 + (" · đang mở" if saved.id == current else "")) for saved in sessions]
        index = self.choose("Mở lại hội thoại", rows)
        return None if index is None else sessions[index]

    def item(self, text: str) -> None:
        """Một mục mờ trong danh sách (như /permissions), ngắt theo bề ngang terminal thay vì để terminal tự bẻ chữ."""
        self._wrapped("    ", visible(text), "dim")

    def _rule(self) -> None:
        if self.terminal:
            self.line("  " + "─" * max(1, self.width - 4), "dim")

    def reply(self) -> ReplyWriter:
        return ReplyWriter(self)

    def session_header(self, version: str, directory: str, *, model: str, effort: str) -> None:
        """Đầu phiên gọn như Claude Code (chủ web chọn bản phác ngày 2026-09-22): mascot cạnh ba dòng ngắn.

        Tài khoản, số bước và các gợi ý phím không nằm ở đây nữa, để phần giữa màn hình chỉ còn lời Peto: số bước ở dòng
        dưới ô nhập, tài khoản ở ``peto status``, phím và lệnh ở ``/help``.
        """
        if not self.terminal:
            self.line(f"Peto Agent {version} · {directory} · {model} · mức {effort}")
            return
        for text in self.header_lines(version, directory, model=model, effort=effort):
            self.line(text)

    def header_lines(self, version: str, directory: str, *, model: str, effort: str) -> list[str]:
        """Các dòng đầu phiên (đã có mã màu), theo bề ngang và bề cao cửa sổ lúc gọi."""
        art = self._mascot_art()
        room = self.width - (1 + len(art[0]) + 3 if art else 2)
        details = (self.paint("Peto Agent", "bold") + self.paint(f" {version}", "dim"),
                   self.paint(clip_cells(f"{model} · mức {effort}", room), "dim"),
                   self.paint(clip_cells(visible(directory), room), "dim"))
        lines = [""]
        if not art:
            lines += ["  " + text for text in details]
        else:
            # Ba dòng chữ nằm giữa chiều cao của hình.
            first = (len(art) - len(details)) // 2
            for index, row in enumerate(art):
                text = details[index - first] if 0 <= index - first < len(details) else ""
                lines.append(" " + self._mascot_row(row) + ("   " + text if text else ""))
        return lines + [""]

    def _mascot_art(self):
        """Cỡ mascot lớn nhất vừa cửa sổ cả bề ngang lẫn bề cao; None thì chỉ in chữ.

        Terminal tắt màu (``NO_COLOR``) cũng không có hình: ký tự khối không màu chỉ còn một mảng xám.
        """
        if not self.colors:
            return None
        for art in mascot.ARTS:
            if (self.width >= 1 + len(art[0]) + 3 + HEADER_TEXT_MIN
                    and self.height >= len(art) + HEADER_SPARE_ROWS):
                return art
        return None

    def _mascot_row(self, row) -> str:
        """Một hàng mascot: màu 24-bit cho chữ và nền của từng ô."""
        parts = []
        for char, fg, bg in row:
            if char == " " and bg is None:
                parts.append(" ")
                continue
            codes = []
            if fg is not None:
                codes.append(f"38;2;{fg >> 16};{fg >> 8 & 255};{fg & 255}")
            if bg is not None:
                codes.append(f"48;2;{bg >> 16};{bg >> 8 & 255};{bg & 255}")
            parts.append(f"\033[{';'.join(codes)}m{char}\033[0m")
        return "".join(parts)

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

    # Tên hội thoại đang mở và tên thư mục dự án: thanh trên cùng của màn hình toàn phần, tiêu đề tab (CLI 0.22.0).
    session_title: str | None = None
    folder_name: str = ""

    def set_session_title(self, title: str | None) -> None:
        self.session_title = title

    def tab_title(self, state: str = "") -> str:
        """Tiêu đề tab terminal: trạng thái, rồi tên hội thoại (chưa có thì tên thư mục), như "OC | tên" của opencode."""
        name = self.session_title or self.folder_name
        if len(name) > 40:
            name = name[:39] + "…"
        return " · ".join(part for part in ("Peto", state, name) if part)

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

    # ---- Sự kiện có cấu trúc (events.py). Bản này vẽ lại đúng các dòng như trước khi có sự kiện.

    def tool_started(self, call: ToolCall) -> None:
        """Một công cụ bắt đầu chạy. Bản dòng nối tiếp chưa vẽ gì: dòng của công cụ in lúc xong."""

    def tool_progress(self, call_id: str, seconds: float, output: str) -> None:
        self.command_progress(seconds, output)

    def preview(self, kind: str, body: dict) -> None:
        """Thứ công cụ sắp làm, hiện trước khi hỏi (và cả khi đã được cho phép sẵn): diff, lệnh, đổi tên, gọi MCP."""
        if kind == "file":
            self.diff(body["title"], body["before"], body["after"])
        elif kind == "patch":
            for item in body["files"]:
                verb = {"add": "Muốn tạo", "delete": "Muốn xóa"}.get(item["op"], "Muốn sửa")
                where = item["path"] + (f" → {item['new_path']}" if item.get("new_path") else "")
                self.diff(f"{verb} {where}", item["before"], item["after"])
        elif kind == "move":
            self.line()
            self.line(f"  ✎ Muốn đổi tên {body['old']} → {body['new']}", "blue")
            self.line("    Nội dung giữ nguyên.", "dim")
        elif kind in {"command", "background"}:
            self.command(body["command"], body["directory"], body.get("timeout", 0), shell=body.get("shell", "cmd"),
                         background=kind == "background")
        elif kind == "mcp":
            self.line(f"MCP {body['server']} → {body['tool']}\n" + json.dumps(body["arguments"], ensure_ascii=False))
        elif kind == "mcp_enable":
            self.line("Kết nối MCP: " + json.dumps(body["spec"], ensure_ascii=False))
            self.line("MCP cục bộ chạy với quyền tài khoản máy; không nằm trong giới hạn công cụ tệp của Peto.")

    def ask(self, permission: Permission) -> str:
        """Hỏi một câu quyền; trang và tên miền thì in phần giải thích trước câu hỏi."""
        body = permission.body
        if permission.kind == "page":
            self.page_permission(body["origin"], body["action"])
        elif permission.kind == "site":
            self.site_permission(body["url"], body["site"], body.get("unusual", False))
        elif permission.kind == "loop":
            self.line()
            self._wrapped("  ⟳ ", f"Peto gọi {body['name']} y hệt {body['count']} lần liền mà không có tệp nào đổi.",
                          "yellow")
        return self.ask_permission(allow_session=permission.allow_session, allow_always=permission.allow_always,
                                   session_label=permission.session_label, question=permission.question)

    def notice(self, text: str, level: str = "dim") -> None:
        """Một dòng báo ngắn trong lúc làm (quyền đã nhớ, trình duyệt đổi chế độ…); level là dim hoặc yellow."""
        self.line(f"  {text}", level)

    def search(self, state: str) -> None:
        """Bước này có tra web (chạy ở phía dịch vụ AI)."""
        if state == "searching":
            self.step("Tìm trên web")

    def tool_finished(self, done: ToolDone) -> None:
        """Dòng kết quả của một công cụ, dựng từ kết quả gửi cho model và phần meta chỉ để hiển thị."""
        name, args, result, meta = done.name, done.args, done.result, done.meta
        if meta.get("stopped"):
            return
        if meta.get("raised") == "guide":
            self.step(meta["message"])
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
        if name == "run_command" and "exit_code" in result:
            # Lệnh đã chạy: "error" ở đây là lỗi của lệnh (hết giờ…), in cùng dòng kết quả.
            self.command_result(result)
            return
        if "error" in result:
            # Lỗi trả thẳng cho Peto (vượt giới hạn, bỏ qua vì bước trước lỗi…): trước đây không in gì.
            return
        if name == "update_plan":
            self.plan(meta["plan"])
        elif name == "list_files":
            self.step(f"Xem thư mục {result['path']}")
        elif name == "read_file":
            rel = result["path"]
            self.step(f"Đọc {rel} (dòng {result['start_line']}–{result['end_line']})" if result["total_lines"]
                      else f"Đọc {rel} (tệp trống)")
        elif name == "search_files":
            self.step(f'Tìm "{args.get("pattern", "")}" trong {meta.get("base", ".")}')
        elif name == "find_files":
            self.step(f'Tìm tệp "{args.get("pattern", "")}" trong {meta.get("base", ".")}: {result.get("total", 0)} tệp')
        elif name == "edit_file":
            self.success(f"Đã sửa {result['path']} (+{result['added_lines']} −{result['removed_lines']})")
        elif name == "write_file":
            self.success(("Đã tạo " if result.get("created") else "Đã ghi đè ")
                         + f"{result['path']} (+{result['added_lines']} −{result['removed_lines']})")
        elif name == "delete_file":
            self.success(f"Đã xóa {result['path']} (−{result['removed_lines']})")
        elif name == "move_file":
            self.success(f"Đã đổi tên {result['moved_from']} → {result['path']}")
        elif name == "apply_patch":
            for item in result["files"]:
                verb = {"add": "Đã tạo", "delete": "Đã xóa"}.get(item["op"], "Đã sửa")
                where = f"{item['moved_from']} → {item['path']}" if item.get("moved_from") else item["path"]
                self.success(f"{verb} {where} (+{item['added_lines']} −{item['removed_lines']})")
        elif name == "ask_user":
            for item in result.get("answers") or []:
                self.step(f"Bạn trả lời \"{item['question']}\": {', '.join(item['answer']) or '(trống)'}")
            if result.get("dismissed"):
                self.step("Bạn bỏ qua câu hỏi của Peto")
        elif name == "start_command":
            where = result.get("cwd", ".")
            self.success(f"Đã chạy nền #{result['id']}: {result['command']}" + (f" (trong {where})" if where != "." else ""))
        elif name == "read_command_output":
            state = "đang chạy" if result.get("running") else f"đã dừng, mã thoát {result.get('exit_code')}"
            self.step(f"Đọc output lệnh nền #{result['id']} ({state})")
        elif name == "stop_command":
            self.success(f"Đã dừng lệnh nền #{result['id']}: {result['command']}")
        elif name == "run_command":
            self.command_result(result)
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
            self.line(f"Đã nạp skill {args.get('name')} · {result['path']}", "dim")

    def request_finished(self, end: RequestEnd) -> None:
        """Một dòng duy nhất cuối mỗi yêu cầu (bản phác chủ web chọn ngày 2026-09-22): số bước còn lại nằm dưới ô
        nhập, thời gian từng phần và token chi tiết xem bằng /usage."""
        parts = [f"{OUTCOME_MARKS[end.outcome]} {OUTCOME_LABELS[end.outcome]} {format_duration(end.seconds)}"]
        if end.changes:
            parts.append(f"sửa {len(end.changes)} tệp")
        if end.commands:
            failed = sum(1 for command in end.commands
                         if command.get("classification") not in {"passed", "success", "no_match"})
            parts.append(f"chạy {len(end.commands)} lệnh" + (f" ({failed} lỗi)" if failed else ""))
        if end.background_jobs:
            parts.append(f"đang chạy {end.background_jobs} lệnh nền")
        if end.plan_left:
            parts.append(f"còn {end.plan_left} việc chưa xong")
        if end.context_tokens:
            parts.append(f"hội thoại {format_tokens(end.context_tokens)} token")
        self.line("  " + " · ".join(parts), "dim")

    def ask_permission(self, *, allow_session: bool = False, allow_always: bool = False,
                       session_label: str = "nhớ lệnh này trong phiên", question: str = PERMISSION_QUESTION) -> str:
        """Hỏi y/n/a; lệnh chạy và thao tác trên trang thì thêm [s] (nhớ trong phiên) và [l] (luôn cho phép ở dự án
        này). ``question`` đổi câu hỏi cuối, ví dụ "đồng ý cho trang này tới hết yêu cầu?".

        Hết đầu vào (EOF) thì coi như không đồng ý.
        """
        self.clear_status()
        waiting = self._title
        self.title("Peto · cần bạn duyệt")
        self.bell()
        try:
            return self._ask(allow_session, allow_always, session_label, question)
        finally:
            self.title(waiting)

    def _ask(self, allow_session: bool, allow_always: bool = False, session_label: str = "nhớ lệnh này trong phiên",
             base_question: str = PERMISSION_QUESTION) -> str:
        choices = ["y", "n", "a"] + (["s"] if allow_session else []) + (["l"] if allow_always else [])
        extras = ([f"[s] {session_label}"] if allow_session else []) + \
                 (["[l] luôn cho phép ở dự án này"] if allow_always else [])
        while True:
            try:
                question = base_question
                if extras:
                    question = "    " + "  ".join(extras) + " · " + question.strip()
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
            if answer in choices:
                self._diff_rows = []
                return answer
            self.line(f"    Gõ {', '.join(choices[:-1])} hoặc {choices[-1]} nhé.", "yellow")

    def prompt(self, *, footer: str = "", status: str = "") -> str:
        """Ô nhập: ``status`` canh phải phía trên đường kẻ, ``footer`` mờ phía dưới. Không có ô nhập thì dùng reader."""
        self.clear_status()
        self.attached = []
        if self.editor is not None:
            try:
                text = self.editor.read("› ", self.paint, boxed=True, footer=footer, status=status)
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

    def think(self, text: str) -> None:
        """Tóm tắt suy nghĩ của model. Bản dòng nối tiếp chưa hiện; dòng "Peto đang nghĩ" vẫn đếm giây."""

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
