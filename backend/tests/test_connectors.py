"""Kết nối GitHub: quyền sở hữu, OAuth, mã hóa, công cụ chỉ đọc và vòng chat thật."""
import asyncio
import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import httpx
import pytest
import storage as db

from features.accounts import auth
from features.chat import service as chat_service
from features.connectors import github
from features.connectors.tools import GitHubSession, current_session, NAMES
from storage import connectors as store
from storage import connection
from core.config import SESSION_COOKIE
from ai.base import ChatMessage, StreamChunk
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider

TOKEN = 'ghu_test-secret-credential'


@pytest.fixture(autouse=True)
async def clean_connections():
    await db.init_db()
    async def clear():
        async with connection.connect() as database:
            await database.execute('DELETE FROM connector_accounts')
            await database.execute('DELETE FROM connector_oauth_states')
            await database.commit()
    await clear()
    yield
    await clear()


@pytest.fixture
def configured(monkeypatch):
    for name, value in {'CLIENT_ID': 'test-github-client', 'CLIENT_SECRET': 'test-github-secret',
                        'REDIRECT_URI': 'https://peto.test/api/connectors/github/callback', 'APP_SLUG': 'peto-test',
                        'ENCRYPTION_SECRET': 'test-key-not-real-' * 3, 'FRONTEND_URL': ''}.items():
        monkeypatch.setattr(github, name, value)


async def saved(owner=TEST_OWNER, **extra):
    data = {'access_token': TOKEN, 'refresh_token': '', 'expires_at': None, **extra}
    await store.save_github(owner, 'nguoi-test', github.encrypt(data), 'revision-1')


