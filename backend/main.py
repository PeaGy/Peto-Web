"""API của Peto Web.

Chat chữ, lịch sử riêng từng người, stream câu trả lời qua SSE.

Danh tính đến từ đăng nhập Discord OAuth (``auth.py``); ``owner`` có dạng
``discord:<id>`` và mọi truy vấn hội thoại đều lọc theo nó ở backend.

Nếu Memory Gateway của bot được bật, prompt sẽ được ghép thêm trí nhớ dài hạn
của đúng người đang đăng nhập — một chiều, chỉ đọc, và hỏng thì bỏ qua.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import auth
import db
import static_files
from ai import ChatMessage, ProviderError, get_provider
from ai.routing import choose_effort
from auth import current_owner
from config import (
    ALLOWED_DISCORD_IDS,
    ALLOWED_ORIGINS,
    MAX_HISTORY_MESSAGES,
    MAX_INPUT_CHARS,
    MEMORY_GATEWAY_TOKEN,
    MEMORY_GATEWAY_URL,
    RESPONSE_TIMEOUTS,
    STATIC_DIR,
    discord_id_from_owner,
)
from discord_memory import discord_memory
from persona import SYSTEM_PROMPT, build_memory_context
from rate_limit import AdmissionDenied, admission

logger = logging.getLogger("peto_web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    logger.info("Peto Web sẵn sàng — provider=%s", get_provider().name)
    if not auth.is_configured():
        logger.warning("Chưa cấu hình Discord OAuth — chưa ai đăng nhập được.")
    elif not ALLOWED_DISCORD_IDS:
        logger.warning(
            "PETO_ALLOWED_DISCORD_IDS đang rỗng — mọi lượt đăng nhập sẽ bị từ chối."
        )

    # Cấu hình nửa vời rất dễ xảy ra và trước đây im lặng hoàn toàn: đặt URL mà
    # quên token thì trí nhớ tắt lặng lẽ, người dùng chỉ thấy "Peto không nhớ gì".
    if discord_memory.enabled:
        logger.info("Trí nhớ từ Discord: BẬT (%s)", discord_memory.base_url)
    elif MEMORY_GATEWAY_URL or MEMORY_GATEWAY_TOKEN:
        missing = "PETO_MEMORY_GATEWAY_TOKEN" if not MEMORY_GATEWAY_TOKEN else "PETO_MEMORY_GATEWAY_URL"
        logger.warning(
            "Trí nhớ từ Discord: TẮT vì thiếu %s. Peto sẽ không nhớ gì từ bot.",
            missing,
        )
    else:
        logger.info("Trí nhớ từ Discord: tắt (chưa cấu hình).")
    yield


app = FastAPI(title="Peto Web", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(auth.router)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"ok": True, "provider": get_provider().name}


@app.get("/api/conversations")
async def list_conversations(owner: str = Depends(current_owner)) -> dict:
    return {"conversations": await db.list_conversations(owner)}


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str, owner: str = Depends(current_owner)
) -> dict:
    if not await db.owns_conversation(owner, conversation_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return {"messages": await db.get_messages(owner, conversation_id)}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, owner: str = Depends(current_owner)
) -> dict:
    if not await db.delete_conversation(owner, conversation_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return {"deleted": True}


async def _build_system_prompt(owner: str) -> str:
    """Prompt gốc, ghép thêm trí nhớ từ Discord nếu lấy được.

    Trí nhớ chỉ được tra bằng Discord ID lấy từ phiên đã xác minh — không bao
    giờ từ dữ liệu do trình duyệt gửi lên. Lấy không được thì bỏ qua, chat vẫn
    chạy bình thường.
    """
    user = await db.get_user(owner)
    if not user:
        return SYSTEM_PROMPT

    discord_id = discord_id_from_owner(owner)
    snapshot = await discord_memory.fetch(discord_id) if discord_id else None

    context = build_memory_context(
        display_name=user.get("display_name") or user.get("username") or "",
        summary=snapshot.summary if snapshot else "",
        explicit=snapshot.explicit if snapshot else (),
    )
    return f"{SYSTEM_PROMPT}\n\n{context}" if context else SYSTEM_PROMPT


async def _stream_reply(
    system_prompt: str, history: list[ChatMessage], effort: str
) -> AsyncIterator[str]:
    """Gọi provider một lần, có timeout theo effort. Trả về từng mảnh text."""
    provider = get_provider()
    timeout = RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    async with asyncio.timeout(timeout):
        async for chunk in provider.stream(
            system_prompt=system_prompt, messages=history, effort=effort
        ):
            yield chunk


@app.post("/api/chat")
async def chat(request: ChatRequest, owner: str = Depends(current_owner)):
    text = request.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Tin nhắn quá dài (tối đa {MAX_INPUT_CHARS} ký tự)",
        )

    if request.conversation_id:
        conversation_id = request.conversation_id
        if not await db.owns_conversation(owner, conversation_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    else:
        conversation_id = await db.create_conversation(owner)

    await db.add_message(conversation_id, "user", text)
    await db.set_title_if_empty(conversation_id, text)

    history = [
        ChatMessage(role=row["role"], content=row["content"])
        for row in await db.get_messages(
            owner, conversation_id, limit=MAX_HISTORY_MESSAGES
        )
    ]
    effort = choose_effort(text)
    system_prompt = await _build_system_prompt(owner)

    async def event_stream() -> AsyncIterator[str]:
        yield sse({"type": "meta", "conversation_id": conversation_id, "effort": effort})

        collected: list[str] = []
        try:
            async with admission.slot(owner):
                try:
                    async for chunk in _stream_reply(system_prompt, history, effort):
                        collected.append(chunk)
                        yield sse({"type": "delta", "text": chunk})
                except TimeoutError:
                    # Chat thường được thử lại đúng 1 lần, và chỉ khi chưa kịp
                    # phát ra chữ nào — giống cách bot Discord giới hạn retry.
                    if collected or effort != "low":
                        raise
                    logger.warning("Timeout effort=low — thử lại 1 lần")
                    async for chunk in _stream_reply(
                        system_prompt, history, effort
                    ):
                        collected.append(chunk)
                        yield sse({"type": "delta", "text": chunk})
        except AdmissionDenied as denied:
            yield sse({"type": "error", "message": denied.message})
            return
        except ProviderError as err:
            logger.warning("Provider lỗi: %s", err)
            yield sse({"type": "error", "message": str(err)})
            return
        except TimeoutError:
            logger.warning("Timeout sau %ss (effort=%s)", RESPONSE_TIMEOUTS[effort], effort)
            yield sse(
                {"type": "error", "message": "Peto nghĩ lâu quá nên bỏ lượt này. Thử lại nha."}
            )
            return
        except asyncio.CancelledError:
            # Người dùng đóng tab hoặc bấm dừng: giữ lại phần đã trả lời.
            if collected:
                await db.add_message(conversation_id, "assistant", "".join(collected))
            raise
        except Exception:
            logger.exception("Lỗi không mong đợi khi gọi AI")
            yield sse(
                {"type": "error", "message": "Có lỗi ở phía máy chủ. Thử lại sau nha."}
            )
            return

        reply = "".join(collected).strip()
        if reply:
            await db.add_message(conversation_id, "assistant", reply)
        yield sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Phải gắn SAU mọi route API, vì nó bắt mọi đường dẫn còn lại.
static_files.mount(app, STATIC_DIR)
