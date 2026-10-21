"""Thí điểm Peto/xAI chạy mã tính toán (21/10/2026): công cụ của xAI chỉ ở tab Trò chuyện, nhật ký có bước "Đã chạy
mã" kèm mã và chữ in ra. Stream giả dựng theo đúng tên sự kiện và dạng item của lần chạy thật trên VPS; không gọi API."""
import json
from types import SimpleNamespace

from ai import ChatMessage
from ai.base import StreamChunk
from ai.claude import ClaudeProvider
from ai.gpt import GPTProvider
from ai.xai import XAIProvider, code_result
from core import config, usage_events
from features.admin import chat_metrics
from features.chat import capabilities, request_context
from features.chat.work_log import MAX_CODE_CHARS, MAX_TOTAL_CODE, WorkLog
from prompts.chat import CODE_PROMPT
from conftest import read_events
from test_admin import recorder, stored_rows  # noqa: F401  (fixture)
from test_chat_request_context import cap, snapshot
from test_clock_tools import FakeStream, Item, done, fake_provider

# Nguyên dạng outputs của lần chạy thật: "logs" là một chuỗi JSON lồng bên trong.
LOGS = json.dumps({'stdout': '161.0 21.19\n', 'stderr': '', 'exit_code': 0, 'command_timed_out': False})
CODE = "import pandas as pd\nprint(round(mean, 2), round(std, 2))"


def code_item(status='completed', logs=LOGS, item_id='ci_1'):
    return Item(type='code_interpreter_call', id=item_id, status=status, code=CODE,
                outputs=[{'type': 'logs', 'logs': logs}])


def code_stream(lead_in='', item=None):
    """Thứ tự sự kiện như lần chạy thật: câu dẫn (nếu có), chạy mã, item xong, chữ trả lời, response.completed."""
    item = item or code_item()
    message = Item(type='message', role='assistant', status='completed',
                   content=[{'type': 'output_text', 'text': '161.00 và 21.19'}])
    events = [SimpleNamespace(type='response.output_text.delta', delta=lead_in)] if lead_in else []
    events += [SimpleNamespace(type='response.output_item.added', item=SimpleNamespace(type='code_interpreter_call')),
               SimpleNamespace(type='response.code_interpreter_call.in_progress'),
               SimpleNamespace(type='response.code_interpreter_call_code.delta', delta=CODE),
               SimpleNamespace(type='response.code_interpreter_call.interpreting'),
               SimpleNamespace(type='response.code_interpreter_call.completed'),
               SimpleNamespace(type='response.output_item.done', item=item),
               SimpleNamespace(type='response.output_text.delta', delta='161.00 và 21.19'),
               done(item, message)]
    return FakeStream(events)


def plan(**changes):
    base = dict(documents=None, files=None, history=None, github_state='unauthorized', github_reason='not_connected',
                search_enabled=True, web_search='auto', tools_enabled=True, finalizing=False, required_search=False)
    return capabilities.select(**{**base, **changes})


def state(tool_plan, name='run_code'):
    item = next(item for item in tool_plan.capabilities if item.name == name)
    return item.state, item.reason


def test_run_code_capability_follows_provider_switch_and_round():
    assert capabilities.CODE_SCHEMA in plan(code_reason=None).schemas
    assert state(plan(code_reason=None)) == ('available', 'request_scope')
    assert state(plan()) == ('unavailable', 'provider_unsupported') and capabilities.CODE_SCHEMA not in plan().schemas
    assert state(plan(code_reason='server_disabled')) == ('disabled', 'server_disabled')
    assert state(plan(code_reason=None, finalizing=True)) == ('disabled', 'finalizing')
    assert state(plan(code_reason=None, required_search=True)) == ('disabled', 'required_web_first')
    # Chỉ xAI đã được thử thật; Luna và Haiku không tự nhận công cụ này.
    assert XAIProvider.code_interpreter and not GPTProvider.code_interpreter and not ClaudeProvider.code_interpreter


def test_code_result_reads_nested_logs_and_other_output_shapes():
    assert code_result(code_item().__dict__) == {'code': CODE, 'stdout': '161.0 21.19\n', 'stderr': '', 'exit_code': 0,
                                                 'timed_out': False, 'status': 'completed', 'images': 0}
    raw = code_result({'code': 'print(1)', 'status': 'completed', 'outputs': [{'type': 'logs', 'logs': '1\n'},
                                                                             {'type': 'image', 'url': 'x'}]})
    assert raw['stdout'] == '1\n' and raw['images'] == 1 and raw['exit_code'] is None
    late = code_result({'outputs': [{'type': 'logs', 'logs': json.dumps({'stdout': '', 'stderr': 'Killed',
                                                                        'exit_code': 137, 'command_timed_out': True})}]})
    assert late['timed_out'] is True and late['exit_code'] == 137 and late['stderr'] == 'Killed'


async def test_chat_round_sends_the_tool_and_reports_one_step_per_run(client, monkeypatch):
    provider, requests = fake_provider(monkeypatch, [code_stream(lead_in='Mình tính bằng Python.')])
    token = request_context.current.set(snapshot())
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tính')])]
    finally:
        request_context.current.reset(token)
    request = requests[0]
    assert {'type': 'code_interpreter'} in request['tools'] and CODE_PROMPT in request['instructions']
    assert cap(request, 'run_code')['state'] == 'available' and cap(request, 'run_code')['tools'] == ['code_interpreter']
    code = [chunk for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == 'code']
    # Item về hai lần (output_item.done và response.completed) nhưng chỉ một bước "xong".
    assert [chunk.text for chunk in code if chunk.text == 'done'] == ['done']
    assert code[-1].info['stdout'] == '161.0 21.19\n' and code[-1].info['code'] == CODE
    # Câu dẫn trước lúc chạy mã thành bản nháp (replace), không dính vào câu trả lời sau đó.
    kinds = [chunk.kind if isinstance(chunk, StreamChunk) else 'text' for chunk in chunks]
    assert kinds.index('replace') < kinds.index('code')
    assert ''.join(chunk for chunk in chunks if isinstance(chunk, str)).endswith('161.00 và 21.19')


