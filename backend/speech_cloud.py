"""Cloud speech adapters; credentials and budget stay on the server."""
import asyncio
import json
import logging
import math
import os
import struct
import uuid
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
# CosyVoice (cùng khóa Alibaba Cloud với Qwen) chỉ có WebSocket, và khóa phải nằm trong header lúc bắt tay.
COSYVOICE_ENDPOINTS = {
    'intl': 'wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference',
    'cn': 'wss://dashscope.aliyuncs.com/api-ws/v1/inference',
}
COSYVOICE_RATE = 24000
# Nguồn đọc bằng khóa của chính người dùng mà phải đi qua máy chủ: StepFun chặn trình duyệt gọi thẳng (CORS), Qwen
# trả địa chỉ tệp âm thanh mà trình duyệt không tải được (kiểm ngày 2026-09-24), còn WebSocket của CosyVoice cần
# header Authorization mà trình duyệt không gắn được.
RELAY_NAMES = {'stepfun': 'StepFun', 'qwen': 'Alibaba Cloud'}
RELAY_MODELS = {'stepfun': 'stepaudio-2.5-tts', 'qwen': 'qwen3-tts-flash'}
# websockets ghi các header bắt tay (có cả khóa) ở mức DEBUG: logger riêng này không bao giờ ghi mức đó.
_ws_log = logging.getLogger('peto.voice.cosyvoice')
_ws_log.setLevel(logging.WARNING)


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


def pcm_to_wav(pcm, rate):
    """Bọc PCM16 mono thành WAV, để trang đọc được độ to cho nhân vật nhép miệng."""
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt '
            + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', len(pcm)) + pcm)


class CosyVoiceFailed(Exception):
    """Sự kiện task-failed của CosyVoice; chỉ giữ mã lỗi, câu báo lỗi của Alibaba không tới người dùng."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


async def _cosyvoice(key, model, voice, text, endpoint):
    """Một lượt CosyVoice theo giao thức WebSocket của Alibaba: run-task, chờ task-started, gửi chữ rồi finish-task,
    gom các khung âm thanh nhị phân tới task-finished."""
    from websockets.asyncio.client import connect as ws_connect

    task = str(uuid.uuid4())

    def message(action, payload):
        return json.dumps({'header': {'action': action, 'task_id': task, 'streaming': 'duplex'}, 'payload': payload})

    audio = bytearray()
    async with ws_connect(endpoint, additional_headers={'Authorization': 'Bearer ' + key}, logger=_ws_log,
                          open_timeout=15, close_timeout=2) as socket:
        await socket.send(message('run-task', {
            'task_group': 'audio', 'task': 'tts', 'function': 'SpeechSynthesizer', 'model': model, 'input': {},
            # Companion nói tiếng Anh: gợi ý ngôn ngữ để số và ký hiệu được đọc theo tiếng Anh (v1 không có, v2 trở lên có).
            'parameters': {'text_type': 'PlainText', 'voice': voice, 'format': 'pcm', 'sample_rate': COSYVOICE_RATE,
                           'language_hints': ['en']},
        }))
        async for frame in socket:
            if isinstance(frame, bytes):
                audio.extend(frame)
                if len(audio) > MAX_AUDIO:
                    raise HTTPException(502, 'Âm thanh trả về quá lớn.')
                continue
            header = json.loads(frame).get('header') or {}
            event = header.get('event')
            if event == 'task-started':
                await socket.send(message('continue-task', {'input': {'text': text}}))
                await socket.send(message('finish-task', {'input': {}}))
            elif event == 'task-failed':
                raise CosyVoiceFailed(str(header.get('error_code') or ''))
            elif event == 'task-finished':
                break
    if len(audio) < 2:
        raise ValueError('CosyVoice không trả âm thanh')
    return pcm_to_wav(bytes(audio[:len(audio) // 2 * 2]), COSYVOICE_RATE)


def relay_error(name, code):
    """Mã lỗi của nhà cung cấp thành câu tiếng Việt; không bao giờ đưa nguyên văn lỗi của họ (có thể lộ khóa) ra ngoài."""
    if code in (401, 403):
        return HTTPException(400, f'Khóa {name} không đúng hoặc chưa có quyền dùng giọng nói.')
    if code == 402:
        return HTTPException(402, f'Tài khoản {name} của bạn đã hết số dư.')
    if code == 429:
        return HTTPException(429, f'{name} đang giới hạn lượt gọi của khóa này. Thử lại sau.')
    if code in (400, 404, 422):
        return HTTPException(400, f'{name} không nhận mã giọng hoặc model này. Kiểm tra lại trong Cài đặt.')
    return HTTPException(502, f'{name} đang bận hoặc từ chối yêu cầu. Thử lại sau.')


def cosyvoice_status(code):
    """Mã lỗi chữ trong task-failed của CosyVoice, quy về mã HTTP tương ứng để dùng chung relay_error."""
    if 'Arrearage' in code:
        return 402
    if 'Throttling' in code or 'RateQuota' in code:
        return 429
    if 'ApiKey' in code or 'AccessDenied' in code or 'Unauthorized' in code:
        return 401
    if 'Invalid' in code or 'NotFound' in code or 'BadRequest' in code or 'Unsupported' in code:
        return 400
    return 502


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
    if provider == 'qwen' and model.startswith('cosyvoice-'):
        return await _relay_cosyvoice(name, key, model, voice, text, region)
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            if provider == 'stepfun':
                return await _stepfun(client, key, model, voice, text)
            return await _qwen(client, key, model, voice, text, QWEN_ENDPOINTS.get(region, QWEN_ENDPOINTS['intl']))
    except httpx.HTTPStatusError as error:
        raise relay_error(name, error.response.status_code) from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, f'Không nhận được âm thanh từ {name}.') from None


async def _relay_cosyvoice(name, key, model, voice, text, region):
    # Nạp lúc dùng: VPS còn websockets cũ (trước bản 14) thì chỉ CosyVoice báo lỗi, cả máy chủ vẫn chạy.
    try:
        import websockets
        from websockets.asyncio.client import connect  # noqa: F401
    except ImportError:
        raise HTTPException(503, 'Máy chủ Peto chưa sẵn sàng cho CosyVoice: chủ web cần cài lại thư viện của backend.') from None
    try:
        async with asyncio.timeout(60):
            return await _cosyvoice(key, model, voice, text, COSYVOICE_ENDPOINTS.get(region, COSYVOICE_ENDPOINTS['intl']))
    except websockets.exceptions.InvalidStatus as error:
        raise relay_error(name, error.response.status_code) from None
    except CosyVoiceFailed as error:
        raise relay_error(name, cosyvoice_status(error.code)) from None
    except (TimeoutError, OSError, websockets.exceptions.WebSocketException, ValueError, TypeError, AttributeError):
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
