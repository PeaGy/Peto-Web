"""Hoạt ảnh "Knight Rider" ở chân màn hình lúc Peto đang làm (CLI 0.22.0, chủ web chọn ngày 2026-10-14).

Chuyển từ ``packages/tui/src/ui/spinner.ts`` của opencode (MIT License, Copyright (c) 2025 opencode,
https://github.com/anomalyco/opencode): 8 ô, một ô sáng chạy qua phải, dừng 9 khung, chạy về, dừng 30 khung, kéo theo
vệt 6 màu nhạt dần; ô tắt mờ đi lúc dừng và sáng dần lúc chạy. opencode vẽ màu có độ trong suốt trên nền nó tự tô;
terminal không có độ trong suốt và Peto không tô nền chung, nên mọi màu được trộn sẵn với màu nền của theme.
"""

from __future__ import annotations

import time

from .text import S
from .theme import blend

FRAME_MS = 40
WIDTH = 8
HOLD_START, HOLD_END = 30, 9
TRAIL = 6
# Ô tắt: độ đục so với màu chính, và mức mờ nhất lúc dừng (opencode: inactiveFactor 0.6, minAlpha 0.3).
INACTIVE, MIN_ALPHA = 0.6, 0.3
TOTAL = WIDTH + HOLD_END + (WIDTH - 1) + HOLD_START


def _state(frame: int) -> tuple[int, bool, int, int, int, int, bool]:
    """(ô sáng, đang dừng, đã dừng bao lâu, dừng tổng cộng, đã chạy bao lâu, chạy tổng cộng, đang chạy qua phải)."""
    back = WIDTH - 1
    if frame < WIDTH:
        return frame, False, 0, 0, frame, WIDTH, True
    if frame < WIDTH + HOLD_END:
        return WIDTH - 1, True, frame - WIDTH, HOLD_END, 0, 0, True
    if frame < WIDTH + HOLD_END + back:
        moved = frame - WIDTH - HOLD_END
        return WIDTH - 2 - moved, False, 0, 0, moved, back, False
    return 0, True, frame - WIDTH - HOLD_END - back, HOLD_START, 0, 0, False


def _index(char: int, state: tuple) -> int:
    """Vị trí của ô trong vệt (0 là ô sáng nhất), -1 nếu ô đang tắt."""
    active, holding, held, _, _, _, forward = state
    distance = active - char if forward else char - active
    if holding:
        return distance + held
    if 0 <= distance < TRAIL:
        return distance
    return -1


def _fade(state: tuple) -> float:
    _, holding, held, hold_total, moved, move_total, _ = state
    if holding and hold_total:
        return max(MIN_ALPHA, 1 - min(held / hold_total, 1) * (1 - MIN_ALPHA))
    if not holding and move_total:
        return MIN_ALPHA + min(moved / max(1, move_total - 1), 1) * (1 - MIN_ALPHA)
    return 1.0


def _brighten(color: str, factor: float) -> str:
    parts = [min(255, round(int(color[index:index + 2], 16) * factor)) for index in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(parts)


def trail_colors(color: str, background: str) -> list[str]:
    """Màu của vệt: đầu sáng nhất, ô thứ hai lóe sáng hơn một chút, rồi nhạt dần theo cấp số 0,65."""
    colors = []
    for step in range(TRAIL):
        if step == 0:
            alpha, factor = 1.0, 1.0
        elif step == 1:
            alpha, factor = 0.9, 1.15
        else:
            alpha, factor = 0.65 ** (step - 1), 1.0
        colors.append(blend(_brighten(color, factor), background, alpha))
    return colors


def frame_number(now: float | None = None) -> int:
    return int((time.monotonic() if now is None else now) * 1000 / FRAME_MS) % TOTAL


def spans(theme, color: str | None, frame: int | None = None) -> list[S]:
    """Các ô của một khung. ``color`` là màu chính (None khi tắt màu: ô sáng vẫn khác ký hiệu)."""
    frame = frame_number() if frame is None else frame
    state = _state(frame)
    on, off = theme.glyphs["scan_on"], theme.glyphs["scan_off"]
    background = getattr(theme, "bg", None)
    trail = trail_colors(color, background) if color and background else []
    dim = blend(color, background, INACTIVE * _fade(state)) if color and background else None
    out = []
    for char in range(WIDTH):
        index = _index(char, state)
        if 0 <= index < TRAIL:
            out.append(S(on, trail[index] if trail else None))
        else:
            out.append(S(off, dim))
    return out
