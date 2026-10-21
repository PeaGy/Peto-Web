"""Script phép thử thực thi mã (ops/code_execution_probe.py): mặc định chạy khô, không gọi mạng, không lộ khóa."""
import json

import httpx
import pytest

from core import config
from ops import code_execution_probe as probe


def recording(inner: httpx.MockTransport, seen: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return inner.handle_request(request)
    return httpx.MockTransport(handler)


def refusing() -> httpx.MockTransport:
    def handler(request):
        raise AssertionError('Không được gọi mạng')
    return httpx.MockTransport(handler)


async def test_dry_run_haiku_reads_blocks_downloads_and_deletes_the_file():
    evidence, _ = await probe.run('haiku', False)
    request = evidence['requests'][0]
    assert request['stop_reason'] == 'end_turn' and request['usage']['server_tool_use'] == {'code_execution_requests': 1}
    assert [block['type'] for block in request['blocks']] == ['server_tool_use', 'bash_code_execution_tool_result', 'text']
    assert evidence['check'] == {'mean_seen': True, 'stdev_seen': True, 'png_returned': True, 'files_deleted': True}
    dumped = json.dumps(evidence)
    # Mã tệp và container chỉ còn dạng băm trong bằng chứng.
    assert 'file_fake_chart' not in dumped and 'container_fake' not in dumped


async def test_dry_run_xai_resends_items_with_store_false():
    seen = []
    evidence, _ = await probe.run('xai', False, transport=recording(probe.fake_transport(), seen))
    assert [request.url.path for request in seen] == ['/v1/responses', '/v1/responses']
    second = json.loads(seen[1].content)
    assert second['store'] is False and second['tools'] == [{'type': 'code_interpreter'}]
    assert [item.get('type', 'message') for item in second['input']] == ['message', 'code_interpreter_call', 'message',
                                                                         'message']
    assert evidence['check']['code_items'] == 2 and evidence['check']['follow_up_accepted'] is True
    assert evidence['auth_mode'] == 'dry_run'


def test_main_defaults_to_dry_run_and_writes_evidence(tmp_path, capsys):
    out = tmp_path / 'haiku.json'
    assert probe.main(['haiku', '--out', str(out)]) == 0
    evidence = json.loads(out.read_text(encoding='utf-8'))
    assert evidence['mode'] == 'dry_run' and evidence['expected']['mean'] == 161.0
    assert 'CHẠY KHÔ' in capsys.readouterr().out


async def test_paid_run_refuses_without_credentials_before_any_request(monkeypatch):
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', '')
    with pytest.raises(SystemExit):
        await probe.run('haiku', True, transport=refusing())
    from ai import xai_auth
    monkeypatch.setattr(xai_auth, 'load_tokens', lambda path: None)
    monkeypatch.delenv('XAI_API_KEY', raising=False)
    with pytest.raises(SystemExit):
        await probe.run('xai', True, transport=refusing())


async def test_xai_probe_never_refreshes_the_shared_oauth_token(monkeypatch):
    from ai import xai_auth
    expired = xai_auth.TokenBundle(access_token='old-access-token-123', refresh_token='refresh-token-456', expires_at=0)

    async def no_refresh(bundle):
        raise AssertionError('Phép thử không được refresh token của backend')
    monkeypatch.setattr(xai_auth, 'refresh_tokens', no_refresh)
    monkeypatch.setattr(xai_auth, 'load_tokens', lambda path: expired)
    with pytest.raises(SystemExit, match='không tự refresh'):
        await probe.run('xai', True, transport=refusing())
    fresh = xai_auth.TokenBundle(access_token='live-access-token-789', refresh_token='refresh-token-456',
                                 expires_at=9_999_999_999)
    monkeypatch.setattr(xai_auth, 'load_tokens', lambda path: fresh)
    seen = []
    evidence, secrets = await probe.run('xai', True, transport=recording(probe.fake_transport(), seen))
    assert seen[0].headers['authorization'] == 'Bearer live-access-token-789'
    assert evidence['auth_mode'] == 'oauth' and secrets == ['live-access-token-789']
    assert 'live-access-token-789' not in probe.scrub(json.dumps(evidence), secrets)


async def test_paid_path_sends_the_key_only_in_headers_and_never_in_evidence(monkeypatch):
    secret = 'sk-ant-test-SECRET-0123456789'
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', secret)
    seen = []
    evidence, secrets = await probe.run('haiku', True, transport=recording(probe.fake_transport(), seen))
    first = json.loads(seen[0].content)
    assert seen[0].headers['x-api-key'] == secret and secret not in seen[0].content.decode()
    assert first['tools'] == [{'type': probe.TOOL_VERSION, 'name': 'code_execution'}]
    assert first['thinking'] == {'type': 'adaptive'} and first['output_config'] == {'effort': 'low'}
    assert secret not in probe.scrub(json.dumps(evidence), secrets)
    assert [request.method for request in seen[1:]] == ['GET', 'GET', 'DELETE', 'GET']


async def test_http_error_is_recorded_without_more_requests():
    def handler(request):
        return httpx.Response(400, json={'error': {'type': 'invalid_request_error', 'message': 'tool not enabled'}})
    seen = []
    evidence, _ = await probe.run('haiku', False, transport=recording(httpx.MockTransport(handler), seen))
    assert len(seen) == 1
    assert evidence['requests'][0]['http_status'] == 400
    assert evidence['requests'][0]['error_type'] == 'invalid_request_error' and evidence['files'] == []
    assert evidence['check']['mean_seen'] is False


async def test_pause_turn_continues_once_with_the_same_container():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        reason = 'pause_turn' if len(calls) == 1 else 'end_turn'
        return httpx.Response(200, content=probe._sse([
            {'type': 'message_start', 'message': {'usage': {'input_tokens': 10}}},
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': 'Đang chạy'}},
            {'type': 'content_block_stop', 'index': 0},
            {'type': 'message_delta', 'delta': {'stop_reason': reason, 'container': {'id': 'container_live'}},
             'usage': {'output_tokens': 5}},
            {'type': 'message_stop'}]))

    evidence, _ = await probe.run('haiku', False, transport=httpx.MockTransport(handler))
    assert len(calls) == 2 and calls[1]['container'] == 'container_live'
    assert calls[1]['messages'][-1] == {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Đang chạy'}]}
    assert [request['stop_reason'] for request in evidence['requests']] == ['pause_turn', 'end_turn']
