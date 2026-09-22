"""Markdown tối thiểu, dòng trạng thái tạm và hội thoại lưu theo thư mục."""

from __future__ import annotations

import io

from peto_agent import history
from peto_agent.loop import format_duration, format_tokens
from peto_agent.ui import UI

BOLD, CYAN, DIM, RESET = "\033[1m", "\033[36m", "\033[2m", "\033[0m"


def test_markdown_is_colored_only_when_the_terminal_supports_it():
    assert UI(out=io.StringIO(), colors=False).markdown("**Peto** dùng `max_age`") == "**Peto** dùng `max_age`"

    ui = UI(out=io.StringIO(), colors=True)
    assert ui.markdown("Lỗi ở **hạn cookie**: `max_age` sai") == f"Lỗi ở {BOLD}hạn cookie{RESET}: {CYAN}max_age{RESET} sai"
    assert ui.markdown("## Cách sửa `auth.py`") == f"{BOLD}Cách sửa auth.py{RESET}"
    assert ui.markdown("- xem [tài liệu](https://example.com)") == "• xem tài liệu (https://example.com)"
    assert ui.markdown("dùng `**kwargs` với __init__") == f"dùng {CYAN}**kwargs{RESET} với __init__"
    assert ui.markdown("---") == f"{DIM}{'─' * 40}{RESET}"

    assert ui.markdown("```python") == f"{DIM}```python{RESET}"
    assert ui.markdown("x = 2 ** 3  # **không đậm**") == f"{CYAN}x = 2 ** 3  # **không đậm**{RESET}"
    assert ui.markdown("```") == f"{DIM}```{RESET}"
    ui.markdown("```")
    ui.end_markdown()
    assert ui.markdown("**đậm**") == f"{BOLD}đậm{RESET}", "khối code chưa đóng không được lan sang câu trả lời sau"


def test_status_line_is_redrawn_in_place_and_cleared_before_other_output():
    out = io.StringIO()
    ui = UI(out=out, reader=lambda prompt: "y", colors=True)
    ui.status("… Peto đang nghĩ · 1s")
    ui.status("… Peto đang nghĩ · 1s")
    ui.status("… Peto đang nghĩ · 2s")
    ui.line("Peto › xong")
    ui.status("… Peto đang nghĩ · 0s")
    assert ui.ask_permission() == "y"
    clear = "\r\033[2K"
    assert out.getvalue().startswith(f"{clear}{DIM}… Peto đang nghĩ · 1s{RESET}{clear}{DIM}… Peto đang nghĩ · 2s{RESET}"
                                    f"{clear}Peto › xong\n{clear}{DIM}… Peto đang nghĩ · 0s{RESET}{clear}")
    assert "Đồng ý?" in out.getvalue()

    plain = UI(out=io.StringIO(), colors=False)
    plain.status("… Peto đang nghĩ · 1s")
    assert plain.out.getvalue() == ""


