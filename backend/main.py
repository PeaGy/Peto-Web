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
from typing import Literal

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import attachments as attachment_lib
import auth
import db
import document_reader
import imagine_api
import profile_api
import static_files
import titles
from ai import ChatAttachment, ChatMessage, ProviderError, StreamChunk, get_provider
from ai.routing import choose_effort
from attachments import AttachmentError
from app_identity import get_app_identity
from auth import current_owner
from chat_tools import resolve_browser_timezone, resolve_timezone, time_context
from config import (
    ALLOWED_ORIGINS,
    MAX_ATTACHMENTS,
    MAX_DOCUMENT_CONTEXT_CHARS,
    MAX_HISTORY_IMAGES,
    MAX_HISTORY_MESSAGES,
    MAX_INPUT_CHARS,
    MEMORY_GATEWAY_TOKEN,
    MEMORY_GATEWAY_URL,
    RESPONSE_TIMEOUTS,
    STATIC_DIR,
    WEB_SEARCH_ENABLED,
    discord_id_from_owner,
)
from discord_memory import discord_memory
from persona import COMPANION_PROMPT, SYSTEM_PROMPT, build_memory_context, build_profile_context
from rate_limit import AdmissionDenied, admission
from web_search import normalize_sources

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
app.include_router(profile_api.router)


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
    web_search: Literal["auto", "on", "off"] = "auto"
    # "companion" khi nhắn từ tab Companion: persona trả lời ngắn bằng tiếng Anh, mạch trò chuyện riêng.
    mode: str = Field(default="chat", max_length=16)


ALLOWED_EFFORTS = {"auto", "low", "medium", "high"}
CONVERSATION_MODES = {"chat", "companion"}


def _public_attachment(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["filename"],
        "mime": row["mime"],
        "kind": row["kind"],
        "size": row["size"],
        "url": f"/api/attachments/{row['id']}",
        "document": document_reader.public_document(row.get("document")),
    }


def _public_message(row: dict) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "status": row.get("status", "complete"),
        "created_at": row["created_at"],
        "attachments": [_public_attachment(item) for item in row.get("attachments") or []],
        "sources": normalize_sources(row.get("sources")),
    }


def _resolve_effort(requested: str | None, text: str) -> str:
    value = (requested or "auto").strip().lower()
    if value not in ALLOWED_EFFORTS:
        raise HTTPException(
            status_code=400,
            detail="Mức suy nghĩ phải là auto, low, medium hoặc high",
        )
    return choose_effort(text) if value == "auto" else value


def _resolve_mode(requested: str) -> str:
    """Tab gửi tin; sai giá trị thì báo lỗi thay vì lặng lẽ coi như tab Trò chuyện."""
    if requested not in CONVERSATION_MODES:
        raise HTTPException(status_code=400, detail="Chế độ trò chuyện không hợp lệ")
    return requested


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
    # Ưu tiên tệp mới; chia đều phần còn lại giữa các tệp cùng một tin nhắn.
    excerpts: dict[str, str] = {}
    remaining = MAX_DOCUMENT_CONTEXT_CHARS
    for row in reversed(rows):
        files = [item for item in row.get("attachments") or [] if item.get("kind") == "file"]
        documents = {item["id"]: document_reader.cached_document(item.get("document")) for item in files}
        lengths = {key: len(document.get("text", "")) if document else 0 for key, document in documents.items()}
        allowances: dict[str, int] = {}
        # Tệp ngắn chỉ lấy phần cần dùng, nhường chỗ còn lại cho tệp dài cùng lượt.
        for index, key in enumerate(sorted(lengths, key=lengths.get)):
            allowances[key] = min(lengths[key], remaining // (len(files) - index))
            remaining -= allowances[key]
        for item in files:
            document = documents[item["id"]]
            if document is None:
                excerpts[item["id"]] = "Tệp chưa được đọc trong lượt này. Không suy đoán nội dung từ tên tệp."
                continue
            text = document.get("text", "")
            excerpt = text[:allowances[item["id"]]]
            notice = document["notice"]
            if len(excerpt) < len(text):
                notice += " Chỉ một phần hoặc không có nội dung tệp trong ngữ cảnh lượt này do tổng tài liệu quá dài. Nói rõ nếu thiếu phần cần hỏi."
            excerpts[item["id"]] = f"[Trạng thái đọc: {notice}]\n{excerpt}"
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
                elif item.get("kind") == "file":
                    excerpt = excerpts[item["id"]]
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
                sources=tuple(normalize_sources(row.get("sources"))),
            )
        )
    return out


