"""Benchmark với fixture và HTTP giả; không dùng khóa, mạng hoặc billing thật."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai.base import ChatMessage, ProviderError, StreamChunk
from evals import adapter, runner, report
from evals.__main__ import main
from evals.schema import Case, EvalError, Settings, load_cases

DATASET = Path(__file__).resolve().parents[1] / 'evals' / 'cases.json'
CLOCK = datetime(2026, 10, 9, tzinfo=UTC)


def turn(user='chào', **kwargs):
    return {'user': user, 'expectation': 'Trả lời đúng việc.', 'rubric': ['accuracy'], 'checks': [], **kwargs}


def case(key='fake-one', persona='chat', turns=None, context=None):
    return Case(key, 'Bài giả', persona, 'memory', turns or [turn()], context or {})


def write_json(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    return path


class Script:
    def __init__(self, replies):
        self.replies, self.seen, self.closed = iter(replies), [], 0

    async def stream(self, **kwargs):
        self.seen.append(deepcopy(kwargs))
        try:
            for piece in next(self.replies):
                if isinstance(piece, Exception):
                    raise piece
                if isinstance(piece, float):
                    await asyncio.sleep(piece)
                else:
                    yield piece
        finally:
            self.closed += 1


def scripted(provider):
    return lambda *args: (provider, adapter.Capture('fake'))


@pytest.fixture
def short_prompts(monkeypatch):
    async def prepare(cases, models, clock):
        return {(model, item.id, index): {'text': 'Chỉ dẫn giả', 'sha256': 'fake-sha'}
                for model in models for item in cases for index in range(len(item.turns))}
    monkeypatch.setattr(runner, 'prepare_prompts', prepare)


def test_curated_dataset_and_registry_budgets():
    cases = load_cases(DATASET)
    assert len(cases) == 30 and sum(len(item.turns) for item in cases) == 37
    assert {item.persona for item in cases} == {'chat', 'companion', 'roleplay'}
    assert Settings().validate(cases) == 37
    assert Settings(models=('peto', 'luna', 'haiku'), max_calls=150).validate(cases) == 111
    for settings in (Settings(mode='live'), Settings(models=('sonnet',)), Settings(models=('peto',), effort='max'),
                     Settings(max_calls=36), Settings(max_output_tokens=1025), Settings(timeout=True)):
        with pytest.raises(EvalError):
            settings.validate(cases)


@pytest.mark.parametrize('mutation', ['path', 'duplicate', 'rubric', 'regex', 'critical'])
def test_rejects_invalid_or_file_backed_fixtures(tmp_path, mutation):
    raw = json.loads(DATASET.read_text(encoding='utf-8'))
    first = raw['cases'][0]['turns'][0]
    if mutation == 'path':
        first['attachments'] = [{'name': 'secret.txt', 'path': '.env'}]
    elif mutation == 'duplicate':
        raw['cases'][1]['id'] = raw['cases'][0]['id']
    elif mutation == 'rubric':
        first['rubric'] = [{}]
    else:
        first['checks'] = [{'kind': 'match', 'label': 'Kiểm tra', 'value': '(' if mutation == 'regex' else 'x',
                            'critical': 1 if mutation == 'critical' else False}]
    with pytest.raises(EvalError):
        load_cases(write_json(tmp_path / 'bad.json', raw))


def test_paid_flag_blocks_before_configuration(monkeypatch, capsys):
    import evals.__main__ as cli
    def forbidden(*args):
        pytest.fail('Không được import cấu hình hoặc gọi API.')
    monkeypatch.setattr(cli, 'configure', forbidden)
    monkeypatch.setattr(cli, 'execute', forbidden)
    assert main(['run', '--mode', 'live']) == 2
    assert 'Chưa gọi API' in capsys.readouterr().err


def test_missing_keys_fail_before_provider(tmp_path, monkeypatch):
    from core import config
    monkeypatch.setattr(config, 'OPENAI_API_KEY', '')
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', '')
    for models in (('luna',), ('haiku',)):
        with pytest.raises(EvalError, match='chưa gọi API'):
            adapter.ensure_credentials(models)


def test_mock_configuration_ignores_dotenv_and_credentials(tmp_path, monkeypatch):
    from evals.__main__ import configure
    import logging
    import os
    for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'XAI_API_KEY'):
        monkeypatch.setenv(name, 'khoa-gia-can-xoa')
    for name in ('PYTHON_DOTENV_DISABLED', 'PETO_AI_PROVIDER', 'PETO_WEB_DB', 'PETO_XAI_TOKEN_PATH',
                 'PETO_UPLOAD_DIR', 'PETO_MEMORY_GATEWAY_URL', 'PETO_MEMORY_GATEWAY_TOKEN'):
        monkeypatch.setenv(name, os.getenv(name, ''))
    previous = logging.root.manager.disable
    try:
        configure('mock', str(tmp_path))
        assert os.environ['PYTHON_DOTENV_DISABLED'] == '1'
        assert not any(os.getenv(name) for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'XAI_API_KEY'))
        assert os.environ['PETO_WEB_DB'] == str(tmp_path / 'unused.db')
    finally:
        logging.disable(previous)


async def test_actual_prompts_use_fake_context_without_database_or_gateway(monkeypatch):
    from features.chat import prompt_context
    from prompts import COMPANION_SYSTEM_PROMPT, ROLEPLAY_SYSTEM_PROMPT, SYSTEM_PROMPT, english
    originals = [prompt_context.db.get_user, prompt_context.db.get_profile,
                 prompt_context.discord_memory.fetch, prompt_context.companion_memory.memory_block]
    monkeypatch.setattr(prompt_context.db, 'init_db', AsyncMock(side_effect=AssertionError('Không mở DB')))
    items = [case(turns=[turn('Đầu tiên'), turn('từ-bí-mật-tương-lai')], context={
        'profile': {'nickname': 'TênGiả'}, 'memory': ['Tôi thích trà hoa nhài.']}),
        case('fake-companion', 'companion', context={'summary': 'Dự án ĐènGiấy'}),
        case('fake-roleplay', 'roleplay')]
    prompts = await adapter.prepare_prompts(items, ('peto', 'luna', 'haiku'), CLOCK)
    assert prompts['peto', 'fake-one', 0]['text'].startswith(SYSTEM_PROMPT)
    for model in ('luna', 'haiku'):
        assert prompts[model, 'fake-one', 0]['text'].startswith(english.CORE_PROMPT)
        assert 'TênGiả' in prompts[model, 'fake-one', 0]['text']
        assert 'trà hoa nhài' in prompts[model, 'fake-one', 0]['text']
    assert prompts['luna', 'fake-companion', 0]['text'].startswith(COMPANION_SYSTEM_PROMPT)
    assert 'ĐènGiấy' in prompts['luna', 'fake-companion', 0]['text']
    assert prompts['haiku', 'fake-roleplay', 0]['text'].startswith(ROLEPLAY_SYSTEM_PROMPT)
    assert 'từ-bí-mật-tương-lai' not in prompts['peto', 'fake-one', 0]['text']
    assert '2026-10-09' in prompts['luna', 'fake-one', 0]['text']
    assert originals == [prompt_context.db.get_user, prompt_context.db.get_profile,
                         prompt_context.discord_memory.fetch, prompt_context.companion_memory.memory_block]
    assert await adapter.prepare_prompts(items, ('peto', 'luna', 'haiku'), CLOCK) == prompts
    prompt_context.db.init_db.assert_not_awaited()


def test_synthetic_documents_keep_actual_attachment_status():
    ready = adapter.user_message(turn(attachments=[{'name': 'review.py', 'text': 'x = 42'}]))
    assert ready.attachments[0].name == 'review.py'
    assert 'x = 42' in ready.attachments[0].text_excerpt
    missing = adapter.user_message(turn(attachments=[{'name': 'review.py', 'status': 'missing'}]))
    assert 'Tệp chưa được đọc' in missing.attachments[0].text_excerpt


async def test_multiturn_preserves_private_raw_but_only_times_visible_text(tmp_path, short_prompts):
    provider = Script([[StreamChunk('thinking', 'không đưa vào lời'), '<|EMO', 'TE_HAPPY|><pri',
                        'vate>Chosen=7</private>', 0.02, 'I chose a number.'],
                       ['<|EMOTE_HAPPY|>Yes, seven!']])
    result = await runner.run([case(persona='companion', turns=[turn(), turn('Số 7 đúng không?')])],
                              Settings(), DATASET, tmp_path / 'out', factory=scripted(provider), clock=CLOCK)
    rows = result['samples'][0]['turns']
    assert rows[0]['visible_response'] == 'I chose a number.'
    assert 'Chosen=7' in rows[0]['raw_response'] and 'không đưa' not in rows[0]['raw_response']
    assert rows[0]['first_visible_ms'] > rows[0]['first_text_ms'] + 10
    assert [message.role for message in provider.seen[1]['messages']] == ['user', 'assistant', 'user']
    assert 'Chosen=7' in provider.seen[1]['messages'][1].content
    assert all(not entry['tools_enabled'] and entry['web_search'] == 'off' for entry in provider.seen)
    assert result['request_count'] == 2 and provider.closed == 2
    review = report.review_template(result)
    second = next(row for row in review['samples'] if row['user'] == 'Số 7 đúng không?')
    assert second['reference_private_notes'] == [{'turn': 1, 'notes': ['Chosen=7']}]
    assert all('model' not in row for row in review['samples'])


async def test_concurrent_cases_have_independent_histories(tmp_path, short_prompts):
    providers = []
    def factory(*args):
        provider = Script([[0.01, 'Đã nhận.'], ['Tiếp tục.']])
        providers.append(provider)
        return provider, adapter.Capture('fake')
    items = [case('one', turns=[turn('riêng-một'), turn('tiếp-một')]),
             case('two', turns=[turn('riêng-hai'), turn('tiếp-hai')])]
    result = await runner.run(items, Settings(concurrency=2), DATASET, tmp_path / 'out', factory=factory)
    assert len(result['samples']) == 2 and result['request_count'] == 4
    for provider in providers:
        history = provider.seen[1]['messages']
        assert len(history) == 3
        assert ('một' in history[0].content) == ('một' in history[-1].content)


@pytest.mark.parametrize('reply,expected', [([0.2, 'Quá muộn'], 'timeout'),
    ([ProviderError('Không in khoa-gia-bi-mat')], 'provider_error'), (['x' * 33_000], 'output_limit'), ([], 'empty')])
async def test_failed_turn_stops_dependencies_without_retry(tmp_path, short_prompts, reply, expected):
    provider = Script([reply, ['Không được gọi']])
    result = await runner.run([case(turns=[turn(), turn('tiếp')])], Settings(timeout=0.04), DATASET,
                              tmp_path / 'out', factory=scripted(provider))
    assert [row['status'] for row in result['samples'][0]['turns']] == [expected, 'skipped_dependency']
    assert len(provider.seen) == 1 and provider.closed == 1
    assert 'khoa-gia-bi-mat' not in (tmp_path / 'out' / 'results.json').read_text(encoding='utf-8')


async def test_large_followup_is_blocked_before_next_request(tmp_path, short_prompts):
    provider = Script([['a' * 1600], ['không được gọi']])
    result = await runner.run([case(turns=[turn(), turn('tiếp')])], Settings(max_input_chars=1500),
                              DATASET, tmp_path / 'out', factory=scripted(provider))
    assert [row['status'] for row in result['samples'][0]['turns']] == ['complete', 'budget_exceeded']
    assert len(provider.seen) == 1 and result['request_count'] == 1


async def test_setup_failure_keeps_safe_report(tmp_path, short_prompts):
    def factory(*args):
        raise RuntimeError('Không in secret-key-in-body')
    result = await runner.run([case()], Settings(), DATASET, tmp_path / 'out', factory=factory)
    assert result['samples'][0]['setup_failed']
    assert result['samples'][0]['turns'][0]['status'] == 'provider_error'
    assert result['request_count'] == 0 and 'secret-key-in-body' not in json.dumps(result)


async def test_cancel_preserves_finished_turns(tmp_path, short_prompts):
    provider = Script([['Lượt đã xong.'], [20.0, 'chưa xong']])
    task = asyncio.create_task(runner.run([case(turns=[turn(), turn('tiếp')])], Settings(), DATASET,
                                         tmp_path / 'out', factory=scripted(provider)))
    for _ in range(100):
        if len(provider.seen) == 2:
            break
        await asyncio.sleep(0.005)
    assert len(provider.seen) == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = json.loads((tmp_path / 'out' / 'results.json').read_text(encoding='utf-8'))
    assert not saved['finished'] and saved['samples'][0]['turns'][0]['visible_response'] == 'Lượt đã xong.'
    assert provider.closed == 2


def test_physical_request_budget_checks_input_output_and_limit():
    budget = adapter.CallBudget(Settings(max_calls=1, max_input_chars=1000))
    for request in ({'input': 'x' * 1001}, {'max_output_tokens': 1025}):
        with pytest.raises(adapter.BudgetExceeded):
            budget.claim(request)
    assert budget.used == 0
    budget.claim({'max_output_tokens': 128})
    with pytest.raises(adapter.BudgetExceeded):
        budget.claim({})
    assert budget.used == 1


async def test_openai_provider_captures_native_usage_and_disables_tools(monkeypatch):
    from ai import gpt
    from test_clock_tools import FakeStream
    usage = {'input_tokens': 100, 'output_tokens': 40, 'input_tokens_details': {'cached_tokens': 25},
             'output_tokens_details': {'reasoning_tokens': 10}}
    stream = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã hiểu.'),
        SimpleNamespace(type='response.completed', response=SimpleNamespace(model='gpt-6-luna-snapshot',
            usage=usage, output=[], status='completed'))])
    create = AsyncMock(return_value=stream)
    sdk = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock(), max_retries=2, timeout=600)
    monkeypatch.setattr(gpt, 'AsyncOpenAI', lambda **kwargs: sdk)
    monkeypatch.setattr(gpt, 'OPENAI_API_KEY', 'khoa-gia')
    settings = Settings(mode='live', models=('luna',), max_output_tokens=512, allow_paid=True)
    budget = adapter.CallBudget(settings)
    provider, capture = adapter.make_provider('luna', settings, budget)
    chunks = [chunk async for chunk in provider.stream(system_prompt='Chỉ dẫn', messages=[ChatMessage('user', 'chào')],
                                                      effort='low', web_search='off', tools_enabled=False)]
    assert 'Đã hiểu.' in chunks and stream.closed
    request = create.call_args.kwargs
    assert request['max_output_tokens'] == 512 and not request.get('tools')
    assert sdk.max_retries == 0 and sdk.timeout == settings.timeout
    assert budget.used == 1 and capture.records[0]['actual_model'] == 'gpt-6-luna-snapshot'
    assert capture.records[0]['usage']['uncached_input_tokens'] == 75
    await adapter.close_provider(provider)
    sdk.close.assert_awaited_once()


@pytest.mark.parametrize('max_calls,expected_calls', [(1, 1), (2, 2)])
async def test_claude_continuations_count_physical_requests(monkeypatch, max_calls, expected_calls):
    from ai import claude
    from core import config
    from test_claude import message_events, sdk_with_responses
    first = message_events([{'type': 'text', 'text': 'Đang nghĩ.'}], 'pause_turn', input_tokens=11, output_tokens=3)
    second = message_events([{'type': 'text', 'text': 'Xong.'}], input_tokens=12, output_tokens=4)
    for events in (first, second):
        events[0]['message']['usage'].update(cache_read_input_tokens=5, cache_creation_input_tokens=2)
    sdk, calls, closed = sdk_with_responses(first, second)
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'khoa-gia')
    monkeypatch.setattr(claude, 'AsyncAnthropic', lambda **kwargs: sdk)
    settings = Settings(mode='live', models=('haiku',), max_calls=max_calls, max_output_tokens=512, allow_paid=True)
    budget = adapter.CallBudget(settings)
    provider, capture = adapter.make_provider('haiku', settings, budget)
    kwargs = dict(system_prompt='Chỉ dẫn', messages=[ChatMessage('user', 'chào')], effort='low', web_search='off', tools_enabled=False)
    try:
        if max_calls == 1:
            with pytest.raises(adapter.BudgetExceeded):
                _ = [chunk async for chunk in provider.stream(**kwargs)]
        else:
            assert 'Xong.' in [chunk async for chunk in provider.stream(**kwargs)]
        assert budget.used == expected_calls == len(calls) == len(capture.records)
        assert capture.records[0]['usage']['input_tokens'] == 18
        assert capture.records[0]['usage']['output_tokens'] == 3
        assert all(call['max_tokens'] == 512 and not call.get('tools') for call in calls)
        assert closed and sdk.max_retries == 0
    finally:
        await adapter.close_provider(provider)


def test_usage_unknowns_and_cache_costs_are_not_zero():
    assert adapter.normalize_usage(None, 'openai') is None
    incomplete = adapter.normalize_usage({'input_tokens': 100, 'output_tokens': 5}, 'openai')
    assert incomplete['cache_read_tokens'] is None and incomplete['uncached_input_tokens'] is None
    rate = {'sample': {'input': 2, 'output': 10, 'cached_input': 0.2, 'cache_write': 3}}
    call = {'actual_model': 'sample', 'usage': incomplete}
    assert report.call_cost(call, rate) is None
    complete = adapter.normalize_usage({'input_tokens': 100, 'output_tokens': 5,
        'cache_read_input_tokens': 20, 'cache_creation_input_tokens': 10}, 'anthropic')
    assert complete['input_tokens'] == 130
    assert report.call_cost({'actual_model': 'sample', 'usage': complete}, rate) == pytest.approx(0.000284)
    assert report.call_cost({'actual_model': 'sample', 'usage': complete}, {'sample': {k:v for k,v in rate['sample'].items() if k != 'cache_write'}}) is None


async def test_blind_grading_unknown_metrics_and_preserved_review(tmp_path, short_prompts):
    result = await runner.run([case(context={'memory': ['Tôi thích trà.']})], Settings(), DATASET, tmp_path / 'out',
                              factory=scripted(Script([['Đã hiểu.']])))
    review = report.review_template(result)
    assert review['samples'][0]['context']['memory'] == ['Tôi thích trà.']
    assert 'model' not in review['samples'][0] and review['samples'][0]['scores'] == {'accuracy': None}
    review['samples'][0]['scores']['accuracy'] = 5
    path = write_json(tmp_path / 'out' / 'review.json', review)
    grades = report.load_ratings(result, path)
    summary = report.write_report(result, tmp_path / 'out', ratings=grades)
    row = summary['groups'][0]
    assert not row['quality'] and row['input_tokens'] is None and row['estimated_usd'] is None
    assert json.loads(path.read_text(encoding='utf-8')) == review
    live = deepcopy(result)
    live['mode'] = 'live'
    assert report.summarize(live, ratings=grades)['groups'][0]['quality']['accuracy'] == {'mean': 5, 'samples': 1}
    assert 'accuracy: 5' in report.compare([live], [report.summarize(live, ratings=grades)])
    review['samples'][0]['scores']['accuracy'] = True
    with pytest.raises(EvalError):
        report.load_ratings(result, write_json(path, review))
    review['run_id'] = 'khac-lan'
    with pytest.raises(EvalError):
        report.load_ratings(result, write_json(path, review))


def test_redacts_known_environment_key(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret-key-gia')
    assert 'secret-key-gia' not in json.dumps(runner.redact({'a': ['secret-key-gia']}))


async def test_usage_totals_and_error_rates_exclude_skipped_turns(tmp_path, short_prompts):
    result = await runner.run([case(turns=[turn(), turn('tiếp')])], Settings(timeout=0.03), DATASET,
                              tmp_path / 'out', factory=scripted(Script([[0.1, 'quá muộn']])))
    group = report.summarize(result)['groups'][0]
    assert group['attempted_turns'] == 1 and group['error_rate'] == group['timeout_rate'] == 1
    result['samples'][0]['turns'][0]['calls'] = [{'requested_model': 'sample', 'actual_model': 'sample',
        'usage': adapter.normalize_usage({'input_tokens': 100, 'output_tokens': 40,
            'input_tokens_details': {'cached_tokens': 25}}, 'openai')}]
    group = report.summarize(result)['groups'][0]
    assert group['input_tokens'] == 100 and group['output_tokens'] == 40
    assert group['cache_read_tokens'] == 25 and group['cache_write_tokens'] == 0
    assert group['reasoning_tokens'] is None and group['estimated_usd'] is None
