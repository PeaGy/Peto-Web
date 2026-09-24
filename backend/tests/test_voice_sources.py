"""Nguồn giọng Companion: lượt miễn phí của Giọng Peto theo tài khoản, và đường chuyển tiếp cho khóa riêng."""
import json
import uuid

import httpx
import pytest
from fastapi import Response

import speech_cloud as cloud
import voice_api as voice

WAV = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 40


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud, 'DB_PATH', tmp_path / 'speech.db')
    monkeypatch.setenv('PETO_TTS_OPENAI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-owner-key')
    monkeypatch.setenv('PETO_TTS_OPENAI_MODEL', 'tts-1')
    monkeypatch.setenv('PETO_TTS_QWEN_ENABLED', 'false')
    monkeypatch.setenv('PETO_TTS_STEPFUN_ENABLED', 'false')
    monkeypatch.setenv('PETO_TTS_MONTHLY_USD', '10')
    # Mỗi test một "tháng" riêng: tài khoản thử dùng chung giữa các test, lượt đã dùng không được dồn sang test khác.
    month = f'test-{uuid.uuid4().hex[:8]}'
    monkeypatch.setattr(voice, 'voice_month', lambda: (month, '2026-10-01'))
    # Test máy nhà ở tệp khác có gửi nhịp tim; ở đây máy nhà luôn bắt đầu là đang tắt.
    monkeypatch.setattr(voice, 'last_seen', 0.0)
    voice.active_speakers.clear()


def upstream(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(cloud.httpx, 'AsyncClient',
                        lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


async def used(client) -> int:
    return (await client.get('/api/voice/health')).json()['official']['used']


async def test_health_reports_the_official_allowance_to_members_only(client, anon_client):
    data = (await client.get('/api/voice/health')).json()
    assert data['official'] == {'voices': [f'openai:{name}' for name in cloud.OPENAI_VOICES], 'allowed': True,
                                'used': 0, 'limit': voice.VOICE_FREE_CHARS_MONTHLY, 'resets': '2026-10-01'}
    assert data['home'] == {'online': False, 'voices': voice.VOICES}
    await anon_client.post('/api/auth/guest')
    guest = (await anon_client.get('/api/voice/health')).json()['official']
    assert guest['allowed'] is False and guest['used'] == 0


async def test_official_voice_spends_the_monthly_allowance_then_stops(client, monkeypatch):
    monkeypatch.setattr(voice, 'VOICE_FREE_CHARS_MONTHLY', 10)
    upstream(monkeypatch, lambda request: httpx.Response(200, content=WAV))
    first = await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'openai:nova'})
    assert first.status_code == 200 and first.headers['x-peto-voice-used'] == '5'
    second = await client.post('/api/voice/speak', json={'text': 'World', 'voice': 'openai:nova'})
    assert second.headers['x-peto-voice-used'] == '10'
    third = await client.post('/api/voice/speak', json={'text': 'Again', 'voice': 'openai:nova'})
    assert third.status_code == 429
    assert 'hết lượt Giọng Peto' in third.json()['detail'] and '01/10' in third.json()['detail']
    assert await used(client) == 10


async def test_a_failed_official_line_gives_the_characters_back(client, monkeypatch):
    upstream(monkeypatch, lambda request: httpx.Response(500))
    response = await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'openai:nova'})
    assert response.status_code == 502
    assert await used(client) == 0


async def test_an_exhausted_allowance_falls_back_to_the_home_voice(client, monkeypatch):
    monkeypatch.setattr(voice, 'VOICE_FREE_CHARS_MONTHLY', 3)

    async def home(body, request, owner):
        return Response(WAV, media_type='audio/wav')

    monkeypatch.setattr(voice, 'local_speak', home)
    response = await client.post('/api/voice/speak',
                                 json={'text': 'Hello', 'voice': 'openai:nova', 'fallback': 'playful-1'})
    assert response.status_code == 200 and response.headers['x-peto-voice'] == 'playful-1'
    assert await used(client) == 0


