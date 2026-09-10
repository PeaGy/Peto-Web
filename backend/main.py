"""API của Peto Web.

Chat chữ, lịch sử riêng từng người, stream câu trả lời qua SSE.

Danh tính đến từ ``auth.py``: Discord, Google, hoặc khách. ``owner`` có dạng
``<provider>:<id>`` và mọi truy vấn hội thoại đều lọc theo nó ở backend.

Nếu Memory Gateway của bot được bật, prompt sẽ được ghép thêm trí nhớ dài hạn
của đúng người đang đăng nhập — một chiều, chỉ đọc, và hỏng thì bỏ qua.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pathlib import Path

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import attachments as attachment_lib
import auth
import db
import imagine_api
import static_files
from ai import ChatAttachment, ChatMessage, ProviderError, StreamChunk, get_provider
from ai.routing import choose_effort
from attachments import AttachmentError
from app_identity import get_app_identity
from auth import current_owner
from chat_tools import ToolInputError, resolve_timezone, time_context
from config import (
    ALLOWED_ORIGINS,
    MAX_ATTACHMENTS,
    MAX_HISTORY_IMAGES,
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
    resolve_timezone()  # Báo lỗi cấu hình sớm nếu thiếu dữ liệu múi giờ.
    await db.init_db()
    logger.info("Peto Web sẵn sàng — provider=%s", get_provider().name)
    mo = [name for name, ready in auth.available_providers().items() if ready]
    logger.info("Cách đăng nhập đang bật: %s", ", ".join(mo))
    # Không còn allowlist: nói thẳng ở log để người vận hành không tưởng nhầm
    # đây vẫn là bản riêng tư.
    logger.warning(
        "Đăng ký mở: bất kỳ ai mở được địa chỉ này đều dùng được và đều "
        "tiêu quota AI của máy chủ."
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
app.include_router(imagine_api.router)


class AttachmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    mime: str = Field(default="", max_length=120)
    data: str = Field(min_length=8)


class ChatRequest(BaseModel):
    message: str = ""
    conversation_id: str | None = None
    effort: str | None = None
    timezone: str | None = Field(default=None, max_length=100)
    attachments: list[AttachmentIn] = Field(default_factory=list)


ALLOWED_EFFORTS = {"auto", "low", "medium", "high"}


def _public_attachment(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["filename"],
        "mime": row["mime"],
        "kind": row["kind"],
        "size": row["size"],
        "url": f"/api/attachments/{row['id']}",
    }


def _public_message(row: dict) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "status": row.get("status", "complete"),
        "created_at": row["created_at"],
        "attachments": [_public_attachment(item) for item in row.get("attachments") or []],
    }


def _resolve_effort(requested: str | None, text: str) -> str:
    value = (requested or "auto").strip().lower()
    if value not in ALLOWED_EFFORTS:
        raise HTTPException(
            status_code=400,
            detail="Mức suy nghĩ phải là auto, low, medium hoặc high",
        )
    return choose_effort(text) if value == "auto" else value


def _title_from(text: str, files: list[attachment_lib.ValidatedAttachment]) -> str:
    cleaned = " ".join(text.split())
    if cleaned:
        return cleaned
    if not files:
        return ""
    first = files[0]
    prefix = "Ảnh" if first.kind == "image" else "Tệp"
    return f"{prefix}: {first.name}"


def _to_chat_messages(rows: list[dict]) -> list[ChatMessage]:
    image_ids: list[str] = []
    for row in reversed(rows):
        for item in row.get("attachments") or []:
            if item.get("kind") == "image":
                image_ids.append(item["id"])
                if len(image_ids) >= MAX_HISTORY_IMAGES:
                    break
        if len(image_ids) >= MAX_HISTORY_IMAGES:
            break
    load_images = set(image_ids)

    out: list[ChatMessage] = []
    for row in rows:
        attached: list[ChatAttachment] = []
        for item in row.get("attachments") or []:
            data_url = ""
            excerpt = ""
            path = item.get("path")
            try:
                if item.get("kind") == "image" and item["id"] in load_images and path:
                    data_url = attachment_lib.as_data_url(path, item["mime"])
                elif item.get("kind") == "file" and path:
                    excerpt = attachment_lib.read_text_excerpt(path, item["mime"])
            except OSError:
                logger.warning("Không đọc được tệp đính kèm %s", item.get("id"))
            attached.append(
                ChatAttachment(
                    kind=item["kind"],
                    name=item["filename"],
                    mime=item["mime"],
                    data_url=data_url,
                    text_excerpt=excerpt,
                )
            )
        out.append(
            ChatMessage(
                role=row["role"],
                content=row["content"],
                attachments=tuple(attached),
            )
        )
    return out


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"ok": True, "provider": get_provider().name}


@app.get("/api/app-info")
async def app_info() -> dict:
    """Tên và avatar của Peto, lấy từ chính Discord application.

    Không yêu cầu đăng nhập vì màn hình đăng nhập cũng cần hiển thị, và nội
    dung trả về vốn đã là thông tin công khai của application.
    """
    return await get_app_identity()


@app.get("/api/conversations")
async def list_conversations(
    owner: str = Depends(current_owner),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    rows = await db.list_conversations(owner, limit=limit + 1, offset=offset)
    return {"conversations": rows[:limit], "has_more": len(rows) > limit}


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str, owner: str = Depends(current_owner)
) -> dict:
    if not await db.owns_conversation(owner, conversation_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    rows = await db.get_messages(owner, conversation_id)
    return {"messages": [_public_message(row) for row in rows]}


@app.get("/api/attachments/{attachment_id}")
async def get_attachment(attachment_id: str, owner: str = Depends(current_owner)):
    record = await db.get_attachment(owner, attachment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")
    path = Path(record["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")
    inline = record["kind"] == "image"
    return FileResponse(
        path,
        media_type=record["mime"],
        filename=record["filename"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


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


def _as_chunk(item: str | StreamChunk) -> StreamChunk:
    if isinstance(item, StreamChunk):
        return item
    return StreamChunk("text", item)


async def _stream_reply(
    system_prompt: str, history: list[ChatMessage], effort: str, timezone: str | None = None
) -> AsyncIterator[StreamChunk]:
    """Gọi provider một lần, có timeout theo effort. Trả về từng mảnh stream."""
    provider = get_provider()
    timeout = RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    async with asyncio.timeout(timeout):
        async for chunk in provider.stream(
            system_prompt=f"{system_prompt}\n\n{time_context(timezone)}",
            messages=history, effort=effort, timezone=timezone,
        ):
            yield _as_chunk(chunk)


@app.post("/api/chat")
async def chat(request: ChatRequest, owner: str = Depends(current_owner)):
    try:
        timezone = resolve_timezone(request.timezone)
    except ToolInputError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    text = request.message.strip()
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Tin nhắn quá dài (tối đa {MAX_INPUT_CHARS} ký tự)",
        )
    if len(request.attachments) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Mỗi tin chỉ gửi tối đa {MAX_ATTACHMENTS} tệp",
        )

    try:
        files = attachment_lib.validate_batch(
            [item.model_dump() for item in request.attachments]
        )
    except AttachmentError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    if not text and not files:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")

    effort = _resolve_effort(request.effort, text)

    if request.conversation_id:
        conversation_id = request.conversation_id
        if not await db.owns_conversation(owner, conversation_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")

    async def event_stream() -> AsyncIterator[str]:
        conversation_id = request.conversation_id
        collected: list[str] = []
        complete = False
        failure: str | None = None
        try:
            async with admission.slot(owner):
                # Từ chối cooldown/hàng chờ trước khi ghi bất kỳ tin nhắn nào.
                if conversation_id and not await db.owns_conversation(owner, conversation_id):
                    raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
                with anyio.CancelScope(shield=True):
                    if not conversation_id:
                        conversation_id = await db.create_conversation(owner)
                    saved_paths: list[Path] = []
                    try:
                        message_id = await db.add_message(conversation_id, "user", text)
                        for item in files:
                            attachment_id, path = attachment_lib.write_file(conversation_id, item)
                            saved_paths.append(path)
                            await db.add_attachment(
                                attachment_id=attachment_id, owner=owner,
                                conversation_id=conversation_id, message_id=message_id,
                                filename=item.name, mime=item.mime, kind=item.kind,
                                size=len(item.data), path=str(path),
                            )
                    except Exception:
                        attachment_lib.delete_files(saved_paths)
                        raise
                    await db.set_title_if_empty(conversation_id, _title_from(text, files))
                    rows = await db.get_messages(owner, conversation_id, limit=MAX_HISTORY_MESSAGES)
                stored_user = next(row for row in rows if row["id"] == message_id)
                yield sse({
                    "type": "meta", "conversation_id": conversation_id, "effort": effort,
                    "message": _public_message(stored_user),
                })
                history = _to_chat_messages(rows)
                system_prompt = await _build_system_prompt(owner)
                try:
                    async for chunk in _stream_reply(system_prompt, history, effort, timezone):
                        if chunk.kind == "thinking":
                            yield sse({"type": "thinking", "text": chunk.text})
                            continue
                        collected.append(chunk.text)
                        yield sse({"type": "delta", "text": chunk.text})
                except TimeoutError:
                    # Chat thường được thử lại đúng 1 lần, và chỉ khi chưa kịp
                    # phát ra chữ nào — giống cách bot Discord giới hạn retry.
                    if collected or effort != "low":
                        raise
                    logger.warning("Timeout effort=low — thử lại 1 lần")
                    async for chunk in _stream_reply(
                        system_prompt, history, effort, timezone
                    ):
                        if chunk.kind == "thinking":
                            yield sse({"type": "thinking", "text": chunk.text})
                            continue
                        collected.append(chunk.text)
                        yield sse({"type": "delta", "text": chunk.text})
                complete = bool("".join(collected).strip())
                if not complete:
                    failure = "Peto chưa trả lời được lượt này. Nhắn lại giúp nha."
        except AdmissionDenied as denied:
            failure = denied.message
        except ProviderError as err:
            logger.warning("Provider lỗi: %s", err)
            failure = str(err)
        except TimeoutError:
            logger.warning("Timeout sau %ss (effort=%s)", RESPONSE_TIMEOUTS[effort], effort)
            failure = "Peto nghĩ lâu quá nên dừng lượt này. Phần đã trả lời được giữ lại."
        except Exception:
            logger.exception("Lỗi không mong đợi khi gọi AI")
            failure = "Có lỗi ở phía máy chủ. Thử lại sau nha."
        finally:
            # Cả timeout/lỗi lẫn đóng tab đều giữ phần đã phát. Shield tránh
            # cancel scope của StreamingResponse hủy luôn thao tác lưu SQLite.
            reply = "".join(collected).strip()
            if reply and conversation_id:
                with anyio.CancelScope(shield=True):
                    if await db.owns_conversation(owner, conversation_id):
                        await db.add_message(
                            conversation_id, "assistant", reply,
                            status="complete" if complete else "incomplete",
                        )
        if failure:
            yield sse({"type": "error", "message": failure})
        else:
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