def test_saved_conversation_belongs_to_one_folder_and_server(project, tmp_path):
    other = tmp_path / "du-an-khac"
    other.mkdir()
    items = [{"type": "message", "role": "user", "content": "Sửa README"},
             {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Xong rồi nè."}]}]
    history.save(project, "https://peto.example", items)
    saved = history.load(project, "https://peto.example")
    assert saved is not None and saved.items == items and saved.message_count == 2
    assert history.recap(saved.items) == [("Bạn", "Sửa README"), ("Peto", "Xong rồi nè.")]
    assert history.when(saved.saved_at).startswith("lúc ") and history.when(saved.saved_at).endswith(" hôm nay")
    assert history.load(project, "https://khac.example") is None
    assert history.load(other, "https://peto.example") is None

    history._path(project).write_text("{hỏng", encoding="utf-8")
    assert history.load(project, "https://peto.example") is None


def test_durations_and_token_counts_read_naturally():
    assert [format_duration(value) for value in (0.4, 42, 60, 125)] == ["0 giây", "42 giây", "1 phút", "2 phút 5 giây"]
    assert [format_tokens(value) for value in (850, 1000, 1234, 9960, 18432, 999_499, 999_500, 1_250_000)] == [
        "850", "1k", "1.2k", "10k", "18k", "999k", "1M", "1.2M"]


def _plain(text: str) -> list[str]:
    import re

    return [re.sub(r"\033\[[0-9;]*m", "", line) for line in text.splitlines()]


TEXT_ONLY = ["", "  Peto Agent 0.9.5", "  Peto · mức thấp", "  ~/Downloads/web_test", ""]


def _header(**size) -> str:
    ui = UI(out=io.StringIO(), colors=True, **size)
    ui.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    return ui.out.getvalue()


def test_session_header_puts_the_mascot_beside_three_short_lines():
    """Đầu phiên gọn như Claude Code: mascot có màu cạnh ba dòng ngắn, không tài khoản, số bước hay gợi ý phím."""
    from peto_agent import mascot

    output = _header(width=100, height=40)
    lines = _plain(output)
    art = mascot.ARTS[0]
    assert len(lines) == len(art) + 2 and lines[0] == lines[-1] == ""
    rows = lines[1:-1]
    first = (len(art) - 3) // 2
    assert rows[first].endswith("   Peto Agent 0.9.5")
    assert rows[first + 1].endswith("   Peto · mức thấp")
    assert rows[first + 2].endswith("   ~/Downloads/web_test")
    assert "\033[38;2;" in output and "48;2;" in output, "màu 24-bit cho ký tự khối và màu nền của ô"
    assert all("\033[" in line for line in output.splitlines()[1:-1]), "hàng nào của hình cũng có màu"


def test_header_picks_the_largest_mascot_that_fits_the_window():
    """Terminal thấp dùng hình nhỏ hơn, để lúc mở phần trên của hình không trôi mất.

    Bảng terminal chừng 13 dòng của VS Code có quả lê thay vì chỉ còn chữ (chủ web đề nghị ngày 2026-09-22).
    """
    from peto_agent import mascot
    from peto_agent.ui import HEADER_SPARE_ROWS, HEADER_TEXT_MIN

    big, small, pear = mascot.ARTS

    def art_rows(width: int, height: int) -> int:
        lines = _plain(_header(width=width, height=height))
        return 0 if lines == TEXT_ONLY else len(lines) - 2

    def just_wide_enough(art) -> int:
        # UI.width chừa một cột, nên cửa sổ phải rộng hơn một cột so với phép tính.
        return 1 + len(art[0]) + 3 + HEADER_TEXT_MIN + 1

    assert art_rows(100, 40) == len(big)
    assert art_rows(100, len(big) + HEADER_SPARE_ROWS - 1) == len(small)
    assert art_rows(100, len(small) + HEADER_SPARE_ROWS - 1) == len(pear)
    assert art_rows(100, 13) == len(pear), "bảng terminal 13 dòng của VS Code vẫn có quả lê"
    assert art_rows(100, len(pear) + HEADER_SPARE_ROWS - 1) == 0, "thấp quá thì chỉ còn chữ"
    assert art_rows(just_wide_enough(small), 40) == len(small)
    assert art_rows(just_wide_enough(pear), 40) == len(pear)
    assert art_rows(just_wide_enough(pear) - 1, 40) == 0


def test_vscode_terminal_keeps_two_more_columns_free(monkeypatch):
    """VS Code che chừng hai cột sát mép phải: chữ cuối của dòng trạng thái canh phải từng bị mất ở đó (2026-09-22).

    Chừa cả cho ô nhập lẫn phần ngắt dòng câu trả lời; cỡ truyền thẳng vào UI (như trong test) thì giữ nguyên.
    """
    import os
    import shutil

    from peto_agent import line_editor
    from peto_agent import ui as display

    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(100, 24): os.terminal_size((120, 30)))
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert display.terminal_size() == (120, 30)
    assert UI(out=io.StringIO(), colors=True).width == 119

    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    covered = display.VSCODE_COVERED_COLUMNS
    assert covered >= 2 and display.terminal_size() == (120 - covered, 30)
    assert UI(out=io.StringIO(), colors=True).width == 119 - covered
    assert UI(out=io.StringIO(), colors=True, width=120).width == 119
    assert line_editor.LineEditor(None, io.StringIO()).size() == (120 - covered, 30)


def test_header_falls_back_when_the_window_is_narrow_or_colorless():
    assert _plain(_header(width=40, height=40)) == TEXT_ONLY

    colorless = UI(out=io.StringIO(), colors=True, width=100, height=40)
    colorless.colors = False  # terminal có NO_COLOR: ký tự khối không màu chỉ còn một mảng xám, nên bỏ hình
    colorless.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    assert colorless.out.getvalue().splitlines() == TEXT_ONLY

    piped = UI(out=io.StringIO(), colors=False)
    piped.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    assert piped.out.getvalue() == "Peto Agent 0.9.5 · ~/Downloads/web_test · Peto · mức thấp\n"


def test_mascot_data_is_clean_block_art_from_large_to_small():
    """Dữ liệu sinh bằng tools/make_mascot.py: hình chữ nhật, chỉ ký tự khối (terminal tự vẽ lấp kín ô) hay dấu cách.

    Không Braille, vì chấm Braille lấy từ font nên nhỏ và thưa; không ░▒▓, vì chúng là hoa văn chấm.
    """
    from peto_agent import mascot

    assert [(len(art[0]), len(art)) for art in mascot.ARTS] == [(24, 12), (18, 9), (6, 6)]
    for art in mascot.ARTS:
        assert {len(row) for row in art} == {len(art[0])}
        for row in art:
            for char, fg, bg in row:
                assert char == " " or ("▀" <= char <= "▟" and char not in "░▒▓")
                assert all(color is None or 0 <= color <= 0xFFFFFF for color in (fg, bg))
                assert char == " " or fg is not None, "ký tự khối phải có màu chữ"
