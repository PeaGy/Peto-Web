"""Giọng nói Companion: máy nhà (qua kết nối HTTPS chủ động), Giọng Peto (nguồn chính thức, có lượt miễn phí) và
đường chuyển tiếp cho khóa riêng của người dùng."""
import asyncio
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from auth import current_owner
from chat_tools import resolve_timezone
from config import VOICE_FREE_CHARS_MONTHLY, provider_from_owner
import db
import speech_cloud

router = APIRouter(prefix="/api/voice")
VOICES = ["playful-1", "gentle-2"]
TIMEOUT = 120
MAX_AUDIO = 8 * 1024 * 1024
jobs: dict = {}
last_seen = 0.0
active_speakers: set[str] = set()
# Lượt miễn phí của Giọng Peto chỉ dành cho tài khoản Discord, Google (chủ web chọn ngày 2026-09-24): khách tạo mới
# được vô hạn, nên chia lượt theo tài khoản khách thì một người rút cạn được cả tháng.
MEMBERS = {"discord", "google"}
GUEST_OFFICIAL = "Lượt Giọng Peto dành cho tài khoản Discord và Google. Bạn vẫn dùng được Máy nhà hoặc khóa của mình."
RELAY_TEXT = re.compile(r"^[\w.\- ]{1,64}$")


def voice_month() -> tuple[str, str]:
    """Tháng tính lượt (giờ PETO_DEFAULT_TIMEZONE, như hạn mức bước của agent) và ngày làm mới lượt."""
    now = datetime.now(ZoneInfo(resolve_timezone()))
    following = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return now.strftime("%Y-%m"), following.date().isoformat()


def is_member(owner: str) -> bool:
    return provider_from_owner(owner) in MEMBERS


def worker_auth(request: Request):
    token = os.environ.get("PETO_VOICE_WORKER_TOKEN", "")
    if len(token) < 32 or not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        raise HTTPException(401, "Kết nối tạo giọng chưa được xác thực.")


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    voice: str
    fallback: str | None = None


class Relay(BaseModel):
    provider: str
    text: str = Field(min_length=1, max_length=300)
    voice: str
    model: str | None = None
    region: str = "intl"


@router.get("/health")
async def health(owner: str = Depends(current_owner)):
    ready = time.monotonic() - last_seen < 15
    official = speech_cloud.catalog()
    voices = official + (VOICES if ready else [])
    month, resets = voice_month()
    member = is_member(owner)
    return {
        "ok": bool(voices),
        "voices": voices,
        "home": {"online": ready, "voices": VOICES},
        "official": {
            "voices": official,
            "allowed": member,
            "used": await db.voice_chars_used(owner, month) if member else 0,
            "limit": VOICE_FREE_CHARS_MONTHLY,
            "resets": resets,
        },
    }


@router.post("/speak")
async def speak(body: Speech, request: Request, owner: str = Depends(current_owner)):
    if not body.text.strip():
        raise HTTPException(400, 'Nội dung không hợp lệ.')
    official = speech_cloud.catalog()
    allowed = VOICES + official
    if body.voice not in allowed or (body.fallback and body.fallback not in allowed):
        raise HTTPException(400, 'Giọng không hợp lệ hoặc chưa được cấu hình.')
    if owner in active_speakers or len(active_speakers) >= 4:
        raise HTTPException(429, 'Giọng nói đang bận. Thử lại sau giây lát.')
    active_speakers.add(owner)
    month, resets = voice_month()

    async def generate(selected):
        if selected in VOICES:
            return await local_speak(Speech(text=body.text, voice=selected), request, owner)
        # Giọng Peto chạy bằng khóa của chủ web: trừ lượt của tài khoản trước khi gọi, trả lại nếu không đọc được.
        if not is_member(owner):
            raise HTTPException(403, GUEST_OFFICIAL)
        used = await db.take_voice_chars(owner, month, len(body.text), VOICE_FREE_CHARS_MONTHLY)
        if used is None:
            raise HTTPException(429, f'Đã hết lượt Giọng Peto tháng này; lượt mới có từ ngày {resets[8:]}/{resets[5:7]}. '
                                     'Bạn vẫn dùng được Máy nhà hoặc khóa của mình.', headers={'X-Peto-Quota': 'exhausted'})
        try:
            audio = await speech_cloud.while_connected(request, speech_cloud.synthesize(body.text, selected))
        except Exception:
            await db.refund_voice_chars(owner, month, len(body.text))
            raise
        return Response(audio, media_type='audio/wav',
                        headers={'Cache-Control': 'no-store', 'X-Peto-Voice-Used': str(used)})

    try:
        try:
            response = await generate(body.voice)
            selected = body.voice
        except HTTPException as error:
            exhausted = (error.headers or {}).get('X-Peto-Quota') == 'exhausted'
            if (error.status_code not in (502, 503, 504) and not exhausted) or not body.fallback \
                    or body.fallback == body.voice:
                raise
            if await request.is_disconnected():
                raise HTTPException(499, 'Đã dừng đọc.')
            selected = body.fallback
            response = await generate(selected)
        response.headers['X-Peto-Voice'] = selected
        return response
    finally:
        active_speakers.discard(owner)


