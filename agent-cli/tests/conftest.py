"""Cấu hình test của Peto Agent CLI: chạy bằng pytest trong venv gốc của dự án, không cần cài gói."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peto_agent.ui import UI  # noqa: E402


def handoff(text="Chưa xác nhận hành vi thực tế của ứng dụng."):
    """Bản bàn giao đúng định dạng cho các test khác tập trung vào lưu/khôi phục lịch sử."""
    return ("## Goal\nTiếp tục yêu cầu gốc đã ghim trong hội thoại.\n"
            "## Constraints and decisions\nGiữ ràng buộc và điều chỉnh của người dùng.\n"
            f"## Completed work and evidence\n{text}\n"
            "## Files and current state\nĐọc lại tệp trước khi sửa; xem checkpoint để biết tệp liên quan.\n"
            "## Errors and unverified assumptions\nKhông coi kiểm file là xác nhận ứng dụng đã chạy.\n"
            "## Next steps\nKiểm chứng phần chưa đạt theo yêu cầu đang làm.\n")


class FakeUI(UI):
    """Không in ra terminal; trả lời câu hỏi theo danh sách cho sẵn. Phần tử là exception thì ném ra."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        super().__init__(out=io.StringIO(), reader=self._read, colors=False)

    def _read(self, prompt: str) -> str:
        if not self.answers:
            raise EOFError
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def text(self) -> str:
        return self.out.getvalue()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture(autouse=True)
def command_list(monkeypatch):
    """Phiên đặt lại lựa chọn của /model theo máy chủ giả; trả danh sách lệnh về như cũ sau mỗi test."""
    from peto_agent import commands

    monkeypatch.setattr(commands, "COMMANDS", commands.COMMANDS)


@pytest.fixture(autouse=True)
def agent_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "agent-home"
    monkeypatch.setenv("PETO_AGENT_HOME", str(home))
    monkeypatch.setenv("PETO_AGENT_NO_BROWSER", "1")
    # Ảnh chụp dự án (CLI 0.26.0) gọi git trước và sau mỗi lệnh; test của nó tự bật lại.
    monkeypatch.setenv("PETO_AGENT_NO_SNAPSHOTS", "1")
    return home


@pytest.fixture
def ask_permissions(project, agent_home):
    """Các test kiểm giao diện từ chối/nhớ quyền phải chọn chế độ hỏi rõ ràng, thay vì dựa vào mặc định cũ."""
    from peto_agent import approvals
    assert approvals.set_policy(project, "ask")
