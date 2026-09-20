"""Tệp đính kèm bằng @: bắt đúng đường dẫn, đọc lúc gửi, và tính như đã read_file."""

from __future__ import annotations

from conftest import FakeUI

from peto_agent import mentions
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


def setup(project, answers=()):
    workspace = Workspace(project)
    return workspace, Tools(workspace, FakeUI(answers))


def test_find_only_takes_tokens_that_start_a_word():
    text = "sửa @src/app.py và @docs/ giúp mình, hỏi a@b.com nhé, @src/app.py nữa"
    assert mentions.find(text) == ["src/app.py", "docs/"]
    assert mentions.find("dùng @app.route trong flask") == ["app.route"]
    assert mentions.find("xem @src/app.py.") == ["src/app.py"], "bỏ dấu chấm cuối câu"
    assert mentions.find(" ".join(f"@t{index}.py" for index in range(20))) == [f"t{index}.py" for index in range(8)]


def test_attaching_a_file_counts_as_reading_it(project):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("mot\nhai\n", encoding="utf-8")
    workspace, tools = setup(project, ["y"])

    attached = mentions.attach(workspace, tools, "sửa @src/app.py giúp mình")
    assert attached.paths == ["src/app.py"]
    assert attached.steps == ["Đính kèm src/app.py (2 dòng)"]
    assert not attached.notices
    assert "sửa @src/app.py giúp mình" in attached.text
    assert "[Tệp đính kèm: src/app.py · 2 dòng]\nmot\nhai" in attached.text

    # Điểm chính: sửa được ngay, không cần một bước read_file nữa.
    result = tools.edit_file("src/app.py", "hai", "ba")
    assert result["ok"] is True
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "mot\nba\n"


def test_subfolder_guidance_travels_with_the_file(project):
    (project / "web").mkdir()
    (project / "web" / "AGENTS.md").write_text("Chỉ dùng TypeScript ở đây.\n", encoding="utf-8")
    (project / "web" / "app.ts").write_text("export const a = 1\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("Hướng dẫn gốc.\n", encoding="utf-8")
    workspace, tools = setup(project, ["y"])

    attached = mentions.attach(workspace, tools, "@web/app.ts")
    assert "Chỉ dùng TypeScript ở đây." in attached.text
    assert "Hướng dẫn gốc." not in attached.text, "hướng dẫn gốc đã nằm trong chỉ dẫn mỗi bước rồi"
    # Hướng dẫn được ghi nhận nên lần sửa đầu không bị chặn để nhận hướng dẫn.
    assert tools.edit_file("web/app.ts", "1", "2")["ok"] is True


def test_paths_that_are_not_files_are_left_alone_and_refusals_are_explained(project):
    (project / ".env").write_text("TOKEN=1", encoding="utf-8")
    (project / "anh.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    workspace, tools = setup(project)

    quiet = mentions.attach(workspace, tools, "dùng @app.route và @types/node, mail a@b.com")
    assert quiet.text == "dùng @app.route và @types/node, mail a@b.com"
    assert not quiet.notices and not quiet.steps

    loud = mentions.attach(workspace, tools, "@.env @anh.png @../ngoai.txt")
    assert len(loud.notices) == 3
    assert "bí mật" in loud.notices[0] and "nhị phân" in loud.notices[1]
    assert "ngoài thư mục dự án" in loud.notices[2]
    assert loud.text == "@.env @anh.png @../ngoai.txt", "không đính kèm thì chữ người dùng giữ nguyên"


def test_long_files_and_folders_are_bounded(project, monkeypatch):
    monkeypatch.setattr(mentions, "MAX_LINES_PER_FILE", 3)
    (project / "dai.txt").write_text("".join(f"dòng {index}\n" for index in range(50)), encoding="utf-8")
    (project / "src").mkdir()
    for index in range(4):
        (project / "src" / f"t{index}.py").write_text("x\n", encoding="utf-8")
    workspace, tools = setup(project)

    attached = mentions.attach(workspace, tools, "@dai.txt và @src")
    assert "Chỉ đính kèm 3 dòng đầu trong 50 dòng" in attached.text
    assert "dòng 2" in attached.text and "dòng 40" not in attached.text
    assert "[Thư mục đính kèm: src · 4 mục]" in attached.text
    assert attached.steps[1] == "Đính kèm src (4 mục)"


def test_total_budget_stops_attaching_and_says_so(project, monkeypatch):
    monkeypatch.setattr(mentions, "MAX_TOTAL_CHARS", 80)
    (project / "a.txt").write_text("a" * 200, encoding="utf-8")
    (project / "b.txt").write_text("b" * 200, encoding="utf-8")
    workspace, tools = setup(project)

    attached = mentions.attach(workspace, tools, "@a.txt @b.txt")
    assert attached.paths == ["a.txt"]
    assert "tin đã đủ dài" in attached.notices[0]


def test_the_input_line_offers_commands_and_paths_from_the_same_menu(project):
    """Bảng gợi ý của phiên: "/" ra lệnh, "@" ra đường dẫn, Tab điền nốt."""
    from peto_agent import __main__ as cli
    from peto_agent.line_editor import EditorState, Key

    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("x\n", encoding="utf-8")
    state = EditorState(cli._suggester(Workspace(project)))

    for char in "/mo":
        state.handle(Key("char", char))
    assert [item.label for item in state.items()] == ["/moi", "/model"]

    state.handle(Key("escape"))  # ẩn bảng gợi ý
    state.handle(Key("escape"))  # xóa chữ đang gõ
    for char in "sửa @ap":
        state.handle(Key("char", char))
    state.handle(Key("tab"))
    assert state.text == "sửa @src/app.py"


def test_suggestions_complete_the_path_inside_the_line(project):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("x\n", encoding="utf-8")
    (project / "src" / "utils.py").write_text("x\n", encoding="utf-8")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "x.js").write_text("x\n", encoding="utf-8")
    files = mentions.Files(Workspace(project))

    assert mentions.suggest("sửa giúp mình", files) == []
    items = mentions.suggest("sửa @ap", files)
    assert [item.label for item in items] == ["src/app.py"]
    assert items[0].text == "sửa @src/app.py", "chọn gợi ý thì chỉ thay phần @, giữ chữ đã gõ"
    assert [item.label for item in mentions.suggest("@", files)] == ["src/app.py", "src/utils.py"]
    assert all("node_modules" not in item.label for item in mentions.suggest("@x", files))