@router.post("/relay")
async def relay(body: Relay, request: Request, owner: str = Depends(current_owner)):
    """Đọc bằng khóa riêng của người dùng cho nguồn trình duyệt không gọi thẳng được (StepFun, Qwen Cloud).

    Khóa đến trong header X-Voice-Key và chỉ đi qua lượt này: không lưu, không ghi nhật ký, không trừ lượt hay ngân
    sách của chủ web. Khách cũng dùng được, vì tiền là của chính khóa đó.
    """
    key = request.headers.get("x-voice-key", "").strip()
    if not key or len(key) > 256 or not key.isascii() or not key.isprintable():
        raise HTTPException(400, "Chưa có khóa hợp lệ của nhà cung cấp này. Nhập khóa trong Cài đặt → Giọng nói.")
    if body.provider not in speech_cloud.RELAY_NAMES:
        raise HTTPException(400, "Nguồn giọng này không đi qua máy chủ Peto.")
    if not body.text.strip() or not RELAY_TEXT.match(body.voice) or (body.model and not RELAY_TEXT.match(body.model)):
        raise HTTPException(400, "Mã giọng, model hoặc nội dung không hợp lệ.")
    if body.region not in speech_cloud.QWEN_ENDPOINTS:
        raise HTTPException(400, "Vùng không hợp lệ.")
    if owner in active_speakers or len(active_speakers) >= 4:
        raise HTTPException(429, "Giọng nói đang bận. Thử lại sau giây lát.")
    active_speakers.add(owner)
    try:
        audio = await speech_cloud.while_connected(request, speech_cloud.relay(
            body.provider, key, body.text, body.voice.strip(), body.model, body.region))
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    finally:
        active_speakers.discard(owner)


async def local_speak(body: Speech, request: Request, owner: str):
    if body.voice not in VOICES or not body.text.strip():
        raise HTTPException(400, "Giọng hoặc nội dung không hợp lệ.")
    if time.monotonic() - last_seen >= 15:
        raise HTTPException(503, "Máy tạo giọng đang ngoại tuyến. Bạn vẫn có thể chat chữ.")
    if len(jobs) >= 4 or any(job["owner"] == owner for job in jobs.values()):
        raise HTTPException(429, "Máy tạo giọng đang bận. Thử lại sau giây lát.")
    key = uuid.uuid4().hex
    future = asyncio.get_running_loop().create_future()
    jobs[key] = {"owner": owner, "body": body.model_dump(), "future": future, "claimed": False}
    deadline = time.monotonic() + TIMEOUT
    try:
        while not future.done():
            if await request.is_disconnected():
                raise HTTPException(499, "Đã dừng chờ giọng nói.")
            if time.monotonic() > deadline:
                raise HTTPException(504, "Tạo giọng quá lâu. Hãy thử lại.")
            await asyncio.wait({future}, timeout=0.25)
        audio = future.result()
        if audio is None:
            raise HTTPException(503, "Máy tạo giọng chưa đọc được câu này. Hãy thử lại.")
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    finally:
        jobs.pop(key, None)
        future.cancel()


@router.post("/worker/heartbeat", dependencies=[Depends(worker_auth)])
async def heartbeat():
    global last_seen
    last_seen = time.monotonic()
    return {"ok": True}


@router.get("/worker/next", dependencies=[Depends(worker_auth)])
async def next_job():
    for key, job in jobs.items():
        if not job["claimed"]:
            job["claimed"] = True
            return {"id": key, **job["body"]}
    return Response(status_code=204)


@router.post("/worker/result/{key}", dependencies=[Depends(worker_auth)])
async def result(key: str, request: Request):
    job = jobs.get(key)
    if not job or not job["claimed"] or job["future"].done():
        raise HTTPException(404, "Lượt đọc đã kết thúc.")
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO:
            raise HTTPException(413, "Âm thanh quá lớn.")
    failed = request.headers.get("x-voice-error") == "1"
    if not failed and (len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE"):
        raise HTTPException(400, "Âm thanh không hợp lệ.")
    if not job["future"].done():
        job["future"].set_result(None if failed else bytes(audio))
    return {"ok": True}
