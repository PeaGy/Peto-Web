"""Ô nhập kiểu OpenCode: thanh ┃ hồng trên nền nhạt, hàng "Peto · model · mức", mép dưới ╹▀▀, dòng chân mờ.

Bảng gợi ý (/lệnh, @tệp) hiện phía trên ô như OpenCode. Gửi xong, ô biến thành khung tin của người dùng nằm lại trong
lịch sử cuộn. Thuần Python như ``line_editor.layout`` nên test được.
"""

from __future__ import annotations

from ..line_editor import MAX_ITEMS, EditorState, Frame, clean
from .text import Line, S, cells, clip, fit, render, wrap

PAD = 2
PLACEHOLDER = "Nhờ Peto làm gì đó…"


def _text_rows(state: EditorState, theme, bg: str | None, width: int, *, show_cursor: bool):
    """Các hàng chữ trong ô và chỗ con trỏ (hàng, cột). Đoạn dán, ảnh hiện bằng nhãn màu."""
    rows: list[list] = [[]]
    column = 0
    cursor = None
    for index, char in enumerate(state.text):
        if show_cursor and index == state.cursor:
            cursor = (len(rows) - 1, column)
        if char == "\n":
            rows.append([])
            column = 0
            continue
        if state.is_paste(char) or state.is_image(char):
            glyph, color = clip(state.label(char), width), theme.info
        else:
            glyph, color = ("    " if char == "\t" else char), theme.text
        size = cells(glyph)
        if column + size > width and column:
            rows.append([])
            column = 0
            if show_cursor and index == state.cursor:
                cursor = (len(rows) - 1, column)
        rows[-1].append(S(glyph, color, bg))
        column += size
    if cursor is None:
        cursor = (len(rows) - 1, column)
    return rows, cursor


def user_panel(state: EditorState, theme, width: int) -> list[Line]:
    """Tin vừa gửi: thanh ┃ hồng trên nền panel, đệm một hàng trên và dưới."""
    panel_width = max(8, width - PAD)
    bg = theme.panel
    # Ngắt ở khoảng trắng (ô nhập ngắt từng ký tự để con trỏ đúng chỗ; tin đã gửi thì đọc cho dễ).
    rows = []
    for paragraph in state.text.split("\n"):
        spans = [S(state.label(char), theme.info, bg) if state.is_paste(char) or state.is_image(char)
                 else S("    " if char == "\t" else char, theme.text, bg) for char in paragraph]
        rows += wrap(_merge(spans), panel_width - 5)
    lines = []
    for row in [[]] + rows + [[]]:
        lines.append(Line([S(" " * PAD)]) + fit(Line([S("┃", theme.primary, bg), S("  ", bg=bg)] + row), panel_width, bg))
    return lines


