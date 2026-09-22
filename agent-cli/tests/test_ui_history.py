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


def test_session_header_puts_the_mascot_beside_three_short_lines():
    """Đầu phiên gọn như Claude Code: mascot có màu cạnh ba dòng ngắn, không tài khoản, số bước hay gợi ý phím."""
    from peto_agent import mascot

    ui = UI(out=io.StringIO(), colors=True, width=100)
    ui.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    output = ui.out.getvalue()
    lines = _plain(output)
    assert len(lines) == len(mascot.ART) + 2 and lines[0] == lines[-1] == ""
    art = lines[1:-1]
    first = (len(mascot.ART) - 3) // 2
    assert art[first].endswith("   Peto Agent 0.9.5")
    assert art[first + 1].endswith("   Peto · mức thấp")
    assert art[first + 2].endswith("   ~/Downloads/web_test")
    assert "\033[38;2;" in output and ";48;2;" in output, "màu 24-bit cho nét chấm và phần tô"
    assert all(any("⠀" <= char <= "⣿" for char in line) for line in art[1:-1])


def test_header_falls_back_when_the_window_is_narrow_or_colorless():
    narrow = UI(out=io.StringIO(), colors=True, width=40)
    narrow.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    assert _plain(narrow.out.getvalue()) == ["", "  Peto Agent 0.9.5", "  Peto · mức thấp", "  ~/Downloads/web_test", ""]

    colorless = UI(out=io.StringIO(), colors=True, width=100)
    colorless.colors = False  # terminal có NO_COLOR: vẫn vẽ nét chấm, không mã màu
    colorless.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    assert "\033[" not in colorless.out.getvalue()
    assert any("⠁" <= char <= "⣿" for char in colorless.out.getvalue())

    piped = UI(out=io.StringIO(), colors=False)
    piped.session_header("0.9.5", "~/Downloads/web_test", model="Peto", effort="thấp")
    assert piped.out.getvalue() == "Peto Agent 0.9.5 · ~/Downloads/web_test · Peto · mức thấp\n"


def test_mascot_data_is_a_clean_rectangle():
    """Dữ liệu sinh bằng tools/make_mascot.py: mọi hàng cùng độ rộng, chỉ có chữ Braille hay dấu cách, màu hợp lệ."""
    from peto_agent import mascot

    widths = {len(row) for row in mascot.ART}
    assert widths == {18} and len(mascot.ART) == 9
    for row in mascot.ART:
        for char, fg, bg in row:
            assert char == " " or "⠀" <= char <= "⣿"
            assert all(color is None or 0 <= color <= 0xFFFFFF for color in (fg, bg))
