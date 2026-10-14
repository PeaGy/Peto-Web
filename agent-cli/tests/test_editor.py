"""/editor: soạn yêu cầu dài trong trình soạn của bạn, chữ nằm sẵn trong ô nhập (CLI 0.23.0, theo opencode)."""

from __future__ import annotations

import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from conftest import FakeUI
from test_footer import settle
from test_screen import rich_glyphs, run  # noqa: F401 - fixture màn hình giả

from peto_agent import __main__ as cli
from peto_agent import external_editor


@pytest.fixture
def fake_editor(tmp_path: Path):
    """Trình soạn giả: chép tệp nó được mở vào ``seen.txt``, rồi thêm ``append`` vào cuối tệp (rỗng là không sửa gì)."""

    def make(append: str = "", code: int = 0) -> str:
        script = tmp_path / f"soan-{len(list(tmp_path.glob('soan-*.py')))}.py"
        script.write_text(textwrap.dedent(f"""
            import sys
            from pathlib import Path
            path = Path(sys.argv[1])
            Path({str(tmp_path / 'seen.txt')!r}).write_text(str(path) + "\\n" + path.read_text(encoding="utf-8"),
                                                          encoding="utf-8")
            if {append!r}:
                with path.open("a", encoding="utf-8") as file:
                    file.write({append!r})
            sys.exit({code})
        """), encoding="utf-8")
        return f'"{sys.executable}" "{script}"'

    make.seen = tmp_path / "seen.txt"
    return make


def test_the_editor_comes_from_visual_editor_vs_code_or_notepad(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert external_editor.command() == ("notepad.exe" if sys.platform == "win32" else "vi")
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    monkeypatch.setattr(external_editor.shutil, "which", lambda name: "C:/code.cmd" if name == "code" else None)
    assert external_editor.command() == "code --wait"
    monkeypatch.setenv("EDITOR", "nvim")
    assert external_editor.command() == "nvim"
    monkeypatch.setenv("VISUAL", '"C:\\Program Files\\Notepad++\\notepad++.exe" -multiInst')
    assert external_editor.command().endswith("-multiInst")
    assert external_editor.label(external_editor.command()) == "notepad++.exe"
    assert external_editor.label("code --wait") == "VS Code" and external_editor.label("notepad.exe") == "Notepad"


def test_edit_returns_the_new_text_and_removes_the_temp_file(fake_editor):
    text = external_editor.edit("Sửa lỗi checksum\n", cmd=fake_editor(append="Thêm test cho tệp rỗng.\n"))
    assert text == "Sửa lỗi checksum\nThêm test cho tệp rỗng."
    opened, _, content = fake_editor.seen.read_text(encoding="utf-8").partition("\n")
    assert content == "Sửa lỗi checksum\n" and opened.endswith(".md") and "peto-" in opened
    assert not Path(opened).exists(), "tệp tạm bị xóa"
    assert external_editor.edit("Giữ nguyên", cmd=fake_editor()) is None, "không đổi gì thì thôi"
    assert external_editor.edit("", cmd=fake_editor(append="   \n")) is None, "chỉ có khoảng trắng thì thôi"


def test_editor_failures_are_explained(fake_editor):
    with pytest.raises(external_editor.EditorError, match="thoát với mã 3"):
        external_editor.edit("x", cmd=fake_editor(append="y", code=3))
    with pytest.raises(external_editor.EditorError, match="Không tìm thấy trình soạn"):
        external_editor.edit("x", cmd="peto-khong-co-trinh-soan-nay")


def test_the_command_prefills_the_prompt_or_says_nothing_changed(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(external_editor, "edit", lambda initial, cmd=None: initial + "\nthêm dòng hai")
    cli._editor(ui, "dòng một")
    assert "Đang soạn trong" in ui.text and "Chữ của tin đó" in ui.text and "dòng một\n    thêm dòng hai" in ui.text
    monkeypatch.setattr(external_editor, "edit", lambda initial, cmd=None: None)
    cli._editor(ui, "")
    assert "Không có chữ mới" in ui.text

    def broken(initial, cmd=None):
        raise external_editor.EditorError("Không tìm thấy trình soạn \"vim\".")

    monkeypatch.setattr(external_editor, "edit", broken)
    cli._editor(ui, "")
    assert "Không tìm thấy trình soạn \"vim\"." in ui.text


def test_the_full_screen_steps_aside_while_editing_and_comes_back(run, monkeypatch):  # noqa: F811
    screen = run(90, 20)
    screen.ui.line("chữ trước khi soạn")
    seen = {}

    def edit(initial, cmd=None):
        seen["switches"] = list(screen.terminal.switches)
        seen["main"] = "\n".join(screen.rows())
        # Câu trả lời /btw tới giữa lúc soạn thì chờ, không vẽ đè lên trình soạn.
        screen.ui.ask_aside("hỏi giữa chừng", lambda: ("trả lời sau", False))
        time.sleep(0.3)
        seen["drawn_while_away"] = "trả lời sau" in "\n".join(screen.rows())
        return "Yêu cầu dài\nnhiều dòng"

    monkeypatch.setattr(external_editor, "edit", edit)
    monkeypatch.setattr(external_editor, "command", lambda: "notepad.exe")
    cli._editor(screen.ui, "")
    assert seen["switches"] == ["vào", "ra"], "rời màn hình của Peto trong lúc soạn"
    assert "Đang soạn trong Notepad" in seen["main"] and not seen["drawn_while_away"]
    assert screen.terminal.switches == ["vào", "ra", "vào"]
    engine = screen.ui.engine
    assert engine.state.text == "Yêu cầu dài\nnhiều dòng", "chữ nằm sẵn trong ô nhập, chưa gửi"
    assert any("chữ trước khi soạn" in row for row in screen.rows()), "hội thoại vẽ lại như cũ"
    assert settle(lambda: engine.panel is not None), "hộp /btw hiện khi đã quay lại"
    time.sleep(0.35)
    from peto_agent.line_editor import Key
    screen.press(Key("escape"))
    assert settle(lambda: engine.panel is None)
    assert not [thread for thread in threading.enumerate() if thread.name == "peto-btw"] or settle(
        lambda: not [thread for thread in threading.enumerate() if thread.name == "peto-btw"])
