"""Tệp người dùng đính kèm bằng @ ngay trong ô nhập.

Mỗi lần gọi model là một bước trong hạn mức ngày, nên bắt Peto gọi read_file cho tệp người dùng đã biết trước là phí.
Gõ ``@src/app.py`` thì CLI đọc tệp ngay lúc gửi tin và gắn nội dung vào tin đó. Nội dung này được tính là đã đọc: mã
băm được nhớ và hướng dẫn AGENTS.md của thư mục con đi kèm luôn, đúng như sau một lần read_file, nên Peto sửa được
ngay. Luật sửa tệp không đổi: tệp đổi sau lúc đính kèm thì edit_file vẫn từ chối, và mỗi lần ghi vẫn hỏi người dùng.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .workspace import Workspace, WorkspaceError, list_entries

# @ phải đứng đầu từ, nếu không "a@b.com" hay "user@host" cũng bị coi là tệp.
TOKEN = re.compile(r"(?:(?<=\s)|^)@([^\s@'\"`<>|]+)")
# Dấu câu người ta hay gõ ngay sau đường dẫn; tên tệp thật gần như không kết thúc bằng mấy ký tự này.
TRAILING = ".,;:!?)]}\"'"
# Khoảng dòng gõ ở cuối: "@src/app.py:120-180" hay "@src/app.py:120". Phải có số ngay sau dấu hai chấm, nên đường
# dẫn tuyệt đối kiểu "C:\du-an\app.py" không bị hiểu nhầm thành khoảng dòng.
RANGE = re.compile(r":(\d+)(?:-(\d+))?$")
MAX_MENTIONS = 8
MAX_LINES_PER_FILE = 1000
MAX_CHARS_PER_FILE = 60_000
MAX_TOTAL_CHARS = 120_000
MAX_DIR_ENTRIES = 200
# Danh sách tệp cho bảng gợi ý được dựng lại sau ngần này giây, để tệp mới tạo cũng hiện ra.
SUGGEST_TTL = 5.0
MAX_SUGGESTIONS = 8

HEADER = ("Tệp người dùng đính kèm bằng @. Nội dung đọc từ đĩa đúng lúc gửi tin này nên tính như read_file: sửa được "
          "ngay bằng edit_file, không cần đọc lại. Tệp nào cần xem thêm phần chưa đính kèm thì dùng read_file.")


@dataclass
class Attached:
    # Chữ sẽ gửi cho Peto: chữ người dùng gõ, rồi tới các khối tệp.
    text: str
    # Dòng in ra như bước công cụ, ví dụ "Đính kèm src/app.py (120 dòng)".
    steps: list[str] = field(default_factory=list)
    # Dòng báo vàng khi có tệp không đính kèm được.
    notices: list[str] = field(default_factory=list)
    # Đường dẫn đã đính kèm, để ghi nhật ký (không ghi nội dung).
    paths: list[str] = field(default_factory=list)


def find(text: str) -> list[str]:
    """Các đường dẫn gõ sau @ trong tin, giữ thứ tự và bỏ trùng."""
    found: list[str] = []
    for match in TOKEN.finditer(text):
        token = match.group(1).rstrip(TRAILING) or match.group(1)
        if token not in found:
            found.append(token)
        if len(found) >= MAX_MENTIONS:
            break
    return found


def split_range(token: str) -> tuple[str, tuple[int, int | None] | None]:
    """"src/app.py:120-180" thành ("src/app.py", (120, 180)); không ghi khoảng dòng thì phần sau là None."""
    match = RANGE.search(token)
    if match is None:
        return token, None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else None
    if start < 1 or (end is not None and end < start):
        return token, None
    return token[:match.start()], (start, end)


def _clip(text: str, lines: list[str]) -> tuple[str, str]:
    """Cắt bớt tệp dài; trả (nội dung, ghi chú) với ghi chú rỗng khi không phải cắt."""
    if len(lines) > MAX_LINES_PER_FILE:
        kept = "\n".join(lines[:MAX_LINES_PER_FILE])
        return kept, f"Chỉ đính kèm {MAX_LINES_PER_FILE} dòng đầu trong {len(lines)} dòng; đọc tiếp bằng read_file."
    if len(text) > MAX_CHARS_PER_FILE:
        return text[:MAX_CHARS_PER_FILE], "Tệp dài nên chỉ đính kèm phần đầu; đọc tiếp bằng read_file."
    return text, ""


def _directory(workspace: Workspace, target: Path, rel: str) -> tuple[str, str]:
    entries, truncated = list_entries(workspace, target, 2, MAX_DIR_ENTRIES)
    note = " · đã cắt bớt" if truncated else ""
    block = (f"[Thư mục đính kèm: {rel} · {len(entries)} mục{note}]\n" + "\n".join(entries) + f"\n[Hết {rel}]")
    return block, f"Đính kèm {rel} ({len(entries)} mục)"


def _file(workspace: Workspace, tools, target: Path, rel: str, budget: int,
          span: tuple[int, int | None] | None = None) -> tuple[str, str]:
    file = workspace.read(target)
    lines = file.text.split("\n")
    if file.text.endswith("\n"):
        lines.pop()
    total = len(lines)
    if span is None:
        content, note = _clip(file.text, lines)
        label, step = f"{total} dòng", f"{total} dòng"
    else:
        start = span[0]
        if start > total:
            raise WorkspaceError(f"{rel} chỉ có {total} dòng.")
        end = max(start, min(total, span[1] or total, start + MAX_LINES_PER_FILE - 1))
        content = "\n".join(lines[start - 1:end])
        note = ("Chỉ đính kèm khoảng dòng người dùng chỉ định; phần còn lại đọc bằng read_file."
                if (start > 1 or end < total) else "")
        label, step = f"dòng {start}–{end} / {total} dòng", f"dòng {start}–{end}"
    if len(content) > budget:
        content, note = content[:budget], "Hết chỗ đính kèm nên chỉ gửi phần đầu; đọc tiếp bằng read_file."
    workspace.remember(target, file)
    # Hướng dẫn của thư mục con phải đi cùng nội dung, vì lần sửa đầu tiên không còn bước read_file để nhận nó nữa.
    # Hướng dẫn ở gốc dự án thì máy chủ đã gửi sẵn trong chỉ dẫn của mỗi bước.
    guides = [item for item in tools.guidance_for(target) if item.get("scope") != "."]
    header = f"[Tệp đính kèm: {rel} · {label}]"
    if note:
        header += f"\n{note}"
    for guide in guides:
        header += f"\n[Hướng dẫn {guide['path']} áp dụng cho {guide['scope']}]\n{guide['text']}"
    return f"{header}\n{content}\n[Hết {rel}]", f"Đính kèm {rel} ({step})"


def attach(workspace: Workspace, tools, text: str) -> Attached:
    """Đọc các tệp người dùng nhắc bằng @ rồi gắn vào tin sắp gửi."""
    result = Attached(text=text)
    blocks: list[str] = []
    budget = MAX_TOTAL_CHARS
    for token in find(text):
        path_text, span = split_range(token)
        if not path_text:
            continue
        try:
            target = workspace.resolve(path_text, must_exist=False)
        except WorkspaceError as err:
            # Chỉ có thể là ngoài thư mục dự án hoặc tệp bí mật: người dùng gõ hẳn ra thì đáng được báo.
            result.notices.append(f"Không đính kèm @{token}: {err}")
            continue
        if not target.exists():
            # "@app.route", "@types/node"… không phải đường dẫn trong dự án thì im lặng bỏ qua.
            continue
        rel = workspace.relative(target)
        if budget <= 0:
            result.notices.append(f"Không đính kèm @{token}: tin đã đủ dài, nhờ Peto tự đọc tệp này.")
            continue
        try:
            block, step = (_directory(workspace, target, rel) if target.is_dir()
                           else _file(workspace, tools, target, rel, budget, span))
        except (WorkspaceError, OSError) as err:
            result.notices.append(f"Không đính kèm @{token}: {err}")
            continue
        blocks.append(block)
        budget -= len(block)
        result.steps.append(step)
        result.paths.append(rel)
    if blocks:
        result.text = "\n\n".join([text, HEADER, *blocks])
    return result


class Files:
    """Danh sách tệp trong dự án cho bảng gợi ý @, dựng lại sau vài giây thay vì quét theo từng phím."""

    def __init__(self, workspace: Workspace, ttl: float = SUGGEST_TTL, clock=time.monotonic):
        self.ws = workspace
        self.ttl = ttl
        self.clock = clock
        self._paths: list[str] = []
        self._at = 0.0

    def paths(self) -> list[str]:
        now = self.clock()
        if not self._paths or now - self._at > self.ttl:
            self._paths = sorted(self.ws.relative(path) for path in self.ws.iter_files(self.ws.root))
            self._at = now
        return self._paths


def suggest(text: str, files: Files) -> list:
    """Gợi ý đường dẫn khi từ cuối dòng bắt đầu bằng @; dòng khác trả danh sách rỗng."""
    from .commands import Suggestion

    match = re.search(r"(?:(?<=\s)|^)@([^\s@'\"`<>|]*)$", text)
    if match is None:
        return []
    head, typed = text[:match.start()], match.group(1).lower()
    starts, inside = [], []
    for path in files.paths():
        lowered = path.lower()
        if lowered.startswith(typed) or lowered.rsplit("/", 1)[-1].startswith(typed):
            starts.append(path)
        elif typed and typed in lowered:
            inside.append(path)
        if len(starts) >= MAX_SUGGESTIONS:
            break
    found = (starts + inside)[:MAX_SUGGESTIONS]
    return [Suggestion(f"{head}@{path}", path, "đính kèm tệp này vào yêu cầu") for path in found]
