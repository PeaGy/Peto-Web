"""Dùng prompt/provider/bộ lọc hiện có, trong tiến trình CLI với dữ liệu giả."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import math
from unittest.mock import AsyncMock, patch

from .schema import Case, EvalError, Settings


async def prepare_prompts(cases: list[Case], models: tuple[str, ...], clock: datetime) -> dict:
    from features.chat import prompt_context
    from features.accounts.discord_memory import MemorySnapshot
    from prompts.context import build_companion_memory, build_companion_summary
    from shared.time_tools import current_datetime, time_context
    prompts = {}
    # Ghép tuần tự trước khi chạy song song; không để ngữ cảnh bài này lẫn vào bài khác.
    for model in models:
        for case in cases:
            context = case.context
            profile = dict(full_name='', nickname='', occupation='', instructions='') | context.get('profile', {})
            snapshot = MemorySnapshot(summary=context.get('summary', ''), explicit=tuple(context.get('memory', [])))
            companion = '\n\n'.join(filter(None, (build_companion_memory(context.get('memory', [])),
                                                   build_companion_summary(context.get('summary', '')))))
            with ExitStack() as stack:
                stack.enter_context(patch.object(prompt_context.db, 'get_user', AsyncMock(return_value={
                    'display_name': profile['nickname'] or 'Người Thử'})))
                stack.enter_context(patch.object(prompt_context.db, 'get_profile', AsyncMock(return_value=profile)))
                stack.enter_context(patch.object(prompt_context.discord_memory, 'fetch', AsyncMock(
                    return_value=MemorySnapshot() if case.persona == 'companion' else snapshot)))
                stack.enter_context(patch.object(prompt_context.companion_memory, 'memory_block', AsyncMock(return_value=companion)))
                # Lượt Chat cũng đọc trí nhớ dùng chung: trả rỗng để bộ đánh giá không bao giờ chạm cơ sở dữ liệu.
                stack.enter_context(patch.object(prompt_context.companion_memory, 'chat_memory_block', AsyncMock(return_value='')))
                verified_clock = current_datetime('Asia/Ho_Chi_Minh', now=clock)
                stack.enter_context(patch('shared.time_tools.current_datetime', return_value=verified_clock))
                for index, turn in enumerate(case.turns):
                    question = '\n'.join(t['user'] for t in case.turns[max(0, index - 2):index + 1])
                    # Tệp giả đều là chữ (text/plain, xem user_message): như app, đã có tệp chữ thì kèm cách đọc log.
                    body = await prompt_context._build_system_prompt(
                        'discord:000000000000000000', mode='companion' if case.persona == 'companion' else 'chat',
                        model=model, agent_question=question,
                        text_files=any(t.get('attachments') for t in case.turns[:index + 1]))
                    body += '\n\n' + time_context('Asia/Ho_Chi_Minh')
                    prompts[model, case.id, index] = {'text': body, 'sha256': hashlib.sha256(body.encode()).hexdigest()}
    return prompts


def user_message(turn: dict):
    from features.chat.history import _to_chat_messages
    from features.documents.reader import result
    attachments = []
    for index, item in enumerate(turn.get('attachments', [])):
        status = item.get('status', 'ready')
        document = None if status == 'missing' else result(status, 'Tệp chữ giả của bộ đánh giá.', text=item.get('text', ''))
        attachments.append({'id': f'fixture-{index}', 'filename': item['name'], 'kind': 'file',
                            'mime': 'text/plain', 'document': document})
    # Không có path, ảnh hoặc tệp trên đĩa. Vẫn đi qua cách phân bổ nội dung của Chat.
    return _to_chat_messages([{'role': 'user', 'content': turn['user'], 'attachments': attachments}])[0]


class VisibleStream:
    def __init__(self, persona: str):
        from features.companion.emotion_tags import MarkerFilter
        from features.companion.private_notes import NoteFilter
        self.notes = NoteFilter() if persona == 'companion' else None
        self.markers = MarkerFilter() if persona == 'companion' else None

    def feed(self, piece: str) -> str:
        return self.markers.feed(self.notes.feed(piece)) if self.notes else piece

    def flush(self) -> str:
        return self.markers.feed(self.notes.flush()) + self.markers.flush() if self.notes else ''


def input_chars(prompt: str, messages: list) -> int:
    return len(prompt) + len(json.dumps([asdict(message) for message in messages], ensure_ascii=False))


class BudgetExceeded(RuntimeError):
    """Dừng trước request tiếp theo; không để SDK nhầm với ValueError khi đọc phản hồi."""


@dataclass
class CallBudget:
    settings: Settings
    used: int = 0

    def claim(self, request: dict, output_cap: int | None = None):
        # Không await giữa kiểm tra và tăng số lượt: an toàn với các task cùng event loop.
        if self.used >= self.settings.max_calls:
            raise BudgetExceeded('Đã hết giới hạn request.')
        body = {key: request[key] for key in ('instructions', 'input', 'system', 'messages') if key in request}
        if len(json.dumps(body, ensure_ascii=False)) > self.settings.max_input_chars:
            raise BudgetExceeded('Đầu vào vượt giới hạn ký tự.')
        output = request.get('max_output_tokens', request.get('max_tokens', 0))
        if output > (output_cap if output_cap is not None else self.settings.max_output_tokens):
            raise BudgetExceeded('Request vượt giới hạn token đầu ra.')
        self.used += 1


def _number(value):
    return value if type(value) is int and value >= 0 else None


def normalize_usage(usage, service: str) -> dict | None:
    if usage is None:
        return None
    data = usage.model_dump() if hasattr(usage, 'model_dump') else usage
    if not isinstance(data, dict):
        return None
    incoming, outgoing = _number(data.get('input_tokens')), _number(data.get('output_tokens'))
    if incoming is None or outgoing is None:
        return None
    if service == 'anthropic':
        read = _number(data.get('cache_read_input_tokens'))
        write = _number(data.get('cache_creation_input_tokens'))
        total = incoming + read + write if read is not None and write is not None else None
        uncached = incoming
    else:
        read = _number((data.get('input_tokens_details') or {}).get('cached_tokens'))
        write, total = 0, incoming
        uncached = incoming - read if read is not None and read <= incoming else None
    return {'input_tokens': total, 'output_tokens': outgoing, 'uncached_input_tokens': uncached,
            'cache_read_tokens': read, 'cache_write_tokens': write,
            'reasoning_tokens': _number((data.get('output_tokens_details') or {}).get('reasoning_tokens'))}


@dataclass
class Capture:
    service: str
    records: list[dict] = field(default_factory=list)

    def begin(self, request: dict) -> dict:
        row = {'requested_model': request['model'], 'actual_model': None, 'usage': None}
        self.records.append(row)
        return row

    def finish(self, row: dict, response):
        row['actual_model'] = getattr(response, 'model', None)
        row['usage'] = normalize_usage(getattr(response, 'usage', None), self.service)


class ResponsesGate:
    def __init__(self, original, capture: Capture, budget: CallBudget, output_cap: int | None = None):
        self.original, self.capture, self.budget, self.output_cap = original, capture, budget, output_cap

    async def create(self, **kwargs):
        self.budget.claim(kwargs, self.output_cap)
        row = self.capture.begin(kwargs)
        stream = await self.original.create(**kwargs)
        return ResponseEvents(stream, row, self.capture)


class ResponseEvents:
    def __init__(self, stream, row, capture):
        self.stream, self.row, self.capture = stream, row, capture

    async def __aiter__(self):
        async for event in self.stream:
            if getattr(event, 'type', '') in {'response.completed', 'response.incomplete', 'response.failed'}:
                response = getattr(event, 'response', None)
                if response is not None:
                    self.capture.finish(self.row, response)
            yield event

    async def close(self):
        await self.stream.close()


class MessagesGate:
    def __init__(self, original, capture: Capture, budget: CallBudget, output_cap: int | None = None):
        self.original, self.capture, self.budget, self.output_cap = original, capture, budget, output_cap

    def stream(self, **kwargs):
        self.budget.claim(kwargs, self.output_cap)
        row = self.capture.begin(kwargs)
        return MessageContext(self.original.stream(**kwargs), row, self.capture)


class MessageContext:
    def __init__(self, context, row, capture):
        self.context, self.row, self.capture = context, row, capture

    async def __aenter__(self):
        return MessageEvents(await self.context.__aenter__(), self.row, self.capture)

    async def __aexit__(self, *args):
        return await self.context.__aexit__(*args)


class MessageEvents:
    def __init__(self, stream, row, capture):
        self.stream, self.row, self.capture = stream, row, capture

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __aiter__(self):
        return self.stream.__aiter__()

    async def get_final_message(self):
        message = await self.stream.get_final_message()
        self.capture.finish(self.row, message)
        return message


def ensure_credentials(models: tuple[str, ...]):
    import os
    from ai.models import MODELS
    from core import config
    from pathlib import Path
    for model in models:
        service = MODELS[model].service
        ready = {'openai': bool(config.OPENAI_API_KEY), 'anthropic': bool(config.ANTHROPIC_API_KEY),
                 'xai': bool(os.getenv('XAI_API_KEY')) or Path(config.XAI_TOKEN_PATH).is_file()}[service]
        if not ready:
            raise EvalError(f'Chưa có credential cho {MODELS[model].label}; chưa gọi API nào.')


def make_provider(model: str, settings: Settings, budget: CallBudget):
    from ai.models import MODELS
    from ai.mock import MockProvider
    info = MODELS[model]
    capture = Capture(info.service)
    cap = settings.output_cap(model)
    if settings.mode == 'mock':
        return MockProvider(model), capture
    if info.service == 'anthropic':
        from ai.claude import ClaudeProvider
        provider = ClaudeProvider(info.slug, info.label)
        sdk = provider._client.sdk
        sdk.max_retries, sdk.timeout = 0, settings.timeout
        sdk.messages = MessagesGate(sdk.messages, capture, budget, cap)
    elif info.service == 'openai':
        from ai.gpt import GPTProvider
        provider = GPTProvider(info.slug, info.label)
    else:
        from ai.xai import XAIProvider
        provider = XAIProvider()
    provider.max_output_tokens = cap
    if info.service != 'anthropic':
        provider._client.max_retries, provider._client.timeout = 0, settings.timeout
        provider._client.responses = ResponsesGate(provider._client.responses, capture, budget, cap)
    return provider, capture


@contextmanager
def output_caps(settings: Settings):
    """Bộ bài bỏ trần 1.024 token mà provider tự đặt cho lượt không công cụ (side_output_cap).

    Chỉ đổi trong tiến trình CLI, trong lúc bộ bài chạy. Trần thật vẫn là provider.max_output_tokens (mức của app),
    và CallBudget từ chối request nào vượt số đó trước khi gửi.
    """
    if settings.suite is None:
        yield
        return
    from unittest.mock import patch
    with patch('ai.xai.side_output_cap', lambda default: default):
        yield


def model_slug(model: str) -> str:
    """Slug gửi cho nhà cung cấp, cũng là khóa của bảng giá --rates."""
    from ai.models import MODELS
    from core import config
    return config.XAI_MODEL if model == 'peto' else MODELS[model].slug


def estimate(cases: list[Case], settings: Settings, prompts: dict, rates: dict | None = None) -> dict:
    """Ước tính trước khi chạy: số request, trần token đầu ra và token đầu vào theo cách đếm của Chat.

    Token đầu vào là ước lượng (features/chat/context_budget.tokens), không phải cách đếm của nhà cung cấp. Trần đầu
    vào giả định mỗi câu trả lời trước dài hết trần đầu ra, và không vượt --max-input-chars của mỗi request.
    """
    from features.chat.context_budget import tokens
    rates = rates or {}
    # Mỗi ký tự UTF-8 trong BMP tối đa 3 byte; bộ đếm của Chat lấy byte/3 × 1,15.
    request_ceiling = math.ceil(settings.max_input_chars * 1.15)
    models, usd, missing = {}, 0.0, []
    for model in settings.models:
        cap = settings.output_cap(model)
        turns = known = ceiling = 0
        for case in cases:
            history = []
            for index, turn in enumerate(case.turns):
                history.append(user_message(turn))
                base = tokens(prompts[model, case.id, index]['text'], [asdict(message) for message in history])
                known += base
                ceiling += min(base + index * cap, request_ceiling)
                turns += 1
        turns, known, ceiling = turns * settings.repeat, known * settings.repeat, ceiling * settings.repeat
        slug = model_slug(model)
        row = {'slug': slug, 'turns': turns, 'output_cap': cap, 'output_tokens_max': turns * cap,
               'input_tokens_known': known, 'input_tokens_max': ceiling, 'usd_max': None}
        rate = rates.get(slug)
        if rate:
            # Cận trên: không trừ cache; phần ghi cache của Claude có thể đắt hơn đầu vào thường.
            row['usd_max'] = round((ceiling * max(rate['input'], rate.get('cache_write', 0))
                                    + row['output_tokens_max'] * rate['output']) / 1_000_000, 4)
            usd += row['usd_max']
        else:
            missing.append(slug)
        models[model] = row
    largest = max(row['output_cap'] for row in models.values())
    return {'planned_turns': sum(row['turns'] for row in models.values()), 'max_calls': settings.max_calls,
            'models': models, 'output_tokens_max': sum(row['output_tokens_max'] for row in models.values()),
            'output_tokens_hard': settings.max_calls * largest,
            'input_tokens_max': sum(row['input_tokens_max'] for row in models.values()),
            'usd_max': round(usd, 4) if not missing else None, 'unpriced': missing,
            'method': 'Token đầu vào ước lượng bằng bộ đếm của Chat (byte/3 × 1,15), không phải số của nhà cung cấp.'}


def describe_estimate(value: dict) -> list[str]:
    lines = [f"Ước tính: {value['planned_turns']} lượt, tối đa {value['max_calls']} request "
             '(tính cả request tiếp tục của Claude).']
    for model, row in value['models'].items():
        usd = f"; tối đa khoảng {row['usd_max']} USD" if row['usd_max'] is not None else ''
        lines.append(f"- {model} ({row['slug']}): {row['turns']} lượt, trần {row['output_cap']} token đầu ra/request, "
                     f"đầu ra tối đa {row['output_tokens_max']} token, đầu vào khoảng {row['input_tokens_known']}–"
                     f"{row['input_tokens_max']} token{usd}.")
    lines.append(f"Tổng: đầu ra tối đa {value['output_tokens_max']} token theo kế hoạch "
                 f"(tuyệt đối {value['output_tokens_hard']} nếu dùng hết số request), đầu vào tối đa khoảng "
                 f"{value['input_tokens_max']} token.")
    if value['usd_max'] is not None:
        lines.append(f"Chi phí tối đa khoảng {value['usd_max']} USD theo bảng giá --rates, chưa trừ cache.")
    else:
        lines.append('Chưa ước tính USD: thiếu giá cho ' + ', '.join(value['unpriced']) + ' trong --rates.')
    lines.append(value['method'])
    return lines


async def close_provider(provider):
    client = getattr(provider, '_client', None)
    if client is not None:
        client = getattr(client, 'sdk', client)
        await client.close()