async def test_no_code_tool_outside_chat_when_disabled_or_for_other_providers(client, monkeypatch):
    # Không có snapshot: Companion hoặc lượt phụ.
    provider, requests = fake_provider(monkeypatch, [code_stream()])
    _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tính')])]
    assert {'type': 'code_interpreter'} not in requests[0]['tools'] and CODE_PROMPT not in requests[0]['instructions']
    # Công tắc máy chủ tắt: không gửi công cụ, manifest nói rõ lý do.
    monkeypatch.setattr(config, 'XAI_CODE_EXECUTION', False)
    provider, requests = fake_provider(monkeypatch, [code_stream()])
    token = request_context.current.set(snapshot())
    try:
        _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tính')])]
    finally:
        request_context.current.reset(token)
    assert {'type': 'code_interpreter'} not in requests[0]['tools']
    assert cap(requests[0], 'run_code') == {'name': 'run_code', 'state': 'disabled', 'reason': 'server_disabled',
                                            'tools': ['code_interpreter']}
    # Dịch vụ chưa được thử thật (Luna, Haiku): không có công cụ.
    monkeypatch.setattr(config, 'XAI_CODE_EXECUTION', True)
    provider, requests = fake_provider(monkeypatch, [code_stream()])
    provider.code_interpreter = False
    token = request_context.current.set(snapshot())
    try:
        _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tính')])]
    finally:
        request_context.current.reset(token)
    assert cap(requests[0], 'run_code')['state'] == 'unavailable'
    assert cap(requests[0], 'run_code')['reason'] == 'provider_unsupported'


def test_work_log_keeps_code_and_output_and_marks_failures():
    log = WorkLog(started=0, clock=lambda: 1.0)
    assert log.code('running') and log.steps[-1].kind == 'code' and log.steps[-1].label == 'Đang chạy mã…'
    assert log.code('running') == '' and len(log.steps) == 1
    log.code('done', code_result(code_item().__dict__))
    step = log.steps[-1].public()
    assert step['label'] == 'Đã chạy mã' and step['state'] == 'done' and step['detail'] == 'Python · 2 dòng'
    assert step['code'] == CODE and step['output'] == '161.0 21.19'
    failed = json.dumps({'stdout': '', 'stderr': 'ZeroDivisionError: division by zero', 'exit_code': 1,
                         'command_timed_out': False})
    log.code('done', code_result(code_item(logs=failed, item_id='ci_2').__dict__))
    step = log.steps[-1].public()
    assert step['state'] == 'failed' and step['label'] == 'Mã chạy lỗi' and 'mã thoát 1' in step['detail']
    assert step['output'] == '[stderr]\nZeroDivisionError: division by zero'
    late = json.dumps({'stdout': '', 'stderr': '', 'exit_code': 137, 'command_timed_out': True})
    log.code('done', code_result(code_item(logs=late).__dict__))
    assert log.steps[-1].label == 'Mã chạy quá thời gian'


def test_work_log_bounds_code_per_step_and_per_turn():
    log = WorkLog(started=0, clock=lambda: 1.0)
    big = {'code': 'x = 1\n' * 2000, 'stdout': 'y\n' * 4000, 'status': 'completed', 'exit_code': 0}
    for _ in range(6):
        log.code('done', big)
    steps = [step.public() for step in log.steps]
    assert all(len(step.get('code', '')) <= MAX_CODE_CHARS for step in steps)
    assert sum(len(step.get('code', '')) + len(step.get('output', '')) for step in steps) <= MAX_TOTAL_CODE
    assert steps[0]['code'].startswith('x = 1\nx = 1\n')
    # Bước chạy dở khi lượt xong vẫn đóng như các bước khác.
    log.code('running')
    assert log.close(True)['steps'][-1]['label'] == 'Đã chạy mã'


async def test_chat_turn_persists_the_code_step_and_records_runs(client, recorder):  # noqa: F811
    events = await read_events(await client.post('/api/chat', json={'message': 'Tính trung bình __chayma__'}))
    assert events[-1]['type'] == 'done', events
    work = next(event['work'] for event in events if event['type'] == 'work')
    step = next(step for step in work['steps'] if step['kind'] == 'code')
    assert step['label'] == 'Đã chạy mã' and step['output'] == '135.0' and 'statistics.mean' in step['code']
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    failed = await read_events(await client.post('/api/chat', json={'message': '__chayma__:loi',
                                                                    'conversation_id': conversation}))
    assert failed[-1]['type'] == 'done'
    history = (await client.get(f'/api/conversations/{conversation}/messages')).json()['messages']
    steps = [step for message in history if message.get('work') for step in message['work']['steps'] if step['kind'] == 'code']
    assert [step['state'] for step in steps] == ['done', 'failed']
    await usage_events.flush()
    rows = [row for row in await stored_rows() if row['purpose'] == 'code']
    assert [row['outcome'] for row in rows] == ['ok', 'error']
    assert chat_metrics.summarize(rows, lambda values, q: None)['tools'] == {
        'results': 0, 'errors': 0, 'web_errors': 0, 'code_runs': 2, 'code_errors': 1}
