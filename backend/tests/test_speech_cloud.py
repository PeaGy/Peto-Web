import asyncio
import json
import pytest
import httpx
from fastapi import HTTPException
import speech_cloud as cloud
import voice_api as voice

WAV = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 40

@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud, 'DB_PATH', tmp_path / 'speech.db')
    monkeypatch.setenv('PETO_TTS_OPENAI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('PETO_TTS_OPENAI_MODEL', 'tts-1')
    monkeypatch.setenv('PETO_TTS_QWEN_ENABLED', 'false')
    monkeypatch.setenv('PETO_TTS_STEPFUN_ENABLED', 'false')
    monkeypatch.setenv('PETO_TTS_MONTHLY_USD', '10')
    voice.active_speakers.clear()

@pytest.fixture
def stepfun(monkeypatch):
    monkeypatch.setenv('PETO_TTS_STEPFUN_ENABLED', 'true')
    monkeypatch.setenv('STEP_API_KEY', 'fake-step')
    monkeypatch.setenv('PETO_TTS_STEPFUN_MODEL', 'stepaudio-2.5-tts')
    monkeypatch.setenv('PETO_TTS_STEPFUN_VOICES', 'jilingshaonv')

def test_stepfun_requires_opt_in_and_key(monkeypatch):
    monkeypatch.setenv('STEP_API_KEY', 'fake-step')
    assert not any(v.startswith('stepfun:') for v in cloud.catalog())
    monkeypatch.setenv('PETO_TTS_STEPFUN_ENABLED', 'true')
    monkeypatch.setenv('PETO_TTS_STEPFUN_VOICES', 'jilingshaonv, lively-girl')
    assert 'stepfun:jilingshaonv' in cloud.catalog()
    assert 'stepfun:lively-girl' in cloud.catalog()
    monkeypatch.delenv('STEP_API_KEY')
    assert not any(v.startswith('stepfun:') for v in cloud.catalog())

@pytest.mark.asyncio
async def test_stepfun_routes_wav_with_server_credentials(client, monkeypatch, stepfun):
    original = httpx.AsyncClient
    def handler(request):
        assert str(request.url) == 'https://api.stepfun.ai/v1/audio/speech'
        assert request.headers['authorization'] == 'Bearer fake-step'
        assert json.loads(request.content) == {
            'model': 'stepaudio-2.5-tts', 'voice': 'jilingshaonv',
            'input': 'Hello', 'language': 'en', 'response_format': 'wav',
        }
        return httpx.Response(200, content=WAV)
    monkeypatch.setattr(cloud.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    response = await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'stepfun:jilingshaonv'})
    assert response.status_code == 200
    assert response.content == WAV
    assert response.headers['x-peto-voice'] == 'stepfun:jilingshaonv'

@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 402, 429])
async def test_stepfun_config_and_balance_errors_do_not_fallback(client, monkeypatch, stepfun, status):
    original = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(status, json={'error': 'private upstream error'})
    monkeypatch.setattr(cloud.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    response = await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'stepfun:jilingshaonv', 'fallback': 'openai:nova'})
    assert response.status_code == status
    assert len(calls) == 1
    assert 'private upstream error' not in response.text

@pytest.mark.asyncio
async def test_stepfun_budget_blocks_before_network(monkeypatch, stepfun):
    monkeypatch.setenv('PETO_TTS_MONTHLY_USD', '0.00001')
    def forbidden(**kwargs):
        pytest.fail('Budget must block before opening HTTP client')
    monkeypatch.setattr(cloud.httpx, 'AsyncClient', forbidden)
    with pytest.raises(HTTPException) as error:
        await cloud.synthesize('Hello', 'stepfun:jilingshaonv')
    assert error.value.status_code == 429

