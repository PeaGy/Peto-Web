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
STEPFUN_URL = 'https://api.stepfun.ai/v1/audio/speech'
QWEN_ENDPOINTS = {
    'intl': 'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
    'cn': 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
}
# Nguồn đọc bằng khóa của chính người dùng mà phải đi qua máy chủ: StepFun chặn trình duyệt gọi thẳng (CORS), còn
# Qwen trả địa chỉ tệp âm thanh mà trình duyệt không tải được (kiểm ngày 2026-09-24).
RELAY_NAMES = {'stepfun': 'StepFun', 'qwen': 'Qwen Cloud'}
RELAY_MODELS = {'stepfun': 'stepaudio-2.5-tts', 'qwen': 'qwen3-tts-flash'}


def enabled(name):
    return os.getenv(name, '').lower() in ('1', 'true', 'yes')


def catalog():
    result = []
    if enabled('PETO_TTS_OPENAI_ENABLED') and os.getenv('OPENAI_API_KEY'):
        result += ['openai:' + voice for voice in OPENAI_VOICES]
    if enabled('PETO_TTS_QWEN_ENABLED') and os.getenv('DASHSCOPE_API_KEY'):
        result += ['qwen:' + voice.strip() for voice in os.getenv('PETO_TTS_QWEN_VOICES', 'Cherry,Serena').split(',') if voice.strip()]
    if enabled('PETO_TTS_STEPFUN_ENABLED') and os.getenv('STEP_API_KEY', '').strip():
        result += ['stepfun:' + voice.strip() for voice in os.getenv('PETO_TTS_STEPFUN_VOICES', 'jilingshaonv').split(',') if voice.strip()]
    return result


def model_rate(provider):
    if provider == 'openai':
        model = os.getenv('PETO_TTS_OPENAI_MODEL', 'tts-1')
        rates = {'tts-1': 15, 'tts-1-hd': 30}
    elif provider == 'stepfun':
        model = os.getenv('PETO_TTS_STEPFUN_MODEL', 'stepaudio-2.5-tts')
        # USD / million raw characters. Conservative: StepFun counts two
        # English letters as one billing character; we reserve one per letter.
        rates = {'stepaudio-2.5-tts': 85}
    elif provider == 'qwen':
        model = os.getenv('PETO_TTS_QWEN_MODEL', 'qwen3-tts-flash')
        rates = {'qwen3-tts-flash': 10, 'qwen3-tts-vc-2026-01-22': 11.5}
    else:
        raise HTTPException(503, 'Nguồn giọng chưa được hỗ trợ.')
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


async def _stepfun(client, key, model, voice, text):
    async with client.stream('POST', STEPFUN_URL, headers={'Authorization': 'Bearer ' + key},
            json={'model': model, 'voice': voice, 'input': text,
                  'language': 'en', 'response_format': 'wav'}) as response:
        return await read_audio(response)


async def _qwen(client, key, model, voice, text, endpoint):
    response = await client.post(endpoint, headers={'Authorization': 'Bearer ' + key},
        json={'model': model, 'input': {'text': text, 'voice': voice, 'language_type': 'English'}})
    response.raise_for_status()
    url = audio_url(response.json()['output']['audio']['url'])
    async with client.stream('GET', url) as audio:
        return await read_audio(audio)


async def synthesize(text, voice):
    if voice not in catalog():
        raise HTTPException(503, 'Nguồn giọng chưa được cấu hình trên máy chủ.')
    provider, name = voice.split(':', 1)
    model, _ = model_rate(provider)
    await reserve(provider, len(text))
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            if provider == 'stepfun':
                return await _stepfun(client, os.environ['STEP_API_KEY'].strip(), model, name, text)
            if provider == 'openai':
                async with client.stream('POST', 'https://api.openai.com/v1/audio/speech',
                        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']},
                        json={'model': model, 'voice': name, 'input': text, 'response_format': 'wav'}) as response:
                    return await read_audio(response)
            endpoint = os.getenv('PETO_TTS_QWEN_ENDPOINT', QWEN_ENDPOINTS['intl'])
            if urlsplit(endpoint).scheme != 'https':
                raise HTTPException(503, 'Qwen endpoint phải dùng HTTPS.')
            return await _qwen(client, os.environ['DASHSCOPE_API_KEY'], model, name, text, endpoint)
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        if provider == 'stepfun':
            if code == 402:
                raise HTTPException(402, 'StepFun chưa đủ số dư. Kiểm tra Billing trên StepFun; bạn vẫn có thể chat chữ.') from None
            if code == 429:
                raise HTTPException(429, 'StepFun đã chạm hạn mức hoặc giới hạn lượt gọi. Kiểm tra Usage trên StepFun rồi thử lại.') from None
            if code == 400:
                raise HTTPException(400, 'StepFun không chấp nhận yêu cầu. Kiểm tra model và mã giọng trong cấu hình máy chủ.') from None
        if code in (401, 403):
            raise HTTPException(503, 'Khóa API hoặc quyền sử dụng TTS chưa hợp lệ.') from None
        raise HTTPException(502, 'Nhà cung cấp giọng nói đang bận hoặc từ chối yêu cầu. Thử lại sau.') from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Không nhận được âm thanh từ nhà cung cấp.') from None


async def relay(provider, key, text, voice, model=None, region='intl'):
    """Đọc bằng khóa của chính người dùng, cho nguồn trình duyệt không gọi thẳng được (RELAY_NAMES).

    Khóa chỉ đi qua trong lượt này: không lưu, không ghi nhật ký, không tính vào ngân sách của chủ web. Địa chỉ gọi
    là cố định theo nhà cung cấp, nên đây không phải proxy cho địa chỉ tùy ý.
    """
    name = RELAY_NAMES.get(provider)
    if not name:
        raise HTTPException(400, 'Nguồn giọng này không đi qua máy chủ Peto.')
    model = model or RELAY_MODELS[provider]
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            if provider == 'stepfun':
                return await _stepfun(client, key, model, voice, text)
            return await _qwen(client, key, model, voice, text, QWEN_ENDPOINTS.get(region, QWEN_ENDPOINTS['intl']))
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        if code in (401, 403):
            raise HTTPException(400, f'Khóa {name} không đúng hoặc chưa có quyền dùng giọng nói.') from None
        if code == 402:
            raise HTTPException(402, f'Tài khoản {name} của bạn đã hết số dư.') from None
        if code == 429:
            raise HTTPException(429, f'{name} đang giới hạn lượt gọi của khóa này. Thử lại sau.') from None
        if code in (400, 404, 422):
            raise HTTPException(400, f'{name} không nhận mã giọng hoặc model này. Kiểm tra lại trong Cài đặt.') from None
        raise HTTPException(502, f'{name} đang bận hoặc từ chối yêu cầu. Thử lại sau.') from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, f'Không nhận được âm thanh từ {name}.') from None


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
