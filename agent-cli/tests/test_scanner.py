"""Hoạt ảnh Knight Rider ở chân màn hình (CLI 0.22.0, chuyển từ ui/spinner.ts của opencode)."""

from __future__ import annotations

from peto_agent.tui import scanner
from peto_agent.tui.footer import TICK_MS
from peto_agent.tui.theme import Theme, blend


def text(spans) -> str:
    return "".join(part for part, _ in spans)


def test_one_cycle_runs_right_holds_runs_back_and_rests():
    theme = Theme(rich=True)
    frames = [text(scanner.spans(theme, theme.primary, frame)) for frame in range(scanner.TOTAL)]
    assert scanner.TOTAL == 8 + 9 + 7 + 30, "đi 8, dừng 9, về 7, nghỉ 30 khung như opencode"
    assert frames[0] == "■⬝⬝⬝⬝⬝⬝⬝" and frames[3] == "■■■■⬝⬝⬝⬝", "đầu sáng chạy sang phải, vệt kéo phía sau"
    assert frames[7] == "⬝⬝■■■■■■", "vệt dài nhất 6 ô"
    assert frames[8 + 9] == "⬝⬝⬝⬝⬝⬝■■" or frames[8 + 9].endswith("■"), "chạy về từ bên phải"
    assert frames[-1] == "⬝" * 8, "cuối lúc nghỉ thì tắt hết"
    assert all(len(frame) == 8 for frame in frames)
    assert scanner.frame_number(0.0) == 0 and scanner.frame_number(scanner.FRAME_MS / 1000 * 5) == 5
    assert scanner.FRAME_MS < TICK_MS, "màn hình toàn phần vẽ dày hơn nhịp thường lúc có hoạt ảnh"


def test_colours_are_premixed_with_the_background_and_fade_along_the_trail():
    theme = Theme(rich=True)
    trail = scanner.trail_colors(theme.primary, theme.bg)
    assert trail[0] == theme.primary.lower() or trail[0] == blend(theme.primary, theme.bg, 1.0)
    assert trail[2] == blend(theme.primary, theme.bg, 0.65)
    head = scanner.spans(theme, theme.primary, 3)
    assert head[3][1]["fg"] == trail[0] and head[0][1]["fg"] == trail[3]
    planning = scanner.spans(theme, theme.secondary, 3)
    assert planning[3][1]["fg"] != head[3][1]["fg"], "chế độ Lập kế hoạch tô màu khác"


def test_old_consoles_and_no_colour_still_show_the_moving_head():
    plain = Theme(rich=False)
    assert text(scanner.spans(plain, plain.primary, 3)) == "■■■■····"
    bare = Theme(colors=False, rich=True)
    spans = scanner.spans(bare, bare.primary, 3)
    assert text(spans) == "■■■■⬝⬝⬝⬝" and all(style["fg"] is None for _, style in spans)
