"""Xử lý lượt chat và stream SSE; giữ phần trả lời khi bị ngắt."""

from __future__ import annotations
from starlette.background import BackgroundTask
import asyncio
import uuid
from time import perf_counter
from collections.abc import AsyncIterator
from contextlib import aclosing
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
from storage import chat_turns
from features.chat import turn_control
from features.documents import reader as document_reader
from features.companion import emotion_tags
from features.documents.tools import DocumentSession, asks_edit, current_session as document_session_context
from features.connectors.tools import GitHubSession, current_session as github_session_context
from storage import connectors as connector_store
from features.companion import private_notes
from features.chat import titles
from features.chat.work_log import NOTE_LIMIT, WorkLog, read_detail
from ai import ChatMessage, ChatProvider, ProviderError, StreamChunk, get_provider
from ai import byok
from ai.routing import choose_effort
from shared.attachments import AttachmentError
from features.accounts.auth import current_owner
from shared.time_tools import resolve_browser_timezone, time_context
from core.config import (
    MAX_ATTACHMENTS,
    MAX_HISTORY_MESSAGES,
    MAX_INPUT_CHARS,
    RESPONSE_TIMEOUTS,
    TURN_TIMEOUT_SECONDS,
    WEB_SEARCH_ENABLED,
)
from core import usage_events
from core.rate_limit import AdmissionDenied, admission
from shared.web_search import normalize_sources, spoken_reply
from features.chat import conversations as conversation_actions
from features.chat.history import (
    _public_message,
    _read_legacy_documents,
    _title_from,
    _to_chat_messages,
    _visible,
    context_rows,
)
from features.chat.prompt_context import _build_system_prompt
from prompts.chat import DOCUMENT_MODE_PROMPT
from features.chat.schemas import (
    ALLOWED_EFFORTS,
    CONVERSATION_MODES,
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


ROLEPLAY_REMOVED = "Chế độ nhập vai không còn nữa. Tải lại trang để trò chuyện bình thường, hoặc dùng tab Companion."


def _as_chunk(item: str | StreamChunk) -> StreamChunk:
    if isinstance(item, StreamChunk):
        return item
    return StreamChunk("text", item)


class TurnTimeout(TimeoutError):
    """Lượt bị dừng: ``idle`` là quá lâu không nhận được gì mới từ provider, ``turn`` là cả lượt chạy quá giới hạn."""

    def __init__(self, kind: str, seconds: float):
        super().__init__(kind)
        self.kind = kind
        self.seconds = seconds


def _duration(seconds: float) -> str:
    minutes, rest = divmod(round(seconds), 60)
    if not minutes:
        return f"{rest} giây"
    return f"{minutes} phút {rest} giây" if rest else f"{minutes} phút"


def _timeout_message(error: TimeoutError, effort: str) -> str:
    if isinstance(error, TurnTimeout) and error.kind == "turn":
        return (f"Lượt này đã chạy {_duration(error.seconds)}, mức tối đa của một lượt, nên Peto dừng. "
                "Phần đã làm được giữ lại; nhắn “tiếp tục” nếu cần Peto làm nốt.")
    seconds = error.seconds if isinstance(error, TurnTimeout) else RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    return (f"Peto chờ {_duration(seconds)} mà không nhận được gì thêm từ dịch vụ AI nên dừng lượt này. "
            "Phần đã làm được giữ lại.")


async def _stream_reply(
    system_prompt: str, history: list[ChatMessage], effort: str, timezone: str | None = None, web_search: str = "auto",
    document_session=None, model: str = ai_models.DEFAULT_MODEL, spoken: bool = False,
    files: attachment_tools.AttachmentFiles | None = None, github_session=None, provider: ChatProvider | None = None,
) -> AsyncIterator[StreamChunk]:
    """Gọi provider của model đã chọn một lần. Trả về từng mảnh stream. ``spoken`` là lượt
    Companion: câu trả lời được đọc thành tiếng, nên chỉ dẫn tra web dặn không chèn đường dẫn hay dấu trích dẫn.
    ``files`` là các tệp của hội thoại mà Peto được tìm/đọc thêm trong lượt này.

    Chỉ dừng khi bị kẹt hoặc quá dài: mỗi mảnh nhận được (kể cả nhịp ``pulse`` lúc Grok soạn lệnh dài) dời mốc im lặng
    thêm RESPONSE_TIMEOUTS[effort], nhưng không quá TURN_TIMEOUT_SECONDS tính từ đầu. Việc sửa Excel nhiều vòng có
    thể mất vài phút; trước đây cả lượt chỉ được 3/5/8 phút nên bị cắt giữa chừng dù Peto vẫn đang làm.
    ``provider`` là provider dựng riêng cho lượt dùng khóa API của người dùng (ai/byok.py)."""
    provider = provider or get_provider(model)
    idle = RESPONSE_TIMEOUTS.get(effort, RESPONSE_TIMEOUTS["low"])
    loop = asyncio.get_running_loop()
    hard = loop.time() + TURN_TIMEOUT_SECONDS
    token = document_session_context.set(document_session)
    files_token = attachment_tools.current_files.set(files)
    spoken_token = spoken_reply.set(spoken)
    github_token = github_session_context.set(github_session)
    limit = None
    try:
        async with asyncio.timeout_at(min(loop.time() + idle, hard)) as limit:
            async with aclosing(provider.stream(
                system_prompt=f"{system_prompt}\n\n{time_context(timezone)}",
                messages=history, effort=effort, timezone=timezone,
                web_search=web_search,
            )) as stream:
                async for chunk in stream:
                    limit.reschedule(min(loop.time() + idle, hard))
                    yield _as_chunk(chunk)
    except TimeoutError as error:
        if limit is not None and limit.expired():
            whole = limit.when() >= hard
            raise TurnTimeout("turn" if whole else "idle", TURN_TIMEOUT_SECONDS if whole else idle) from error
        raise
    finally:
        github_session_context.reset(github_token)
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
        if any(item.kind != 'image' for item in files):
            raise HTTPException(status_code=400, detail="Companion chỉ nhận ảnh JPEG, PNG, WebP hoặc GIF. Tài liệu gửi trong tab Trò chuyện nhé.")
        # Companion phải trả lời thật nhanh để kịp đọc thành tiếng: suy nghĩ ít. Tra web thì Peto tự quyết khi cần (chủ web
        # chọn ngày 2026-09-28, như mô-đun tra web của AIRI), không có kiểu "luôn tìm". Trang gửi "off" khi công tắc Cài
        # đặt → Tra web đang tắt, mà mặc định là tắt.
        effort = "low"
        web_search = "off" if web_search == "off" else "auto"

    # Bộ não Companion dùng khóa API riêng (chủ web chốt 13/10/2026): khóa nằm trong header, chỉ dùng cho lượt này.
    own_key: byok.Choice | None = None
    if request.provider is not None:
        if mode != "companion":
            raise HTTPException(status_code=400, detail="Khóa API riêng chỉ dùng cho Companion.")
        headers = http_request.headers if http_request is not None else {}
        try:
            own_key = byok.choose(request.provider.id, request.provider.model, request.provider.endpoint,
                                  headers.get("x-peto-provider-key"), headers.get("x-peto-search-key"))
        except byok.ByokError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        # Nhà cung cấp không có tìm kiếm riêng mà chưa có khóa Tavily: lượt này không tra web (và đọc sớm được).
        if own_key.info.search == "tavily" and not own_key.search_key:
            web_search = "off"
    own_provider = own_key.info.id if own_key else ""

    # Chế độ nhập vai đã bỏ ngày 2026-10-18 (đã có Companion); trang cũ còn gửi "roleplay" thì báo rõ.
    if request.persona != "assistant":
        raise HTTPException(status_code=400, detail=ROLEPLAY_REMOVED)
    if request.conversation_id:
        settings = await db.conversation_settings(owner, request.conversation_id)
        if settings is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
        if settings['archived']:
            raise HTTPException(409, 'Hãy khôi phục hội thoại đã lưu trữ trước khi gửi tin nhắn.')
        if settings["mode"] != mode:
            raise HTTPException(status_code=400, detail="Hội thoại này thuộc tab khác")
        # Hội thoại nhập vai cũ chỉ còn để xem: lịch sử có thể có nội dung 18+, không được gửi tiếp tới model nào.
        if settings["persona"] == "roleplay":
            raise HTTPException(409, conversation_actions.LEGACY_ROLEPLAY)
    history_limit = MAX_HISTORY_MESSAGES
    # Trí nhớ dùng chung (companion_memory.py) đọc Companion và Chat. Lượt dùng khóa riêng không ghi nhớ (chủ web chốt
    # 13/10/2026).
    remembers = own_key is None
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
    try:
        model = ai_models.resolve(owner, request.model, "web").key
    except ai_models.ModelUnavailable as err:
        raise HTTPException(status_code=err.status, detail=err.message) from None

    if effort not in ai_models.supported_efforts(model):
        raise HTTPException(status_code=400, detail="Model này không hỗ trợ mức suy nghĩ đã chọn.")

    conversation_id = request.conversation_id
    request_id = request.request_id or uuid.uuid4().hex
    await chat_turns.reserve(owner, request_id)
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
        # cảm xúc đi riêng bằng sự kiện "emotion" kèm vị trí chữ, để nhân vật đổi mặt theo đoạn tiếng đang phát.
        notes = private_notes.NoteFilter() if mode == "companion" else None
        markers = emotion_tags.MarkerFilter() if mode == "companion" else None
        # Cảm xúc đầu tiên của lượt. Tra web thì phần viết trước lúc tra bị bỏ ("replace"), có khi mất luôn thẻ cảm xúc.
        turn_emotion: str | None = None
        # Nhật ký "Đang làm" của tab Trò chuyện (Companion có dòng trạng thái riêng): gửi từng bước, lưu cùng tin nhắn.
        log = WorkLog(started) if mode == "chat" else None
        work: dict | None = None
        message_id = None
        # Chữ của lần gọi mô hình hiện tại bắt đầu từ đâu trong ``collected``: lượt gọi kết thúc bằng lệnh công cụ thì
        # phần chữ đó là câu dẫn, chuyển sang nhật ký.
        round_start = 0
        last_artifact: dict | None = None

        def visible_events(text: str, final: bool = False) -> str | None:
            nonlocal turn_emotion
            if notes and markers:
                markers.feed(notes.feed(text) + (notes.flush() if final else ""))
                if final:
                    markers.flush()
                turn_emotion = turn_emotion or markers.emotion
                events = "".join(sse(event) for event in markers.take_events())
                return events or None
            return sse({"type": "delta", "text": text}) if text else None

        def chunk_event(chunk: StreamChunk) -> str | None:
            nonlocal sources, search_started, first_text_at, notes, markers, round_start, last_artifact
            # Dòng chú thích SSE: trình duyệt bỏ qua, nhưng giữ kết nối qua Cloudflare khi Grok soạn lệnh dài mà chưa
            # có chữ nào để gửi (luồng im quá 100 giây có thể bị cắt).
            if chunk.kind == 'pulse': return ': ping\n\n'
            # Các sự kiện cũ (document_status, file_lookup, search…) vẫn gửi cho trang mở từ trước khi cập nhật và cho
            # Companion; trang mới vẽ nhật ký từ sự kiện "step".
            steps = ''
            if chunk.kind == 'round':
                round_start = len(collected)
                return (log.round() if log else '') or None
            if chunk.kind == 'tool':
                return (log.tool(chunk.text) if log else '') or None
            if chunk.kind == 'note':
                text = ''.join(collected[round_start:]).strip()
                if log and text and len(text) <= NOTE_LIMIT:
                    del collected[round_start:]
                    return log.note(text) + sse({'type': 'replace', 'text': ''.join(collected)})
                if not text:
                    return None
                # Chữ dài trước lệnh công cụ là nội dung thật: giữ trong câu trả lời, ngắt đoạn như trước.
                collected.append('\n\n')
                return visible_events('\n\n')
            if chunk.kind == 'tool_result':
                steps = log.tool_result(chunk.info or {}, last_artifact) if log else ''
                last_artifact = None
                return steps or None
            if chunk.kind == 'artifact':
                last_artifact = chunk.artifact
                return sse({'type': 'artifact', 'artifact': chunk.artifact})
            if chunk.kind == 'document_status':
                if log:
                    steps = log.tool_start(chunk.text) if chunk.text else log.tool_end()
                return steps + sse({'type': 'document_status', 'text': chunk.text})
            if chunk.kind in ("file_lookup", "file_lookup_done"):
                if log:
                    steps = log.lookup(chunk.text, chunk.kind == "file_lookup")
                return steps + sse({"type": "file_lookup", "text": chunk.text, "live": chunk.kind == "file_lookup"})
            if chunk.kind in ("connector_lookup", "connector_lookup_done"):
                if log:
                    steps = log.github(chunk.text, chunk.kind == "connector_lookup")
                return steps + sse({"type": "connector_lookup", "text": chunk.text, "live": chunk.kind == "connector_lookup"})
            if chunk.kind == "search":
                search_started = True
                if log:
                    steps = log.search(chunk.text)
                return steps + sse({"type": "search", "status": chunk.text})
            if chunk.kind == "page":
                search_started = True
                if log:
                    steps = log.page(chunk.text)
                return steps + sse({"type": "search", "status": "searching" if chunk.text == "fetching" else "completed"})
            if chunk.kind == "sources":
                sources = normalize_sources([*sources, *chunk.sources])
                search_started = True
                if log:
                    steps = log.sources(len(sources))
                return steps + sse({"type": "sources", "sources": sources})
            if chunk.kind == "thinking":
                if log:
                    return log.thinking(chunk.text) or None
                return sse({"type": "thinking", "text": chunk.text})
            if chunk.kind == "replace":
                if notes:
                    collected.clear()
                    notes = private_notes.NoteFilter()
                    markers = emotion_tags.MarkerFilter(turn_emotion)
                    return sse({"type": "replace"})
                # Chỉ bỏ bản nháp của lần gọi hiện tại; chữ các lần gọi trước vẫn là câu trả lời. Bản nháp ngắn trước lúc
                # tra web là câu dẫn ("Peto lấy lời và vài nguồn…"): giữ trong nhật ký "Đang làm" như câu trước công cụ.
                draft = ''.join(collected[round_start:]).strip()
                del collected[round_start:]
                steps = ''
                if log:
                    if draft and len(draft) <= NOTE_LIMIT:
                        steps = log.note(draft)
                    else:
                        log.replace()
                return steps + sse({"type": "replace", "text": ''.join(collected)})
            if chunk.text and first_text_at is None:
                first_text_at = perf_counter()
            if log and chunk.text:
                steps = log.text()
            collected.append(chunk.text)
            return (steps + (visible_events(chunk.text) or '')) or None

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
                project_documents: list[dict] = []
                project_prompt = await project_context(owner, project_id, request.project_file_ids,
                    documents=project_documents)
                # Từ chối cooldown/hàng chờ trước khi ghi bất kỳ tin nhắn nào.
                if conversation_id and not await db.owns_conversation(owner, conversation_id):
                    raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
                documents: list[dict | None] = []
                document_count = sum(item.kind == "file" for item in files)
                names = [item.name for item in files if item.kind == "file"]
                if document_count:
                    step = log.read_start(f"Đang đọc {names[0]}…" if document_count == 1 else f"Đang đọc {document_count} tệp…") if log else ""
                    yield sse({"type": "reading", "text": f"Peto đang đọc {document_count} tài liệu…"}) + step
                for item in files:
                    documents.append(await document_reader.read_document(item.data, item.mime) if item.kind == "file" else None)
                if document_count:
                    read = [document for item, document in zip(files, documents) if item.kind == "file"]
                    step = log.read_done(f"Đã đọc {names[0]}" if document_count == 1 else f"Đã đọc {document_count} tệp",
                                         read_detail(read[0]) if document_count == 1 else "") if log else ""
                    # Thiếu dòng này thì bước "Peto đang đọc…" trong danh sách "Đang làm…" giữ nguyên chữ "đang" tới hết lượt.
                    yield sse({"type": "reading", "text": ""}) + step
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
                        conversation_id = await db.create_conversation(owner, mode=mode, project_id=project_id)
                    saved_paths: list[Path] = []
                    try:
                        if request.branch_message_id:
                            # Câu hỏi cuối vừa bị dừng/hỏng: gửi lại ngay tại chỗ; còn lại tạo phiên bản như trước.
                            message_id = await conversation_actions.retry_in_place(owner, conversation_id, request.branch_message_id, text)
                            if message_id is None:
                                conversation_id, message_id = await conversation_actions.fork(owner, conversation_id, request.branch_message_id, text)
                        else:
                            message_id = await db.add_message(conversation_id, "user", text, provider=own_provider)
                        await chat_turns.bind(owner, request_id, conversation_id, message_id)
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
                    if mode == 'chat':
                        # Lưu lựa chọn trong UI, không lưu mức suy nghĩ đã giải từ Tự động cho riêng tin này.
                        from storage.conversations import set_chat_selection
                        await set_chat_selection(owner, conversation_id, model, (request.effort or 'auto').strip().lower())
                    rows = await db.get_messages(owner, conversation_id, limit=history_limit)
                stored_user = next(row for row in rows if row["id"] == message_id)
                yield sse({
                    "type": "meta", "conversation_id": conversation_id, "effort": effort,
                    "message": _public_message(stored_user),
                    # Không có tra web thì chữ Companion không bị thay bằng bản nháp sau tìm kiếm.
                    "voice_stream": mode == "companion" and web_search == "off",
                })
                if MAX_ATTACHMENTS > document_count and any(
                    item.get("kind") == "file" and not document_reader.cached_document(item.get("document"))
                    for row in rows for item in row.get("attachments") or []
                ):
                    step = log.read_start("Đang đọc lại tài liệu đã gửi trước đó…") if log else ""
                    yield sse({"type": "reading", "text": "Peto đang đọc tài liệu đã gửi trước đó…"}) + step
                    await _read_legacy_documents(owner, rows, MAX_ATTACHMENTS - document_count)
                    step = log.read_done("Đã đọc lại tài liệu đã gửi trước đó") if log else ""
                    yield sse({"type": "reading", "text": ""}) + step
                active_rows = context_rows(rows)
                history, system_prompt = await asyncio.gather(
                    anyio.to_thread.run_sync(_to_chat_messages, active_rows, project_documents),
                    _build_system_prompt(owner, mode, install_command, conversation_id,
                        agent_question='\n'.join(str(row.get('content', ''))[:4000]
                            for row in [r for r in active_rows if r.get('role') == 'user' and r.get('turn_state') != 'stopped'][-3:]), model=model,
                        memory=own_key is None),
                )
                document_session = DocumentSession(owner, conversation_id, rows) if mode == 'chat' else None
                if document_session:
                    document_session.edit_request = asks_edit(text)
                if project_prompt:
                    system_prompt += '\n\n' + project_prompt
                # Tệp trong lịch sử vừa đọc (đã lọc theo chủ tài khoản trong SQL): Peto tìm/đọc thêm được khi cần.
                files_session = attachment_tools.AttachmentFiles(rows, owner) if mode == 'chat' else None
                if request.document_mode and mode == 'chat':
                    system_prompt += '\n\n' + DOCUMENT_MODE_PROMPT
                prepared_at = perf_counter()
                github_session = GitHubSession(owner) if mode == 'chat' and await connector_store.get_github(owner) else None
                # A timeout may already have consumed provider tokens. Do not repeat the whole turn invisibly.
                async with aclosing(_stream_reply(system_prompt, history, effort, timezone, web_search, document_session,
                                                 model, spoken=mode == "companion", files=files_session, github_session=github_session,
                                                 provider=byok.build(own_key) if own_key else None)) as stream:
                    async for chunk in stream:
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
        except TimeoutError as error:
            outcome = "timeout"
            logger.warning("Dừng lượt: %s (effort=%s, im lặng tối đa %ss, cả lượt tối đa %ss)",
                           getattr(error, "kind", "provider"), effort, RESPONSE_TIMEOUTS.get(effort), TURN_TIMEOUT_SECONDS)
            failure = _timeout_message(error, effort)
        except Exception:
            outcome = "internal_error"
            logger.exception("Lỗi không mong đợi khi gọi AI")
            failure = "Có lỗi ở phía máy chủ. Thử lại sau nha."
        finally:
            with anyio.CancelScope(shield=True):
                state = await chat_turns.finish(owner, request_id, 'complete' if complete else
                                               'timeout' if outcome == 'timeout' else 'interrupted' if outcome == 'cancelled' else 'error')
            if state == 'stopped':
                complete = False
            ended_at = perf_counter()
            logger.info(
                "chat_timing model=%s effort=%s mode=%s queue_ms=%s prepare_ms=%s first_text_ms=%s total_ms=%d search=%s complete=%s outcome=%s",
                f"byok:{own_provider}" if own_key else model, effort, mode,
                round((admitted_at - started) * 1000) if admitted_at is not None else None,
                round((prepared_at - admitted_at) * 1000) if prepared_at is not None and admitted_at is not None else None,
                round((first_text_at - started) * 1000) if first_text_at is not None else None,
                round((ended_at - started) * 1000), search_started, complete, outcome,
            )
            usage_events.record(
                "turn", service="byok" if own_key else ai_models.MODELS[model].service,
                model=f"byok:{own_provider}" if own_key else model, surface=mode,
                outcome="stopped" if state == "stopped" else outcome, complete=complete,
                elapsed_ms=round((ended_at - started) * 1000),
                first_text_ms=round((first_text_at - started) * 1000) if first_text_at is not None else None,
            )
            # Cả timeout/lỗi lẫn đóng tab đều giữ phần đã phát. Shield tránh
            # cancel scope của StreamingResponse hủy luôn thao tác lưu SQLite.
            reply = "".join(collected).strip()
            # Câu chốt giữ cảm xúc đầu tiên của lượt, để nghe lại vẫn đúng mặt dù bản nháp đã bị thay sau tra web.
            if turn_emotion and reply:
                if emotion_tags.first(private_notes.strip(reply)) != turn_emotion:
                    reply = f"<|EMOTE_{turn_emotion.upper()}|> {reply}"
            artifacts = document_session.created if document_session else []
            if artifacts and not reply: reply = 'Tệp đã được tạo. Phản hồi bị ngắt; bạn vẫn có thể tải tài liệu bên dưới.'
            work = log.close(complete) if log else None
            if conversation_id and ((reply and _visible(reply, mode)) or (state == 'stopped' and message_id)):
                with anyio.CancelScope(shield=True):
                    if await db.owns_conversation(owner, conversation_id):
                        assistant_id = await db.add_message(
                            conversation_id, "assistant", reply,
                            status="complete" if complete else "incomplete",
                            sources=sources,
                            artifacts=artifacts,
                            work=work,
                            provider=own_provider,
                        )
                        await chat_turns.attach_reply(owner, request_id, assistant_id)
        if state == 'stopped':
            return
        if work is not None and admitted_at is not None:
            # Bản chốt của nhật ký (bước suy nghĩ quá ngắn đã bỏ, bước dở đã đóng), đúng như bản lưu cùng tin nhắn.
            yield sse({"type": "work", "work": work})
        if failure:
            yield sse({"type": "error", "message": failure})
        else:
            turn_complete = complete
            # Đánh dấu "đang ghi nhớ" trước "done" cho trường ``pending`` của GET /api/companion/memory. Dòng "Peto vừa
            # ghi nhớ" từng đọc trường này đã bỏ ngày 11/10/2026; hiện trang không đọc nó nữa.
            if complete and remembers and await companion_memory.enabled_for(owner):
                companion_memory.mark_pending(owner)
            yield sse({"type": "done"})

    async def controlled_stream():
        key = (owner, request_id)
        row = await chat_turns.get(owner, request_id)
        if not row or row['state'] == 'stopped':
            yield sse({'type': 'stopped'})
            return
        with anyio.CancelScope() as scope:
            ticket = turn_control.RunningTurn(scope, asyncio.Event())
            turn_control.running[key] = ticket
            try:
                if (await chat_turns.get(owner, request_id))['state'] != 'stopped':
                    stream = event_stream()
                    try:
                        async for event in stream:
                            yield event
                    finally:
                        with anyio.CancelScope(shield=True):
                            await stream.aclose()
            finally:
                turn_control.running.pop(key, None)
                ticket.done.set()
        row = await chat_turns.get(owner, request_id)
        if row and row['state'] == 'stopped':
            yield sse({'type': 'stopped'})

    async def name_after_response():
        if conversation_id and mode == "chat":
            await titles.maybe_generate(owner, conversation_id, model)
        # Ghi nhớ chạy sau khi trả lời xong, như đặt tiêu đề: câu trả lời và giọng đọc không phải chờ.
        if conversation_id and remembers and turn_complete:
            await companion_memory.remember(owner, history_limit)

    return StreamingResponse(
        controlled_stream(),
        background=BackgroundTask(name_after_response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
