"""Đọc dữ liệu bài thi và kiểm tra giới hạn trước khi có thể gọi AI."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

GROUPS = ('identity', 'conversation', 'memory', 'reasoning', 'truth', 'protocol')
PERSONAS = ('chat', 'companion', 'roleplay')
RUBRICS = {
    'accuracy': 'Đúng dữ kiện, phép tính và kết luận; phân biệt điều chưa xác minh.',
    'helpfulness': 'Đáp ứng việc người dùng cần, đủ chi tiết để dùng được và không dài thừa.',
    'naturalness': 'Giọng phù hợp tình huống, không máy móc hoặc liên tục hỏi ngược.',
    'identity': 'Giữ đúng persona của chế độ; trung thực về khả năng thật.',
    'memory': 'Dùng đúng dữ kiện được cung cấp, ưu tiên sửa đổi mới và không bịa ký ức.',
}
CHECK_KINDS = ('match', 'avoid', 'max_chars', 'emotion', 'private_hidden', 'spoken_plain')


class EvalError(ValueError):
    """Lỗi cấu hình hoặc dữ liệu đã có lời giải thích an toàn."""


def read_json(path: Path, *, limit: int = 10_000_000):
    try:
        if path.stat().st_size > limit:
            raise EvalError(f'Tệp JSON vượt giới hạn {limit // 1_000_000} MB.')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise EvalError('Không đọc được tệp JSON; kiểm tra đường dẫn, mã UTF-8 và cú pháp.') from err


def text(value, label: str, limit: int = 20_000, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise EvalError(f'{label} phải là chữ và nằm trong giới hạn độ dài.')
    return value


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    persona: str
    group: str
    turns: list[dict]
    context: dict


def load_cases(path: Path) -> list[Case]:
    raw = read_json(path)
    if not isinstance(raw, dict) or raw.get('version') != 1 or not isinstance(raw.get('cases'), list):
        raise EvalError('Bộ bài cần version=1 và danh sách cases.')
    if not 1 <= len(raw['cases']) <= 500:
        raise EvalError('Bộ bài cần từ 1 tới 500 tình huống.')
    cases, seen = [], set()
    for item in raw['cases']:
        if not isinstance(item, dict) or set(item) - {'id', 'title', 'persona', 'group', 'turns', 'context'}:
            raise EvalError('Trường tình huống không hợp lệ.')
        key = text(item.get('id'), 'Mã bài', 80)
        if not re.fullmatch(r'[a-z][a-z0-9-]*', key) or key in seen:
            raise EvalError('Mã bài phải duy nhất, gồm chữ thường, số và dấu gạch ngang.')
        seen.add(key)
        if item.get('persona') not in PERSONAS or item.get('group') not in GROUPS:
            raise EvalError('Persona hoặc nhóm bài không hợp lệ.')
        turns = item.get('turns')
        if not isinstance(turns, list) or not 1 <= len(turns) <= 6:
            raise EvalError('Mỗi bài cần từ 1 tới 6 lượt người dùng.')
        for turn in turns:
            if not isinstance(turn, dict) or set(turn) - {'user', 'attachments', 'checks', 'rubric', 'expectation'}:
                raise EvalError('Trường lượt hội thoại không hợp lệ.')
            text(turn.get('user'), 'Tin nhắn')
            text(turn.get('expectation'), 'Hướng dẫn chấm', 4000)
            rubric = turn.get('rubric')
            if (not isinstance(rubric, list) or not rubric or any(not isinstance(r, str) or r not in RUBRICS for r in rubric)
                    or len(set(rubric)) != len(rubric)):
                raise EvalError('Mỗi lượt cần các tiêu chí chất lượng hợp lệ, không trùng.')
            checks = turn.get('checks', [])
            if not isinstance(checks, list) or len(checks) > 20:
                raise EvalError('Danh sách phép kiểm tra không hợp lệ.')
            for check in checks:
                if not isinstance(check, dict) or set(check) - {'kind', 'value', 'critical', 'label'} or check.get('kind') not in CHECK_KINDS:
                    raise EvalError('Phép kiểm tra không hợp lệ.')
                text(check.get('label'), 'Tên phép kiểm tra', 200)
                if not isinstance(check.get('critical', False), bool):
                    raise EvalError('critical phải là true hoặc false.')
                if check['kind'] in {'match', 'avoid'}:
                    pattern = text(check.get('value'), 'Biểu thức kiểm tra', 500)
                    try:
                        re.compile(pattern)
                    except re.error as err:
                        raise EvalError('Biểu thức kiểm tra sai cú pháp.') from err
                elif check['kind'] == 'max_chars':
                    if type(check.get('value')) is not int or not 1 <= check['value'] <= 20_000:
                        raise EvalError('Giới hạn ký tự không hợp lệ.')
                elif 'value' in check:
                    raise EvalError('Phép kiểm tra này không nhận value.')
                if check['kind'] in {'emotion', 'private_hidden', 'spoken_plain'} and item['persona'] != 'companion':
                    raise EvalError('Phép kiểm tra giọng nói chỉ dành cho Companion.')
            attachments = turn.get('attachments', [])
            if not isinstance(attachments, list) or len(attachments) > 4:
                raise EvalError('Mỗi lượt chỉ có tối đa 4 tệp chữ giả.')
            for attachment in attachments:
                if not isinstance(attachment, dict) or set(attachment) - {'name', 'text', 'status'}:
                    raise EvalError('Tệp giả chỉ nhận name, text và status; không nhận đường dẫn.')
                text(attachment.get('name'), 'Tên tệp', 120)
                text(attachment.get('text', ''), 'Nội dung tệp', empty=True)
                if attachment.get('status', 'ready') not in {'ready', 'partial', 'missing'}:
                    raise EvalError('Trạng thái tệp giả không hợp lệ.')
        context = item.get('context', {})
        if not isinstance(context, dict) or set(context) - {'profile', 'memory', 'summary'}:
            raise EvalError('Ngữ cảnh giả không hợp lệ.')
        profile = context.get('profile', {})
        if not isinstance(profile, dict) or set(profile) - {'full_name', 'nickname', 'occupation', 'instructions'}:
            raise EvalError('Hồ sơ giả không hợp lệ.')
        for value in profile.values():
            text(value, 'Hồ sơ', 4000, empty=True)
        memory = context.get('memory', [])
        if not isinstance(memory, list) or len(memory) > 20:
            raise EvalError('Danh sách trí nhớ giả không hợp lệ.')
        for value in memory:
            text(value, 'Trí nhớ', 2000)
        text(context.get('summary', ''), 'Tóm tắt', 4000, empty=True)
        cases.append(Case(key, text(item.get('title'), 'Tên bài', 200), item['persona'], item['group'], turns, context))
    return cases


@dataclass(frozen=True)
class Settings:
    mode: str = 'mock'
    models: tuple[str, ...] = ('peto',)
    effort: str = 'low'
    repeat: int = 1
    concurrency: int = 1
    timeout: float = 90
    max_calls: int = 60
    max_output_tokens: int = 1024
    max_input_chars: int = 60_000
    allow_paid: bool = False

    def validate(self, cases: list[Case]) -> int:
        from ai.models import MODELS, supported_efforts
        if self.mode not in {'mock', 'live'} or (self.mode == 'live' and not self.allow_paid):
            raise EvalError('Chạy thật cần --mode live và --allow-paid; mặc định chỉ chạy mock.')
        if not self.models or len(set(self.models)) != len(self.models):
            raise EvalError('Danh sách model rỗng hoặc bị trùng.')
        for model in self.models:
            if model not in MODELS or self.effort not in supported_efforts(model):
                raise EvalError('Model hoặc mức suy nghĩ không được registry Peto hỗ trợ.')
            if not MODELS[model].web:
                raise EvalError('Bản đầu chỉ đo model trên Web; model chỉ dành cho Agent dùng bộ thi Agent hiện có.')
        for value, low, high, label in ((self.repeat, 1, 5, 'Số lần lặp'), (self.concurrency, 1, 4, 'Concurrency'),
                                      (self.max_calls, 1, 500, 'Số request'), (self.max_output_tokens, 128, 1024, 'Token đầu ra'),
                                      (self.max_input_chars, 1000, 120_000, 'Ký tự đầu vào')):
            if type(value) is not int or not low <= value <= high:
                raise EvalError(f'{label} cần nằm trong khoảng {low}–{high}.')
        if type(self.timeout) not in {int, float} or not math.isfinite(self.timeout) or not 0 < self.timeout <= 600:
            raise EvalError('Timeout cần lớn hơn 0 và không vượt 600 giây.')
        planned = sum(len(case.turns) for case in cases) * self.repeat * len(self.models)
        if not cases or planned > self.max_calls:
            raise EvalError(f'Kế hoạch cần {planned} lượt; vượt --max-calls={self.max_calls} hoặc chưa chọn bài.')
        return planned
