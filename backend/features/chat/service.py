"""Xử lý lượt chat và stream SSE; giữ phần trả lời khi bị ngắt."""

from __future__ import annotations
from starlette.background import BackgroundTask
import asyncio
from time import perf_counter
from collections.abc import AsyncIterator
from pathlib import Path
import anyio
from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from features.agent import install as agent_install
from ai import models as ai_models
from shared import attachment_tools
from shared import attachments as attachment_lib
from features.companion import memory as companion_memory
import storage as db
from features.documents import reader as document_reader
from features.companion import emotion_tags
from features.documents.tools import DocumentSession, current_session as document_session_context
from features.companion import private_notes
from features.chat import titles
from ai import ChatMessage, ProviderError, StreamChunk, get_provider
from ai.routing import choose_effort
from shared.attachments import AttachmentError
from features.accounts.auth import current_owner
from shared.time_tools import resolve_browser_timezone, time_context
from core.config import (
    MAX_ATTACHMENTS,
    MAX_HISTORY_MESSAGES,
    MAX_INPUT_CHARS,
    RESPONSE_TIMEOUTS,
    ROLEPLAY_MAX_HISTORY,
    WEB_SEARCH_ENABLED,
    provider_from_owner,
)
from core.rate_limit import AdmissionDenied, admission
from shared.web_search import normalize_sources, spoken_reply
from features.chat import conversations as conversation_actions
from features.chat.history import (
    _public_message,
    _read_legacy_documents,
    _title_from,
    _to_chat_messages,
    _visible,
)
from features.chat.prompt_context import _build_system_prompt
from features.chat.schemas import (
    ALLOWED_EFFORTS,
    CONVERSATION_MODES,
    CONVERSATION_PERSONAS,
    ChatRequest,
)
from shared.events import sse
import logging

logger = logging.getLogger("peto_web")

def _resolve_effort(requested: str | None, text: str) -> str:
    value = (requested or "auto").strip().lower()
    if value not in ALLOWED_EFFORTS:
        raise HTTPException(
            status_code=400,
            detail="Mức suy nghĩ không hợp lệ.",
        )
    return choose_effort(text) if value == "auto" else value


def _resolve_mode(requested: str) -> str:
    """Tab gửi tin; sai giá trị thì báo lỗi thay vì lặng lẽ coi như tab Trò chuyện."""
    if requested not in CONVERSATION_MODES:
        raise HTTPException(status_code=400, detail="Chế độ trò chuyện không hợp lệ")
    return requested


async def _check_roleplay_start(owner: str, mode: str) -> None:
    """Chỉ mở hội thoại nhập vai (có thể có nội dung 18+) cho tài khoản Discord/Google đã xác nhận đủ 18 tuổi.

    Kiểm ở máy chủ, không tin giao diện: tài khoản khách ai cũng tạo được nên không được bật.
    """
    if mode != "chat":
        raise HTTPException(status_code=400, detail="Tab Companion không dùng chế độ nhập vai.")
    if provider_from_owner(owner) == "guest":
        raise HTTPException(status_code=403, detail="Chế độ nhập vai chỉ dùng được với tài khoản Discord hoặc Google.")
    if not await db.has_roleplay_consent(owner):
        raise HTTPException(status_code=403, detail="Bạn cần xác nhận đủ 18 tuổi trước khi bật chế độ nhập vai.")


def _as_chunk(item: str | StreamChunk) -> StreamChunk:
    if isinstance(item, StreamChunk):
        return item
    return StreamChunk("text", item)