async def _read_legacy_documents(owner: str, rows: list[dict], budget: int) -> None:
    """Bổ sung chữ cho tệp cũ khi hỏi tiếp, giới hạn việc đọc lại mỗi lượt."""
    for row in reversed(rows):
        for item in row.get("attachments") or []:
            if item.get("kind") != "file" or document_reader.cached_document(item.get("document")):
                continue
            if budget <= 0:
                return
            budget -= 1
            try:
                data = await anyio.to_thread.run_sync(Path(item["path"]).read_bytes)
                document = await document_reader.read_document(data, item["mime"])
            except OSError:
                document = document_reader.result("unreadable", "Không tìm thấy tệp đã lưu. Hãy gửi lại tài liệu nhé.")
            await db.save_document(owner, item["id"], document)
            item["document"] = document


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


@app.get("/api/companion")
async def get_companion(owner: str = Depends(current_owner)) -> dict:
    """Mạch trò chuyện của tab Companion: cuộc mới nhất cùng các tin gần đây."""
    conversation_id = await db.latest_conversation(owner, "companion")
    if not conversation_id:
        return {"conversation_id": None, "messages": []}
    rows = await db.get_messages(owner, conversation_id, limit=MAX_HISTORY_MESSAGES)
    return {"conversation_id": conversation_id, "messages": [_public_message(row) for row in rows]}


async def _build_system_prompt(owner: str, mode: str = "chat") -> str:
    """Prompt gốc, ghép thêm trí nhớ từ Discord (nếu lấy được), hồ sơ người
    dùng tự điền trong Cài đặt, và persona riêng khi nhắn từ tab Companion.

    Trí nhớ chỉ được tra bằng Discord ID lấy từ phiên đã xác minh — không bao
    giờ từ dữ liệu do trình duyệt gửi lên. Lấy không được thì bỏ qua, chat vẫn
    chạy bình thường.
    """
    mode_block = COMPANION_PROMPT if mode == "companion" else ""
    user = await db.get_user(owner)
    if not user:
        return "\n\n".join(part for part in (SYSTEM_PROMPT, mode_block) if part)

    discord_id = discord_id_from_owner(owner)
    snapshot = await discord_memory.fetch(discord_id) if discord_id else None

    context = build_memory_context(
        display_name=user.get("display_name") or user.get("username") or "",
        summary=snapshot.summary if snapshot else "",
        explicit=snapshot.explicit if snapshot else (),
    )
    # Đọc lại ở MỖI lượt, không đệm: người dùng sửa hồ sơ trong Cài đặt thì
    # ngay tin nhắn kế tiếp đã theo.
    profile = await db.get_profile(owner)
    profile_block = build_profile_context(
        full_name=profile["full_name"],
        nickname=profile["nickname"],
        occupation=profile_api.occupation_label(profile["occupation"]),
        instructions=profile["instructions"],
    )
    # Persona Companion đứng sau trí nhớ và hồ sơ để thắng thói quen trả lời dài bằng tiếng Việt ở trên.
    return "\n\n".join(part for part in (SYSTEM_PROMPT, context, profile_block, mode_block) if part)


def _as_chunk(item: str | StreamChunk) -> StreamChunk:
    if isinstance(item, StreamChunk):
        return item
    return StreamChunk("text", item)


async def _stream_reply(
    system_prompt: str, history: list[ChatMessage], effort: str, timezone: str | None = None, web_search: str = "auto"
) -> AsyncIterator[StreamChunk]:
    """Gọi provider một lần, có timeout theo effort. Trả về từng mảnh stream."""
    provider = get_provider()
    timeout = RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    async with asyncio.timeout(timeout):
        async for chunk in provider.stream(
            system_prompt=f"{system_prompt}\n\n{time_context(timezone)}",
            messages=history, effort=effort, timezone=timezone,
            web_search=web_search,
        ):
            yield _as_chunk(chunk)


