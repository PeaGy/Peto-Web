"""Cổng kiểu OpenAI Chat Completions cho bộ não AIRI chạy trong trình duyệt (thử nghiệm, 15/11/2026).

Bản AIRI stage-web phục vụ ở ``/airi/`` tự dựng prompt, phiên và thẻ nhân vật ngay trong trình duyệt; máy chủ chỉ là
điểm gọi model. Cổng này nhận đúng hình dạng Chat Completions mà provider "OpenAI Compatible" của AIRI gửi
(``@xsai/stream-text``), vì AIRI đã có sẵn đường đó: không phải viết thêm gì phía trình duyệt ngoài địa chỉ.

- Xác thực bằng cookie phiên Peto, đúng như ``POST /api/chat`` (``current_owner``): chưa đăng nhập là 401. Không có
  mã thiết bị, không tính hạn mức bước của Peto Agent.
- Cả lượt chạy trong ``admission.slot(owner)`` như Chat, nên giới hạn đồng thời và thời gian chờ là một.
- Luôn dùng model mặc định (Peto) qua ``ai.get_provider``; system prompt là của AIRI gửi lên, máy chủ luôn nối thêm
  ``COMPANION_CARD_RULE`` (luật cố định dưới 18 tuổi mà thẻ nhân vật Companion đã dùng).
- Chỉ chữ: không công cụ, không tra web, không ảnh. Không lưu gì vào database, không ghi nội dung tin vào log.
- Không có khóa nào của máy chủ đi xuống trình duyệt: phản hồi chỉ có chữ do model sinh.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ai import ChatMessage, ProviderError, StreamChunk, get_provider
from ai import models as ai_models
from core.config import RESPONSE_TIMEOUTS, TURN_TIMEOUT_SECONDS
from core.rate_limit import AdmissionDenied, admission
from features.accounts.auth import current_owner
from prompts import COMPANION_CARD_RULE

logger = logging.getLogger("peto_web.airi")
router = APIRouter(prefix="/api/companion/v1")

MODEL_ID = "peto"
# Trần đầu vào của một lượt: AIRI gửi cả lịch sử cùng system prompt dài (thẻ nhân vật, mô-đun) mỗi lượt.
MAX_MESSAGES = 200
MAX_TOTAL_CHARS = 200_000
MAX_BODY_BYTES = 1_000_000


def _error(status: int, message: str, kind: str = "invalid_request_error") -> JSONResponse:
    """Lỗi theo hình dạng OpenAI (``{"error": {...}}``) để thư viện phía AIRI đọc được."""
    return JSONResponse({"error": {"message": message, "type": kind, "code": status}}, status_code=status)


def _text_of(content: object) -> str:
    """Chữ của một tin: chuỗi, hoặc mảng phần nội dung (chỉ lấy phần ``text``; ảnh, âm thanh bị bỏ)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content
                 if isinstance(part, dict) and part.get("type") in ("text", "input_text") and isinstance(part.get("text"), str)]
        return "\n".join(part for part in parts if part)
    return ""


def _convert(messages: object) -> tuple[str, list[ChatMessage]]:
    """Tách system prompt của AIRI và lịch sử user/assistant. Sai hình dạng thì HTTP 400 bằng lời tiếng Việt."""
    if not isinstance(messages, list) or not messages:
        raise HTTPException(400, "Thiếu danh sách tin nhắn.")
    if len(messages) > MAX_MESSAGES:
        raise HTTPException(400, f"Quá nhiều tin nhắn trong một lượt (tối đa {MAX_MESSAGES}).")
    system: list[str] = []
    history: list[ChatMessage] = []
    total = 0
    for item in messages:
        if not isinstance(item, dict):
            raise HTTPException(400, "Tin nhắn không hợp lệ.")
        role = item.get("role")
        text = _text_of(item.get("content"))
        total += len(text)
        if role in ("system", "developer"):
            if text.strip():
                system.append(text)
        elif role in ("user", "assistant"):
            if text.strip():
                history.append(ChatMessage(role, text))
        elif role == "tool":
            # Bản thử chỉ có chữ: kết quả công cụ (nếu AIRI tự chạy công cụ phía trình duyệt) đi lại như lời người dùng.
            if text.strip():
                history.append(ChatMessage("user", f"[Kết quả công cụ]\n{text}"))
        else:
            raise HTTPException(400, "Vai trò tin nhắn không hợp lệ.")
    if total > MAX_TOTAL_CHARS:
        raise HTTPException(400, f"Lượt này quá dài (tối đa {MAX_TOTAL_CHARS} ký tự).")
    if not history or history[-1].role != "user":
        raise HTTPException(400, "Tin cuối cùng phải là của người dùng.")
    system_prompt = "\n\n".join([*system, COMPANION_CARD_RULE])
    return system_prompt, history