@pytest.mark.asyncio
async def test_budget_is_atomic_persistent_and_shared(monkeypatch):
    monkeypatch.setenv('PETO_TTS_MONTHLY_USD', '0.0015')
    results = await asyncio.gather(cloud.reserve('openai', 100), cloud.reserve('openai', 100), return_exceptions=True)
    assert sum(item is None for item in results) == 1
    assert sum(isinstance(item, HTTPException) and item.status_code == 429 for item in results) == 1
    with pytest.raises(HTTPException):
        await cloud.reserve('qwen', 1)

@pytest.mark.asyncio
async def test_openai_adapter_uses_server_key_and_validates_audio(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        assert str(request.url) == 'https://api.openai.com/v1/audio/speech'
        assert request.headers['authorization'] == 'Bearer fake'
        assert b'"voice":"nova"' in request.content
        return httpx.Response(200, content=WAV)
    monkeypatch.setattr(cloud.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    assert await cloud.synthesize('Hello', 'openai:nova') == WAV

@pytest.mark.asyncio
async def test_qwen_download_does_not_forward_key(monkeypatch):
    monkeypatch.setenv('PETO_TTS_QWEN_ENABLED', 'true')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'fake-qwen')
    monkeypatch.setenv('PETO_TTS_QWEN_MODEL', 'qwen3-tts-flash')
    monkeypatch.setenv('PETO_TTS_QWEN_VOICES', 'Cherry')
    monkeypatch.delenv('PETO_TTS_QWEN_ENDPOINT', raising=False)
    original = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request.method)
        if request.method == 'POST':
            assert request.headers['authorization'] == 'Bearer fake-qwen'
            assert json.loads(request.content)['input'] == {'text': 'Hello', 'voice': 'Cherry', 'language_type': 'English'}
            return httpx.Response(200, json={'output': {'audio': {'url': 'http://dashscope-result-sg.oss-ap-southeast-1.aliyuncs.com/voice.wav'}}})
        assert request.url.scheme == 'https'
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=WAV)
    monkeypatch.setattr(cloud.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    assert await cloud.synthesize('Hello', 'qwen:Cherry') == WAV
    assert calls == ['POST', 'GET']

@pytest.mark.asyncio
async def test_fallback_is_explicit_and_reported(client, monkeypatch):
    voice.last_seen = 0
    async def synthesize(text, selected): return WAV
    monkeypatch.setattr(cloud, 'synthesize', synthesize)
    body = {'text': 'Hello', 'voice': 'playful-1'}
    assert (await client.post('/api/voice/speak', json=body)).status_code == 503
    response = await client.post('/api/voice/speak', json={**body, 'fallback': 'openai:nova'})
    assert response.content == WAV
    assert response.headers['x-peto-voice'] == 'openai:nova'
    assert not voice.active_speakers

@pytest.mark.asyncio
async def test_budget_error_never_triggers_fallback(client, monkeypatch):
    calls = []
    async def synthesize(text, selected):
        calls.append(selected)
        raise HTTPException(429, 'budget')
    monkeypatch.setattr(cloud, 'synthesize', synthesize)
    response = await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'openai:nova', 'fallback': 'openai:shimmer'})
    assert response.status_code == 429
    assert calls == ['openai:nova']

@pytest.mark.asyncio
async def test_disconnect_cancels_upstream():
    stopped = asyncio.Event()
    class Request:
        async def is_disconnected(self):
            await asyncio.sleep(0.01)
            return True
    async def generate():
        try: await asyncio.sleep(60)
        finally: stopped.set()
    with pytest.raises(HTTPException): await cloud.while_connected(Request(), generate())
    assert stopped.is_set()

def test_rejects_untrusted_downloads():
    for url in ['https://localhost/file', 'https://evil.com/x', 'https://dashscope-result-x.aliyuncs.com.evil.com/x', 'https://a:b@dashscope-result-x.aliyuncs.com/x']:
        with pytest.raises(HTTPException): cloud.audio_url(url)
    assert cloud.audio_url('http://dashscope-result-sg.oss-ap-southeast-1.aliyuncs.com/x') .startswith('https://')
