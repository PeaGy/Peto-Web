"""/export: hội thoại đang mở thành một tệp Markdown đọc được (CLI 0.23.0, theo /export của opencode).

Chỉ có những gì đã hiện trên màn hình: tin của bạn, lời Peto, mỗi công cụ một gạch đầu dòng ngắn và danh sách việc.
Không có nội dung tệp Peto đọc, output lệnh hay ảnh, nên tệp xuất ra gửi cho người khác được.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import transcript

PLAN_MARKS = {"done": "[x]", "in_progress": "[ ]", "pending": "[ ]"}
MAX_DETAIL = 120


def _clip(text: str, limit: int = MAX_DETAIL) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _code(text: str) -> str:
    """Một đoạn code nằm trên một dòng: chọn số dấu ` đủ để bọc cả dấu ` bên trong."""
    text = _clip(text)
    ticks = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def _counts(result: dict) -> str:
    parts = []
    if result.get("added_lines"):
        parts.append(f"+{result['added_lines']}")
    if result.get("removed_lines"):
        parts.append(f"−{result['removed_lines']}")
    return f" ({' '.join(parts)})" if parts else ""


def tool_lines(event: transcript.Event) -> list[str]:
    """Một lời gọi công cụ thành một hay vài dòng Markdown."""
    name, args, result = event.name, event.args, event.result
    if result is None:
        return [f"- Dùng `{name}` (chưa có kết quả)"]
    error = f" — không xong: {_clip(result['error'])}" if result.get("error") else ""
    path = args.get("path") or result.get("path") or ""
    if name == "read_file":
        where = f":{args['start_line']}-{args.get('end_line') or ''}" if args.get("start_line") else ""
        return [f"- Đọc {_code(str(path) + where)}{error}"]
    if name == "list_files":
        return [f"- Xem thư mục {_code(path or '.')}{error}"]
    if name in {"search_files", "find_files"}:
        verb = "Tìm tệp" if name == "find_files" else "Tìm"
        inside = f" trong {_code(path)}" if path and path != "." else ""
        return [f"- {verb} {_code(args.get('pattern', ''))}{inside}{error}"]
    if name == "edit_file":
        return [f"- Sửa {_code(path)}{'' if error else _counts(result)}{error}"]
    if name == "write_file":
        verb = "Tạo" if result.get("created") else ("Ghi" if error else "Ghi đè")
        return [f"- {verb} {_code(path)}{'' if error else _counts(result)}{error}"]
    if name == "delete_file":
        return [f"- Xóa {_code(path)}{error}"]
    if name == "move_file":
        return [f"- Đổi tên {_code(path)} → {_code(args.get('new_path') or '')}{error}"]
    if name == "apply_patch":
        if error or not isinstance(result.get("files"), list):
            return [f"- Áp bản patch{error}"]
        lines = []
        for item in result["files"]:
            verb = {"add": "Tạo", "delete": "Xóa"}.get(item.get("op"), "Sửa")
            where = (f"{_code(item['moved_from'])} → {_code(item.get('path', ''))}" if item.get("moved_from")
                     else _code(item.get("path", "")))
            lines.append(f"- {verb} {where}{_counts(item)}")
        return lines
    if name == "run_command":
        prompt = "PS> " if args.get("shell") == "powershell" else "$ "
        command = _code(prompt + str(args.get("command", "")).split("\n")[0])
        if "exit_code" in result:
            return [f"- Chạy {command} → mã thoát {result['exit_code']}"]
        return [f"- Chạy {command}{error}"]
    if name == "start_command":
        return [f"- Chạy nền {_code('$ ' + str(args.get('command', '')))}{error}"]
    if name == "read_command_output":
        return [f"- Đọc output lệnh nền #{args.get('job_id', '?')}{error}"]
    if name == "explore":
        return [f"- Khám phá ({result.get('steps', 0)} bước): {_clip(str(args.get('task', '')))}{error}"]
    if name == "read_output":
        what = f"tìm {_code(str(args['pattern']))} trong" if args.get("pattern") else "đọc"
        return [f"- {what.capitalize()} output đầy đủ {_code(str(args.get('output_id', '')))}{error}"]
    if name == "read_history":
        return [f"- Tra lịch sử trước tóm tắt ({len(result.get('entries') or [])} mục){error}"]
    if name == "stop_command":
        return [f"- Dừng lệnh nền #{args.get('job_id', '?')}{error}"]
    if name == "update_plan":
        steps = [step for step in args.get("steps") or [] if isinstance(step, dict)]
        lines = ["- Danh sách việc:"]
        for step in steps:
            mark = PLAN_MARKS.get(step.get("status"), "[ ]")
            suffix = " (đang làm)" if step.get("status") == "in_progress" else ""
            lines.append(f"  - {mark} {_clip(step.get('title', ''))}{suffix}")
        return lines if steps else []
    if name == "ask_user":
        lines = []
        for item in result.get("answers") or []:
            if isinstance(item, dict):
                answer = ", ".join(str(part) for part in item.get("answer") or []) or "(trống)"
                lines.append(f"- Peto hỏi: {_clip(item.get('question', ''))} → {_clip(answer)}")
        if result.get("dismissed"):
            lines.append("- Peto hỏi, bạn bỏ qua câu hỏi")
        return lines or [f"- Peto hỏi bạn{error}"]
    if name == "browser_open":
        return [f"- Mở trang {_code(args.get('url', ''))}{error}"]
    if name == "browser_screenshot":
        return [f"- Chụp màn hình trang{error}"]
    if name == "browser_read":
        return [f"- Đọc chữ trên trang{error}"]
    if name in {"browser_click", "browser_type", "browser_press"}:
        verb = {"browser_click": "Bấm", "browser_type": "Gõ vào", "browser_press": "Nhấn phím"}[name]
        target = args.get("key") if name == "browser_press" else args.get("target")
        return [f"- {verb} {_code(target or '')} trên trang{error}"]
    if name == "browser_login":
        return [f"- Nhờ bạn đăng nhập trên trình duyệt{error}"]
    if name == "load_skill":
        return [f"- Nạp skill {_code(args.get('name', ''))}{error}"]
    if name.startswith("mcp_"):
        return [f"- Dùng MCP {_code(args.get('server', ''))}{error}"]
    return [f"- Dùng công cụ {_code(name)}{error}"]


def markdown(items: list[dict], *, title: str, model: str, folder: str, when: datetime, version: str) -> str:
    out = [f"# {title or 'Hội thoại với Peto'}", "",
           f"- Ngày: {when:%d/%m/%Y %H:%M}", f"- Model: {model}", f"- Thư mục: {folder}",
           f"- Xuất từ Peto Agent {version}; không gồm nội dung tệp, output lệnh và ảnh.", ""]
    speaker = None

    def heading(name: str) -> None:
        nonlocal speaker
        if speaker != name:
            out.extend([f"## {name}", ""])
            speaker = name

    for event in transcript.events(items):
        if event.kind in {"user", "steer"}:
            speaker = None
            heading("Bạn (nhắn thêm lúc Peto đang làm)" if event.kind == "steer" else "Bạn")
            body = [event.text.strip()] if event.text.strip() else []
            if event.files:
                body.append("Đính kèm: " + ", ".join(_code(path) for path in event.files))
            if event.images:
                body.append("Ảnh: " + ", ".join(event.images))
            out.extend(["\n\n".join(body) or "(chỉ có ảnh)", ""])
            speaker = None
        elif event.kind == "summary":
            out.extend(["> **Phần trước của hội thoại đã được tóm tắt:**", ">"])
            out.extend(f"> {line}" if line else ">" for line in event.text.strip().split("\n"))
            out.append("")
            speaker = None
        elif event.kind == "note":
            heading("Peto")
            out.extend([f"*{event.text}*", ""])
        elif event.kind == "reply":
            heading("Peto")
            out.extend([event.text.strip(), ""])
        else:
            heading("Peto")
            if lines := tool_lines(event):
                if out[-1] == "" and len(out) > 1 and out[-2].startswith(("- ", "  - ")):
                    out.pop()
                out.extend([*lines, ""])
    return "\n".join(out).rstrip() + "\n"


def slug(title: str) -> str:
    """Tên tệp không dấu từ tên hội thoại: "Sửa lỗi checksum" thành "sua-loi-checksum"."""
    text = unicodedata.normalize("NFD", title.replace("đ", "d").replace("Đ", "D"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:40].rstrip("-") or "hoi-thoai"


def save(root: Path, text: str, *, title: str, when: datetime) -> Path:
    """Ghi ``peto-<tên>-<ngày>.md`` ở gốc dự án, không bao giờ ghi đè (thêm -2, -3… khi đã có)."""
    base = f"peto-{slug(title)}-{when:%Y%m%d}"
    for number in range(1, 1000):
        path = root / (f"{base}.md" if number == 1 else f"{base}-{number}.md")
        try:
            with path.open("x", encoding="utf-8", newline="\n") as file:
                file.write(text)
            return path
        except FileExistsError:
            continue
    raise FileExistsError(f"Đã có quá nhiều tệp {base}*.md trong thư mục này.")