async def _text_stream(system_prompt: str, history: list[ChatMessage]) -> AsyncIterator[str]:
    """Gọi model mặc định một lần, chỉ chuyển phần chữ; dừng khi im lặng quá lâu hay cả lượt quá dài như Chat."""
    provider = get_provider(ai_models.DEFAULT_MODEL)
    idle = RESPONSE_TIMEOUTS.get("low", 120.0)
    loop = asyncio.get_running_loop()
    hard = loop.time() + TURN_TIMEOUT_SECONDS
    async with asyncio.timeout_at(min(loop.time() + idle, hard)) as limit:
        operation = provider.stream(system_prompt=system_prompt, messages=history, effort="low",
                                    timezone=None, web_search="off", tools_enabled=False)
        async with aclosing(operation) as stream:
            async for item in stream:
                limit.reschedule(min(loop.time() + idle, hard))
                chunk = item if isinstance(item, StreamChunk) else StreamChunk("text", item)
                if chunk.kind == "text" and chunk.text:
                    yield chunk.text


def _failure(error: BaseException) -> tuple[int, str]:
    if isinstance(error, AdmissionDenied):
        return 429, error.message
    if isinstance(error, ProviderError):
        logger.warning("Provider lỗi (AIRI): %s", error)
        return 502, str(error)
    if isinstance(error, TimeoutError):
        return 504, "Peto chờ quá lâu mà dịch vụ AI không gửi gì thêm nên dừng lượt này."
    logger.exception("Lỗi không mong đợi ở cổng AIRI", exc_info=error)
    return 500, "Có lỗi ở phía máy chủ. Thử lại sau nha."


def _chunk(completion_id: str, created: int, delta: dict, finish: str | None = None) -> str:
    body = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return "data: " + json.dumps(body, ensure_ascii=False) + "\n\n"


@router.get("/models")
async def list_models(owner: str = Depends(current_owner)) -> dict:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "peto"}]}


@router.post("/chat/completions")
async def chat_completions(request: Request, owner: str = Depends(current_owner)):
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return _error(413, "Yêu cầu quá lớn.")
    try:
        body = json.loads(raw or b"null")
    except ValueError:
        return _error(400, "Thân yêu cầu không phải JSON.")
    if not isinstance(body, dict):
        return _error(400, "Thân yêu cầu không hợp lệ.")
    try:
        system_prompt, history = _convert(body.get("messages"))
    except HTTPException as error:
        return _error(error.status_code, str(error.detail))
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    started = time.perf_counter()

    def log_turn(outcome: str, chars: int) -> None:
        # Chỉ số đo, không nội dung tin.
        logger.info("airi_turn outcome=%s messages=%d reply_chars=%d total_ms=%d", outcome, len(history), chars,
                    round((time.perf_counter() - started) * 1000))

    if not body.get("stream"):
        parts: list[str] = []
        try:
            async with admission.slot(owner):
                async for text in _text_stream(system_prompt, history):
                    parts.append(text)
        except Exception as error:  # noqa: BLE001 - mọi lỗi đều thành lời báo cho trình duyệt
            status, message = _failure(error)
            log_turn("error", 0)
            return _error(status, message, "rate_limit_error" if status == 429 else "server_error")
        reply = "".join(parts)
        log_turn("complete", len(reply))
        return {"id": completion_id, "object": "chat.completion", "created": created, "model": MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]}

    async def events() -> AsyncIterator[str]:
        chars = 0
        try:
            async with admission.slot(owner):
                yield _chunk(completion_id, created, {"role": "assistant", "content": ""})
                async for text in _text_stream(system_prompt, history):
                    chars += len(text)
                    yield _chunk(completion_id, created, {"content": text})
        except Exception as error:  # noqa: BLE001
            status, message = _failure(error)
            log_turn("error", chars)
            yield "data: " + json.dumps({"error": {"message": message, "type": "server_error", "code": status}},
                                        ensure_ascii=False) + "\n\n"
            return
        log_turn("complete", chars)
        yield _chunk(completion_id, created, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