@pytest.fixture
def github_http(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        path = request.url.path
        if path == '/login/oauth/access_token':
            return httpx.Response(200, json={'access_token': TOKEN, 'refresh_token': 'refresh-test', 'expires_in': 28800, 'refresh_token_expires_in': 100000})
        if path == '/user':
            return httpx.Response(200, json={'login': 'nguoi-test', 'id': 17})
        if path == '/user/installations':
            return httpx.Response(200, json={'total_count': 1, 'installations': [{'id': 7, 'account': {'login': 'nguoi-test'}}]})
        if path == '/user/installations/7/repositories':
            return httpx.Response(200, json={'total_count': 1, 'repositories': [{'full_name': 'nguoi-test/Peto', 'private': True, 'default_branch': 'main'}]})
        if path == '/repos/nguoi-test/Peto/actions/runs':
            return httpx.Response(200, json={'total_count': 1, 'workflow_runs': [{'id': 12, 'name': 'Frontend', 'status': 'completed', 'conclusion': 'failure'}]})
        if path == '/repos/nguoi-test/Peto/actions/runs/12/jobs':
            return httpx.Response(200, json={'total_count': 1, 'jobs': [{'id': 34, 'name': 'frontend', 'status': 'completed', 'conclusion': 'failure', 'steps': [{'name': 'Test', 'conclusion': 'failure'}]}]})
        if path == '/repos/nguoi-test/Peto/actions/jobs/34':
            return httpx.Response(200, json={'run_id': 12})
        if path.endswith('/jobs/34/logs'):
            return httpx.Response(302, headers={'location': 'https://logs.blob.core.windows.net/job.txt?sig=private-signature'})
        if request.url.host == 'logs.blob.core.windows.net':
            return httpx.Response(200, text=f'##[error] Assertion failed\n{TOKEN}\nCuối log')
        if '/contents/' in path:
            return httpx.Response(200, json={'type': 'file', 'encoding': 'base64', 'size': 20,
                                           'content': base64.b64encode('Xin chào repo'.encode()).decode()})
        return httpx.Response(404, json={})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(github.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    return requests


async def test_requires_login_and_unconfigured_is_honest(anon_client, client):
    assert (await anon_client.get('/api/connectors')).status_code == 401
    assert (await anon_client.post('/api/connectors/github/connect')).status_code == 401
    assert (await anon_client.delete('/api/connectors/github')).status_code == 401
    info = (await client.get('/api/connectors')).json()['connectors'][0]
    assert not info['configured'] and info['status'] == 'not_connected'
    assert (await client.post('/api/connectors/github/connect')).status_code == 503


async def authorize(client):
    response = await client.post('/api/connectors/github/connect')
    assert response.status_code == 200
    params = parse_qs(urlsplit(response.json()['authorize_url']).query)
    assert params['code_challenge_method'] == ['S256'] and 'scope' not in params
    return params


async def test_oauth_state_pkce_encryption_and_no_token_to_frontend(client, configured, github_http):
    params = await authorize(client)
    state = params['state'][0]
    response = await client.get('/api/connectors/github/callback', params={'state': state, 'code': 'test-code'})
    assert response.status_code == 303 and 'connector_result=connected' in response.headers['location']
    token_request = next(request for request in github_http if request.url.path == '/login/oauth/access_token')
    fields = parse_qs(token_request.content.decode())
    expected = base64.urlsafe_b64encode(hashlib.sha256(fields['code_verifier'][0].encode()).digest()).decode().rstrip('=')
    assert expected == params['code_challenge'][0]
    account = await store.get_github(TEST_OWNER)
    assert TOKEN not in account['credentials'] and github.decrypt(account['credentials'])['access_token'] == TOKEN
    public = (await client.get('/api/connectors')).text
    assert TOKEN not in public and 'credentials' not in public and 'refresh_token' not in public and TEST_OWNER not in public
    assert (await client.get('/api/connectors/github/callback', params={'state': state, 'code': 'test-code'})).headers['location'].endswith('invalid')


async def test_state_is_bound_to_account_and_session(client, configured, github_http):
    params = await authorize(client)
    previous = client.cookies.get(SESSION_COOKIE)
    client.cookies.set(SESSION_COOKIE, auth._sign('guest:other'))
    query = {'state': params['state'][0], 'code': 'test-code'}
    assert (await client.get('/api/connectors/github/callback', params=query)).headers['location'].endswith('invalid')
    assert not github_http
    client.cookies.set(SESSION_COOKIE, previous)
    assert (await client.get('/api/connectors/github/callback', params=query)).headers['location'].endswith('connected')


async def test_expired_state_and_cancelled_callback(client, configured, github_http):
    params = await authorize(client)
    async with connection.connect() as db:
        await db.execute('UPDATE connector_oauth_states SET expires_at=0')
        await db.commit()
    assert (await client.get('/api/connectors/github/callback', params={'state': params['state'][0], 'code': 'x'})).headers['location'].endswith('invalid')
    params = await authorize(client)
    response = await client.get('/api/connectors/github/callback', params={'state': params['state'][0], 'error': 'access_denied'})
    assert response.headers['location'].endswith('cancelled') and not github_http


async def test_disconnection_is_isolated_and_cancels_pending_consent(client, configured, github_http):
    await saved()
    await saved('guest:other')
    params = await authorize(client)
    assert (await client.delete('/api/connectors/github')).status_code == 200
    assert await store.get_github(TEST_OWNER) is None
    assert await store.get_github('guest:other') is not None
    assert (await client.get('/api/connectors/github/callback', params={'state': params['state'][0], 'code': 'x'})).headers['location'].endswith('invalid')
    result = await GitHubSession(TEST_OWNER).run('github_actions', json.dumps({'repository': 'nguoi-test/Peto', 'action': 'runs'}))
    assert not result['ok'] and not github_http


async def test_expiring_tokens_refresh_once_under_concurrency(client, configured, github_http):
    await saved(expires_at=time.time() - 1, refresh_token='refresh-test', refresh_expires_at=time.time() + 1000)
    assert await asyncio.gather(github.access_token(TEST_OWNER), github.access_token(TEST_OWNER)) == [TOKEN, TOKEN]
    assert sum(request.url.path == '/login/oauth/access_token' for request in github_http) == 1
    assert github.decrypt((await store.get_github(TEST_OWNER))['credentials'])['expires_at'] > time.time()


async def test_missing_refresh_and_corrupt_cipher_require_reconnect(client, configured):
    await saved(expires_at=1)
    assert (await github.status(TEST_OWNER))['status'] == 'reconnect'
    with pytest.raises(github.GitHubError):
        await github.access_token(TEST_OWNER)
    await store.save_github(TEST_OWNER, 'nguoi-test', 'corrupted', '1')
    assert (await github.status(TEST_OWNER))['status'] == 'reconnect'


async def test_repository_reads_actions_logs_and_sources(client, configured, github_http):
    await saved()
    tools = GitHubSession(TEST_OWNER)
    listing = await tools.run('github_list_repositories', '{}')
    assert listing['repositories'][0]['name'] == 'nguoi-test/Peto' and not listing['has_more_installations']
    file = await tools.run('github_read_repository', json.dumps({'repository': 'nguoi-test/Peto', 'path': 'README.md'}))
    assert file['text'] == 'Xin chào repo' and file['sources'][0]['url'].endswith('/blob/HEAD/README.md')
    logs = await tools.run('github_actions', json.dumps({'repository': 'nguoi-test/Peto', 'action': 'job_log', 'job_id': 34}))
    assert logs['ok'] and 'Assertion failed' in logs['text'] and TOKEN not in json.dumps(logs)
    assert 'private-signature' not in json.dumps(logs)
    assert logs['sources'][0]['url'].endswith('/actions/runs/12/job/34')
    external = next(request for request in github_http if request.url.host == 'logs.blob.core.windows.net')
    assert 'authorization' not in external.headers
    assert all(request.method == 'GET' for request in github_http)


@pytest.mark.parametrize('name,args', [
    ('github_read_repository', {'repository': '../secret'}),
    ('github_read_repository', {'repository': 'nguoi-test/Peto', 'path': '../.env'}),
    ('github_actions', {'repository': 'nguoi-test/Peto', 'action': 'rerun', 'run_id': 12}),
    ('github_actions', {'repository': 'nguoi-test/Peto', 'action': 'jobs', 'run_id': True}),
    ('github_list_repositories', {'url': 'http://localhost/private'}),
    ('delete_repository', {}),
])
async def test_invalid_tools_cannot_make_arbitrary_requests(client, configured, github_http, name, args):
    await saved()
    result = await GitHubSession(TEST_OWNER).run(name, json.dumps(args))
    assert not result['ok'] and not github_http


async def test_log_redirect_cannot_reach_internal_hosts(configured, monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    real = httpx.AsyncClient
    monkeypatch.setattr(github.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(github.GitHubError):
        await github.api_get(TOKEN, '/repos/a/b/actions/jobs/1/logs', log=True)
    assert len(requests) == 1


async def test_response_limit_and_auth_errors_are_safe(configured, monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(github.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(lambda _: httpx.Response(401, text=TOKEN)), **kw))
    with pytest.raises(github.GitHubError) as error:
        await github.api_get(TOKEN, '/user')
    assert TOKEN not in str(error.value) and 'hết hạn' in str(error.value)
    monkeypatch.setattr(github, 'MAX_RESPONSE_BYTES', 8)
    # Giới hạn nhỏ truyền trực tiếp vì giá trị mặc định được gắn lúc định nghĩa hàm.
    response = httpx.Response(200, content=b'a' * 20)
    with pytest.raises(github.GitHubError):
        await github.read_response(response, 8)


async def test_real_provider_connector_roundtrip_and_title_exclusion(client, configured, github_http, monkeypatch):
    await saved()
    streams = [FakeStream([done(call('github_actions', json.dumps({'repository': 'nguoi-test/Peto', 'action': 'runs'})))]),
               FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Lần chạy 12 bị lỗi.'), done()])]
    provider, requests = fake_provider(monkeypatch, streams)
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': provider)
    events = await read_events(await client.post('/api/chat', json={'message': 'Kiểm tra Actions nguoi-test/Peto', 'web_search': 'off'}))
    assert events[-1]['type'] == 'done'
    assert [event['live'] for event in events if event['type'] == 'connector_lookup'] == [True, False]
    assert any(event['type'] == 'sources' for event in events)
    assert set(tool.get('name') for tool in requests[0]['tools']) >= NAMES
    assert TOKEN not in json.dumps(requests) and TOKEN not in json.dumps(events)
    output = json.loads(requests[1]['input'][-1]['output'])
    assert output['runs'][0]['conclusion'] == 'failure' and 'chỉ dẫn' in output['note']
    second, title_requests = fake_provider(monkeypatch, [FakeStream([done()])])
    context = current_session.set(GitHubSession(TEST_OWNER))
    try:
        _ = [chunk async for chunk in second.stream(system_prompt='Tên', messages=[ChatMessage('user', 'Tên')], tools_enabled=False)]
    finally:
        current_session.reset(context)
    assert title_requests[0]['tools'] == []


async def test_companion_and_other_accounts_receive_no_connector_tools(client, configured, monkeypatch):
    await saved('guest:other')
    class Provider:
        async def stream(self, **kwargs):
            assert current_session.get() is None
            yield 'Chào bạn'
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Provider())
    assert (await read_events(await client.post('/api/chat', json={'message': 'Chào'})))[-1]['type'] == 'done'
    await saved()
    assert (await read_events(await client.post('/api/chat', json={'message': 'Chào', 'mode': 'companion'})))[-1]['type'] == 'done'
