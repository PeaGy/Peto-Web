"""Nhật ký "Đang làm" của một lượt chat, kiểu Dòng thời gian chủ dự án chọn ngày 5/10/2026.

Máy chủ ghi từng bước từ các mảnh provider gửi về: đọc tệp, suy nghĩ (kèm tóm tắt suy nghĩ Grok gửi), câu ngắn Peto nói
trước khi dùng công cụ, soạn lệnh, chạy công cụ (sửa/tạo tệp, tra trong tệp, đọc GitHub, tra web). Mỗi bước có giờ bắt
đầu và kết thúc, tính bằng mili giây từ đầu lượt. Trình duyệt nhận từng bước qua sự kiện "step" để vẽ dòng thời gian có
đồng hồ; cuối lượt cả nhật ký lưu cùng tin nhắn (cột ``messages.work``), nên tải lại trang vẫn thấy.

Trước đây nhật ký chỉ dựng ở trình duyệt, chỉ hiện thời gian tổng tính bằng giây, mất khi tải lại trang, và biến mất
cùng bong bóng khi lượt hỏng mà chưa có chữ: lượt sửa Excel bị dừng ở phút thứ năm không để lại gì để biết Peto đã thử gì.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from shared.events import sse

MAX_STEPS = 80
MAX_SUMMARY_CHARS = 4_000       # mỗi bước suy nghĩ
MAX_TOTAL_SUMMARY = 16_000      # cả lượt
MAX_PROBLEMS = 8
MAX_PROBLEM_CHARS = 300
# Chữ Peto viết trước khi gọi công cụ thường là một câu dẫn ("Mình sửa bảng lương trước…"): đưa vào dòng thời gian
# thay vì câu trả lời. Dài hơn chừng này thì là nội dung thật, giữ trong câu trả lời.
NOTE_LIMIT = 600
# Bước suy nghĩ không có tóm tắt mà ngắn hơn chừng này (chỉ là thời gian chờ chữ đầu tiên) thì bỏ khi lưu.
SHORT_THOUGHT_MS = 1_500

# Công cụ có tham số dài: Grok soạn lệnh mất thời gian thấy được, nên có bước "soạn" riêng.
COMPOSE = {
    'edit_spreadsheet': 'Đang soạn lệnh sửa tệp Excel…',
    'create_document': 'Đang soạn tài liệu…',
    'create_presentation': 'Đang soạn slide…',
    'create_spreadsheet': 'Đang soạn bảng tính…',
}


def _done_label(label: str) -> str:
    """"Đang sửa tệp Excel…" → "Đã sửa tệp Excel"."""
    text = label.rstrip('…').rstrip('.')
    return 'Đã ' + text[5:] if text.startswith('Đang ') else text


def _clip(text: str, limit: int) -> str:
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _number(value: int) -> str:
    return f'{value:,}'.replace(',', '.')


def read_detail(document: dict | None) -> str:
    """Một dòng về tệp vừa đọc: "5 trang tính · 152 công thức", "12 trang · có OCR", "đọc được một phần"…"""
    if not document:
        return ''
    parts = []
    if document.get('sheets'):
        parts.append(f'{_number(document["sheets"])} trang tính')
        if document.get('formulas'):
            parts.append(f'{_number(document["formulas"])} công thức')
    elif document.get('pages'):
        parts.append(f'{_number(document["pages"])} trang')
    if document.get('ocr_pages'):
        parts.append('có OCR')
    status = document.get('status')
    if status == 'partial':
        parts.append('đọc được một phần')
    elif status in ('unreadable', 'no_text'):
        parts.append('chưa đọc được chữ')
    return ' · '.join(parts)


@dataclass
class Step:
    id: str
    kind: str                  # read | think | note | compose | tool | lookup | github | search
    label: str
    start: int
    state: str = 'live'        # live | done | failed | stopped
    end: int | None = None
    detail: str = ''
    summary: str = ''
    problems: list[str] = field(default_factory=list)

    def public(self) -> dict:
        data = {'id': self.id, 'kind': self.kind, 'label': self.label, 'state': self.state, 'start': self.start}
        if self.end is not None:
            data['end'] = self.end
        if self.detail:
            data['detail'] = self.detail
        if self.summary:
            data['summary'] = self.summary
        if self.problems:
            data['problems'] = self.problems
        return data


class WorkLog:
    """Các hàm trả về chuỗi sự kiện SSE cần gửi (có thể rỗng); ``close`` trả nhật ký để lưu."""

    def __init__(self, started: float | None = None, clock=perf_counter):
        self.clock = clock
        self.started = clock() if started is None else started
        self.steps: list[Step] = []
        self.count = 0
        self.summary_chars = 0
        self.text_at: int | None = None
        self.github_read = self.github_failed = 0

    def now(self) -> int:
        return max(0, round((self.clock() - self.started) * 1000))

    # ---------- dùng chung ----------

    @staticmethod
    def _event(step: Step | None) -> str:
        return sse({'type': 'step', 'step': step.public()}) if step else ''

    def _live(self, kind: str) -> Step | None:
        return next((step for step in reversed(self.steps) if step.kind == kind and step.state == 'live'), None)

    def _begin(self, kind: str, label: str, at: int | None = None, state: str = 'live', **fields) -> tuple[Step | None, str]:
        if len(self.steps) >= MAX_STEPS:
            return None, ''
        events = ''
        github = self._live('github')
        if github and kind != 'github':
            events += self._finish(github)
        self.count += 1
        step = Step(f'{kind}-{self.count}', kind, label, self.now() if at is None else at, state, **fields)
        if state != 'live':
            step.end = step.start
        self.steps.append(step)
        return step, events + self._event(step)

    def _finish(self, step: Step | None, label: str | None = None, state: str = 'done', **fields) -> str:
        if step is None or step.state != 'live':
            return ''
        step.state, step.end = state, self.now()
        if label:
            step.label = label
        for name, value in fields.items():
            setattr(step, name, value)
        return self._event(step)

    # ---------- đọc tệp gửi kèm ----------

    def read_start(self, label: str) -> str:
        return self._begin('read', label)[1]

    def read_done(self, label: str, detail: str = '') -> str:
        return self._finish(self._live('read'), label, detail=detail)

    # ---------- mô hình ----------

    def round(self) -> str:
        """Một lần gọi mô hình bắt đầu: thời gian tới chữ hay lệnh đầu tiên là thời gian suy nghĩ."""
        self.text_at = None
        if self._live('think'):
            return ''
        return self._begin('think', 'Đang suy nghĩ…')[1]

    def thinking(self, delta: str) -> str:
        step = self._live('think')
        events = ''
        if step is None:
            step, events = self._begin('think', 'Đang suy nghĩ…')
        if step is None or not delta:
            return events
        room = min(MAX_SUMMARY_CHARS - len(step.summary), MAX_TOTAL_SUMMARY - self.summary_chars)
        if room <= 0:
            return events
        piece = delta[:room]
        step.summary += piece
        self.summary_chars += len(piece)
        return events + sse({'type': 'thinking', 'step': step.id, 'text': piece})

    def text(self) -> str:
        if self.text_at is None:
            self.text_at = self.now()
        return self._finish(self._live('think'), 'Đã suy nghĩ')

    def tool(self, name: str) -> str:
        """Mô hình bắt đầu viết lệnh gọi công cụ ``name``."""
        events = self._finish(self._live('think'), 'Đã suy nghĩ')
        if name in COMPOSE and not self._live('compose'):
            events += self._begin('compose', COMPOSE[name])[1]
        return events

    def note(self, text: str) -> str:
        """Chữ Peto viết trước khi gọi công cụ: một câu dẫn trong dòng thời gian, đặt đúng lúc bắt đầu viết."""
        at = self.text_at if self.text_at is not None else self.now()
        self.text_at = None
        return self._begin('note', _clip(text, NOTE_LIMIT), at=at, state='done')[1]

    def replace(self) -> None:
        self.text_at = None

    # ---------- công cụ ----------

    def tool_start(self, label: str) -> str:
        compose = self._live('compose')
        events = self._finish(compose, _done_label(compose.label) if compose else None)
        return events + self._begin('tool', label)[1]

    def tool_result(self, info: dict, artifact: dict | None = None) -> str:
        """Kết quả gọn của công cụ tạo/sửa tệp: tên tệp và quy mô khi xong, từng lỗi khi bị từ chối."""
        step = self._live('tool')
        if step is None:
            return ''
        if info.get('ok'):
            label, detail = info.get('label'), info.get('detail') or ''
            if not label and artifact:
                label = f'Đã tạo {artifact.get("filename") or "tệp"}'
                pages, unit = artifact.get('pages'), {'pptx': 'slide', 'xlsx': 'trang tính'}.get(artifact.get('format'), 'trang')
                detail = detail or (f'{pages} {unit}' if pages else '')
            return self._finish(step, label or _done_label(step.label), detail=_clip(detail, 200))
        problems = [_clip(item, MAX_PROBLEM_CHARS) for item in (info.get('problems') or [info.get('error') or ''])
                    if str(item).strip()][:MAX_PROBLEMS]
        label = info.get('label') or ('Chưa sửa được tệp' if info.get('tool') == 'edit_spreadsheet' else 'Chưa tạo được tệp')
        return self._finish(step, label, state='failed', problems=problems)

    def tool_end(self) -> str:
        step = self._live('tool')
        return self._finish(step, _done_label(step.label)) if step else ''

    def lookup(self, text: str, live: bool) -> str:
        if live:
            return self._begin('lookup', text)[1]
        step = self._live('lookup')
        if step is None:
            return self._begin('lookup', text, state='done')[1]
        return self._finish(step, text)

    def github(self, text: str, live: bool) -> str:
        """Gom các lần đọc GitHub liền nhau thành một bước, như danh sách cũ ("GitHub · 11 mục đã đọc")."""
        step = self._live('github')
        events = ''
        if step is None:
            self.github_read = self.github_failed = 0
            step, events = self._begin('github', 'Đang đọc GitHub…')
            if step is None:
                return events
        if not live:
            if text.startswith('Đã đọc GitHub'):
                self.github_read += 1
            else:
                self.github_failed += 1
                issue = _clip(text, MAX_PROBLEM_CHARS)
                if issue not in step.problems and len(step.problems) < MAX_PROBLEMS:
                    step.problems.append(issue)
        parts = [f'{self.github_read} mục đã đọc'] + ([f'{self.github_failed} mục chưa đọc được'] if self.github_failed else [])
        step.label = ('Đang đọc GitHub' if live else 'Đọc GitHub') + ' · ' + ' · '.join(parts)
        return events + self._event(step)

    def search(self, status: str) -> str:
        step = self._live('search')
        if status == 'completed':
            return self._finish(step, 'Đã tìm trên web') if step else ''
        return '' if step else self._begin('search', 'Đang tìm trên web…')[1]

    def sources(self, count: int) -> str:
        step = next((item for item in reversed(self.steps) if item.kind == 'search'), None)
        detail = f'{count} nguồn' if count else ''
        if step is None or step.detail == detail:
            return ''
        step.detail = detail
        return self._event(step)

    # ---------- cuối lượt ----------

    def close(self, complete: bool) -> dict:
        """Kết thúc các bước còn dở (xong, hoặc dừng nếu lượt hỏng/bị ngắt) và trả nhật ký để lưu cùng tin nhắn."""
        end = self.now()
        for step in self.steps:
            if step.state == 'live':
                step.state = 'done' if complete else 'stopped'
                step.end = end
                if step.state == 'done':
                    step.label = 'Đã suy nghĩ' if step.kind == 'think' else _done_label(step.label)
        # Giữ thứ tự tới (provider báo câu dẫn trước lệnh công cụ), đúng như trình duyệt đã vẽ trong lúc chạy.
        kept = [step for step in self.steps if not (
            step.kind == 'think' and not step.summary and step.state == 'done'
            and (step.end or 0) - step.start < SHORT_THOUGHT_MS)]
        return {'ms': end, 'steps': [step.public() for step in kept], 'complete': complete}
