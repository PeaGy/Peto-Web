"""Cấu hình test của Peto Agent CLI: chạy bằng pytest trong venv gốc của dự án, không cần cài gói."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peto_agent.ui import UI  # noqa: E402


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
def agent_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "agent-home"
    monkeypatch.setenv("PETO_AGENT_HOME", str(home))
    monkeypatch.setenv("PETO_AGENT_NO_BROWSER", "1")
    return home
