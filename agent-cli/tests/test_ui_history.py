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
