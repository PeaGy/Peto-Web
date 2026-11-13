"""Xử lý lượt chat và stream SSE; giữ phần trả lời khi bị ngắt."""

from __future__ import annotations
from starlette.background import BackgroundTask
import asyncio
import uuid
from time import perf_counter
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
import anyio
from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from features.agent import install as agent_install
from ai import models as ai_models
from shared import attachment_tools
from shared import attachments as attachment_lib
from features.companion import memory as companion_memory
from features.companion import cards as companion_cards
from features.companion import quotes as companion_quotes
import storage as db
from storage import chat_turns, chat_quotes, connection as db_connection
from features.chat import turn_control
from features.chat import context as chat_context, context_budget, request_context, client_environment
from shared import chat_history_tools
from features.documents import reader as document_reader
from features.companion import emotion_tags
from features.documents.tools import DocumentSession, asks_edit, current_session as document_session_context
from features.connectors.tools import GitHubSession, current_session as github_session_context, tool_access as github_access
from features.companion import private_notes
from features.companion import player_tools
from features.companion import player_reply
from prompts.companion_player import PLAYER_PROMPT, PLAYER_LIBRARY_PROMPT, PLAYER_DISCOVERY_PROMPT, PLAYER_SESSION_PROMPT, PLAYER_HISTORY_PROMPT
from features.chat import titles
from features.chat.work_log import NOTE_LIMIT, WorkLog, read_detail
from ai import ChatMessage, ChatProvider, ProviderError, StreamChunk, get_provider
from ai import byok
from ai.routing import choose_effort
from shared.attachments import AttachmentError
from features.accounts.auth import current_owner
from shared.time_tools import browser_timezone_selection, time_context
from core.config import (
    MAX_ATTACHMENTS,
    MAX_HISTORY_MESSAGES,
    CHAT_MAX_HISTORY,
    MAX_INPUT_CHARS,
    RESPONSE_TIMEOUTS,
    TURN_TIMEOUT_SECONDS,
    WEB_SEARCH_ENABLED,
)
from core import config, usage_events
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
from features.chat.prompt_context import _build_system_prompt, has_text_files, keyword_guides
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
    budget=None, history_session=None, snapshot=None, player_session=None,
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
    budget_token = context_budget.current.set(budget)
    history_token = chat_history_tools.current.set(history_session)
    snapshot_token = request_context.current.set(snapshot)
    player_token = player_tools.current.set(player_session)
    limit = None
    # Tab Trò chuyện (có snapshot): mốc giờ đã đóng băng trong khối runtime ở đuôi đầu vào (request_context.py), để
    # system prompt giữ nguyên giữa các lượt. Companion và các lượt khác vẫn nối giờ vào system prompt như trước.
    full_prompt = system_prompt if snapshot is not None else f"{system_prompt}\n\n{time_context(timezone)}"
    try:
        with usage_events.measurement(surface='companion' if spoken else 'chat' if snapshot else None, effort=effort):
            async with asyncio.timeout_at(min(loop.time() + idle, hard)) as limit:
                operation = player_reply.guarded_reply(provider, player_session,
                    system_prompt=full_prompt,
                    messages=history, effort=effort, timezone=timezone, web_search=web_search,
                ) if player_session else provider.stream(
                    system_prompt=full_prompt,
                    messages=history, effort=effort, timezone=timezone,
                    web_search=web_search,
                )
                async with aclosing(operation) as stream:
                    async for chunk in stream:
                        limit.reschedule(min(loop.time() + idle, hard))
                        yield _as_chunk(chunk)
    except TimeoutError as error:
        if limit is not None and limit.expired():
            whole = limit.when() >= hard
            raise TurnTimeout("turn" if whole else "idle", TURN_TIMEOUT_SECONDS if whole else idle) from error
        raise
    finally:
        player_tools.current.reset(player_token)
        request_context.current.reset(snapshot_token)
        chat_history_tools.current.reset(history_token)
        context_budget.current.reset(budget_token)
        github_session_context.reset(github_token)
        spoken_reply.reset(spoken_token)
        attachment_tools.current_files.reset(files_token)
        document_session_context.reset(token)


@dataclass
class _TurnSetup:
    """Đầu vào đã kiểm của một lượt ``POST /api/chat`` (``_resolve_turn``); không đổi trong suốt lượt."""
    owner: str
    request: ChatRequest
    http_request: Request | None
    install_command: str
    text: str
    files: list
    mode: str
    model: str
    effort: str
    web_search: str
    timezone: str | None
    timezone_source: str
    own_key: byok.Choice | None
    own_provider: str
    card: dict | None
    remembers: bool
    project_id: str | None
    history_limit: int
    request_id: str


