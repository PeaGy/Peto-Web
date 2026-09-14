"""Kiểm tra đường chuyển âm thanh, xác thực và giới hạn chờ bằng dữ liệu giả."""
import asyncio
import time

import pytest
import voice_api as voice
import auth
from config import SESSION_COOKIE, owner_key

HEADERS = {"Authorization": "Bearer " + "t" * 40}
WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40


@pytest.fixture(autouse=True)
def clean_voice(monkeypatch):
    monkeypatch.setenv("PETO_VOICE_WORKER_TOKEN", "t" * 40)
    voice.jobs.clear()
    voice.last_seen = 0
    yield
    voice.jobs.clear()


async def wait_job():
    for _ in range(100):
        if voice.jobs:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Không nhận được lượt đọc.")


@pytest.mark.asyncio
async def test_auth_and_offline(client, anon_client):
    assert (await anon_client.get('/api/voice/health')).status_code == 401
    assert (await client.get('/api/voice/worker/next')).status_code == 401
    assert (await client.get('/api/voice/health')).json()['voices'] == []
    assert (await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'playful-1'})).status_code == 503


@pytest.mark.asyncio
async def test_audio_roundtrip_and_owner_limit(client, anon_client):
    assert (await anon_client.post('/api/voice/worker/heartbeat', headers=HEADERS)).status_code == 200
    task = asyncio.create_task(client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'gentle-2'}))
    await wait_job()
    assert (await client.post('/api/voice/speak', json={'text': 'Again', 'voice': 'gentle-2'})).status_code == 429
    job = (await anon_client.get('/api/voice/worker/next', headers=HEADERS)).json()
    assert job['voice'] == 'gentle-2'
    assert (await anon_client.get('/api/voice/worker/next', headers=HEADERS)).status_code == 204
    path = '/api/voice/worker/result/' + job['id']
    assert (await client.post(path, content=WAV)).status_code == 401
    assert (await anon_client.post(path, headers=HEADERS, content=b'bad')).status_code == 400
    assert (await anon_client.post(path, headers=HEADERS, content=WAV)).status_code == 200
    response = await task
    assert response.content == WAV
    assert response.headers['cache-control'] == 'no-store'
    assert not voice.jobs
    assert (await anon_client.post(path, headers=HEADERS, content=WAV)).status_code == 404


@pytest.mark.asyncio
async def test_timeout_and_worker_failure(client, monkeypatch):
    voice.last_seen = time.monotonic()
    monkeypatch.setattr(voice, 'TIMEOUT', 0.01)
    assert (await client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'playful-1'})).status_code == 504
    assert not voice.jobs


@pytest.mark.asyncio
async def test_two_listeners_receive_their_own_audio(client, anon_client):
    anon_client.cookies.set(SESSION_COOKIE, auth._sign(owner_key('discord', '999999999999999999')))
    voice.last_seen = time.monotonic()
    first = asyncio.create_task(client.post('/api/voice/speak', json={'text': 'First', 'voice': 'playful-1'}))
    await wait_job()
    second = asyncio.create_task(anon_client.post('/api/voice/speak', json={'text': 'Second', 'voice': 'gentle-2'}))
    for _ in range(100):
        if len(voice.jobs) == 2:
            break
        await asyncio.sleep(0.01)
    assert len(voice.jobs) == 2
    for suffix in (b'first', b'second'):
        job = (await client.get('/api/voice/worker/next', headers=HEADERS)).json()
        await client.post('/api/voice/worker/result/' + job['id'], headers=HEADERS, content=WAV + suffix)
    assert (await first).content == WAV + b'first'
    assert (await second).content == WAV + b'second'
    assert not voice.jobs


@pytest.mark.asyncio
async def test_cancel_cleans_up_queue(client):
    voice.last_seen = time.monotonic()
    task = asyncio.create_task(client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'playful-1'}))
    await wait_job()
    job = (await client.get('/api/voice/worker/next', headers=HEADERS)).json()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not voice.jobs
    assert (await client.post('/api/voice/worker/result/' + job['id'], headers=HEADERS, content=WAV)).status_code == 404


@pytest.mark.asyncio
async def test_worker_reports_failure(client):
    voice.last_seen = time.monotonic()
    task = asyncio.create_task(client.post('/api/voice/speak', json={'text': 'Hello', 'voice': 'playful-1'}))
    await wait_job()
    job = (await client.get('/api/voice/worker/next', headers=HEADERS)).json()
    await client.post('/api/voice/worker/result/' + job['id'], headers={**HEADERS, 'X-Voice-Error': '1'}, content=b'')
    assert (await task).status_code == 503
    assert not voice.jobs
