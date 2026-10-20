"""Request budgeting and Sol migration use fake accounts/providers only."""
import copy
from types import SimpleNamespace

import pytest

from ai import agent, models
from ai.base import ProviderError
from core import config
from features.agent import api, budget
from test_agent_api import connect, bearer, events_of
from test_models import FakeStream, completed


def test_catalog_limits_are_per_actual_model_and_deployment_cap(monkeypatch):
    monkeypatch.setattr(config, 'AGENT_MODEL', 'grok-4.7')
    assert budget.limits('peto')['context'] == 500000
    assert budget.limits('sol')['context'] == 1050000
    assert budget.limits('sol')['identity'] == 'openai/gpt-6.1-sol'
    assert budget.limits('sol')['output'] == config.OPENAI_MAX_OUTPUT_TOKENS
    assert budget.limits('haiku')['output'] == config.ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS
    monkeypatch.setattr(config, 'AGENT_MODEL', 'my-custom-model')
    assert budget.limits('peto')['known'] is False
    monkeypatch.setenv('PETO_AGENT_CONTEXT_LIMITS', '{"my-custom-model":{"context":64000,"output":4096}}')
    assert budget.limits('peto')['context'] == 64000 and budget.limits('peto')['output'] == 4096


async def test_budget_preflight_refunds_without_calling_provider_and_old_client_still_works(client, anon_client, monkeypatch):
    token = await connect(anon_client, client)
    before = (await anon_client.get('/api/agent/me', headers=bearer(token))).json()['steps_used']
    calls = []
    async def fake(**kwargs):
        calls.append(kwargs)
        yield agent.AgentEvent('done', output=({'type':'message','role':'assistant','content':'done'},))
    monkeypatch.setattr(api, 'agent_step', fake)
    monkeypatch.setattr(api, '_instructions', lambda *args, **kwargs: 'system')
    monkeypatch.setenv('PETO_AGENT_CONTEXT_LIMITS', '{"grok-4.7":{"context":32768,"output":8192}}')
    monkeypatch.setattr(config, 'AGENT_MODEL', 'grok-4.7')
    task = {'input':[{'type':'message','role':'user','content':'x' * 100000}],
            'context':{'features':['context_budget']}}
    events = events_of(await anon_client.post('/api/agent/step', headers=bearer(token), json=task))
    assert events[-1]['code'] == 'context_overflow' and not calls
    me = (await anon_client.get('/api/agent/me', headers=bearer(token))).json()
    assert me['steps_used'] == before
    task['context'] = {}
    events = events_of(await anon_client.post('/api/agent/step', headers=bearer(token), json=task))
    assert events[-1]['type'] == 'done' and len(calls) == 1
    assert 'max_output_tokens' not in calls[0] and 'context_budget' not in events[0]


async def test_budget_metadata_counts_real_instruction_tools_and_fits_output(client, anon_client, monkeypatch):
    token = await connect(anon_client, client)
    calls = []
    async def fake(**kwargs):
        calls.append(kwargs)
        yield agent.AgentEvent('done', output=())
    monkeypatch.setattr(api, 'agent_step', fake)
    events = events_of(await anon_client.post('/api/agent/step', headers=bearer(token), json={
        'input':[{'type':'message','role':'user','content':'hi'}], 'context':{'features':['context_budget']}}))
    data = events[0]['context_budget']
    assert data['overhead_tokens'] > budget.estimate(calls[0]['instructions'])
    assert data['request_tokens'] + calls[0]['max_output_tokens'] <= data['context']


async def test_sol_routes_new_api_id_with_supported_efforts_and_no_key_leak(client, anon_client, monkeypatch):
    token = await connect(anon_client, client)
    from conftest import TEST_OWNER
    monkeypatch.setattr(config, 'OWNER_ACCOUNTS', frozenset({TEST_OWNER}))
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return FakeStream(completed('done'))
    monkeypatch.setattr(agent, 'AI_PROVIDER', 'xai')
    monkeypatch.setattr(agent, 'OPENAI_API_KEY', 'fake-test-key')
    monkeypatch.setattr(agent, '_openai_client', SimpleNamespace(responses=SimpleNamespace(create=create)))
    me = (await anon_client.get('/api/agent/me', headers=bearer(token))).json()
    sol = next(row for row in me['models'] if row['key'] == 'sol')
    assert sol['label'] == '6.1 Sol' and sol['step_cost'] == 4 and 'none' not in sol['efforts']
    assert 'fake-test-key' not in str(me)
    body = {'model':'sol', 'effort':'none', 'input':[{'type':'message','role':'user','content':'hi'}]}
    assert (await anon_client.post('/api/agent/step',headers=bearer(token),json=body)).status_code == 400
    body['effort'] = 'low'
    assert events_of(await anon_client.post('/api/agent/step',headers=bearer(token),json=body))[-1]['type'] == 'done'
    assert calls[0]['model'] == 'gpt-6.1-sol' and calls[0]['reasoning']['effort'] == 'low'
    result = [event async for event in agent.agent_step(instructions='system', input_items=body['input'], tools=[],
                                                       model='sol', effort='low', max_output_tokens=2048)]
    assert result[-1].kind == 'done' and calls[-1]['max_output_tokens'] == 2048


async def test_provider_overflow_is_classified_before_web_fallback(monkeypatch):
    import openai
    import httpx2
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        raise openai.BadRequestError('maximum context length exceeded',
            response=httpx2.Response(400, request=httpx2.Request('POST','https://fake.test/responses')),
            body={'error':{'code':'context_length_exceeded','message':'maximum context length exceeded'}})
    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    with pytest.raises(ProviderError) as failure:
        async for _ in agent._responses_step(fake, 'OpenAI','gpt-6.1-sol',8192,'system',[],[],'low',
                                             auth_message='auth',rate_message='rate',web_search=True):
            pass
    assert failure.value.code == 'context_overflow' and len(calls) == 1


async def test_partial_output_overflow_is_neither_refunded_nor_marked_safe_to_retry(client, anon_client, monkeypatch):
    token = await connect(anon_client, client)
    before = (await anon_client.get('/api/agent/me', headers=bearer(token))).json()['steps_used']
    async def fake(**kwargs):
        yield agent.AgentEvent('delta', 'partial')
        raise ProviderError('failed after output', code='context_overflow')
    monkeypatch.setattr(api, 'agent_step', fake)
    events = events_of(await anon_client.post('/api/agent/step', headers=bearer(token), json={
        'input':[{'type':'message','role':'user','content':'hi'}], 'context':{'features':['context_budget']}}))
    assert events[-1]['type'] == 'error' and 'code' not in events[-1] and 'retryable' not in events[-1]
    assert (await anon_client.get('/api/agent/me', headers=bearer(token))).json()['steps_used'] == before + 1


def test_cli_and_backend_estimates_match_on_unicode_media_and_opaque_reasoning():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('cli_budget', Path(__file__).resolve().parents[2] / 'agent-cli/peto_agent/budget.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    data = [{'type':'message','role':'user','content':[{'type':'input_text','text':'Nhạc mới 日本語'},
            {'type':'input_image','image_url':'data:image/png;base64,'+'x'*100000}]},
            {'type':'reasoning','encrypted_content':'x'*200000}]
    assert cli.estimate(data) == budget.estimate(data) < 2000
    for window, expected in [(128000,112000),(200000,180000),(1050000,945000)]:
        info = {'context':window,'input':window,'output':16000}
        assert cli.ceiling(info) == budget.ceiling(info) == expected