async def _resolve_turn(request: ChatRequest, owner: str, http_request: Request | None) -> _TurnSetup:
    """Kiểm yêu cầu trước khi stream: mọi lỗi ở đây là HTTP 4xx, chưa ghi gì vào database."""
    # FastAPI nhận ra tham số Request qua kiểu khai báo nên luôn truyền vào (đừng đổi thành Request | None). Mặc định
    # None để các test gọi thẳng chat() như trước; khi đó hướng dẫn Peto Agent không kèm tên miền.
    install_command = agent_install.install_command(http_request) if http_request is not None else ""
    if request.web_search == "on" and not WEB_SEARCH_ENABLED:
        raise HTTPException(400, "Tìm kiếm web đang tắt trên máy chủ. Chọn Tự động hoặc Tắt để tiếp tục chat.")
    timezone, timezone_source = browser_timezone_selection(request.timezone)
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
            raise conversation_actions.RevisionTargetMissing()
        if not text and not target.get('attachments'):
            raise HTTPException(400, 'Tin nhắn trống')
    if not text and not files and not request.branch_message_id:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")

    effort = _resolve_effort(request.effort, text)
    mode = _resolve_mode(request.mode)
    if request.player_control is not None and mode != 'companion':
        raise HTTPException(400, 'Player chỉ điều khiển từ Companion.')
    if request.quote_id is not None and (mode != 'companion' or request.branch_message_id):
        raise HTTPException(400, 'Chỉ Companion trả lời một tin nhắn cũ được.')
    if request.quoted_source is not None:
        if mode != 'chat' or not request.conversation_id:
            raise HTTPException(400, 'Chỉ trích câu trả lời đã lưu trong cuộc Trò chuyện hiện tại.')
        async with db_connection.connect() as connection:
            await chat_quotes.validate(connection, owner, request.conversation_id, request.quoted_source.model_dump())
    web_search = request.web_search
    if mode == "companion":
        if any(item.kind != 'image' for item in files):
            raise HTTPException(status_code=400, detail="Companion chỉ nhận ảnh JPEG, PNG, WebP hoặc GIF. Tài liệu gửi trong tab Trò chuyện nhé.")
        # Companion phải trả lời thật nhanh để kịp đọc thành tiếng: suy nghĩ ít. Tra web thì Peto tự quyết khi cần (chủ web
        # chọn ngày 2026-09-28, như mô-đun tra web của AIRI), không có kiểu "luôn tìm". Trang gửi "off" khi công tắc Cài
        # đặt → Tra web đang tắt, mà mặc định là tắt.
        effort = "low"
        web_search = "off" if web_search == "off" else "auto"
    own_key, web_search = _own_key(request, mode, http_request, web_search)
    own_provider = own_key.info.id if own_key else ""
    settings, card, project_id = await _conversation_scope(request, owner, mode)
    # Tab Trò chuyện: trần số tin (G1.2); cửa sổ thật do ngân sách token và mốc đã lưu quyết định (context.py).
    history_limit = CHAT_MAX_HISTORY if mode == 'chat' else MAX_HISTORY_MESSAGES
    # Trí nhớ dùng chung (companion_memory.py) đọc Companion và Chat. Lượt dùng khóa riêng không ghi nhớ (chủ web chốt
    # 13/10/2026), thẻ nhân vật tự tạo cũng không (25/10/2026).
    remembers = own_key is None and (card is None or companion_cards.remembers(card["id"]))
    if request.model != ai_models.DEFAULT_MODEL:
        if mode == "companion":
            raise HTTPException(status_code=400, detail="Tab Companion chỉ dùng Peto.")
    try:
        model = ai_models.resolve(owner, request.model, "web").key
    except ai_models.ModelUnavailable as err:
        raise HTTPException(status_code=err.status, detail=err.message) from None

    if effort not in ai_models.supported_efforts(model):
        raise HTTPException(status_code=400, detail="Model này không hỗ trợ mức suy nghĩ đã chọn.")
    return _TurnSetup(owner, request, http_request, install_command, text, files, mode, model, effort, web_search,
                      timezone, timezone_source, own_key, own_provider, card, remembers, project_id, history_limit,
                      request.request_id or uuid.uuid4().hex)


def _own_key(request: ChatRequest, mode: str, http_request: Request | None, web_search: str):
    """Bộ não Companion dùng khóa API riêng (chủ web chốt 13/10/2026): khóa nằm trong header, chỉ dùng cho lượt này."""
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
    return own_key, web_search


async def _conversation_scope(request: ChatRequest, owner: str, mode: str):
    """Hội thoại, thẻ nhân vật và dự án của lượt; kiểm quyền, tab, lưu trữ và dự án trước khi stream."""
    # Chế độ nhập vai đã bỏ ngày 2026-10-18 (đã có Companion); trang cũ còn gửi "roleplay" thì báo rõ.
    if request.persona != "assistant":
        raise HTTPException(status_code=400, detail=ROLEPLAY_REMOVED)
    settings = None
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
    # Thẻ nhân vật của lượt Companion: mạch đã có giữ thẻ lúc tạo (như AIRI), mạch mới theo thẻ gửi lên hoặc thẻ đang dùng.
    card = None
    if mode == "companion":
        card = await companion_cards.resolve(owner, (settings.get("card_id") or companion_cards.DEFAULT_CARD)
                                             if request.conversation_id else request.card_id)
    elif request.card_id is not None:
        raise HTTPException(400, 'Thẻ nhân vật chỉ dùng cho Companion.')
    from features.projects.context import context as project_context
    project_id = settings.get('project_id') if request.conversation_id else request.project_id
    if mode != 'chat' and (project_id or request.project_file_ids):
        raise HTTPException(400, 'Dự án chỉ dùng trong tab Trò chuyện')
    if request.conversation_id and request.project_id is not None and request.project_id != project_id:
        raise HTTPException(400, 'Hội thoại thuộc dự án khác; chuyển bằng menu hội thoại trước')
    await project_context(owner, project_id, request.project_file_ids)
    return settings, card, project_id


