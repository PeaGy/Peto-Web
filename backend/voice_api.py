"""Chuyển việc tạo giọng tới máy chủ nhà qua kết nối HTTPS chủ động."""
import asyncio
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from auth import current_owner
import speech_cloud

router = APIRouter(prefix="/api/voice")
VOICES = ["playful-1", "gentle-2"]
TIMEOUT = 120
MAX_AUDIO = 8 * 1024 * 1024
jobs: dict = {}
last_seen = 0.0
active_speakers: set[str] = set()


def worker_auth(request: Request):
    token = os.environ.get("PETO_VOICE_WORKER_TOKEN", "")
    if len(token) < 32 or not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        raise HTTPException(401, "Kết nối tạo giọng chưa được xác thực.")


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    voice: str
    fallback: str | None = None


@router.get("/health")
async def health(owner: str = Depends(current_owner)):
    ready = time.monotonic() - last_seen < 15
    voices = speech_cloud.catalog() + (VOICES if ready else [])
    return {"ok": bool(voices), "voices": voices}


@router.post("/speak")
async def speak(body: Speech, request: Request, owner: str = Depends(current_owner)):
    if not body.text.strip():
        raise HTTPException(400, 'Nội dung không hợp lệ.')
    allowed = VOICES + speech_cloud.catalog()
    if body.voice not in allowed or (body.fallback and body.fallback not in allowed):
        raise HTTPException(400, 'Giọng không hợp lệ hoặc chưa được cấu hình.')
    if owner in active_speakers or len(active_speakers) >= 4:
        raise HTTPException(429, 'Giọng nói đang bận. Thử lại sau giây lát.')
    active_speakers.add(owner)
    async def generate(selected):
        if selected in VOICES:
            return await local_speak(Speech(text=body.text, voice=selected), request, owner)
        audio = await speech_cloud.while_connected(request, speech_cloud.synthesize(body.text, selected))
        return Response(audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})
    try:
        try:
            response = await generate(body.voice)
            selected = body.voice
        except HTTPException as error:
            if error.status_code not in (502, 503, 504) or not body.fallback or body.fallback == body.voice:
                raise
            if await request.is_disconnected():
                raise HTTPException(499, 'Đã dừng đọc.')
            selected = body.fallback
            response = await generate(selected)
        response.headers['X-Peto-Voice'] = selected
        return response
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