def frame(state: EditorState, theme, *, width: int, height: int, meta: list[str], footer: str = "",
          placeholder: str = PLACEHOLDER, colors: bool = True, footer_line: Line | None = None,
          above: list[Line] | None = None) -> Frame:
    """Các hàng cần vẽ của ô nhập và chỗ đặt con trỏ.

    ``footer_line`` thay dòng chân bằng chữ ``footer`` (lúc Peto đang làm: thanh chạy, "esc dừng"); ``above`` là các
    hàng đặt trên ô (dòng trạng thái, tin đang chờ gửi), bị bỏ trước khi màn hình thấp quá.
    """
    # Không bao giờ viết vào cột cuối, để khỏi phụ thuộc cách từng terminal tự xuống dòng.
    usable = max(width, 16) - 1
    panel_width = usable - PAD
    if state.finished:
        if not state.text.strip():
            return Frame([""], 0, 0)
        lines = user_panel(state, theme, usable)
        return Frame([render(line, colors) for line in lines], len(lines) - 1, 0)
    bg = theme.element
    text_width = panel_width - 4
    rows, (cursor_row, cursor_col) = _text_rows(state, theme, bg, text_width, show_cursor=True)
    if not state.text and placeholder:
        rows = [[S(clip(placeholder, text_width), theme.muted, bg)]]
    bar = S("┃", theme.primary, bg)

    def row(spans: list) -> Line:
        return Line([S(" " * PAD)]) + fit(Line([bar, S("  ", bg=bg)] + spans), panel_width, bg)

    popup: list[Line] = []
    if state.notice:
        popup += [Line([S(" " * PAD), S(text, theme.warning)]) for text in
                  (clip(part, panel_width) for part in _words(state.notice, panel_width))]
    notice_rows = len(popup)
    items = state.items()
    if items:
        label_width = max(cells(item.label) for item in items)
        for index, item in enumerate(items):
            chosen = index == state.selected
            item_bg = theme.primary if chosen else theme.popup
            head = S(" " + item.label + " " * (label_width - cells(item.label)) + "  ",
                     theme.on_primary if chosen else theme.text, item_bg, b=chosen)
            body = S(item.description, theme.on_primary if chosen else theme.muted, item_bg)
            popup.append(Line([S(" " * PAD)]) + fit(Line([S("┃", theme.border, theme.popup), head, body]),
                                                    panel_width, item_bg))

    meta_spans = []
    for index, part in enumerate(meta):
        if index:
            meta_spans.append(S(" · ", theme.muted, bg))
        color = theme.primary if index == 0 else theme.warning if index == len(meta) - 1 and index > 1 else theme.text
        meta_spans.append(S(part, color, bg, b=index == 0 or (index == len(meta) - 1 and index > 1)))
    cap = Line([S(" " * PAD), S("╹", theme.primary), S("▀" * (panel_width - 1), bg)])
    if footer_line is not None:
        footer_line = Line([S(" " * PAD)]) + fit(footer_line, panel_width)
    elif footer:
        footer_line = Line([S(" " * PAD), S(clip(clean(footer), panel_width), theme.muted)])

    # Màn hình thấp: bỏ dần đệm trên, dòng chân, hàng trống và hàng thông tin; hàng chữ và mép dưới luôn còn.
    budget = max(1, height - 1)
    above = list(above or [])
    while above and budget - len(above) < 4:
        above.pop(0)
    budget -= len(above)
    parts = {"top": True, "blank": True, "meta": bool(meta), "footer": footer_line is not None}
    for drop in ("top", "footer", "blank", "meta"):
        if sum(parts.values()) + 2 <= budget:
            break
        parts[drop] = False
    chrome = sum(parts.values()) + 1
    popup_space = min(MAX_ITEMS + notice_rows, max(0, budget - chrome - 1))
    selected_row = notice_rows + (state.selected or 0) if items else 0
    popup_top = min(max(0, selected_row - popup_space + 1), max(0, len(popup) - popup_space))
    popup = popup[popup_top:popup_top + popup_space]
    available = max(1, budget - chrome - len(popup))
    top = 0
    if len(rows) > available:
        top = min(max(0, cursor_row - available + 1), len(rows) - available)
    visible = rows[top:top + available]

    lines = [Line([S(" " * PAD)]) + fit(line, panel_width) for line in above] + list(popup)
    if parts["top"]:
        lines.append(row([]))
    first_text = len(lines)
    lines += [row(spans) for spans in visible]
    if parts["blank"]:
        lines.append(row([]))
    if parts["meta"]:
        lines.append(row(meta_spans))
    lines.append(cap)
    if parts["footer"]:
        lines.append(footer_line)
    return Frame([render(line, colors) for line in lines], first_text + cursor_row - top, PAD + 3 + cursor_col)


def _merge(spans: list) -> list:
    """Gộp các đoạn liền nhau cùng kiểu, để gập theo từ được (mỗi ký tự là một đoạn riêng)."""
    merged: list = []
    for text, style in spans:
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def _words(text: str, width: int) -> list[str]:
    return ["".join(part for part, _ in row) for row in wrap([S(text)], width)]
