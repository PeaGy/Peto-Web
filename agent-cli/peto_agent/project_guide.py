"""Scoped project guidance, reloaded from disk instead of trusting stale context."""
from .workspace import WorkspaceError

MAX_GUIDE_CHARS = 32000


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
