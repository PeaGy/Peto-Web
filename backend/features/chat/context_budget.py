"""Ngân sách riêng Web Chat; số token là ước lượng, không phải usage của provider."""
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
import json
import math
import os

from ai.base import ProviderError
from ai.models import MODELS
from core import config

# Cùng snapshot API-ID đã đối chiếu trong agent-cli/docs/context-budget-0.30.0.md; không dùng runtime/quyền Agent.
CATALOG = {'grok-4.7': (500_000, 32_000), 'gpt-6-luna': (1_050_000, 128_000),
           'claude-haiku-5-5': (1_000_000, 128_000)}
current: ContextVar[dict | None] = ContextVar('web_chat_budget', default=None)


class ContextOverflow(ProviderError):
    """Ngữ cảnh thực sự vượt hạn mức; tách khỏi cấu hình sai hoặc lỗi provider."""


def estimate(value) -> int:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        if value.get('type') == 'input_image' or value.get('kind') == 'image' and value.get('data_url'):
            return 4096
        return 8 + sum(estimate(key) + estimate(child) for key, child in value.items()
                       if key not in {'image_url', 'data_url', 'encrypted_content'})
    if isinstance(value, (list, tuple)):
        return sum(estimate(child) for child in value)
    return math.ceil(len(str(value).encode('utf-8')) / 3) if value is not None else 0


def tokens(*values) -> int:
    return math.ceil(sum(estimate(value) for value in values) * 1.15)


def policy(key: str) -> dict:
    model = MODELS[key]
    slug = config.XAI_MODEL if key == 'peto' else model.slug
    window, maximum = CATALOG.get(slug, (32_768, 4096))
    try:
        overrides = json.loads(os.getenv('PETO_CHAT_CONTEXT_LIMITS', '{}'))
    except ValueError:
        raise ProviderError('Cấu hình PETO_CHAT_CONTEXT_LIMITS phải là JSON hợp lệ.') from None
    entry = overrides.get(slug, {}) if isinstance(overrides, dict) else None
    if not isinstance(entry, dict) or any(name not in {'context', 'input', 'output'} or type(value) is not int
                                         or not 1024 <= value <= 10_000_000 for name, value in entry.items()):
        raise ProviderError('Cấu hình ngân sách Chat không hợp lệ; nhờ quản trị kiểm tra PETO_CHAT_CONTEXT_LIMITS.')
    window = entry.get('context', window)
    output = min(entry.get('output', maximum), {'xai': config.XAI_MAX_OUTPUT_TOKENS,
                  'openai': config.OPENAI_MAX_OUTPUT_TOKENS, 'anthropic': config.ANTHROPIC_MAX_OUTPUT_TOKENS}[model.service])
    output = min(output, max(1024, window // 3))
    app_limit = config.CHAT_CONTEXT_TOKENS
    limit = min(app_limit, entry.get('input', window), window - output - max(2048, window // 20))
    if limit < 4096:
        raise ProviderError('Ngân sách Chat còn quá ít chỗ cho đầu vào; kiểm tra cấu hình context/output.')
    return {'model': key, 'identity': f'{model.service}/{slug}', 'known': slug in CATALOG or bool(entry),
            'context': window, 'input': limit, 'output': output, 'estimated': True}


def enforce(request: dict) -> None:
    info = current.get()
    if info is None:
        return
    used = tokens(request.get('instructions', ''), request.get('input', []), request.get('tools', []))
    if used > info['input']:
        raise ContextOverflow('Ngữ cảnh lượt này đã vượt ngân sách an toàn. Phần đã làm được giữ lại; '
                            'hãy hỏi tiếp về một phần cụ thể hoặc chia nhỏ tài liệu.')
    request['max_output_tokens'] = min(request['max_output_tokens'], info['output'], info['context'] - used - 2048)


def side_output_cap(default: int) -> int:
    """Chỉ lượt tóm tắt Chat đang được bind mới tăng chỗ JSON; side call khác vẫn giữ giới hạn cũ."""
    info = current.get()
    return min(default, info.get('summary_output', 1024) if info else 1024)
