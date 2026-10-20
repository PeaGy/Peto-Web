"""Khung nổi giữa màn hình như OpenCode (CLI 0.32.0, lộ trình nhiều nguồn M4).

Theo ``packages/tui/src/ui/dialog.tsx``, ``dialog-select.tsx`` và ``dialog-prompt.tsx`` của OpenCode (MIT License,
Copyright (c) 2025 opencode): nền phía sau tối đi (lớp đen độ đục 150/255), khung rộng 60 ô canh giữa và cách đỉnh một
phần tư màn hình, tiêu đề đậm với "esc" bên phải, ô tìm, danh sách chia nhóm (tên nhóm màu accent, đậm), dòng đang chọn
tô nền màu chính, dấu ● trước mục đang dùng, gợi ý phím ở đáy. Chủ web chọn làm giống hệt OpenCode (2026-10-20).

Khung chỉ vẽ và nhận phím; việc làm sau khi chọn (đổi model, lưu khóa) do nơi gọi làm. ``handle`` chạy ở luồng đọc phím
nên không được chờ mạng: khung trả kết quả rồi nơi gọi mới làm việc chậm.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..line_editor import Key
from .text import Line, S, Target, cells, clickable, clip, fit, wrap

INSET = 3
LIST_INSET = INSET + 1
WIDTHS = {"medium": 60, "large": 88}
# Lớp đen phủ lên màn hình phía sau: RGBA(0, 0, 0, 150) của OpenCode.
BACKDROP = 150 / 255
# Trả lời của khung cho bộ vẽ: khung đã có kết quả (xem ``result``).
DONE = "done"


@dataclass
class Option:
    title: str
    value: object = None
    description: str = ""
    footer: str = ""
    # Tên màu trong theme của chữ bên phải (muted, warning…).
    footer_tone: str = "muted"
    category: str = ""
    current: bool = False
    # Ký hiệu ở cột lề trái, như ✓ của nguồn đã kết nối.
    gutter: str = ""
    gutter_tone: str = "success"
    disabled: bool = False
    # Chữ bên phải khi đang tìm (danh sách không còn nhóm): mặc định là tên nhóm, như OpenCode.
    search_footer: str | None = None
    # Chữ phụ chỉ dùng khi tìm (không hiện).
    search_text: str = ""
    # Mục lặp lại để tiện (nhóm "Yêu thích", "Gần đây"): không hiện khi tìm, vì bản chính đã có trong nhóm của nó.
    searchable: bool = True


@dataclass
class Action:
    """Một phím tắt ở chân khung: ``title`` rồi ``key`` (như "Yêu thích ctrl+f")."""

    title: str
    key: str
    name: str
    # Cần một dòng đang chọn mới dùng được (đổi tên, xóa…).
    needs_option: bool = True
    right: bool = False
    hidden: bool = False


@dataclass
class Result:
    kind: str  # "select", "action", "submit" hay "close"
    option: Option | None = None
    action: str = ""
    text: str = ""


def _fold(text: str) -> str:
    from ..commands import fold

    return fold(text)


def _score(query: str, option: Option) -> int:
    """Điểm khớp khi tìm, như fuzzysort của OpenCode: tên trước, nhóm và chữ phụ sau. 0 là không khớp."""
    title = _fold(option.title)
    if query in title:
        return 300 - title.index(query)
    if query in _fold(option.category) or (option.search_text and query in _fold(option.search_text)):
        return 100
    # Các chữ của câu tìm xuất hiện theo thứ tự trong tên ("g61" khớp "gpt-6.1-sol").
    position = 0
    for char in query:
        position = title.find(char, position)
        if position < 0:
            return 0
        position += 1
    return 50


def _matches(key: Key, label: str) -> bool:
    """Phím ``key`` có phải phím tắt ghi là ``label`` ("ctrl+a") không."""
    if label.startswith("ctrl+") and len(label) == 6:
        return key.name == "ctrl" and key.text == label[-1]
    return False


class _Base:
    size = "medium"
    result: Result | None = None

    def width(self, available: int) -> int:
        return max(24, min(WIDTHS[self.size], available))

    @staticmethod
    def _row(theme, width: int, spans: list, bg: str | None = None) -> Line:
        bg = bg or theme.panel
        return fit(Line([S(" " * LIST_INSET, bg=theme.panel)] + spans), width, bg)

    def _header(self, theme, width: int, title: str) -> Line:
        panel = theme.panel
        close = clickable([S("esc", theme.muted, panel)], Target(("dialog-esc", id(self)), lambda: Key("escape")))
        left = [S(" " * LIST_INSET, bg=panel), S(clip(title, width - LIST_INSET * 2 - 5), theme.text, panel, b=True)]
        used = sum(cells(text) for text, _ in left) + 3 + LIST_INSET
        return Line(left + [S(" " * max(1, width - used), bg=panel)] + close + [S(" " * LIST_INSET, bg=panel)])

    def _finish(self, result: Result) -> str:
        self.result = result
        return DONE


class SelectDialog(_Base):
    """Danh sách chọn có ô tìm (DialogSelect của OpenCode)."""

    def __init__(self, title: str, options: list[Option], *, actions: list[Action] | None = None,
                 placeholder: str = "Tìm", search: bool = True, size: str = "medium",
                 empty: str = "Chưa có mục nào", no_match: str = "Không tìm thấy kết quả", message: str = ""):
        self.title = title
        self.options = list(options)
        self.actions = list(actions or [])
        self.placeholder = placeholder
        self.search = search
        self.size = size
        self.empty = empty
        self.no_match = no_match
        self.message = message
        # Màu của dòng báo dưới danh sách: warning (chưa làm được) hay success (vừa làm xong).
        self.message_tone = "warning"
        self.query = ""
        self.top = 0
        self.result = None
        # Mục đang chờ bấm lần nữa để xác nhận (xóa), theo giá trị; câu thay tên dòng đó.
        self.armed: object = None
        self.armed_text = ""
        current = next((index for index, option in enumerate(self.flat()) if option.current), 0)
        self.selected = current

    # ---- Danh sách

    def groups(self) -> list[tuple[str, list[Option]]]:
        query = _fold(self.query.strip())
        if query:
            scored = [(score, index, option) for index, option in enumerate(self.options)
                      if option.searchable and (score := _score(query, option))]
            scored.sort(key=lambda item: (-item[0], item[1]))
            found = [option for _, _, option in scored]
            return [("", found)] if found else []
        grouped: dict[str, list[Option]] = {}
        for option in self.options:
            grouped.setdefault(option.category, []).append(option)
        return list(grouped.items())

    def flat(self) -> list[Option]:
        return [option for _, options in self.groups() for option in options]

    def chosen(self) -> Option | None:
        flat = self.flat()
        return flat[self.selected] if 0 <= self.selected < len(flat) else None

    def replace(self, options: list[Option], *, keep: object = None) -> None:
        """Thay danh sách (vừa đổi tên, xóa, đánh dấu yêu thích), giữ dòng đang chọn nếu còn."""
        self.options = list(options)
        flat = self.flat()
        index = next((position for position, option in enumerate(flat) if option.value == keep), None)
        self.selected = index if index is not None else min(self.selected, max(0, len(flat) - 1))

    def limit(self, height: int) -> int:
        """Số hàng tối đa của danh sách, như OpenCode: nửa màn hình trừ phần khung."""
        return max(3, height // 2 - 6)

    # ---- Vẽ

    def render(self, theme, available: int, height: int) -> list[Line]:
        width = self.width(available)
        panel = theme.panel
        blank = fit(Line([]), width, panel)
        lines = [blank, self._header(theme, width, self.title)]
        if self.search:
            lines += [blank, self._search_line(theme, width)]
        lines.append(blank)
        lines += self._list_lines(theme, width, height)
        if self.message:
            tone = getattr(theme, self.message_tone, theme.warning)
            lines += [blank] + [self._row(theme, width, row)
                                for row in wrap([S(self.message, tone, panel)], width - LIST_INSET * 2)]
        footer = self._footer_line(theme, width)
        if footer is not None:
            lines += [blank, footer]
        lines.append(blank)
        return lines

    def _search_line(self, theme, width: int) -> Line:
        panel = theme.panel
        cursor = S(" ", theme.on_primary, theme.primary)
        if self.query:
            spans = [S(clip(self.query, width - LIST_INSET * 2 - 2), theme.text, panel), cursor]
        else:
            first, rest = self.placeholder[:1], self.placeholder[1:]
            spans = [S(first, theme.on_primary, theme.primary), S(rest, theme.muted, panel)]
        return self._row(theme, width, spans)

    def _entries(self) -> list[tuple[str, object]]:
        """Các hàng của danh sách: ("category", tên), ("gap", None) hay ("option", chỉ số trong flat)."""
        rows: list[tuple[str, object]] = []
        index = 0
        for position, (category, options) in enumerate(self.groups()):
            if category:
                if position:
                    rows.append(("gap", None))
                rows.append(("category", category))
            for _ in options:
                rows.append(("option", index))
                index += 1
        return rows

    def _list_lines(self, theme, width: int, height: int) -> list[Line]:
        panel = theme.panel
        flat = self.flat()
        if not flat:
            text = self.no_match if self.query.strip() else self.empty
            return [self._row(theme, width, [S(text, theme.muted, panel)])]
        entries = self._entries()
        limit = self.limit(height)
        overflow = len(entries) > limit
        room = limit - 1 if overflow else limit
        focus = next((position for position, (kind, value) in enumerate(entries)
                      if kind == "option" and value == self.selected), 0)
        # Cuộn vừa đủ để dòng đang chọn hiện ra; dòng đầu tiên kéo luôn tên nhóm của nó vào khung.
        if focus < self.top:
            self.top = focus
            while self.top > 0 and entries[self.top - 1][0] in {"category", "gap"}:
                self.top -= 1
        elif focus >= self.top + room:
            self.top = focus - room + 1
        self.top = max(0, min(self.top, max(0, len(entries) - room)))
        shown = entries[self.top:self.top + room]
        # Tên nhóm không nằm trơ ở đáy khung khi các dòng của nó còn ở dưới.
        while overflow and shown and shown[-1][0] in {"category", "gap"}:
            shown.pop()
        lines = []
        for kind, value in shown:
            if kind == "gap":
                lines.append(fit(Line([]), width, panel))
            elif kind == "category":
                lines.append(self._row(theme, width, [S(str(value), theme.accent, panel, b=True)]))
            else:
                lines.append(self._option_line(theme, width, flat[value], value))
        if overflow:
            more = self.top + room < len(entries)
            lines.append(self._row(theme, width, [S("…" if more else " ", theme.muted, panel)]))
        return lines

    def _option_line(self, theme, width: int, option: Option, index: int) -> Line:
        panel = theme.panel
        active = index == self.selected
        armed = self.armed is not None and option.value == self.armed and active
        if armed:
            bg, text = theme.error, theme.on_primary
        elif active:
            bg, text = theme.primary, theme.on_primary
        else:
            bg = panel
            text = theme.muted if option.disabled else theme.primary if option.current else theme.text
        secondary = text if active else theme.muted
        inner = width - 2  # 1 ô lề mỗi bên: dòng tô không chạm mép khung
        spans = [S(" ", bg=bg)]
        if option.gutter:
            spans.append(S(option.gutter, text if active else getattr(theme, option.gutter_tone), bg))
        elif option.current:
            spans.append(S("●", text, bg))
        else:
            spans.append(S(" ", bg=bg))
        spans.append(S(" ", bg=bg))
        title = self.armed_text if armed else option.title
        footer = option.footer
        if self.query.strip():
            footer = option.search_footer if option.search_footer is not None else (option.category or option.footer)
        footer_width = cells(footer)
        title_room = max(6, inner - 3 - 3 - (footer_width + 2 if footer else 0))
        title_text = clip(title, title_room)
        spans.append(S(title_text, text, bg, b=active))
        used = cells(title_text)
        description = "" if armed or option.description == option.category else option.description
        if description and used + 1 < title_room:
            part = clip(" " + description, title_room - used)
            spans.append(S(part, secondary, bg))
            used += cells(part)
        gap = max(1, inner - 3 - used - footer_width - 3)
        spans.append(S(" " * gap, bg=bg))
        if footer:
            tone = secondary if active else getattr(theme, option.footer_tone, theme.muted)
            spans.append(S(footer, tone, bg))
        row = fit(Line(spans), inner, bg)
        target = Target(("dialog-row", id(self), index), lambda: self._pick(index, Key("enter")),
                        hover=lambda: self._hover(index), look="")
        return Line([S(" ", bg=panel)] + clickable(row.spans, target) + [S(" ", bg=panel)])

    def _visible_actions(self) -> list[Action]:
        return [action for action in self.actions if not action.hidden]

    def _footer_line(self, theme, width: int) -> Line | None:
        actions = self._visible_actions()
        if not actions:
            return None
        panel = theme.panel
        left: list = []
        right: list = []
        for action in actions:
            spans = clickable([S(action.title, theme.text, panel), S(" " + action.key, theme.muted, panel)],
                              Target(("dialog-action", id(self), action.name),
                                     lambda action=action: Key("ctrl", action.key[-1])))
            target = right if action.right else left
            if target:
                target.append(S("  ", bg=panel))
            target.extend(spans)
        used = sum(cells(text) for text, _ in left + right)
        gap = max(2, width - LIST_INSET * 2 - used)
        return fit(Line([S(" " * LIST_INSET, bg=panel)] + left + [S(" " * gap, bg=panel)] + right), width, panel)

    # ---- Phím

    def _pick(self, index: int, key: Key) -> Key:
        self.selected = index
        return key

    def _hover(self, index: int) -> None:
        if index != self.selected:
            self.selected = index
            self.armed = None

    def handle(self, key: Key) -> str | None:
        flat = self.flat()
        armed, self.armed = self.armed, None
        name = key.name
        if name == "escape":
            return self._finish(Result("close"))
        if name in {"up", "down"} and flat:
            step = -1 if name == "up" else 1
            self.selected = (self.selected + step) % len(flat)
            return None
        if name in {"pageup", "pagedown"} and flat:
            step = 10
            self.selected = max(0, min(len(flat) - 1, self.selected + (-step if name == "pageup" else step)))
            return None
        if name in {"home", "end"} and flat and not self.query:
            self.selected = 0 if name == "home" else len(flat) - 1
            return None
        if name == "wheel":
            self.top = max(0, self.top + (-3 if key.text == "up" else 3))
            return None
        if name == "enter":
            option = self.chosen()
            if option is None or option.disabled:
                return None
            return self._finish(Result("select", option))
        if name == "ctrl":
            for action in self._visible_actions():
                if _matches(key, action.key):
                    option = self.chosen()
                    if action.needs_option and option is None:
                        return None
                    # Bấm lần hai cùng phím trên cùng dòng: đã xác nhận (xóa).
                    self.armed = armed
                    return self._finish(Result("action", option, action.name))
            return None
        if self.search and name in {"char", "paste"}:
            self.query += " ".join(key.text.split()) if name == "paste" else key.text
            self.selected, self.top = 0, 0
            return None
        if self.search and name == "backspace" and self.query:
            self.query = self.query[:-1]
            self.selected, self.top = 0, 0
            return None
        return None

    def arm(self, value: object, text: str) -> None:
        """Đặt dòng ``value`` vào trạng thái chờ xác nhận (bấm phím xóa lần nữa), như OpenCode."""
        self.armed, self.armed_text = value, text


class PromptDialog(_Base):
    """Ô nhập một dòng (DialogPrompt của OpenCode). ``secret``: hiện chấm thay chữ (khóa API)."""

    def __init__(self, title: str, *, placeholder: str = "", value: str = "", secret: bool = False,
                 description: str = "", error: str = "", busy: str = "", size: str = "medium",
                 submit: str = "gửi"):
        self.title = title
        self.placeholder = placeholder
        self.value = value
        self.secret = secret
        self.description = description
        self.error = error
        self.busy = busy
        self.size = size
        self.submit = submit
        self.result = None

    def shown(self) -> str:
        return "•" * len(self.value) if self.secret else self.value

    def render(self, theme, available: int, height: int) -> list[Line]:
        width = self.width(available)
        panel = theme.panel
        blank = fit(Line([]), width, panel)
        lines = [blank, self._header(theme, width, self.title), blank]
        room = width - LIST_INSET * 2 - 1
        if self.value:
            text = self.shown()
            if cells(text) > room:
                text = "…" + text[-(room - 1):]
            spans = [S(text, theme.text, panel)]
            if not self.busy:
                spans.append(S(" ", theme.panel, theme.text))
        elif self.busy:
            spans = [S(self.placeholder, theme.muted, panel)]
        else:
            first, rest = self.placeholder[:1] or " ", self.placeholder[1:]
            spans = [S(first, theme.panel, theme.text), S(rest, theme.muted, panel)]
        lines.append(self._row(theme, width, spans))
        for text, tone in ((self.error, theme.error), (self.description, theme.muted)):
            if not text:
                continue
            lines.append(blank)
            for part in wrap([S(text, tone, panel)], width - LIST_INSET * 2):
                lines.append(self._row(theme, width, part))
        lines.append(blank)
        if self.busy:
            lines += [self._row(theme, width, row)
                      for row in wrap([S(self.busy, theme.muted, panel)], width - LIST_INSET * 2)]
        else:
            submit = Target(("dialog-submit", id(self)), lambda: Key("enter"))
            lines.append(self._row(theme, width, clickable([S("enter", theme.text, panel),
                                                            S(" " + self.submit, theme.muted, panel)], submit)))
        lines.append(blank)
        return lines

    def handle(self, key: Key) -> str | None:
        if self.busy:
            return None
        name = key.name
        if name == "escape":
            return self._finish(Result("close"))
        if name == "enter":
            if not self.value.strip():
                return None
            return self._finish(Result("submit", text=self.value.strip()))
        if name in {"char", "paste"}:
            text = key.text.replace("\r", "").replace("\n", "")
            self.value += text
            self.error = ""
            return None
        if name == "backspace" and self.value:
            self.value = self.value[:-1]
            return None
        return None