@app.post("/api/chat")
async def chat(request: ChatRequest, owner: str = Depends(current_owner)):
    if request.web_search == "on" and not WEB_SEARCH_ENABLED:
        raise HTTPException(400, "Tìm kiếm web đang tắt trên máy chủ. Chọn Tự động hoặc Tắt để tiếp tục chat.")
    timezone = resolve_browser_timezone(request.timezone)
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
    mode = _resolve_mode(request.mode)
    web_search = request.web_search
    if mode == "companion":
        if files:
            raise HTTPException(status_code=400, detail="Companion chưa nhận ảnh hay tệp đính kèm")
        # Companion phải trả lời thật nhanh để kịp đọc thành tiếng: suy nghĩ ít, không tìm web.
        effort = "low"
        web_search = "off"

    if request.conversation_id:
        existing_mode = await db.conversation_mode(owner, request.conversation_id)
        if existing_mode is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
        if existing_mode != mode:
            raise HTTPException(status_code=400, detail="Hội thoại này thuộc tab khác")

    async def event_stream() -> AsyncIterator[str]:
        conversation_id = request.conversation_id
        collected: list[str] = []
        sources: list[dict] = []
        search_started = False

        def chunk_event(chunk: StreamChunk) -> str:
            nonlocal sources, search_started
            if chunk.kind == "search":
                search_started = True
                return sse({"type": "search", "status": chunk.text})
            if chunk.kind == "sources":
                sources = normalize_sources([*sources, *chunk.sources])
                search_started = True
                return sse({"type": "sources", "sources": sources})
            if chunk.kind == "thinking":
                return sse({"type": "thinking", "text": chunk.text})
            collected.append(chunk.text)
            return sse({"type": "delta", "text": chunk.text})

        complete = False
        failure: str | None = None
        # Lượt đặt tên hội thoại, chạy song song với câu trả lời (xem titles.py).
        title_task: asyncio.Task[str] | None = None
        try:
            async with admission.slot(owner):
                # Từ chối cooldown/hàng chờ trước khi ghi bất kỳ tin nhắn nào.
                if conversation_id and not await db.owns_conversation(owner, conversation_id):
                    raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
                documents: list[dict | None] = []
                document_count = sum(item.kind == "file" for item in files)
                if document_count:
                    yield sse({"type": "reading", "text": f"Peto đang đọc {document_count} tài liệu…"})
                for item in files:
                    documents.append(await document_reader.read_document(item.data, item.mime) if item.kind == "file" else None)
                # Hội thoại có thể bị xóa trong lúc bộ đọc đang xử lý tệp.
                if conversation_id and not await db.owns_conversation(owner, conversation_id):
                    raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
                is_new_conversation = not conversation_id
                with anyio.CancelScope(shield=True):
                    if not conversation_id:
                        conversation_id = await db.create_conversation(owner, mode=mode)
                    saved_paths: list[Path] = []
                    try:
                        message_id = await db.add_message(conversation_id, "user", text)
                        for item, document in zip(files, documents):
                            attachment_id, path = attachment_lib.write_file(conversation_id, item)
                            saved_paths.append(path)
                            await db.add_attachment(
                                attachment_id=attachment_id, owner=owner,
                                conversation_id=conversation_id, message_id=message_id,
                                filename=item.name, mime=item.mime, kind=item.kind,
                                size=len(item.data), path=str(path),
                                document=document,
                            )
                    except Exception:
                        attachment_lib.delete_files(saved_paths)
                        raise
                    await db.set_title_if_empty(conversation_id, _title_from(text, files))
                    rows = await db.get_messages(owner, conversation_id, limit=MAX_HISTORY_MESSAGES)
                # Tên cắt từ tin nhắn đầu chỉ là tạm. Đặt tên tóm tắt bằng một lượt
                # AI riêng chạy song song với câu trả lời, cuối lượt mới ghi đè.
                # Không có chữ thì chẳng có gì để tóm tắt (lượt đặt tên không xem
                # được ảnh): giữ nguyên tên "Ảnh: ..." cắt tạm.
                # Mạch Companion không hiện ở thanh bên nên khỏi đặt tên, bớt một lượt gọi AI.
                if is_new_conversation and mode == "chat" and text.strip():
                    title_task = asyncio.create_task(
                        titles.suggest_title(text, [item.name for item in files])
                    )
                stored_user = next(row for row in rows if row["id"] == message_id)
                yield sse({
                    "type": "meta", "conversation_id": conversation_id, "effort": effort,
                    "message": _public_message(stored_user),
                })
                if MAX_ATTACHMENTS > document_count and any(
                    item.get("kind") == "file" and not document_reader.cached_document(item.get("document"))
                    for row in rows for item in row.get("attachments") or []
                ):
                    yield sse({"type": "reading", "text": "Peto đang đọc tài liệu đã gửi trước đó…"})
                    await _read_legacy_documents(owner, rows, MAX_ATTACHMENTS - document_count)
                    yield sse({"type": "reading", "text": ""})
                history = await anyio.to_thread.run_sync(_to_chat_messages, rows)
                system_prompt = await _build_system_prompt(owner, mode)
                try:
                    async for chunk in _stream_reply(system_prompt, history, effort, timezone, web_search):
                        yield chunk_event(chunk)
                except TimeoutError:
                    # Chat thường được thử lại đúng 1 lần, và chỉ khi chưa kịp
                    # phát ra chữ nào — giống cách bot Discord giới hạn retry.
                    if collected or search_started or web_search == "on" or effort != "low":
                        raise
                    logger.warning("Timeout effort=low — thử lại 1 lần")
                    async for chunk in _stream_reply(
                        system_prompt, history, effort, timezone, web_search
                    ):
                        yield chunk_event(chunk)
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
                            sources=sources,
                        )
            if title_task is not None:
                # Shield như phần lưu tin nhắn: đóng tab giữa chừng thì tên vẫn
                # kịp ghi, mở lại đã thấy tên tóm tắt.
                with anyio.CancelScope(shield=True):
                    title = await titles.resolve(title_task)
                    if title and conversation_id:
                        await db.set_title(owner, conversation_id, title)
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