async def _stream_reply(
    system_prompt: str, history: list[ChatMessage], effort: str, timezone: str | None = None, web_search: str = "auto",
    document_session=None, model: str = ai_models.DEFAULT_MODEL, spoken: bool = False,
    files: attachment_tools.AttachmentFiles | None = None,
) -> AsyncIterator[StreamChunk]:
    """Gọi provider của model đã chọn một lần, có timeout theo effort. Trả về từng mảnh stream. ``spoken`` là lượt
    Companion: câu trả lời được đọc thành tiếng, nên chỉ dẫn tra web dặn không chèn đường dẫn hay dấu trích dẫn.
    ``files`` là các tệp của hội thoại mà Peto được tìm/đọc thêm trong lượt này."""
    provider = get_provider(model)
    timeout = RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    token = document_session_context.set(document_session)
    files_token = attachment_tools.current_files.set(files)
    spoken_token = spoken_reply.set(spoken)
    try:
        async with asyncio.timeout(timeout):
            async for chunk in provider.stream(
                system_prompt=f"{system_prompt}\n\n{time_context(timezone)}",
                messages=history, effort=effort, timezone=timezone,
                web_search=web_search,
            ):
                yield _as_chunk(chunk)
    finally:
        spoken_reply.reset(spoken_token)
        attachment_tools.current_files.reset(files_token)
        document_session_context.reset(token)


