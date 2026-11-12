"""Gói G1.1 chỉ đổi request của tab Trò chuyện: Companion, Agent, BYOK và lượt phụ (đặt tên, tóm tắt, ghi nhớ) phải gửi
đúng từng byte như trước.

``tests/fixtures/unchanged_requests.json`` được ghi bằng chính tệp này chạy trên mã trước thay đổi (commit 62f7b3b) với
``PETO_RECORD_UNCHANGED=1``. Client giả ghi request (kwargs gửi SDK openai, thân HTTP gửi Anthropic); không gọi mạng.
"""
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai import agent, byok, claude
from ai.base import ChatMessage
from ai.claude import ClaudeProvider
from ai.xai import XAIProvider
from core import config
from features.chat import service
from shared import time_tools
from test_claude import message_events, sdk_with_responses
from test_clock_tools import FakeStream, Item, done

FIXTURE = Path(__file__).parent / 'fixtures' / 'unchanged_requests.json'
FIXED = datetime(2026, 11, 12, 8, 30, 15, tzinfo=UTC)
PROFILE = 'Hồ sơ người dùng giả lập.'
THINKING = {'type': 'thinking', 'thinking': 'Đang cân nhắc', 'signature': 'chu-ky-gia'}
CLOCK_TOOL = {'type': 'tool_use', 'id': 'toolu_clock', 'name': 'get_current_datetime', 'input': {'timezone': 'UTC'}}
TEXT = {'type': 'text', 'text': 'Xong.'}


@pytest.fixture
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED.astimezone(tz or UTC)
    monkeypatch.setattr(time_tools, 'datetime', Clock)


def responses_capture(monkeypatch, provider, streams):
    calls, script = [], iter(streams)

    async def create(**kwargs):
        calls.append(deepcopy(kwargs))
        return next(script)
    monkeypatch.setattr(provider._client.responses, 'create', create)
    monkeypatch.setattr(provider, '_prepare', AsyncMock())
    return calls


def tool_then_answer():
    return [FakeStream([done(Item(type='function_call', id='fc_1', call_id='call_1', name='get_current_datetime',
                                  arguments='{"timezone":"UTC"}', status='completed'))]),
            FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Xong.'), done()])]


async def drain(stream):
    return [chunk async for chunk in stream]


async def companion_xai(monkeypatch):
    provider = XAIProvider()
    calls = responses_capture(monkeypatch, provider, tool_then_answer())
    await drain(service._stream_reply(PROFILE, [ChatMessage('user', 'Mấy giờ rồi?')], 'low', 'UTC', 'auto',
                                      provider=provider, spoken=True))
    return calls


async def side_calls(monkeypatch):
    """Lượt đặt tên/tóm tắt/ghi nhớ gọi thẳng provider.stream với tools_enabled=False, không có snapshot."""
    provider = XAIProvider()
    calls = responses_capture(monkeypatch, provider, [FakeStream([done()])])
    await drain(provider.stream(system_prompt='Đặt tên', messages=[ChatMessage('user', 'Chào')], effort='low',
                                web_search='off', tools_enabled=False))
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'khoa-gia')
    haiku = ClaudeProvider('claude-haiku-5-5', 'Haiku')
    sdk, raw, _ = sdk_with_responses(message_events([TEXT]))
    haiku._client.sdk = sdk
    async with sdk:
        await drain(haiku.stream(system_prompt=PROFILE, messages=[ChatMessage('user', 'Tóm tắt')], effort='low',
                                 web_search='off', tools_enabled=False))
    return calls + raw


async def agent_haiku(monkeypatch):
    from features.agent import api as agent_api
    sdk, raw, _ = sdk_with_responses(message_events([THINKING, CLOCK_TOOL], 'tool_use'), message_events([TEXT]))
    monkeypatch.setattr(agent, 'AI_PROVIDER', 'xai')
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'khoa-gia')
    monkeypatch.setattr(agent, '_claude_client', claude.ClaudeClient(sdk, cache_history='always'))
    instructions = agent_api._instructions({'project': 'Dự án', 'os': 'Windows'}, False, 'haiku') + '\n\n' + PROFILE
    schema = {'type': 'function', 'name': 'get_current_datetime', 'description': 'Đồng hồ',
              'parameters': {'type': 'object', 'properties': {}}}
    user = {'type': 'message', 'role': 'user', 'content': 'Mấy giờ?'}
    async with sdk:
        first = await drain(agent.agent_step(instructions=instructions, input_items=[user], tools=[schema],
                                             effort='low', model='haiku'))
        output = list(first[-1].output)
        items = [user, *output, {'type': 'function_call_output', 'call_id': 'toolu_clock', 'output': '{"ok":true}'}]
        await drain(agent.agent_step(instructions=instructions, input_items=items, tools=[schema], effort='low',
                                     model='haiku'))
    return raw


async def byok_turns(monkeypatch):
    monkeypatch.setattr(byok.config, 'AI_PROVIDER', 'xai')
    keyed = byok.build(byok.choose('xai', 'grok-4.7', None, 'xai-khoa-gia-1234567890', None))
    calls = responses_capture(monkeypatch, keyed, tool_then_answer())
    await drain(service._stream_reply(PROFILE, [ChatMessage('user', 'Mấy giờ rồi?')], 'low', 'UTC', 'auto',
                                      provider=keyed, spoken=True))
    claude_keyed = byok.build(byok.choose('anthropic', 'claude-haiku-5-5', None, 'sk-ant-khoa-gia-1234567890', None))
    sdk, raw, _ = sdk_with_responses(message_events([THINKING, CLOCK_TOOL], 'tool_use'), message_events([TEXT]))
    # Dùng HTTP giả của test_claude (khóa giả khoa-gia), giữ nguyên cấu hình adaptive của provider.
    claude_keyed._client.sdk = sdk
    async with sdk:
        await drain(service._stream_reply(PROFILE, [ChatMessage('user', 'Mấy giờ rồi?')], 'low', 'UTC', 'auto',
                                          provider=claude_keyed, spoken=True))
    return calls + raw


SCENARIOS = {'companion_xai': companion_xai, 'side_calls': side_calls, 'agent_haiku': agent_haiku,
             'byok': byok_turns}


@pytest.mark.parametrize('name', list(SCENARIOS))
async def test_non_chat_requests_are_byte_identical_to_before_g11(monkeypatch, fixed_clock, name):
    captured = json.loads(json.dumps(await SCENARIOS[name](monkeypatch), ensure_ascii=False, sort_keys=True))
    stored = json.loads(FIXTURE.read_text(encoding='utf-8')) if FIXTURE.exists() else {}
    if os.environ.get('PETO_RECORD_UNCHANGED') == '1':
        stored[name] = captured
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(json.dumps(stored, ensure_ascii=False, sort_keys=True, indent=1) + '\n', encoding='utf-8')
        return
    assert captured == stored[name]
    # Không lượt nào ngoài tab Trò chuyện nhận khối runtime hay câu nói về nó.
    assert '<peto_runtime>' not in json.dumps(captured, ensure_ascii=False)