async def test_guests_cannot_spend_the_owner_voice(anon_client, monkeypatch):
    def forbidden(request):
        raise AssertionError('khách không được gọi tới nhà cung cấp bằng khóa của chủ web')

    upstream(monkeypatch, forbidden)
    await anon_client.post('/api/auth/guest')
    response = await anon_client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'openai:nova'})
    assert response.status_code == 403 and 'Discord và Google' in response.json()['detail']


async def test_relay_forwards_the_user_key_and_spends_nothing_of_the_owner(client, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=WAV)

    async def forbidden(*args, **kwargs):
        raise AssertionError('khóa riêng không được trừ ngân sách của chủ web')

    upstream(monkeypatch, handler)
    monkeypatch.setattr(cloud, 'reserve', forbidden)
    response = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'user-step-key'},
                                 json={'provider': 'stepfun', 'text': 'Hello', 'voice': 'jilingshaonv'})
    assert response.status_code == 200 and response.content == WAV
    assert str(seen[0].url) == cloud.STEPFUN_URL
    assert seen[0].headers['authorization'] == 'Bearer user-step-key'
    assert json.loads(seen[0].content)['model'] == 'stepaudio-2.5-tts'
    assert await used(client) == 0


@pytest.mark.parametrize(('status', 'message'), [
    (401, 'Khóa StepFun không đúng'), (402, 'hết số dư'), (429, 'giới hạn lượt gọi'), (400, 'không nhận mã giọng'),
])
async def test_relay_explains_provider_errors_in_vietnamese(client, monkeypatch, status, message):
    upstream(monkeypatch, lambda request: httpx.Response(status, json={'error': 'secret upstream detail'}))
    response = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'user-key'},
                                 json={'provider': 'stepfun', 'text': 'Hello', 'voice': 'jilingshaonv'})
    assert message in response.json()['detail']
    assert 'secret upstream' not in response.text


async def test_relay_needs_a_key_a_known_provider_and_plain_ids(client):
    body = {'provider': 'stepfun', 'text': 'Hello', 'voice': 'jilingshaonv'}
    assert 'Chưa có khóa' in (await client.post('/api/voice/relay', json=body)).json()['detail']
    wrong = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'k'}, json={**body, 'provider': 'openai'})
    assert 'không đi qua máy chủ' in wrong.json()['detail']
    odd = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'k'}, json={**body, 'voice': '../x'})
    assert odd.status_code == 400
    region = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'k'}, json={**body, 'region': 'moon'})
    assert region.status_code == 400


async def test_qwen_relay_fetches_the_audio_file_on_the_server(client, monkeypatch):
    def handler(request):
        if request.method == 'POST':
            assert str(request.url) == cloud.QWEN_ENDPOINTS['intl']
            assert request.headers['authorization'] == 'Bearer user-qwen-key'
            return httpx.Response(200, json={'output': {'audio': {
                'url': 'https://dashscope-result-sgp.oss-ap-southeast-1.aliyuncs.com/a.wav?sig=1'}}})
        assert request.url.host.startswith('dashscope-result-')
        return httpx.Response(200, content=WAV)

    upstream(monkeypatch, handler)
    response = await client.post('/api/voice/relay', headers={'X-Voice-Key': 'user-qwen-key'},
                                 json={'provider': 'qwen', 'text': 'Hi', 'voice': 'Cherry'})
    assert response.status_code == 200 and response.content == WAV


async def test_guests_can_relay_with_their_own_key(anon_client, monkeypatch):
    upstream(monkeypatch, lambda request: httpx.Response(200, content=WAV))
    await anon_client.post('/api/auth/guest')
    response = await anon_client.post('/api/voice/relay', headers={'X-Voice-Key': 'guest-own-key'},
                                      json={'provider': 'stepfun', 'text': 'Hello', 'voice': 'jilingshaonv'})
    assert response.status_code == 200
