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

import json
import re
import time

from ..events import Permission, RequestEnd, ToolCall, ToolDone
from ..formats import format_duration, format_tokens
from ..ui import (CLEAR_LINE, READ_ONLY_LINES, REFUSED_LINES, UI, _count, _page_details, _seconds, _viewport_label,
                  _where, action_details, output_lines, page_notes, visible)
from . import prompt as prompt_view
from .diff import Diff
from .markdown import Markdown
from .text import Line, S, clip, fit, render, wrap
from .theme import load as load_theme

PAD = 2
# Đọc, liệt kê, tìm liền nhau thì gộp thành một dòng "Đã xem" như OpenCode.
EXPLORE = {"read_file", "list_files", "search_files"}
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


class TerminalUI(UI):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme = load_theme(colors=self.colors)
        self._group: list[tuple[str, str]] = []
        self._last: str | None = None
        self._preview: tuple[str, dict] | None = None
        self._static_diff = False
        self.thinking_title: str | None = None
        # /suynghi: in cả phần tóm tắt suy nghĩ dưới dòng "+ Đã nghĩ" (mặc định tắt như OpenCode).
        self.show_thoughts = False
        # Chân cố định (footer.py): bật khi phiên có ô nhập đọc phím thô; None thì in nối tiếp như 0.16.
        self.engine = None

    def toggle_thoughts(self) -> bool:
        self.show_thoughts = not self.show_thoughts
        return self.show_thoughts

    # ---- Chân cố định

    def start_footer(self) -> None:
        """Bật chân cố định: ô nhập ở đáy suốt phiên, gõ được cả lúc Peto đang làm."""
        if self.editor is None or self.engine is not None:
            return
        from .footer import FooterEngine

        engine = FooterEngine(self, self.editor, size=self.editor.size)
        try:
            engine.start()
        except OSError:
            return
        self.engine = engine

    def stop_footer(self) -> None:
        if self.engine is not None:
            engine, self.engine = self.engine, None
            engine.stop()

    def write(self, text: str, color: str | None = None) -> None:
        if self.engine is not None:
            self.engine.commit(self.paint(text, color))
            return
        super().write(text, color)

    def commit_user(self, lines: list[Line]) -> None:
        """Tin vừa gửi nằm lại trong lịch sử cuộn thành khung có thanh ┃."""
        self._flush_group()
        text = "\n" if self._last not in {None, "blank"} else ""
        text += "".join(render(line, self.colors) + "\n" for line in lines)
        self.write(text)
        self._last = "user"

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

    def _write_lines(self, lines: list[Line]) -> None:
        self.write("".join(" " * PAD + render(line, self.colors) + "\n" if line.spans else "\n" for line in lines))

    def _emit(self, lines: list[Line], kind: str) -> None:
        """In các hàng của một phần; giữa các phần khác loại có một dòng trống như OpenCode."""
        self._flush_group()
        while lines and not lines[0].spans and self._last in {None, "blank"}:
            lines = lines[1:]
        if not lines:
            return
        if self._last not in {None, "blank"} and lines[0].spans and not (kind == self._last and kind in {"row", "text"}):
            self._write_lines([Line()])
        self._write_lines(lines)
        self._last = "blank" if not lines[-1].spans else kind

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
        self.write(render(Line([(text, style)]), self.colors) + "\n")
        self._last = "row"

    def step(self, text: str) -> None:
        self._emit(self._row("↳", [S(visible(text), self.theme.muted)]), "row")

    def success(self, text: str) -> None:
        self._emit(self._row("✓", [S(visible(text), self.theme.text)], self.theme.success), "row")

    def failure(self, text: str) -> None:
        self._emit(self._row("✗", [S(visible(text), self.theme.error)], self.theme.error), "row")

    def item(self, text: str) -> None:
        self._emit(self._detail(text), "row")

    def notice(self, text: str, level: str = "dim") -> None:
        color = self.theme.warning if level == "yellow" else self.theme.muted
        self._emit(self._row("·", [S(visible(text), color)], color), "row")

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
        self._emit(self._block([S("# ", theme.muted, panel), S("Việc cần làm", theme.muted, panel)], body), "block")
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
        if call.name not in EXPLORE:
            self._flush_group()
            return
        args = call.args
        what = {"read_file": f"Đang đọc {args.get('path', '')}", "list_files": f"Đang xem thư mục {args.get('path', '.')}",
                "search_files": f'Đang tìm "{args.get("pattern", "")}"'}[call.name]
        self.status("… " + what)

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
            self._emit(self._row(self.theme.glyphs["web"], [S("Tìm trên web", self.theme.muted)]), "row")

    def _explore_label(self, name: str, args: dict, result: dict, meta: dict) -> tuple[str, str]:
        if name == "read_file":
            if not result.get("total_lines"):
                return "read", f"{result['path']} (trống)"
            return "read", f"{result['path']}:{result['start_line']}-{result['end_line']}"
        if name == "list_files":
            path = result["path"]
            return "list", ("./" if path == "." else path.rstrip("/") + "/")
        count = len(result.get("matches") or [])
        where = meta.get("base", ".")
        return "search", (f'"{args.get("pattern", "")}" {count}{"+" if result.get("truncated") else ""} kết quả'
                          + (f" trong {where}" if where != "." else ""))

    def _flush_group(self) -> None:
        if not self._group:
            return
        group, self._group = self._group, []
        theme = self.theme
        if len(group) == 1:
            kind, label = group[0]
            verb = {"read": "Đọc ", "list": "Xem thư mục ", "search": "Tìm "}[kind]
            icon = theme.glyphs["search"] if kind == "search" else "→"
            lines = self._row(icon, [S(verb, theme.muted), S(visible(label), theme.dim_text)])
        else:
            counts = {kind: sum(1 for item, _ in group if item == kind) for kind in ("read", "list", "search")}
            names = {"read": "lần đọc", "list": "thư mục", "search": "lần tìm"}
            summary = ", ".join(f"{counts[kind]} {names[kind]}" for kind in ("read", "list", "search") if counts[kind])
            lines = self._row("→", [S("Đã xem: ", theme.muted), S(summary, theme.muted)])
            labels = [label for _, label in group]
            rows = wrap([S(visible(" · ".join(labels)), theme.dim_text)], self.content_width - 5)
            if len(rows) > 2:
                rows = rows[:2]
                rows[-1] = rows[-1] + [S(" …", theme.muted)]
            lines += [Line([S("     ")] + row) for row in rows]
        self._group_out(lines)

    def _group_out(self, lines: list[Line]) -> None:
        if self._last not in {None, "blank", "row"}:
            self._write_lines([Line()])
        self._write_lines(lines)
        self._last = "row"

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
            self._emit(self._shell_block(result), "block")
            return
        if "error" in result:
            self._emit(self._row("·", [S(clip(visible(str(result["error"])), 300), theme.muted)]), "row")
            return
        if name in {"edit_file", "write_file", "delete_file"}:
            self._emit(self._edit_block(name, result), "block")
        elif name == "update_plan":
            self.plan(meta["plan"])
        elif name == "move_file":
            self._emit(self._row("→", [S("Đổi tên ", theme.muted), S(f"{result['moved_from']} → {result['path']}",
                                                                      theme.dim_text)]), "row")
        elif name == "start_command":
            where = result.get("cwd", ".")
            self._emit(self._row("$", [S(f"Chạy nền #{result['id']} ", theme.muted),
                                       S(visible(result["command"]), theme.dim_text),
                                       S(f" · trong {where}" if where != "." else "", theme.muted)]), "row")
        elif name == "read_command_output":
            state = "đang chạy" if result.get("running") else f"đã dừng, mã thoát {result.get('exit_code')}"
            self._emit(self._row("→", [S(f"Đọc output lệnh nền #{result['id']} ({state})", theme.muted)]), "row")
        elif name == "stop_command":
            self._emit(self._row("■", [S(f"Đã dừng lệnh nền #{result['id']}: ", theme.muted),
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
            self._emit(self._row("→", [S("Nạp skill ", theme.muted), S(f'"{args.get("name")}"', theme.dim_text)]), "row")
        elif name == "mcp_call_tool":
            self._emit(self._row(theme.glyphs["tool"], [S("MCP ", theme.muted),
                                                        S(f"{args.get('server')} → {args.get('tool')}", theme.dim_text)]),
                       "row")
        elif name == "mcp_list_tools":
            self._emit(self._row(theme.glyphs["tool"], [S(f"Xem công cụ MCP {args.get('server')}", theme.muted)]), "row")

    def page(self, title: str, details: str, problems: list[str], *, path: str | None = None) -> None:
        """Một lần Peto xem hay thao tác trên trang: dòng chính, dòng chi tiết, tối đa 5 lỗi, đường dẫn ảnh."""
        theme = self.theme
        lines = self._row("%", [S(visible(title), theme.muted)])
        if details:
            lines += self._detail(details)
        for problem in problems[:5]:
            lines += [Line([S("     "), S("✗ ", theme.error)] + row)
                      for row in wrap([S(visible(problem), theme.error)], self.content_width - 7)]
        if len(problems) > 5:
            lines += self._detail(f"… còn {len(problems) - 5} lỗi")
        self._emit(lines, "row")
        if path:
            # In liền một dòng, không gập, để terminal VS Code nhận ra đường dẫn và cho Ctrl+Click mở ảnh.
            self.write(" " * PAD + render(Line([S("     ảnh: ", theme.muted), S(visible(path), theme.muted)]),
                                          self.colors) + "\n")

    def _edit_block(self, name: str, result: dict) -> list[Line]:
        theme = self.theme
        panel = theme.panel
        rel = result["path"]
        verb = {"edit_file": "Sửa", "delete_file": "Xóa"}.get(name, "Tạo" if result.get("created") else "Ghi đè")
        header = [S("← ", theme.muted, panel), S(verb + " ", theme.text, panel, b=True), S(rel, theme.text, panel)]
        if result.get("added_lines"):
            header.append(S(f"  +{result['added_lines']}", theme.diff_added, panel))
        if result.get("removed_lines"):
            header.append(S(f"  −{result['removed_lines']}", theme.diff_removed, panel))
        body: list[Line] = []
        if name != "delete_file" and not self._static_diff and self._preview and self._preview[0] == "file":
            preview = self._preview[1]
            rows = Diff(preview["before"], preview["after"], path=rel).rows(theme, self.content_width - 3)
            body = rows[:BLOCK_DIFF_ROWS]
            if len(rows) > BLOCK_DIFF_ROWS:
                body.append(Line([S(f"… còn {len(rows) - BLOCK_DIFF_ROWS} dòng · /diff để xem đủ", theme.muted, panel)]))
        return self._block(header, body)

    def _shell_block(self, result: dict) -> list[Line]:
        theme = self.theme
        panel = theme.panel
        body = self._preview[1] if self._preview and self._preview[0] in {"command", "background"} else {}
        command = str(body.get("command") or result.get("command") or "")
        powershell = body.get("shell") == "powershell"
        first, *more = command.split("\n")
        header = [S("PS> " if powershell else "$ ", theme.muted, panel), S(visible(first), theme.text, panel)]
        if more:
            header.append(S(f"  (+{len(more)} dòng)", theme.muted, panel))
        if result.get("cwd"):
            header.append(S(f"  trong {result['cwd']}", theme.muted, panel))
        lines = output_lines(str(result.get("output") or ""))
        rows: list[Line] = []
        if len(lines) > OUTPUT_TAIL:
            rows.append(Line([S(f"({len(lines) - OUTPUT_TAIL} dòng trước đó)", theme.muted, panel)]))
        for text in lines[-OUTPUT_TAIL:]:
            rows += [Line(row) for row in wrap([S(text, theme.muted, panel)], self.content_width - 5, hard=True)]
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
            rows = diff.rows(theme, width) if not diff.empty else [Line([S("Nội dung không đổi.", theme.muted)])]
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
        if kind == "undo":
            files = body.get("files") or []
            return ([S("↶ ", theme.muted), S(f"Hoàn tác {len(files)} tệp", theme.text, b=True)],
                    [Line([S(visible(name), theme.muted)]) for name in files])
        return [S(visible(permission.question.strip().removesuffix("›").strip()), theme.text)], []

    def _panel(self, permission: Permission, options: list[Option], selected: int, offset: int,
               budget: int) -> tuple[list[Line], int]:
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
            if index == selected:
                choices.append(S(f" {option.label} ", theme.on_primary, theme.primary, b=True))
            else:
                choices.append(S(f" {option.label} ", theme.muted, element))
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

        def render_lines() -> list[Line]:
            lines, state["hidden"] = self._panel(permission, options, state["selected"], state["offset"], budget)
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
        rows = diff.rows(theme, self.content_width - 3) if not diff.empty else [
            Line([S("Nội dung không đổi.", theme.muted, panel)])]
        header = [S("← ", theme.muted, panel), S(visible(title), theme.text, panel, b=True),
                  S(f"  +{diff.added}", theme.diff_added, panel), S(f"  −{diff.removed}", theme.diff_removed, panel)]
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
        lines = [Line([S("   ")] + row) for row in wrap(spans, self.content_width - 3)]
        self._emit(lines, "footer")

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
        lines = [Line([S("   "), S(visible(text), self.ui.theme.thought)])]
        if self.ui.show_thoughts:
            for paragraph in "".join(self._thought).split("\n"):
                spans = [S(visible(paragraph.replace("**", "")), self.ui.theme.muted, i=True)]
                lines += [Line([S("     ")] + row) for row in wrap(spans, self.ui.content_width - 5)]
        self.ui._emit(lines, "row")

    def feed(self, text: str) -> None:
        if text and not self.started:
            self._think_ended = time.monotonic()
            self._commit_thought()
        self.started = self.started or bool(text)
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._emit(self.markdown.feed(line))
        if self.pending.strip():
            self.ui.status(f"… {visible(self.pending.rstrip(chr(13)).expandtabs(4))[-(self.ui.content_width - 10):]}")

    def finish(self) -> None:
        self._commit_thought()
        if self.pending:
            self._emit(self.markdown.feed(self.pending))
            self.pending = ""
        self._emit(self.markdown.flush())
        self.ui.thinking_title = None

    def _emit(self, lines: list[Line]) -> None:
        if lines:
            self.ui.clear_status()
            self.ui._emit(lines, "text")