async def chat(request: ChatRequest, owner: str = Depends(current_owner), http_request: Request = None):
    # FastAPI nhận ra tham số Request qua kiểu khai báo nên luôn truyền vào (đừng đổi thành Request | None). Mặc định
    # None để các test gọi thẳng chat() như trước; khi đó hướng dẫn Peto Agent không kèm tên miền.
    install_command = agent_install.install_command(http_request) if http_request is not None else ""
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

    if request.branch_message_id:
        if not request.conversation_id or request.mode != 'chat' or files:
            raise HTTPException(400, 'Phiên bản cần một hội thoại và tin nhắn đã lưu')
        original = await db.get_messages(owner, request.conversation_id)
        target = next((row for row in original if row['id'] == request.branch_message_id and row['role'] == 'user'), None)
        if target is None:
            raise HTTPException(404, 'Không tìm thấy tin nhắn')
        if not text and not target.get('attachments'):
            raise HTTPException(400, 'Tin nhắn trống')
    if not text and not files and not request.branch_message_id:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")

    effort = _resolve_effort(request.effort, text)
    mode = _resolve_mode(request.mode)
    web_search = request.web_search
    if mode == "companion":
        if files:
            raise HTTPException(status_code=400, detail="Companion chưa nhận ảnh hay tệp đính kèm")
        # Companion phải trả lời thật nhanh để kịp đọc thành tiếng: suy nghĩ ít. Tra web thì Peto tự quyết khi cần (chủ web
        # chọn ngày 2026-09-28, như mô-đun tra web của AIRI), không có kiểu "luôn tìm". Trang gửi "off" khi công tắc Cài
        # đặt → Tra web đang tắt, mà mặc định là tắt.
        effort = "low"
        web_search = "off" if web_search == "off" else "auto"

    if request.persona not in CONVERSATION_PERSONAS:
        raise HTTPException(status_code=400, detail="Chế độ trả lời không hợp lệ")
    persona = request.persona
    if request.conversation_id:
        settings = await db.conversation_settings(owner, request.conversation_id)
        if settings is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
        if settings['archived']:
            raise HTTPException(409, 'Hãy khôi phục hội thoại đã lưu trữ trước khi gửi tin nhắn.')
        if settings["mode"] != mode:
            raise HTTPException(status_code=400, detail="Hội thoại này thuộc tab khác")
        # Chế độ chọn lúc bắt đầu và giữ cả hội thoại, để lịch sử không trộn giọng trợ lý với giọng nhập vai.
        persona = settings["persona"]
    elif persona == "roleplay":
        await _check_roleplay_start(owner, mode)
    history_limit = ROLEPLAY_MAX_HISTORY if persona == "roleplay" else MAX_HISTORY_MESSAGES
    from features.projects.context import context as project_context
    project_id = settings.get('project_id') if request.conversation_id else request.project_id
    if mode != 'chat' and (project_id or request.project_file_ids):
        raise HTTPException(400, 'Dự án chỉ dùng trong tab Trò chuyện')
    if request.conversation_id and request.project_id is not None and request.project_id != project_id:
        raise HTTPException(400, 'Hội thoại thuộc dự án khác; chuyển bằng menu hội thoại trước')
    await project_context(owner, project_id, request.project_file_ids)
    if request.model != ai_models.DEFAULT_MODEL:
        if mode == "companion":
            raise HTTPException(status_code=400, detail="Tab Companion chỉ dùng Peto.")
        # Persona nhập vai có thể có nội dung 18+: không gửi sang tài khoản OpenAI của chủ web.
        if persona == "roleplay":
            raise HTTPException(status_code=400, detail="Chế độ nhập vai chỉ dùng Peto.")
    try:
        model = ai_models.resolve(owner, request.model, "web").key
    except ai_models.ModelUnavailable as err:
        raise HTTPException(status_code=err.status, detail=err.message) from None

    if effort not in ai_models.supported_efforts(model):
        raise HTTPException(status_code=400, detail="Model này không hỗ trợ mức suy nghĩ đã chọn.")

    conversation_id = request.conversation_id
    turn_complete = False

    async def event_stream() -> AsyncIterator[str]:
        nonlocal conversation_id
        started = perf_counter()
        admitted_at = prepared_at = first_text_at = None
        collected: list[str] = []
        sources: list[dict] = []
        search_started = False
        document_session = None
        # Câu trả lời Companion lưu nguyên, nhưng stream về trình duyệt thì bỏ ghi chú riêng và thẻ cảm xúc của Peto;
        # cảm xúc đi riêng bằng sự kiện "emotion" ngay khi thẻ tới, để nhân vật đổi nét mặt lúc Peto bắt đầu trả lời.
        notes = private_notes.NoteFilter() if mode == "companion" else None
        markers = emotion_tags.MarkerFilter() if mode == "companion" else None
        # Cảm xúc đầu tiên của lượt. Tra web thì phần viết trước lúc tra bị bỏ ("replace"), có khi mất luôn thẻ cảm xúc.
        turn_emotion: str | None = None

        def visible_events(text: str, final: bool = False) -> str | None:
            nonlocal turn_emotion
            if notes and markers:
                text = markers.feed(notes.feed(text) + (notes.flush() if final else ""))
                if final:
                    text += markers.flush()
                emotion = markers.take_emotion()
                turn_emotion = turn_emotion or emotion
                events = (sse({"type": "emotion", "emotion": emotion}) if emotion else "") + (
                    sse({"type": "delta", "text": text}) if text else "")
                return events or None
            return sse({"type": "delta", "text": text}) if text else None

        def chunk_event(chunk: StreamChunk) -> str | None:
            nonlocal sources, search_started, first_text_at, notes, markers
            if chunk.kind == 'artifact': return sse({'type': 'artifact', 'artifact': chunk.artifact})
            if chunk.kind == 'document_status': return sse({'type': 'document_status', 'text': chunk.text})
            if chunk.kind in ("file_lookup", "file_lookup_done"):
                return sse({"type": "file_lookup", "text": chunk.text, "live": chunk.kind == "file_lookup"})
            if chunk.kind == "search":
                search_started = True
                return sse({"type": "search", "status": chunk.text})
            if chunk.kind == "sources":
                sources = normalize_sources([*sources, *chunk.sources])
                search_started = True
                return sse({"type": "sources", "sources": sources})
            if chunk.kind == "thinking":
                return sse({"type": "thinking", "text": chunk.text})
            if chunk.kind == "replace":
                collected.clear()
                if notes:
                    notes = private_notes.NoteFilter()
                    markers = emotion_tags.MarkerFilter()
                return sse({"type": "replace"})
            if chunk.text and first_text_at is None:
                first_text_at = perf_counter()
            collected.append(chunk.text)
            return visible_events(chunk.text)

        nonlocal turn_complete
        complete = False
        outcome = "cancelled"
        failure: str | None = None
        try:
            async with admission.slot(owner):
                admitted_at = perf_counter()
                if conversation_id:
                    current_settings = await db.conversation_settings(owner, conversation_id)
                    if current_settings and current_settings['archived']:
                        raise ProviderError('Hội thoại đã được lưu trữ. Hãy khôi phục trước khi gửi tin nhắn.')
                    if not current_settings or current_settings.get('project_id') != project_id:
                        raise ProviderError('Hội thoại đã chuyển dự án hoặc bị xóa. Mở lại trước khi gửi nhé.')
                project_prompt = await project_context(owner, project_id, request.project_file_ids)
                # Từ chối cooldown/hàng chờ trước khi ghi bất kỳ tin nhắn nào.
                if conversation_id and not await db.owns_conversation(owner, conversation_id):
                    raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
                documents: list[dict | None] = []
                document_count = sum(item.kind == "file" for item in files)
                if document_count:
                    yield sse({"type": "reading", "text": f"Peto đang đọc {document_count} tài liệu…"})
                for item in files:
                    documents.append(await document_reader.read_document(item.data, item.mime) if item.kind == "file" else None)
                if document_count:
                    # Thiếu dòng này thì bước "Peto đang đọc…" trong danh sách "Đang làm…" giữ nguyên chữ "đang" tới hết lượt.
                    yield sse({"type": "reading", "text": ""})
                # Hội thoại có thể bị xóa hoặc chuyển dự án trong lúc đang đọc tệp.
                if conversation_id:
                    current_settings = await db.conversation_settings(owner, conversation_id)
                    if current_settings and current_settings['archived']:
                        raise ProviderError('Hội thoại đã được lưu trữ. Hãy khôi phục trước khi gửi tin nhắn.')
                    if not current_settings or current_settings.get('project_id') != project_id:
                        raise ProviderError('Hội thoại đã chuyển dự án hoặc bị xóa. Mở lại trước khi gửi nhé.')
                is_new_conversation = not conversation_id
                with anyio.CancelScope(shield=True):
                    if not conversation_id:
                        conversation_id = await db.create_conversation(owner, mode=mode, persona=persona, project_id=project_id)
                    saved_paths: list[Path] = []
                    try:
                        if request.branch_message_id:
                            conversation_id, message_id = await conversation_actions.fork(owner, conversation_id, request.branch_message_id, text)
                        else:
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
                    rows = await db.get_messages(owner, conversation_id, limit=history_limit)
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
                history, system_prompt = await asyncio.gather(
                    anyio.to_thread.run_sync(_to_chat_messages, rows),
                    _build_system_prompt(owner, mode, install_command, persona, conversation_id,
                        agent_question='\n'.join(str(row.get('content', ''))[:4000]
                            for row in [r for r in rows if r.get('role') == 'user'][-3:])),
                )
                document_session = DocumentSession(owner, conversation_id) if mode == 'chat' else None
                if project_prompt:
                    system_prompt += '\n\n' + project_prompt
                # Tệp trong lịch sử vừa đọc (đã lọc theo chủ tài khoản trong SQL): Peto tìm/đọc thêm được khi cần.
                files_session = attachment_tools.AttachmentFiles(rows) if mode == 'chat' else None
                if request.document_mode and mode == 'chat':
                    system_prompt += '\n\n[PETO_DOCUMENT_CREATE]\nNgười dùng chọn tạo tài liệu: hãy gọi create_document để tạo tệp theo yêu cầu, mặc định DOCX nếu chưa chọn định dạng. Trả lời ngắn sau khi có kết quả; nội dung dài đặt trong công cụ.'
                prepared_at = perf_counter()
                # A timeout may already have consumed provider tokens. Do not repeat the whole turn invisibly.
                async for chunk in _stream_reply(system_prompt, history, effort, timezone, web_search, document_session,
                                                 model, spoken=mode == "companion", files=files_session):
                    event = chunk_event(chunk)
                    if event:
                        yield event
                if notes:
                    tail = visible_events("", final=True)
                    if tail:
                        yield tail
                if document_session and document_session.created and not ''.join(collected).strip():
                    yield chunk_event(StreamChunk('text', 'Đã tạo xong tài liệu. Bạn xem trước hoặc tải tệp bên dưới nhé.'))
                # Một câu trả lời Companion chỉ có ghi chú riêng thì người dùng không thấy gì: coi như chưa trả lời.
                complete = bool(_visible("".join(collected), mode).strip())
                if not complete:
                    outcome = "empty"
                    failure = "Peto chưa trả lời được lượt này. Nhắn lại giúp nha."
                else:
                    outcome = "complete"
        except AdmissionDenied as denied:
            outcome = denied.reason
            failure = denied.message
        except ProviderError as err:
            outcome = "provider_error"
            logger.warning("Provider lỗi: %s", err)
            failure = str(err)
        except TimeoutError:
            outcome = "timeout"
            logger.warning("Timeout sau %ss (effort=%s)", RESPONSE_TIMEOUTS[effort], effort)
            failure = "Peto nghĩ lâu quá nên dừng lượt này. Phần đã trả lời được giữ lại."
        except Exception:
            outcome = "internal_error"
            logger.exception("Lỗi không mong đợi khi gọi AI")
            failure = "Có lỗi ở phía máy chủ. Thử lại sau nha."
        finally:
            ended_at = perf_counter()
            logger.info(
                "chat_timing model=%s effort=%s mode=%s queue_ms=%s prepare_ms=%s first_text_ms=%s total_ms=%d search=%s complete=%s outcome=%s",
                model, effort, mode,
                round((admitted_at - started) * 1000) if admitted_at is not None else None,
                round((prepared_at - admitted_at) * 1000) if prepared_at is not None and admitted_at is not None else None,
                round((first_text_at - started) * 1000) if first_text_at is not None else None,
                round((ended_at - started) * 1000), search_started, complete, outcome,
            )
            # Cả timeout/lỗi lẫn đóng tab đều giữ phần đã phát. Shield tránh
            # cancel scope của StreamingResponse hủy luôn thao tác lưu SQLite.
            reply = "".join(collected).strip()
            # Câu sau lúc tra web không gắn lại thẻ thì giữ thẻ đã gửi tới nhân vật, để nghe lại tin cũ vẫn đúng mặt.
            if turn_emotion and reply and not emotion_tags.first(reply):
                reply = f"<|EMOTE_{turn_emotion.upper()}|> {reply}"
            artifacts = document_session.created if document_session else []
            if artifacts and not reply: reply = 'Tệp đã được tạo. Phản hồi bị ngắt; bạn vẫn có thể tải tài liệu bên dưới.'
            if reply and conversation_id and _visible(reply, mode):
                with anyio.CancelScope(shield=True):
                    if await db.owns_conversation(owner, conversation_id):
                        await db.add_message(
                            conversation_id, "assistant", reply,
                            status="complete" if complete else "incomplete",
                            sources=sources,
                            artifacts=artifacts,
                        )
        if failure:
            yield sse({"type": "error", "message": failure})
        else:
            turn_complete = complete
            # Trang hỏi lại vài giây sau "done" để hiện dòng "Peto vừa ghi nhớ"; đánh dấu trước cho khỏi hỏi hụt.
            if complete and mode == "companion" and await companion_memory.enabled_for(owner):
                companion_memory.mark_pending(owner)
            yield sse({"type": "done"})

    async def name_after_response():
        if conversation_id and mode == "chat":
            await titles.maybe_generate(owner, conversation_id, model)
        # Ghi nhớ chạy sau khi trả lời xong, như đặt tiêu đề: câu trả lời và giọng đọc không phải chờ.
        if conversation_id and mode == "companion" and turn_complete:
            await companion_memory.remember(owner, history_limit)

    return StreamingResponse(
        event_stream(),
        background=BackgroundTask(name_after_response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