class _ChatTurn:
    """Một lượt chat đang stream (gói G3.2, 13/11/2026: tách từ hàm lồng ``event_stream`` 466 dòng).

    Thứ tự: vào hàng (``admission.slot``) → kiểm phạm vi → đọc tệp mới → lưu tin người dùng → ``meta`` → đọc lại tệp cũ
    → dựng prompt → chuẩn bị lịch sử → phiên công cụ và snapshot → gọi model → lưu câu trả lời và trạng thái. Thứ tự sự
    kiện SSE và mọi điều kiện giữ nguyên như trước khi tách; trạng thái dùng chung nằm trên ``self``.
    """

    def __init__(self, setup: _TurnSetup):
        self.s = setup
        self.conversation_id = setup.request.conversation_id
        # Đọc bởi tác vụ nền sau lượt (đặt tên, tóm tắt G1.3, ghi nhớ).
        self.turn_complete = False
        self.compaction: dict = {}
        # Lượt Chat dịch vụ AI chạy xong mà không viết gì (Peto im lặng có chủ đích): vẫn chốt hoàn tất.
        self.silent = False
        self.started = perf_counter()
        self.admitted_at = self.prepared_at = self.first_text_at = None
        self.collected: list[str] = []
        self.sources: list[dict] = []
        self.search_started = False
        self.document_session = None
        # Câu trả lời Companion lưu nguyên, nhưng stream về trình duyệt thì bỏ ghi chú riêng và thẻ cảm xúc của Peto;
        # cảm xúc đi riêng bằng sự kiện "emotion" kèm vị trí chữ, để nhân vật đổi mặt theo đoạn tiếng đang phát.
        self.notes = private_notes.NoteFilter() if setup.mode == "companion" else None
        self.markers = emotion_tags.MarkerFilter() if setup.mode == "companion" else None
        # Cảm xúc đầu tiên của lượt. Tra web thì phần viết trước lúc tra bị bỏ ("replace"), có khi mất luôn thẻ cảm xúc.
        self.turn_emotion: str | None = None
        # Nhật ký "Đang làm" của tab Trò chuyện (Companion có dòng trạng thái riêng): gửi từng bước, lưu cùng tin nhắn.
        self.log = WorkLog(self.started) if setup.mode == "chat" else None
        self.work: dict | None = None
        self.player_session = None
        self.message_id = None
        # Snapshot của lượt Chat; bước lưu đọc nó để lưu khối runtime đã gửi Grok (G1.1c).
        self.snapshot = None
        # Chữ của lần gọi mô hình hiện tại bắt đầu từ đâu trong ``collected``: lượt gọi kết thúc bằng lệnh công cụ thì
        # phần chữ đó là câu dẫn, chuyển sang nhật ký.
        self.round_start = 0
        self.last_artifact: dict | None = None
        self.checkpoint_at = 0.0
        self.checkpoint_size = 0
        self.complete = False
        self.outcome = "cancelled"
        self.failure: str | None = None
        self.failure_status: int | None = None
        self.state = None
        # Kết quả các bước chuẩn bị, dùng ở bước sau.
        self.project_documents: list[dict] = []
        self.project_prompt = ''
        self.documents: list[dict | None] = []
        self.document_count = 0
        self.rows: list[dict] = []
        self.active_rows: list[dict] = []
        self.system_prompt = ''
        self.runtime_guides = ''
        self.history: list[ChatMessage] = []
        self.prepared = None
        self.files_session = None
        self.github_session = None

    async def checkpoint(self, force=False):
        s = self.s
        if self.message_id is None or (s.mode != 'chat' and not (self.player_session and self.player_session.receipts)):
            return
        now, size = perf_counter(), sum(map(len, self.collected))
        if not force and now - self.checkpoint_at < 1 and abs(size - self.checkpoint_size) < 2048:
            return
        saved = await chat_turns.persist(s.owner, s.request_id, content=''.join(self.collected), sources=self.sources,
            artifacts=self.document_session.created if self.document_session else [],
            work=self.log.snapshot() if self.log else {'player': self.player_session.trace()} if self.player_session else None,
            provider=s.own_provider)
        if saved not in {'running', 'stopped'}:
            raise ProviderError('Hội thoại đã thay đổi. Mở lại lịch sử trước khi gửi tiếp nhé.')
        self.checkpoint_at, self.checkpoint_size = now, size

    def visible_events(self, text: str, final: bool = False) -> str | None:
        if self.notes and self.markers:
            self.markers.feed(self.notes.feed(text) + (self.notes.flush() if final else ""))
            if final:
                self.markers.flush()
            self.turn_emotion = self.turn_emotion or self.markers.emotion
            events = "".join(sse(event) for event in self.markers.take_events())
            return events or None
        return sse({"type": "delta", "text": text}) if text else None

    def chunk_event(self, chunk: StreamChunk) -> str | None:
        s, log = self.s, self.log
        # Dòng chú thích SSE: trình duyệt bỏ qua, nhưng giữ kết nối qua Cloudflare khi Grok soạn lệnh dài mà chưa
        # có chữ nào để gửi (luồng im quá 100 giây có thể bị cắt).
        if chunk.kind == 'pulse': return ': ping\n\n'
        if chunk.kind == 'player_command' and s.mode == 'companion' and s.request.player_control in (1, 2, 3, 4, 5):
            return sse({'type': 'player_command', 'command': chunk.info})
        # Các sự kiện cũ (document_status, file_lookup, search…) vẫn gửi cho trang mở từ trước khi cập nhật và cho
        # Companion; trang mới vẽ nhật ký từ sự kiện "step".
        steps = ''
        if chunk.kind == 'round':
            self.round_start = len(self.collected)
            return (log.round() if log else '') or None
        if chunk.kind == 'tool':
            return (log.tool(chunk.text) if log else '') or None
        if chunk.kind == 'note':
            text = ''.join(self.collected[self.round_start:]).strip()
            if log and text and len(text) <= NOTE_LIMIT:
                del self.collected[self.round_start:]
                return log.note(text) + sse({'type': 'replace', 'text': ''.join(self.collected)})
            if not text:
                return None
            # Chữ dài trước lệnh công cụ là nội dung thật: giữ trong câu trả lời, ngắt đoạn như trước.
            self.collected.append('\n\n')
            return self.visible_events('\n\n')
        if chunk.kind == 'tool_result':
            steps = log.tool_result(chunk.info or {}, self.last_artifact) if log else ''
            self.last_artifact = None
            return steps or None
        if chunk.kind == 'artifact':
            self.last_artifact = chunk.artifact
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
        if chunk.kind in ('code', 'search', 'page', 'source_activity', 'sources', 'thinking'):
            return self._activity_event(chunk)
        if chunk.kind == "replace":
            return self._replace_event()
        if chunk.text and self.first_text_at is None:
            self.first_text_at = perf_counter()
        if log and chunk.text:
            steps = log.text()
        self.collected.append(chunk.text)
        return (steps + (self.visible_events(chunk.text) or '')) or None

    def _activity_event(self, chunk: StreamChunk) -> str | None:
        """Chạy mã, tra web, nguồn và suy nghĩ: ghi nhật ký và gửi sự kiện cũ cho trang chưa cập nhật."""
        s, log = self.s, self.log
        steps = ''
        if chunk.kind == 'code':
            # Mỗi lần chạy mã ghi một sự kiện không có nội dung cho trang Quản trị (lượt chạy, lượt lỗi).
            if s.mode == 'chat' and chunk.text == 'done':
                info = chunk.info or {}
                failed = info.get('timed_out') is True or info.get('status') not in (None, 'completed') \
                    or info.get('exit_code') not in (None, 0)
                usage_events.record('chat_event', service=ai_models.MODELS[s.model].service, model=s.model,
                    surface='chat', effort=s.effort, purpose='code', outcome='error' if failed else 'ok')
            return (log.code(chunk.text, chunk.info) if log else '') or None
        if chunk.kind == "search":
            if s.mode == 'chat' and chunk.text == 'failed':
                usage_events.record('chat_event', service=ai_models.MODELS[s.model].service, model=s.model,
                    surface='chat', effort=s.effort, purpose='web', outcome='error')
            self.search_started = True
            if log:
                steps = log.search(chunk.text)
            return steps + sse({"type": "search", "status": chunk.text})
        if chunk.kind == "page":
            if s.mode == 'chat' and chunk.text == 'failed':
                usage_events.record('chat_event', service=ai_models.MODELS[s.model].service, model=s.model,
                    surface='chat', effort=s.effort, purpose='web', outcome='error')
            self.search_started = True
            if log:
                steps = log.page(chunk.text)
            return steps + sse({"type": "search", "status": "searching" if chunk.text == "fetching" else "completed"})
        if chunk.kind == 'source_activity':
            return log.source_activity(chunk.info) if log else None
        if chunk.kind == "sources":
            self.sources = normalize_sources([*self.sources, *chunk.sources])
            self.search_started = True
            if log:
                steps = log.sources(len(self.sources))
            return steps + sse({"type": "sources", "sources": self.sources})
        # thinking
        if log:
            return log.thinking(chunk.text) or None
        return sse({"type": "thinking", "text": chunk.text})

    def _replace_event(self) -> str:
        if self.notes:
            self.collected.clear()
            self.notes = private_notes.NoteFilter()
            self.markers = emotion_tags.MarkerFilter(self.turn_emotion)
            return sse({"type": "replace"})
        # Chỉ bỏ bản nháp của lần gọi hiện tại; chữ các lần gọi trước vẫn là câu trả lời. Bản nháp ngắn trước lúc
        # tra web là câu dẫn ("Peto lấy lời và vài nguồn…"): giữ trong nhật ký "Đang làm" như câu trước công cụ.
        draft = ''.join(self.collected[self.round_start:]).strip()
        del self.collected[self.round_start:]
        steps = ''
        if self.log:
            if draft and len(draft) <= NOTE_LIMIT:
                steps = self.log.note(draft)
            else:
                self.log.replace()
        return steps + sse({"type": "replace", "text": ''.join(self.collected)})

    async def _check_scope(self) -> None:
        if self.conversation_id:
            current_settings = await db.conversation_settings(self.s.owner, self.conversation_id)
            if current_settings and current_settings['archived']:
                raise ProviderError('Hội thoại đã được lưu trữ. Hãy khôi phục trước khi gửi tin nhắn.')
            if not current_settings or current_settings.get('project_id') != self.s.project_id:
                raise ProviderError('Hội thoại đã chuyển dự án hoặc bị xóa. Mở lại trước khi gửi nhé.')

    async def _read_new_files(self) -> AsyncIterator[str]:
        """Dự án, quyền hội thoại và đọc tệp vừa gửi; báo "Peto đang đọc…" khi có tài liệu."""
        s, log = self.s, self.log
        await self._check_scope()
        from features.projects.context import context as project_context
        self.project_documents = []
        self.project_prompt = await project_context(s.owner, s.project_id, s.request.project_file_ids,
            documents=self.project_documents)
        # Từ chối cooldown/hàng chờ trước khi ghi bất kỳ tin nhắn nào.
        if self.conversation_id and not await db.owns_conversation(s.owner, self.conversation_id):
            raise ProviderError("Hội thoại đã bị xóa. Mở cuộc trò chuyện mới nhé.")
        self.documents = []
        self.document_count = sum(item.kind == "file" for item in s.files)
        names = [item.name for item in s.files if item.kind == "file"]
        if self.document_count:
            step = log.read_start(f"Đang đọc {names[0]}…" if self.document_count == 1 else f"Đang đọc {self.document_count} tệp…") if log else ""
            yield sse({"type": "reading", "text": f"Peto đang đọc {self.document_count} tài liệu…"}) + step
        for item in s.files:
            self.documents.append(await document_reader.read_document(item.data, item.mime) if item.kind == "file" else None)
        if self.document_count:
            read = [document for item, document in zip(s.files, self.documents) if item.kind == "file"]
            step = log.read_done(f"Đã đọc {names[0]}" if self.document_count == 1 else f"Đã đọc {self.document_count} tệp",
                                 read_detail(read[0]) if self.document_count == 1 else "") if log else ""
            # Thiếu dòng này thì bước "Peto đang đọc…" trong danh sách "Đang làm…" giữ nguyên chữ "đang" tới hết lượt.
            yield sse({"type": "reading", "text": ""}) + step
        # Hội thoại có thể bị xóa hoặc chuyển dự án trong lúc đang đọc tệp.
        await self._check_scope()

    async def _save_user_message(self) -> None:
        """Tạo hội thoại, lưu tin người dùng và tệp đính kèm, rồi đọc lịch sử; chạy trọn dù trình duyệt ngắt."""
        s, request = self.s, self.s.request
        with anyio.CancelScope(shield=True):
            if not self.conversation_id:
                self.conversation_id = await db.create_conversation(s.owner, mode=s.mode, project_id=s.project_id,
                                                                    card_id=s.card["id"] if s.card else None)
                if s.card:
                    await companion_cards.open_conversation(s.owner, s.card, self.conversation_id)
            saved_paths: list[Path] = []
            try:
                if request.branch_message_id:
                    quote_change = (request.quoted_source.model_dump() if request.quoted_source is not None else None) \
                        if 'quoted_source' in request.model_fields_set else chat_quotes.UNSET
                    self.message_id = await conversation_actions.retry_in_place(
                        s.owner, self.conversation_id, request.branch_message_id, s.text, quote_change,
                        request_id=s.request_id, model=s.model, effort=s.effort)
                    if self.message_id is None:
                        self.conversation_id, self.message_id = await conversation_actions.fork(
                            s.owner, self.conversation_id, request.branch_message_id, s.text, quote_change)
                        self.message_id = await chat_turns.bind(s.owner, s.request_id, self.conversation_id,
                                                                self.message_id, model=s.model, effort=s.effort)
                else:
                    self.message_id = await chat_turns.bind(s.owner, s.request_id, self.conversation_id, None, s.text,
                        s.own_provider, quote_id=request.quote_id,
                        quoted_source=request.quoted_source.model_dump() if request.quoted_source is not None else None,
                        model=s.model, effort=s.effort)
                for item, document in zip(s.files, self.documents):
                    attachment_id, path = attachment_lib.write_file(self.conversation_id, item)
                    saved_paths.append(path)
                    await db.add_attachment(
                        attachment_id=attachment_id, owner=s.owner,
                        conversation_id=self.conversation_id, message_id=self.message_id,
                        filename=item.name, mime=item.mime, kind=item.kind,
                        size=len(item.data), path=str(path),
                        document=document,
                    )
            except Exception:
                attachment_lib.delete_files(saved_paths)
                raise
            await db.set_title_if_empty(self.conversation_id, _title_from(s.text, s.files))
            if s.mode == 'chat':
                # Lưu lựa chọn trong UI, không lưu mức suy nghĩ đã giải từ Tự động cho riêng tin này.
                from storage.conversations import set_chat_selection
                await set_chat_selection(s.owner, self.conversation_id, s.model, (request.effort or 'auto').strip().lower())
            self.rows = await db.get_messages(s.owner, self.conversation_id, limit=s.history_limit)
            if s.mode == 'chat' and ai_models.MODELS[s.model].service == 'xai':
                # G1.1c: Grok cần lại nguyên văn khối runtime của các lượt trước. Tin hiện tại thì không: lượt này
                # gắn khối mới (thử lại hay tạo lại cùng tin sẽ ghi đè khối cũ).
                runtimes = await db.message_runtimes(s.owner, self.conversation_id)
                for row in self.rows:
                    if row['id'] != self.message_id and row['id'] in runtimes:
                        row['runtime'] = runtimes[row['id']]

    async def _reread_old_files(self) -> AsyncIterator[str]:
        """Tệp gửi trước đó chưa có bản đọc trong bộ nhớ đệm thì đọc lại (giới hạn số tệp mỗi lượt)."""
        log = self.log
        if MAX_ATTACHMENTS > self.document_count and any(
            item.get("kind") == "file" and not document_reader.cached_document(item.get("document"))
            for row in self.rows for item in row.get("attachments") or []
        ):
            step = log.read_start("Đang đọc lại tài liệu đã gửi trước đó…") if log else ""
            yield sse({"type": "reading", "text": "Peto đang đọc tài liệu đã gửi trước đó…"}) + step
            await _read_legacy_documents(self.s.owner, self.rows, MAX_ATTACHMENTS - self.document_count)
            step = log.read_done("Đã đọc lại tài liệu đã gửi trước đó") if log else ""
            yield sse({"type": "reading", "text": ""}) + step

    async def _build_prompt(self) -> None:
        """System prompt, khối chỉ dẫn theo từ khóa (Chat) hay lịch sử (Companion), và phiên tệp/tài liệu."""
        s = self.s
        self.active_rows = context_rows(self.rows)
        # Danh mục tệp của cả hội thoại (lọc theo chủ tài khoản): cũng quyết định có kèm cách đọc log hay không.
        indexed = await chat_context.store.file_index(s.owner, self.conversation_id) if s.mode == 'chat' else []
        agent_question = '\n'.join(str(row.get('content', ''))[:4000]
            for row in [r for r in self.active_rows if r.get('role') == 'user' and r.get('turn_state') != 'stopped'][-3:])
        # Tab Trò chuyện (G1.1b): khối chỉ dẫn theo từ khóa đi trong khối runtime ở đuôi, không ở system, để system
        # giữ nguyên từng byte giữa các lượt (prompt cache). Companion giữ chúng trong system như trước.
        prompt_task = _build_system_prompt(s.owner, s.mode, s.install_command, self.conversation_id,
                agent_question=agent_question, model=s.model,
                memory=s.remembers, text_files=has_text_files(indexed), card=s.card, guides=s.mode != 'chat')
        self.runtime_guides = ''
        if s.mode == 'chat':
            # Context Chat dựng history một lần theo ngân sách; không đọc/base64 ảnh hai lần.
            self.system_prompt, self.runtime_guides = await asyncio.gather(
                prompt_task, keyword_guides(agent_question, 'chat', s.install_command))
            self.history = []
        else:
            # Tin trả lời một tin cũ mang dòng "[Replying to: …]" như AIRI; chỉ trong phần gửi model, không lưu.
            model_rows = await companion_quotes.with_quotes(s.owner, self.conversation_id, self.active_rows)
            self.history, self.system_prompt = await asyncio.gather(
                anyio.to_thread.run_sync(_to_chat_messages, model_rows, self.project_documents), prompt_task)
        generated = await chat_context.store.artifact_index(s.owner, self.conversation_id) if s.mode == 'chat' else []
        inventory = sorted([*indexed, *generated], key=lambda item: item['message_id'])
        tool_rows = [*({'artifacts': [item], 'generated_documents': [item]} if 'version' in item
                      else {'attachments': [item]} for item in inventory), *self.rows]
        self.document_session = DocumentSession(s.owner, self.conversation_id, tool_rows) if s.mode == 'chat' else None
        if self.document_session:
            self.document_session.edit_request = asks_edit(s.text)
        if self.project_prompt:
            self.system_prompt += '\n\n' + self.project_prompt
        # Tệp trong lịch sử vừa đọc (đã lọc theo chủ tài khoản trong SQL): Peto tìm/đọc thêm được khi cần.
        self.files_session = attachment_tools.AttachmentFiles(tool_rows, s.owner, self.conversation_id) if s.mode == 'chat' else None
        if s.request.document_mode and s.mode == 'chat':
            self.system_prompt += '\n\n' + DOCUMENT_MODE_PROMPT

    async def _prepare_history(self) -> AsyncIterator[str]:
        """Tab Trò chuyện: cửa sổ lịch sử theo ngân sách (G1.2), tóm tắt để sau lượt (G1.3)."""
        s, log = self.s, self.log
        self.prepared = None
        if s.mode != 'chat':
            return
        preparing = len(self.rows) >= s.history_limit
        if preparing:
            yield sse({'type': 'reading', 'text': 'Peto đang chuẩn bị ngữ cảnh hội thoại…'}) + (log.read_start('Đang chuẩn bị ngữ cảnh…') if log else '')
        # Ngân sách tính cả khối chỉ dẫn ở đuôi; system gửi đi vẫn là bản không có chúng.
        budget_prompt = self.system_prompt + ('\n\n' + self.runtime_guides.strip() if self.runtime_guides.strip() else '')
        self.prepared = await chat_context.prepare(s.owner, self.conversation_id, s.model, budget_prompt, self.rows,
                                                   self.project_documents, s.history_limit, summarize_now=False)
        if self.prepared.summary_due:
            self.compaction.update(model=s.model, prompt=budget_prompt, window=s.history_limit,
                                   project_documents=tuple(self.project_documents or ()))
        latest_scope = await db.conversation_settings(s.owner, self.conversation_id)
        if not latest_scope or latest_scope['archived'] or latest_scope.get('project_id') != s.project_id:
            raise ProviderError('Hội thoại đã thay đổi trong lúc chuẩn bị ngữ cảnh; mở lại trước khi gửi nhé.')
        self.history = self.prepared.history
        if preparing:
            yield sse({'type': 'reading', 'text': ''}) + (log.read_done('Đã chuẩn bị ngữ cảnh', self.prepared.detail) if log else '')

    async def _open_sessions(self) -> None:
        """GitHub, snapshot của lượt Chat, phiên Player của Companion và phần prompt đi kèm."""
        s, request, prepared = self.s, self.s.request, self.prepared
        self.prepared_at = perf_counter()
        github_state, github_reason = await github_access(s.owner) if s.mode == 'chat' else ('unavailable', 'chat_only')
        self.github_session = GitHubSession(s.owner) if s.mode == 'chat' and github_state == 'available' else None
        self.snapshot = request_context.RequestContext(
            s.request_id, request.request_id is not None, self.conversation_id, s.project_id, s.model,
            (request.effort or 'auto').strip().lower(), s.timezone, s.timezone_source,
            github_state, github_reason,
            client_environment=client_environment.normalize(
                s.http_request.headers if s.http_request is not None else None),
            history_note=prepared.note if prepared else '', guides=self.runtime_guides) if s.mode == 'chat' else None
        self.player_session = player_tools.PlayerSession(s.owner, request.player_control,
            user_text='\n'.join(str(row.get('content', '')) for row in self.active_rows if row.get('role') == 'user')[-32000:]
        ) if s.mode == 'companion' and request.player_control in (1, 2, 3, 4, 5) and s.own_provider != 'gemini' else None
        if self.player_session:
            self.system_prompt += '\n\n' + ({1: PLAYER_PROMPT, 2: PLAYER_LIBRARY_PROMPT, 3: PLAYER_DISCOVERY_PROMPT, 4: PLAYER_SESSION_PROMPT, 5: PLAYER_HISTORY_PROMPT}[request.player_control])
            self.system_prompt += player_reply.past_evidence(self.active_rows)
        elif s.mode == 'companion' and request.player_control in (1, 2, 3, 4, 5):
            self.system_prompt += '\n\nPlayer control is unavailable with this Gemini connection. You can discuss music, but cannot read or change live playback with this provider.'

    async def _reply(self) -> AsyncIterator[str]:
        """Gọi model một lần và chuyển từng mảnh thành sự kiện; chốt hoàn tất, rỗng hay im lặng có chủ đích."""
        s, prepared = self.s, self.prepared
        # A timeout may already have consumed provider tokens. Do not repeat the whole turn invisibly.
        async with aclosing(_stream_reply(self.system_prompt, self.history, s.effort, s.timezone, s.web_search,
                                         self.document_session, s.model, spoken=s.mode == "companion",
                                         files=self.files_session, github_session=self.github_session,
                                         provider=byok.build(s.own_key) if s.own_key else None,
                                         budget=prepared.budget if prepared else None,
                                         history_session=prepared.history_tools if prepared else None,
                                         snapshot=self.snapshot, player_session=self.player_session)) as stream:
            async for chunk in stream:
                event = self.chunk_event(chunk)
                # Lưu trước khi công bố tệp/kết quả công cụ; chữ lưu tối đa mỗi giây hoặc mỗi 2 KiB.
                await self.checkpoint(force=chunk.kind in {'artifact', 'tool_result', 'note', 'replace'}
                                      or bool(self.player_session and chunk.kind in {'player_command', 'round'}))
                if event:
                    yield event
        if self.notes:
            tail = self.visible_events("", final=True)
            if tail:
                yield tail
        if self.document_session and self.document_session.created and not ''.join(self.collected).strip():
            yield self.chunk_event(StreamChunk('text', 'Đã tạo xong tài liệu. Bạn xem trước hoặc tải tệp bên dưới nhé.'))
        # Một câu trả lời Companion chỉ có ghi chú riêng thì người dùng không thấy gì: coi như chưa trả lời.
        self.complete = bool(_visible("".join(self.collected), s.mode).strip())
        # Tab Trò chuyện: dịch vụ AI chạy xong bình thường (lỗi thật đều đã raise ở trên) mà không viết chữ nào là
        # Peto im lặng có chủ đích, ví dụ khi được bảo "đừng trả lời" (thử thật 13/11/2026: Grok chỉ suy nghĩ,
        # 0 chữ). Chủ web chọn coi là lượt hoàn tất, giao diện ghi một dòng mờ; không báo lỗi.
        if not self.complete and s.mode == 'chat':
            self.complete = self.silent = True
        if not self.complete:
            self.outcome = "empty"
            self.failure = "Peto chưa trả lời được lượt này. Nhắn lại giúp nha."
        else:
            self.outcome = "complete"

    def _record_failure(self, error: BaseException) -> None:
        s = self.s
        if isinstance(error, AdmissionDenied):
            self.outcome, self.failure = error.reason, error.message
        elif isinstance(error, conversation_actions.RevisionTargetMissing):
            self.outcome = 'revision_target_missing'
            self.failure, self.failure_status = error.detail, error.status_code
        elif isinstance(error, ProviderError):
            self.outcome = 'context_overflow' if isinstance(error, context_budget.ContextOverflow) else 'provider_error'
            if self.outcome == 'context_overflow':
                usage_events.record('chat_event', service=ai_models.MODELS[s.model].service, model=s.model,
                    surface='chat', effort=s.effort, purpose='context', outcome='overflow')
            logger.warning("Provider lỗi: %s", error)
            self.failure = str(error)
        elif isinstance(error, TimeoutError):
            self.outcome = "timeout"
            logger.warning("Dừng lượt: %s (effort=%s, im lặng tối đa %ss, cả lượt tối đa %ss)",
                           getattr(error, "kind", "provider"), s.effort, RESPONSE_TIMEOUTS.get(s.effort), TURN_TIMEOUT_SECONDS)
            self.failure = _timeout_message(error, s.effort)
        else:
            self.outcome = "internal_error"
            logger.exception("Lỗi không mong đợi khi gọi AI", exc_info=error)
            self.failure = "Có lỗi ở phía máy chủ. Thử lại sau nha."

    async def _persist(self) -> None:
        """Reply, liên kết tệp và trạng thái cuối cùng cùng commit; không được báo hoàn tất trước khi lưu."""
        s = self.s
        reply = "".join(self.collected).strip()
        if self.turn_emotion and reply and emotion_tags.first(private_notes.strip(reply)) != self.turn_emotion:
            reply = f"<|EMOTE_{self.turn_emotion.upper()}|> {reply}"
        if s.mode == 'companion' and not _visible(reply, s.mode).strip():
            reply = ''
        artifacts = self.document_session.created if self.document_session else []
        if artifacts and not reply:
            reply = 'Tệp đã được tạo. Phản hồi bị ngắt; bạn vẫn có thể tải tài liệu bên dưới.'
        self.work = self.log.close(self.complete) if self.log else {'player': self.player_session.trace()} \
            if self.player_session and (self.player_session.receipts or self.player_session.reply_guard) else None
        with anyio.CancelScope(shield=True):
            try:
                self.state = await chat_turns.persist(s.owner, s.request_id, content=reply, sources=self.sources,
                    artifacts=artifacts, work=self.work, provider=s.own_provider,
                    state='complete' if self.complete else 'timeout' if self.outcome == 'timeout' else
                          'interrupted' if self.outcome == 'cancelled' else 'error',
                    outcome='stream_interrupted' if self.outcome == 'cancelled' else self.outcome,
                    save_empty=s.mode == 'chat', allow_empty=self.silent)
            except Exception:
                logger.exception('Không lưu được câu trả lời của lượt chat')
                self.outcome = 'persistence_error'
                self.state = await chat_turns.finish(s.owner, s.request_id, 'interrupted', 'persistence_error')
                self.failure = 'Chưa lưu được toàn bộ câu trả lời. Kiểm tra lịch sử trước khi thử lại nhé.'
            if self.snapshot is not None and self.snapshot.sent and self.message_id:
                # G1.1c: khối runtime đã gửi Grok cho tin này; lượt sau gửi lại nguyên văn để giữ prompt cache.
                try:
                    await db.set_message_runtime(s.owner, self.conversation_id, self.message_id, self.snapshot.sent[0])
                except Exception:
                    logger.exception('Không lưu được khối runtime của lượt chat')
            if self.state != 'complete':
                self.complete = False
                if self.outcome == 'cancelled' and self.state != 'stopped':
                    self.outcome = 'stream_interrupted'
                if self.outcome == 'complete':
                    self.outcome = 'scope_changed' if self.state == 'interrupted' else self.state
                if self.work:
                    self.work['complete'] = False
                if self.state != 'stopped' and not self.failure:
                    self.failure = 'Lượt đã bị ngắt hoặc hội thoại đã thay đổi. Mở lại lịch sử trước khi thử lại nhé.'
        self._record_timing()

    def _record_timing(self) -> None:
        s = self.s
        ended_at = perf_counter()
        logger.info(
            "chat_timing model=%s effort=%s mode=%s queue_ms=%s prepare_ms=%s first_text_ms=%s total_ms=%d search=%s complete=%s outcome=%s",
            f"byok:{s.own_provider}" if s.own_key else s.model, s.effort, s.mode,
            round((self.admitted_at - self.started) * 1000) if self.admitted_at is not None else None,
            round((self.prepared_at - self.admitted_at) * 1000) if self.prepared_at is not None and self.admitted_at is not None else None,
            round((self.first_text_at - self.started) * 1000) if self.first_text_at is not None else None,
            round((ended_at - self.started) * 1000), self.search_started, self.complete, self.outcome,
        )
        usage_events.record(
            "turn", service="byok" if s.own_key else ai_models.MODELS[s.model].service,
            model=f"byok:{s.own_provider}" if s.own_key else s.model, surface=s.mode,
            slug=None if s.own_key else config.XAI_MODEL if s.model == 'peto' else ai_models.MODELS[s.model].slug,
            outcome="stopped" if self.state == "stopped" else self.outcome, complete=self.complete,
            effort=s.effort,
            elapsed_ms=round((ended_at - self.started) * 1000),
            first_text_ms=round((self.first_text_at - self.started) * 1000) if self.first_text_at is not None else None,
        )

    async def events(self) -> AsyncIterator[str]:
        s = self.s
        try:
            async with admission.slot(s.owner):
                self.admitted_at = perf_counter()
                # aclosing: đóng lượt (trình duyệt ngắt) phải đóng ngay bước đang chạy, như khi còn là một hàm.
                async with aclosing(self._read_new_files()) as events:
                    async for event in events:
                        yield event
                await self._save_user_message()
                stored_user = next(row for row in self.rows if row["id"] == self.message_id)
                yield sse({
                    "type": "meta", "conversation_id": self.conversation_id, "effort": s.effort,
                    "message": _public_message(stored_user),
                    # Không có tra web thì chữ Companion không bị thay bằng bản nháp sau tìm kiếm.
                    "voice_stream": s.mode == "companion" and s.web_search == "off",
                })
                await self.checkpoint(force=True)
                async with aclosing(self._reread_old_files()) as events:
                    async for event in events:
                        yield event
                await self._build_prompt()
                async with aclosing(self._prepare_history()) as events:
                    async for event in events:
                        yield event
                await self._open_sessions()
                async with aclosing(self._reply()) as events:
                    async for event in events:
                        yield event
        except (AdmissionDenied, conversation_actions.RevisionTargetMissing, ProviderError, TimeoutError, Exception) as error:
            self._record_failure(error)
        finally:
            await self._persist()
        if self.state == 'stopped':
            return
        if self.log and self.work is not None and self.admitted_at is not None:
            # Bản chốt của nhật ký (bước suy nghĩ quá ngắn đã bỏ, bước dở đã đóng), đúng như bản lưu cùng tin nhắn.
            yield sse({"type": "work", "work": self.work})
        if self.failure:
            event: dict[str, str | int] = {"type": "error", "message": self.failure}
            if self.failure_status is not None:
                event["status"] = self.failure_status
            yield sse(event)
        else:
            self.turn_complete = self.complete
            # Đánh dấu "đang ghi nhớ" trước "done" cho trường ``pending`` của GET /api/companion/memory. Dòng "Peto vừa
            # ghi nhớ" từng đọc trường này đã bỏ ngày 11/10/2026; hiện trang không đọc nó nữa.
            if self.complete and s.remembers and await companion_memory.enabled_for(s.owner):
                companion_memory.mark_pending(s.owner)
            # Mã câu trả lời vừa lưu: Companion cần nó để Trả lời hay Xóa tin này mà không tải lại mạch.
            saved_turn = await chat_turns.get(s.owner, s.request_id)
            yield sse({"type": "done", "message_id": saved_turn['assistant_message_id'] if saved_turn else None})


async def chat(request: ChatRequest, owner: str = Depends(current_owner), http_request: Request = None):
    setup = await _resolve_turn(request, owner, http_request)
    request_id = setup.request_id
    await chat_turns.reserve(owner, request_id)
    turn = _ChatTurn(setup)

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
                    stream = turn.events()
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
        conversation_id, mode = turn.conversation_id, setup.mode
        if conversation_id and mode == "chat":
            await titles.maybe_generate(owner, conversation_id, setup.model)
        # Tóm tắt phần cũ sau câu trả lời (G1.3), chỉ khi lượt hoàn tất: lượt dừng hay lỗi không tốn thêm lần gọi nào.
        if conversation_id and mode == "chat" and turn.turn_complete and turn.compaction:
            await chat_context.compact(owner, conversation_id, **turn.compaction)
        # Ghi nhớ chạy sau khi trả lời xong, như đặt tiêu đề: câu trả lời và giọng đọc không phải chờ.
        if conversation_id and setup.remembers and turn.turn_complete:
            await companion_memory.remember(owner, MAX_HISTORY_MESSAGES)

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
