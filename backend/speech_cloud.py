"""Cloud speech adapters; credentials and budget stay on the server."""
import asyncio
import math
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import aiosqlite
import httpx
from fastapi import HTTPException
from config import DB_PATH

MAX_AUDIO = 8 * 1024 * 1024
OPENAI_VOICES = ('nova', 'shimmer', 'coral', 'sage', 'alloy', 'ash', 'echo', 'fable', 'onyx')


def enabled(name):
    return os.getenv(name, '').lower() in ('1', 'true', 'yes')


def catalog():
    result = []
    if enabled('PETO_TTS_OPENAI_ENABLED') and os.getenv('OPENAI_API_KEY'):
        result += ['openai:' + voice for voice in OPENAI_VOICES]
    if enabled('PETO_TTS_QWEN_ENABLED') and os.getenv('DASHSCOPE_API_KEY'):
        result += ['qwen:' + voice.strip() for voice in os.getenv('PETO_TTS_QWEN_VOICES', 'Cherry,Serena').split(',') if voice.strip()]
    return result


def model_rate(provider):
    if provider == 'openai':
        model = os.getenv('PETO_TTS_OPENAI_MODEL', 'tts-1')
        rates = {'tts-1': 15, 'tts-1-hd': 30}
    else:
        model = os.getenv('PETO_TTS_QWEN_MODEL', 'qwen3-tts-flash')
        rates = {'qwen3-tts-flash': 10, 'qwen3-tts-vc-2026-01-22': 11.5}
    if model not in rates:
        raise HTTPException(503, 'Model TTS chưa có cấu hình tính phí. Hãy kiểm tra cấu hình máy chủ.')
    return model, rates[model]


async def reserve(provider, characters):
    """Atomically charge a conservative estimate before dispatch, across processes.

    Failed/cancelled requests retain their reservation: upstream may still bill them.
    Never logs text, keys, or audio. Budget excludes tax and non-Peto API usage.
    """
    _, rate = model_rate(provider)
    amount = math.ceil(characters * rate)  # micro-USD per character
    try:
        limit = float(os.getenv('PETO_TTS_MONTHLY_USD', '10'))
    except ValueError:
        raise HTTPException(503, 'Cấu hình ngân sách giọng nói không hợp lệ.') from None
    if not math.isfinite(limit) or limit < 0:
        raise HTTPException(503, 'Cấu hình ngân sách giọng nói không hợp lệ.')
    month = datetime.now(timezone.utc).strftime('%Y-%m')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS speech_budget (month TEXT PRIMARY KEY, micros INTEGER NOT NULL)')
        await db.execute('BEGIN IMMEDIATE')
        row = await (await db.execute('SELECT micros FROM speech_budget WHERE month=?', (month,))).fetchone()
        used = row[0] if row else 0
        if used + amount > int(limit * 1_000_000):
            raise HTTPException(429, 'Đã đạt ngân sách TTS tháng này. Bạn vẫn có thể chat chữ.')
        await db.execute('INSERT INTO speech_budget VALUES (?,?) ON CONFLICT(month) DO UPDATE SET micros=excluded.micros', (month, used + amount))
        await db.commit()


async def read_audio(response):
    response.raise_for_status()
    data = bytearray()
    async for chunk in response.aiter_bytes():
        data.extend(chunk)
        if len(data) > MAX_AUDIO:
            raise HTTPException(502, 'Âm thanh trả về quá lớn.')
    if len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise HTTPException(502, 'Nhà cung cấp trả về âm thanh không hợp lệ.')
    return bytes(data)


def audio_url(raw):
    parsed = urlsplit(raw)
    host = parsed.hostname or ''
    # Only signed Alibaba result objects, never arbitrary URLs or redirects.
    if (parsed.scheme not in ('http', 'https') or parsed.username or parsed.password
            or parsed.port not in (None, 443) or not host.startswith('dashscope-result-')
            or not host.endswith('.aliyuncs.com')):
        raise HTTPException(502, 'Địa chỉ âm thanh từ Qwen không hợp lệ.')
    return urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, ''))


async def synthesize(text, voice):
    if voice not in catalog():
        raise HTTPException(503, 'Nguồn giọng chưa được cấu hình trên máy chủ.')
    provider, name = voice.split(':', 1)
    model, _ = model_rate(provider)
    await reserve(provider, len(text))
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            if provider == 'openai':
                async with client.stream('POST', 'https://api.openai.com/v1/audio/speech',
                        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']},
                        json={'model': model, 'voice': name, 'input': text, 'response_format': 'wav'}) as response:
                    return await read_audio(response)
            endpoint = os.getenv('PETO_TTS_QWEN_ENDPOINT', 'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation')
            if urlsplit(endpoint).scheme != 'https':
                raise HTTPException(503, 'Qwen endpoint phải dùng HTTPS.')
            response = await client.post(endpoint,
                headers={'Authorization': 'Bearer ' + os.environ['DASHSCOPE_API_KEY']},
                json={'model': model, 'input': {'text': text, 'voice': name, 'language_type': 'English'}})
            response.raise_for_status()
            url = audio_url(response.json()['output']['audio']['url'])
            async with client.stream('GET', url) as audio:
                return await read_audio(audio)
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        if code in (401, 403):
            raise HTTPException(503, 'Khóa API hoặc quyền sử dụng TTS chưa hợp lệ.') from None
        raise HTTPException(502, 'Nhà cung cấp giọng nói đang bận hoặc từ chối yêu cầu. Thử lại sau.') from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Không nhận được âm thanh từ nhà cung cấp.') from None


async def while_connected(request, action):
    task = asyncio.create_task(action)
    try:
        while not task.done():
            if await request.is_disconnected():
                raise HTTPException(499, 'Đã dừng đọc.')
            await asyncio.wait({task}, timeout=0.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
