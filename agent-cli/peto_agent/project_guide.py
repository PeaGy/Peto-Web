"""Scoped project guidance, reloaded from disk instead of trusting stale context."""
import re

from .workspace import WorkspaceError

MAX_GUIDE_CHARS = 32000
# /nho ghi vào mục này của AGENTS.md ở gốc dự án.
NOTES_HEADING = "## Ghi nhớ"
MAX_NOTE_CHARS = 500
SECTION_END = re.compile(r"#{1,2}\s")


class GuideUpdate(WorkspaceError):
    def __init__(self, guidance):
        super().__init__("Hướng dẫn dự án mới hoặc vừa thay đổi. Đọc project_guidance rồi gọi lại công cụ nếu phù hợp.")
        self.guidance = guidance


def guides(workspace, target=None):
    directory = target.parent if target else workspace.root
    directories = [workspace.root]
    if directory != workspace.root:
        relative = directory.relative_to(workspace.root)
        for part in relative.parts:
            directories.append(directories[-1] / part)
    result = []
    total = 0
    for directory in directories:
        candidate = directory / "AGENTS.md"
        if not candidate.exists():
            continue
        path = workspace.resolve(str(candidate))
        file = workspace.read(path)
        total += len(file.text)
        if total > MAX_GUIDE_CHARS:
            raise WorkspaceError("AGENTS.md vượt 32.000 ký tự; hãy rút gọn hướng dẫn trước khi tiếp tục.")
        result.append({"path": workspace.relative(path), "scope": workspace.relative(directory),
                       "text": file.text, "digest": file.digest})
    return result


def add_note(text: str, note: str) -> str:
    """Thêm "- note" vào cuối mục "## Ghi nhớ" của AGENTS.md (chữ dùng \\n); chưa có mục thì tạo ở cuối tệp.

    Mục kết thúc ở tiêu đề cấp 1 hoặc 2 kế tiếp, nên tiêu đề con (###) trong mục vẫn thuộc mục.
    """
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    bullet = f"- {note}"
    start = next((index for index, line in enumerate(lines)
                  if line.strip().casefold() == NOTES_HEADING.casefold()), None)
    if start is None:
        return "\n".join(lines + ([""] if lines else []) + [NOTES_HEADING, "", bullet]) + "\n"
    end = next((index for index in range(start + 1, len(lines)) if SECTION_END.match(lines[index])), len(lines))
    last = max((index for index in range(start + 1, end) if lines[index].strip()), default=None)
    if last is None:
        # Mục còn trống: một dòng trống sau tiêu đề, và một dòng trống trước tiêu đề kế tiếp nếu có.
        lines = lines[:start + 1] + ["", bullet] + ([""] if end < len(lines) else []) + lines[end:]
    else:
        lines = lines[:last + 1] + [bullet] + lines[last + 1:]
    return "\n".join(lines) + "\n"
