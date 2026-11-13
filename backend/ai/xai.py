"""Responses API: stream văn bản và chạy công cụ được đăng ký của web.

xAI (Peto) và OpenAI (dòng GPT-6, ``ai/gpt.py``) dùng cùng dạng Responses API, nên ``ResponsesProvider`` giữ chung
vòng công cụ, tìm web và nguồn tham khảo; mỗi dịch vụ chỉ khác cách lấy khóa, tên model và lời báo lỗi.
"""

from __future__ import annotations

import hashlib
import logging
import json
from time import perf_counter
import anyio
from collections.abc import AsyncIterator
from contextlib import aclosing

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from core import usage_events
from core import config
from core.config import MAX_HISTORY_IMAGES, XAI_API_BASE, XAI_MAX_OUTPUT_TOKENS, XAI_MODEL, WEB_SEARCH_ENABLED
from ai.xai_auth import XaiAuth, XaiAuthError
from shared.attachment_tools import NAMES as FILE_TOOLS, current_files
from shared.time_tools import execute_tool
from features.documents.tools import current_session
from features.connectors.tools import current_session as github_session_context, NAMES as GITHUB_TOOLS
from shared.web_search import normalize_sources, search_context, citation_ids
from shared.source_activity import display_sources
from shared import chat_history_tools
from features.companion import player_tools
from features.chat.context_budget import enforce as enforce_chat_budget, side_output_cap
from features.chat import capabilities, request_context
from prompts.chat import (CODE_PROMPT, FINALIZING_PROMPT, FOLLOW_UP_PROMPT, GITHUB_PROMPT, NO_GITHUB_PROMPT,
                          RUNTIME_PLACEMENT_PROMPT, SEARCH_FALLBACK_PROMPT)

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk

# Chỉ lấy bản tóm tắt. reasoning_text là suy nghĩ thô, dài và dễ lộ bước bịa.
_REASONING_DELTA_TYPES = {
    "response.reasoning_summary_text.delta",
}

logger = logging.getLogger("peto_web.xai")
# Công cụ tạo tệp trong chat: tên → (dòng trạng thái khi đang làm, phương thức của DocumentSession).
DOCUMENT_TOOLS = {
    'create_document': ('Đang dàn trang và tạo tệp…', 'create'),
    'create_presentation': ('Đang dàn trang slide…', 'present'),
    'create_spreadsheet': ('Đang tính bảng tính…', 'tabulate'),
    'edit_spreadsheet': ('Đang sửa tệp Excel…', 'edit'),
    'edit_document': ('Đang sửa tệp Word…', 'revise'),
}

_TEXT_TYPE = {"user": "input_text", "assistant": "output_text"}
MAX_TOOL_ROUNDS = 3
MAX_GITHUB_TOOL_ROUNDS = 12
MAX_TOOL_CALLS = 8
MAX_GITHUB_TOOL_CALLS = 30
# Hội thoại có tệp Excel hay Word sửa được: sửa một bảng nhiều lỗi cần vài lần edit_spreadsheet (40 thay đổi mỗi lần),
# giải cả bài trong tệp Word cần vài lần edit_document, cộng lần làm lại khi bị từ chối và vài lần tra trong tệp.
MAX_WORKBOOK_TOOL_ROUNDS = 8
MAX_WORKBOOK_TOOL_CALLS = 16
# Grok soạn lệnh công cụ dài hay suy nghĩ mà chưa có gì để hiện: cứ chừng này giây báo một nhịp "vẫn đang làm", để lượt
# chat không bị coi là kẹt và kết nối không bị cắt vì im lặng.
PULSE_SECONDS = 10.0
# Lượt nhờ sửa tệp Excel mà một lần gọi chỉ viết câu ngắn chừng này rồi dừng, chưa gọi công cụ nào: nhắc Grok làm tiếp một
# lần. Ngày 5/10/2026, ở mức Thấp, Grok suy nghĩ 46 giây, viết "Peto sửa lại từ file gốc, không đụng sheet Quy_dinh." rồi
# kết thúc lượt, nên người dùng không nhận được tệp nào.
FOLLOW_UP_CHARS = 300
FOLLOW_UP = FOLLOW_UP_PROMPT


def _dump(item) -> dict:
    return item if isinstance(item, dict) else item.model_dump(mode="json", exclude_none=True)


def _clip(value) -> str:
    return " ".join(str(value or "").split())[:500] or "không rõ lý do"


def _item_source_candidates(item: dict) -> list[dict]:
    candidates = []
    if item.get("type") == "message":
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                candidates.extend({**annotation, "kind": "citation", 'citation_ids': citation_ids(annotation, part.get('text') or '')}
                                  for annotation in part.get("annotations") or []
                                  if isinstance(annotation, dict) and annotation.get("type") == "url_citation")
    elif item.get("type") == "web_search_call":
        action = item.get('action') or {}
        if item.get('status') == 'failed':
            return []
        if action.get('type') in {'open_page', 'find_in_page'}:
            if item.get('status') == 'completed' and action.get('url'):
                candidates.append({'url': action['url'], 'kind': 'result', 'access': 'page'})
        else:
            access = 'page' if action.get('type') == 'fetch' and item.get('status') == 'completed' else 'search'
            candidates.extend({**source, "kind": "result", 'access': access}
                              for source in action.get("sources") or [] if isinstance(source, dict))
    return candidates


def _item_sources(item: dict) -> list[dict]:
    return normalize_sources(_item_source_candidates(item))


def _source_activity(item: dict, provider: str, round_index: int) -> dict | None:
    """Keep native provenance before the compatibility source list is flattened/capped."""
    kind = item.get('type')
    completed = item.get('status') == 'completed'
    sources = display_sources(_item_source_candidates(item)) if kind == 'message' or completed else []
    info = {'sources': sources}
    if kind == 'web_search_call':
        action = item.get('action') if isinstance(item.get('action'), dict) else {}
        operation = action.get('type')
        native_id = item.get('id')
        if isinstance(operation, str) and operation in {'search', 'fetch', 'open_page', 'find_in_page'} and isinstance(native_id, str) and native_id:
            queries = [action['query']] if isinstance(action.get('query'), str) else []
            if isinstance(action.get('queries'), list):
                queries.extend(query for query in action['queries'] if isinstance(query, str))
            call = {'id': f'{provider}:{round_index}:{native_id}',
                    'kind': 'search' if operation == 'search' else 'page', 'operation': operation,
                    'queries': queries, 'state': 'done' if completed else 'failed' if item.get('status') in ('failed', 'incomplete') else 'live',
                    'source_urls': [source['url'] for source in sources]}
            if isinstance(action.get('url'), str):
                call['url'] = action['url']
            info['call'] = call
    return info if sources or 'call' in info else None


def build_input_payload(messages: list[ChatMessage]) -> list[dict]:
    """Đổi lịch sử nội bộ thành input của Responses API, có ảnh và tệp chữ."""
    keep_images = _recent_image_keys(messages, MAX_HISTORY_IMAGES)
    payload: list[dict] = []
    for index, message in enumerate(messages):
        text_type = _TEXT_TYPE.get(message.role, "input_text")
        parts: list[dict] = []
        for att_index, attachment in enumerate(message.attachments):
            key = (index, att_index)
            if attachment.kind == "image" and attachment.data_url and key in keep_images:
                if attachment.source_label:
                    parts.append({"type": text_type, "text": attachment.source_label})
                elif attachment.number:
                    # Số ảnh model dùng khi chèn ảnh vào tài liệu: ![chú thích](anh-N).
                    parts.append({"type": text_type, "text": f"[Ảnh {attachment.number}: {attachment.name}]"})
                parts.append(
                    {
                        "type": "input_image",
                        "image_url": attachment.data_url,
                        "detail": "high",
                    }
                )
            elif attachment.kind == "file" and attachment.text_excerpt:
                parts.append(
                    {
                        "type": text_type,
                        "text": f"[Tệp đính kèm: {attachment.name}]\n{attachment.text_excerpt}",
                    }
                )
            else:
                label = "Tệp" if attachment.kind != "image" else f"Ảnh {attachment.number}" if attachment.number else "Ảnh"
                parts.append(
                    {
                        "type": text_type,
                        "text": f"[{label} đính kèm: {attachment.name}]",
                    }
                )
        if message.content:
            parts.append({"type": text_type, "text": message.content})
        sources = normalize_sources(message.sources)
        if message.role == "assistant" and sources:
            parts.append({"type": "output_text", "text": "[Nguồn tham khảo của câu trả lời trước, không phải kết quả tra mới]\n" + json.dumps(sources, ensure_ascii=False)})
        if not parts:
            parts.append({"type": text_type, "text": ""})
        payload.append({"role": message.role, "content": parts})
    return payload


def _recent_image_keys(messages: list[ChatMessage], limit: int) -> set[tuple[int, int]]:
    keys: list[tuple[int, int]] = []
    for index in range(len(messages) - 1, -1, -1):
        for att_index, attachment in enumerate(messages[index].attachments):
            if attachment.kind == "image" and attachment.data_url:
                keys.append((index, att_index))
                if len(keys) >= limit:
                    return set(keys)
    return set(keys)


def code_result(item: dict) -> dict:
    """Kết quả một lần chạy mã của xAI (item ``code_interpreter_call``). Lần chạy thật ngày 21/10/2026: ``outputs`` là
    ``[{"type": "logs", "logs": "<JSON>"}]`` và chuỗi ``logs`` lại là JSON gồm stdout, stderr, exit_code,
    command_timed_out. Chuỗi không phải JSON thì coi cả chuỗi là chữ in ra (dạng của OpenAI)."""
    stdout, stderr, exit_code, timed_out, images = [], [], None, False, 0
    for output in item.get('outputs') or []:
        if not isinstance(output, dict):
            continue
        if output.get('type') == 'logs':
            raw = output.get('logs')
            try:
                data = json.loads(raw) if isinstance(raw, str) else None
            except ValueError:
                data = None
            if isinstance(data, dict):
                stdout.append(str(data.get('stdout') or ''))
                stderr.append(str(data.get('stderr') or ''))
                if isinstance(data.get('exit_code'), int) and not isinstance(data.get('exit_code'), bool):
                    exit_code = data['exit_code']
                timed_out = timed_out or data.get('command_timed_out') is True
            elif raw:
                stdout.append(str(raw))
        elif output.get('type') == 'image':
            images += 1
    return {'code': str(item.get('code') or ''), 'stdout': ''.join(stdout), 'stderr': ''.join(stderr),
            'exit_code': exit_code, 'timed_out': timed_out, 'status': item.get('status'), 'images': images}


def prefix_hash(request: dict) -> str:
    """Dấu vân tay phần đầu cố định của một request Responses: 8 ký tự hex SHA-256 của ``instructions`` và ``tools``.
    Không chứa chữ nào của người dùng; chỉ để so hai lần gọi liền nhau có cùng phần đầu (prompt cache) hay không."""
    head = json.dumps([request.get('instructions'), request.get('tools')], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(head.encode('utf-8')).hexdigest()[:8]


class _SearchFallback(Exception):
    """Ngắt lượt tra bị lỗi để dành một lượt tổng hợp từ kết quả đã nhận."""


class ResponsesProvider(ChatProvider):
    supported_efforts = ("low", "medium", "high")
    """Phần chung của các dịch vụ dùng Responses API. Lớp con đặt ``_client``, ``model`` và ``max_output_tokens``."""

    name = "responses"
    # Tên dịch vụ trong log máy chủ.
    service = "AI"
    # Dịch vụ chạy mã Python phía mình (``code_interpreter``) đã được thử thật qua đúng đường kết nối của Peto. Chỉ xAI
    # (phép thử 21/10/2026); OpenAI chưa thử, khóa riêng của người dùng chỉ ở Companion.
    code_interpreter = False
    auth_error_message = "Kết nối AI của Peto đã hết hạn. Người quản trị cần đăng nhập lại."
    rate_limit_message = "Peto đang nhận nhiều yêu cầu quá. Đợi chút rồi thử lại nha."
    _client: AsyncOpenAI
    model: str
    max_output_tokens: int
    # Vai của item chứa khối runtime của lượt Chat ở đuôi ``input`` (gói G1.1). None: tài liệu của dịch vụ không nói rõ
    # một item system/developer ở cuối được hỗ trợ (xAI), nên khối đầu lượt là một phần nội dung riêng, có hàng rào,
    # gắn vào tin người dùng hiện tại; khối nối thêm ở vòng sau là một tin vai user riêng.
    runtime_role: str | None = None
    # Gửi ``prompt_cache_key`` (băm từ mã hội thoại) cho lượt Chat: chỉ dịch vụ có tài liệu xác nhận khóa giúp cache.
    prompt_cache_key = False

    async def _prepare(self) -> None:
        """Lấy khóa trước mỗi lượt gọi."""

    def _place_runtime(self, payload: list[dict], text: str, *, first: bool = False) -> None:
        """Nối một khối runtime của máy chủ vào đuôi ``payload``; chỉ nối thêm, không sửa item nào phía trước."""
        part = {"type": "input_text", "text": request_context.fence(text)}
        if self.runtime_role:
            payload.append(request_context.ServerBlock(role=self.runtime_role, content=[part]))
        elif first and payload and payload[-1].get("role") == "user" and isinstance(payload[-1].get("content"), list):
            payload[-1]["content"].append(part)
            snapshot = request_context.current.get()
            if snapshot is not None:
                # Lưu nguyên văn để lượt sau gửi lại đúng chỗ này (G1.1c).
                snapshot.sent.append(part["text"])
        else:
            payload.append(request_context.ServerBlock(role="user", content=[part]))

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
        timezone: str | None = None,
        web_search: str = "auto",
        tools_enabled: bool = True,
    ) -> AsyncIterator[str | StreamChunk]:
        if web_search == "on" and not WEB_SEARCH_ENABLED:
            raise ProviderError("Tìm kiếm web đang tắt trên máy chủ. Chọn Tự động hoặc Tắt để tiếp tục chat.")
        await self._prepare()
        run = _ResponsesRun(self, system_prompt, messages, effort, timezone, web_search, tools_enabled)
        await run.setup()
        # aclosing ở mọi tầng: đóng luồng này (trình duyệt ngắt, lượt dừng) phải đóng ngay các bước bên trong, như khi
        # tất cả còn nằm trong một hàm (lệnh Player đang chờ được dọn ngay, stream của dịch vụ được đóng).
        async with aclosing(run.rounds()) as chunks:
            async for chunk in chunks:
                yield chunk


class _ResponsesRun:
    """Một lần ``ResponsesProvider.stream`` (gói G3.2, 13/11/2026: tách từ hàm 472 dòng, không đổi hành vi).

    Mỗi vòng: chọn công cụ (``capabilities.select``) → dựng request (khối runtime ở đuôi, ngân sách) → gọi dịch vụ và đổi
    sự kiện thành mảnh stream → quyết định dừng, nhắc làm tiếp, tổng hợp sau lượt tra lỗi, hay chạy công cụ rồi gọi tiếp.
    Trạng thái dùng chung giữa các vòng nằm trên ``self``; thứ tự mảnh stream giữ nguyên như trước khi tách.
    """

    def __init__(self, provider: 'ResponsesProvider', system_prompt: str, messages: list[ChatMessage], effort: str,
                 timezone: str | None, web_search: str, tools_enabled: bool):
        self.p = provider
        self.system_prompt = system_prompt
        self.messages = messages
        self.effort = effort
        self.timezone = timezone
        self.web_search = web_search
        self.tools_enabled = tools_enabled
        self.sources: list[dict] = []
        self.search_finished = False
        self.search_ids: set[str] = set()
        # Lần chạy mã đã báo: item về hai lần (output_item.done rồi response.completed), mỗi lần chạy chỉ một bước.
        self.code_ids: set[str] = set()
        self.usable_search_sources: list[dict] = []
        self.search_fallback = False
        self.calls_used = 0
        # Manifest công cụ đã báo trong khối runtime gần nhất: vòng nào khác thì nối thêm một bản snapshot mới.
        self.shown_manifest = None
        self.follow_up_next = False
        self.round_index = 0
        self.finalizing = False

    async def setup(self) -> None:
        """Input (lịch sử, vô hiệu thẻ runtime giả, khối runtime đã gửi Grok), các phiên công cụ và instructions."""
        p = self.p
        self.payload_input = build_input_payload(self.messages)
        # Lượt Chat: chữ không do máy chủ tạo (hồ sơ, trí nhớ, tài liệu dự án trong system prompt; tin, nhãn và trích
        # đoạn tệp trong lịch sử; kết quả công cụ) không được mang thẻ <peto_runtime> thật, để không giả được khối runtime.
        # Lượt khác không có khối runtime nên giữ nguyên byte.
        self.chat_turn = request_context.current.get() is not None
        system_prompt = self.system_prompt
        if self.chat_turn:
            system_prompt = request_context.neutralize(system_prompt)
            for item in self.payload_input:
                for part in item["content"]:
                    if "text" in part:
                        part["text"] = request_context.neutralize(part["text"])
            if not p.runtime_role:
                # G1.1c: Grok chỉ đọc lại cache khi cả request lượt trước là phần đầu của lượt sau (đo trên VPS 13/11/2026:
                # bỏ khối này khỏi lịch sử thì chỉ còn 1.152 token cache). Gắn lại nguyên văn khối runtime đã gửi vào đúng
                # tin người dùng, sau bước vô hiệu thẻ: đây là chữ của máy chủ lưu riêng, người dùng không ghi được.
                for item, message in zip(self.payload_input, self.messages):
                    if message.role == "user" and message.runtime:
                        item["content"].append({"type": "input_text", "text": message.runtime})
        self.search_enabled = self.tools_enabled and WEB_SEARCH_ENABLED and self.web_search != "off"
        self.instructions = f"{system_prompt}\n\n{search_context(self.web_search, self.search_enabled)}"
        # Only Web Chat owns a display catalogue. Companion/Agent keep their existing protocol.
        self.activity_enabled = request_context.current.get() is not None
        self.document_session = current_session.get()
        # Tệp đã gửi trong hội thoại: công cụ tìm/đọc chỉ có khi hội thoại có tệp chữ, PDF, Word hoặc Excel.
        self.files = current_files.get()
        self.file_schemas = self.files.schemas() if self.files else []
        self.chat_history = chat_history_tools.current.get()
        self.github_session = github_session_context.get()
        self.snapshot = snapshot = request_context.current.get()
        self.github_state, self.github_reason = (await self.github_session.availability() if self.github_session else
                                                 (snapshot.github_state, snapshot.github_reason) if snapshot else
                                                 ('unauthorized', 'not_connected'))
        self.github_schemas = self.github_session.schemas() if self.github_session and self.github_state == 'available' else []
        # Chạy mã chỉ ở tab Trò chuyện (có snapshot), không ở Companion hay lượt đặt tên/tóm tắt.
        self.code_reason = ('provider_unsupported' if not p.code_interpreter else
                            'server_disabled' if not config.XAI_CODE_EXECUTION else
                            'chat_only' if snapshot is None or not self.tools_enabled else None)
        # Tab Trò chuyện: instructions đóng băng một lần cho cả lượt (trạng thái GitHub lúc bắt đầu lượt); mọi thứ đổi
        # theo lượt hay theo vòng nằm trong khối runtime ở đuôi input. Lượt khác (Companion, đặt tên, tóm tắt) giữ nguyên.
        self.chat_instructions = (self.instructions + ('\n\n' + (GITHUB_PROMPT if self.github_state == 'available' else NO_GITHUB_PROMPT) if self.tools_enabled else '')
                                  + ('\n\n' + CODE_PROMPT if self.code_reason is None else '')
                                  + '\n\n' + RUNTIME_PLACEMENT_PROMPT) if snapshot is not None else None
        document_session = self.document_session
        workbooks = bool(document_session and (getattr(document_session, 'workbooks', None)
                                               or getattr(document_session, 'word_files', None)))
        self.max_rounds = max(MAX_TOOL_ROUNDS, MAX_GITHUB_TOOL_ROUNDS if self.github_schemas else 0, MAX_WORKBOOK_TOOL_ROUNDS if workbooks else 0)
        self.max_calls = max(MAX_TOOL_CALLS, MAX_GITHUB_TOOL_CALLS if self.github_schemas else 0, MAX_WORKBOOK_TOOL_CALLS if workbooks else 0)
        # Lượt nhờ sửa tệp Excel hay Word còn có thể nhắc làm tiếp: chưa sửa hay tạo tệp nào, và chưa nhắc lần nào.
        self.watching = bool(p.service == "xAI" and self.tools_enabled and workbooks and getattr(document_session, "edit_request", False))

    def tool_output(self, result: dict) -> str:
        text = json.dumps(result, ensure_ascii=False)
        return request_context.neutralize(text) if self.chat_turn else text

    def record_tool_result(self, result):
        # Ghi một kết quả dispatch (kể cả từ chối), không ghi args/tên công cụ/nội dung hoặc ID.
        if self.snapshot is not None:
            usage_events.record('chat_event', service=getattr(self.p, 'usage_service', self.p.service),
                model=self.snapshot.model, surface='chat', effort=self.effort, purpose='tool',
                outcome='error' if result.get('error') or result.get('ok') is False else 'ok')

    def observe_item(self, item: dict):
        if self.activity_enabled and (activity := _source_activity(item, self.p.name, self.round_index)):
            yield StreamChunk('source_activity', info=activity)
        if item.get("type") == "code_interpreter_call" and item.get("status") not in {None, "in_progress", "interpreting"}:
            key = str(item.get("id") or f"code-{len(self.code_ids)}")
            if key not in self.code_ids:
                self.code_ids.add(key)
                yield StreamChunk("code", "done", info=code_result(item))
        if item.get("type") == "web_search_call":
            # Claude đọc trang từ link (action "fetch") không phải một lượt tra web tính phí theo lượt.
            if item.get("id") and (item.get("action") or {}).get("type") != "fetch":
                self.search_ids.add(str(item["id"]))
            if item.get("status") == "failed":
                # Chỉ kết quả tra thành công trong lượt này mới cho phép tổng hợp; nguồn cũ hoặc nguồn
                # nằm trong chính item bị lỗi không chứng minh đã tra được.
                if self.usable_search_sources and not self.search_fallback and not self.finalizing:
                    raise _SearchFallback()
                raise ProviderError("Peto chưa tra cứu web được lượt này. Bạn thử lại nhé.")
            if item.get("status") == "completed":
                self.usable_search_sources = normalize_sources([*self.usable_search_sources, *_item_sources(item)])
            self.search_finished = self.search_finished or item.get("status") == "completed"
            if (item.get("action") or {}).get("type") in {'fetch', 'open_page', 'find_in_page'}:
                yield StreamChunk("page", "fetched" if item.get('status') == 'completed' else 'fetching')
            else:
                yield StreamChunk("search", "completed" if item.get("status") == "completed" else "searching")
        merged = normalize_sources([*self.sources, *_item_sources(item)])
        if merged != self.sources:
            self.sources = merged
            yield StreamChunk("sources", sources=tuple(self.sources))

    def drop_pre_search_draft(self) -> StreamChunk | None:
        """Grok hay viết móc câu hay câu dẫn rồi search rồi viết tiếp. Mỗi lần tra, chữ viết từ lần tra trước tới giờ
        là bản nháp: tab Trò chuyện đưa câu ngắn vào nhật ký "Đang làm", Companion bỏ đi. Trước đây chỉ lần tra đầu
        được xử lý, nên câu dẫn trước lần tra thứ hai ở lại và dính liền vào câu trả lời ("phân tích.Ad gửi…")."""
        self.written.clear()
        self.held.clear()
        if self.emitted_text:
            self.emitted_text = False
            return StreamChunk("replace")
        return None

    async def rounds(self) -> AsyncIterator[str | StreamChunk]:
        for round_index in range(self.max_rounds + 1):
            self.round_index = round_index
            self.follow_up, self.follow_up_next = self.follow_up_next, False
            # Dành lần gọi cuối để tổng hợp kết quả đã đọc, không mở thêm tra cứu khi hết ngân sách.
            self.finalizing = self.tools_enabled and (self.search_fallback or round_index == self.max_rounds
                                                      or self.calls_used >= self.max_calls)
            if round_index and self.github_session:
                self.github_state, self.github_reason = await self.github_session.availability()
            self.plan = capabilities.select(documents=self.document_session, files=self.files, history=self.chat_history,
                github_state=self.github_state, github_reason=self.github_reason, search_enabled=self.search_enabled,
                web_search=self.web_search, tools_enabled=self.tools_enabled, finalizing=self.finalizing,
                required_search=self.search_enabled and self.web_search == 'on' and round_index == 0 and not self.finalizing,
                search_fallback=self.search_fallback, code_reason=self.code_reason)
            self.round_started = perf_counter()
            if self.tools_enabled and not self.follow_up:
                # Mốc cho nhật ký "Đang làm": từ đây tới chữ hay lệnh đầu tiên là lúc mô hình suy nghĩ. Lần gọi nhắc làm
                # tiếp không có mốc riêng: phía chat coi câu báo lần trước vẫn là bản nháp của lần gọi này, để khi Grok gọi
                # công cụ thì câu báo thành câu dẫn trong nhật ký.
                yield StreamChunk("round")
            self.create_kwargs = self._request()
            async with aclosing(self._call()) as chunks:
                async for chunk in chunks:
                    yield chunk
            self.decision = 'tools'
            async with aclosing(self._finish_round()) as chunks:
                async for chunk in chunks:
                    yield chunk
            if self.decision == 'continue':
                continue
            if self.decision == 'return':
                return
            async with aclosing(self._run_tools()) as chunks:
                async for chunk in chunks:
                    yield chunk

    def _request(self) -> dict:
        """Tham số gọi Responses của vòng này; khối runtime nối vào đuôi input, kiểm ngân sách request thật."""
        p, snapshot, finalizing = self.p, self.snapshot, self.finalizing
        create_kwargs: dict = {
            "model": p.model,
            "instructions": self.chat_instructions if self.chat_instructions is not None else
                            self.instructions + ('\n\n' + (GITHUB_PROMPT if self.github_state == 'available' else NO_GITHUB_PROMPT) if self.tools_enabled else '')
                                              + ('\n\n' + CODE_PROMPT if self.code_reason is None else '')
                                              + ('\n\n' + SEARCH_FALLBACK_PROMPT if self.search_fallback else
                                                  '\n\n' + FINALIZING_PROMPT if finalizing else ''),
            "input": self.payload_input,
            "max_output_tokens": p.max_output_tokens if self.tools_enabled else side_output_cap(p.max_output_tokens),
            "reasoning": {
                "effort": self.effort if self.effort in p.supported_efforts else "low"
            },
            "stream": True,
            "tools": self.plan.schemas,
            "include": ["reasoning.encrypted_content"],
            # Tự giữ các item trong lượt này, không cần lưu hội thoại ở dịch vụ AI.
            "store": False,
        }
        if not getattr(p, "send_reasoning", True):
            # Khóa riêng của người dùng với model không chỉnh được mức suy nghĩ (ai/byok.py): gửi tham số này thì cả
            # lượt bị từ chối.
            create_kwargs.pop("reasoning")
            create_kwargs["include"] = []
        if finalizing:
            # Danh sách công cụ đã rỗng: không gửi tool_choice, kể cả "none", vì xAI từ chối cặp này.
            logger.info("Kết thúc tra cứu: vòng=%d công_cụ_đã_gọi=%d github=%s", self.round_index, self.calls_used, bool(self.github_schemas))
        if self.search_enabled:
            create_kwargs["include"].append("web_search_call.action.sources")
            if self.web_search == "on" and self.round_index == 0 and not finalizing:
                # Chỉ đưa công cụ tìm web ở lần đầu để 'required' không bị thỏa bởi đồng hồ.
                create_kwargs["tool_choice"] = "required"
        if snapshot is not None:
            # Khối runtime ở đuôi input, chỉ nối thêm: đầu lượt một khối đóng băng (giờ, envelope, snapshot); vòng
            # có manifest khác lần báo trước thì thêm một bản snapshot mới (cùng mốc giờ); vòng cuối thêm ghi chú.
            manifest = self.plan.manifest(getattr(p._client, 'native_tools', None))
            details = dict(service=p.service, model=p.model, capabilities=manifest,
                           effort=create_kwargs.get('reasoning', {}).get('effort'))
            if self.shown_manifest is None:
                p._place_runtime(self.payload_input, snapshot.runtime(**details), first=True)
            elif manifest != self.shown_manifest:
                p._place_runtime(self.payload_input, snapshot.render(**details))
            self.shown_manifest = manifest
            if self.search_fallback or finalizing:
                p._place_runtime(self.payload_input, SEARCH_FALLBACK_PROMPT if self.search_fallback else FINALIZING_PROMPT)
            if p.prompt_cache_key:
                # Định tuyến tới máy chủ đang giữ cache của hội thoại; chỉ mã hội thoại đã băm, không có owner.
                create_kwargs["prompt_cache_key"] = "peto-chat-" + hashlib.sha256(
                    snapshot.conversation_id.encode()).hexdigest()[:32]
        enforce_chat_budget(create_kwargs)
        return create_kwargs

    async def _call(self) -> AsyncIterator[str | StreamChunk]:
        """Một lần gọi dịch vụ; đổi lỗi SDK thành ProviderError tiếng Việt, luôn ghi số đo và đóng stream."""
        p = self.p
        self.usage: dict = {}
        self.output_items: list[dict] = []
        self.completed = False
        self.recovering_search = False
        self.emitted_text = self.follow_up       # lần gọi nhắc: câu báo lần trước vẫn đang hiện
        self.noted = False
        self.written: list[str] = []     # chữ lần gọi này đã phát
        # Chữ của lần gọi nhắc được giữ lại: Grok gọi công cụ thì phát (thành câu dẫn cùng câu báo), không gọi thì đó
        # chỉ là "XONG" hay lời đệm, bỏ đi.
        self.held: list[str] = []
        stream = None
        try:
            stream = await p._client.responses.create(**self.create_kwargs)
            pulse_at = perf_counter() + PULSE_SECONDS
            async for event in stream:
                if perf_counter() >= pulse_at:
                    pulse_at = perf_counter() + PULSE_SECONDS
                    yield StreamChunk("pulse")
                for chunk in self._event_chunks(event):
                    yield chunk
        except _SearchFallback:
            self.recovering_search = True
            logger.warning("%s: lượt tìm bổ sung bị lỗi; tổng hợp từ %d nguồn đã tra thành công",
                           p.service, len(self.usable_search_sources))
        except AuthenticationError as err:
            raise ProviderError(p.auth_error_message) from err
        except RateLimitError as err:
            # Lời báo giới hạn lượt/hết hạn mức không chứa nội dung hội thoại hay khóa; ghi để biết là hết tiền hay chỉ quá tải.
            logger.warning("%s giới hạn lượt: %s", p.service, _clip(err.message))
            raise ProviderError(p.rate_limit_message, retryable=True) from err
        except APIConnectionError as err:
            raise ProviderError("Peto chưa kết nối được với dịch vụ AI. Thử lại sau chút nhé.", retryable=True) from err
        except APIStatusError as err:
            logger.warning("%s HTTP %s: %s", p.service, err.status_code, _clip(err.message))
            if self.search_enabled and err.status_code in {400, 403}:
                raise ProviderError("Peto chưa dùng được tìm web với kết nối AI hiện tại. Mở menu + rồi chọn Tắt tìm kiếm web để chat tiếp, hoặc nhờ người quản trị kiểm tra quyền tìm kiếm của dịch vụ.") from err
            raise ProviderError("Peto gặp lỗi kết nối với dịch vụ AI. Thử lại sau nha.", retryable=err.status_code >= 500) from err
        finally:
            self._record_call()
            if stream is not None:
                with anyio.CancelScope(shield=True):
                    await stream.close()

    def _record_call(self) -> None:
        p, usage = self.p, self.usage
        logger.info(
            "model_usage service=%s model=%s purpose=%s round=%d elapsed_ms=%d complete=%s input_tokens=%s output_tokens=%s cached_tokens=%s reasoning_tokens=%s search_calls_seen=%d code_calls_seen=%d",
            p.service, p.model, "chat" if self.tools_enabled else "title", self.round_index + 1,
            round((perf_counter() - self.round_started) * 1000), self.completed,
            usage.get("input_tokens"), usage.get("output_tokens"),
            (usage.get("input_tokens_details") or {}).get("cached_tokens"),
            (usage.get("output_tokens_details") or {}).get("reasoning_tokens"), len(self.search_ids), len(self.code_ids),
        )
        # Khóa riêng của người dùng ghi dịch vụ "byok" và slug "byok/…": trang Quản trị không tính vào chi phí chủ web.
        usage_events.record(
            "call", service=getattr(p, "usage_service", p.service), model=getattr(p, "catalog_key", None),
            slug=getattr(p, "usage_slug", p.model),
            purpose="chat" if self.tools_enabled else "side", complete=self.completed,
            elapsed_ms=round((perf_counter() - self.round_started) * 1000),
            input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
            cached_tokens=(usage.get("input_tokens_details") or {}).get("cached_tokens"),
            cache_write_tokens=(usage.get("input_tokens_details") or {}).get("cache_write_tokens"),
            reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
            search_calls=len(self.search_ids),
            # xAI tự báo số tiền đã tính cho lần gọi; dịch vụ khác không có trường này.
            cost_ticks=usage.get("cost_in_usd_ticks"),
            prefix_hash=prefix_hash(self.create_kwargs),
        )

    def _event_chunks(self, event):
        """Mảnh stream cho một sự kiện của dịch vụ (tra web, chạy mã, đọc trang, gọi công cụ, chữ, kết thúc)."""
        event_type = getattr(event, "type", "")
        if event_type in {"response.web_search_call.in_progress", "response.web_search_call.searching",
                          "response.code_interpreter_call.in_progress", "peto.page_fetch.started"}:
            # Câu dẫn viết trước lúc tra web, chạy mã hay đọc trang: vào nhật ký, không dính vào câu trả lời viết sau.
            draft = self.drop_pre_search_draft()
            if draft is not None:
                yield draft
            yield (StreamChunk("code", "running") if event_type == "response.code_interpreter_call.in_progress" else
                   StreamChunk("page", "fetching") if event_type == "peto.page_fetch.started" else
                   StreamChunk("search", "searching"))
        elif event_type == "response.web_search_call.completed":
            self.search_finished = True
            yield StreamChunk("search", "completed")
        elif event_type == "peto.page_fetch.failed":
            yield StreamChunk("page", "failed")
        elif event_type == "response.output_item.added":
            yield from self._item_added(event.item)
        elif event_type == "response.output_text.annotation.added":
            annotation = _dump(event.annotation)
            if annotation.get("type") == "url_citation":
                if self.activity_enabled:
                    display = display_sources([{**annotation, 'kind': 'citation',
                        'citation_ids': citation_ids(annotation, ''.join(self.written))}])
                    if display:
                        yield StreamChunk('source_activity', info={'sources': display})
                merged = normalize_sources([*self.sources, {**annotation, "kind": "citation",
                                                          'citation_ids': citation_ids(annotation, ''.join(self.written))}])
                if merged != self.sources:
                    self.sources = merged
                    yield StreamChunk("sources", sources=tuple(self.sources))
        elif event_type == 'peto.source_activity':
            if self.activity_enabled and (activity := _source_activity(_dump(event.item), self.p.name, self.round_index)):
                yield StreamChunk('source_activity', info=activity)
        elif event_type in _REASONING_DELTA_TYPES:
            delta = getattr(event, "delta", "")
            if delta:
                yield StreamChunk("thinking", delta)
        elif event_type in {"response.output_text.delta", "peto.citation"}:
            delta = getattr(event, "delta", "")
            if delta:
                self.emitted_text = True
                if self.follow_up:
                    self.held.append(delta)
                else:
                    self.written.append(delta)
                    yield delta
        elif event_type == "response.output_item.done":
            item = _dump(event.item)
            self.output_items.append(item)
            yield from self.observe_item(item)
        elif event_type == "response.completed":
            raw_usage = getattr(event.response, "usage", None)
            self.usage = _dump(raw_usage) if raw_usage is not None else {}
            if getattr(event.response, "status", "completed") != "completed":
                raise ProviderError("Peto chưa trả lời xong. Phần đã viết được giữ lại; bạn có thể yêu cầu tiếp tục.")
            self.completed = True
            if getattr(event.response, "output", None):
                self.output_items = [_dump(item) for item in event.response.output]
                for item in self.output_items:
                    yield from self.observe_item(item)
        elif event_type == "response.incomplete":
            raise ProviderError("Câu trả lời chạm giới hạn của lượt AI. Phần đã viết được giữ lại; bạn có thể yêu cầu tiếp tục.")
        elif event_type in {"response.failed", "error"}:
            raise ProviderError("Peto gặp lỗi khi đang trả lời. Thử lại nha.", retryable=True)

    def _item_added(self, item):
        item_type = getattr(item, "type", "")
        if item_type == "web_search_call":
            if self.activity_enabled and (activity := _source_activity(_dump(item), self.p.name, self.round_index)):
                yield StreamChunk('source_activity', info=activity)
            draft = self.drop_pre_search_draft()
            if draft is not None:
                yield draft
            yield StreamChunk("search", "searching")
        elif item_type == "code_interpreter_call":
            draft = self.drop_pre_search_draft()
            if draft is not None:
                yield draft
            yield StreamChunk("code", "running")
        elif item_type == "function_call":
            if self.held:
                yield "\n\n" + "".join(self.held)
                self.held.clear()
            # Chữ viết trước lệnh gọi công cụ thường là câu dẫn: phía chat đưa nó vào nhật ký "Đang làm"
            # (hoặc giữ trong câu trả lời nếu dài). Báo ngay lúc này để các bước tới đúng thứ tự.
            if self.emitted_text and not self.noted:
                self.noted = True
                yield StreamChunk("note")
            # Bắt đầu viết lệnh gọi công cụ: lệnh sửa Excel dài có thể mất cả phút.
            yield StreamChunk("tool", str(getattr(item, "name", "") or ""))

    async def _finish_round(self) -> AsyncIterator[str | StreamChunk]:
        """Sau một lần gọi: tổng hợp sau lượt tra lỗi, dừng, hay nhắc làm tiếp. Đặt ``self.decision``."""
        if self.recovering_search:
            # Bỏ bản nháp của lần gọi vừa ngắt trước khi mở mốc suy nghĩ mới. Không chạy lệnh công cụ
            # chưa thực thi, không gửi item tra bị lỗi hoặc item đang viết dở sang lượt tổng hợp.
            yield StreamChunk("search", "failed")
            yield StreamChunk("replace")
            self.payload_input.extend(item for item in self.output_items
                                      if item.get("status") in {None, "completed"}
                                      and item.get("type") in {"message", "reasoning", "web_search_call"}
                                      and (item.get("type") != "web_search_call" or item.get("status") == "completed"))
            self.search_fallback = True
            self.search_enabled = False
            self.watching = False
            self.follow_up_next = False
            self.decision = 'continue'
            return
        if not self.completed:
            raise ProviderError("Kết nối tới AI bị ngắt trước khi trả lời xong.", retryable=True)
        self.tool_calls = [item for item in self.output_items if item.get("type") == "function_call"]
        if self.tool_calls and not self.tools_enabled:
            raise ProviderError("Tác vụ đặt tên không được gọi công cụ.")
        if not self.tool_calls:
            if self.web_search == "on" and not self.search_finished and not self.sources:
                raise ProviderError("Dịch vụ chưa xác nhận đã tra web. Peto chưa thể xem câu trả lời này là đã kiểm chứng; bạn thử lại nhé.")
            self.decision = 'return'
            if self.follow_up:
                # Nhắc rồi vẫn không gọi công cụ: câu báo giữ nguyên làm câu trả lời. Chữ ngắn thêm vào (như "XONG")
                # bỏ đi; chữ dài là nội dung thật (danh sách lỗi khi người dùng dặn chờ đồng ý) thì giữ.
                extra = "".join(self.held).strip()
                logger.info("Nhắc làm tiếp: vẫn không gọi công cụ, chữ thêm %d ký tự", len(extra))
                if len(extra) > FOLLOW_UP_CHARS:
                    yield "\n\n" + extra
                return
            written_text = "".join(self.written).strip()
            if self.watching and not self.finalizing and self.round_index + 1 < self.max_rounds \
                    and self.calls_used < self.max_calls and 0 < len(written_text) <= FOLLOW_UP_CHARS:
                self.watching = False
                self.follow_up_next = True
                self.payload_input.extend(self.output_items)
                self.payload_input.append({"role": "user", "content": [{"type": "input_text", "text": FOLLOW_UP}]})
                logger.info("Nhắc làm tiếp: lần gọi %d chỉ viết %d ký tự, chưa gọi công cụ", self.round_index + 1,
                            len(written_text))
                self.decision = 'continue'
            return
        if self.finalizing:
            raise ProviderError("Dịch vụ AI vẫn yêu cầu tra cứu sau khi được yêu cầu kết thúc. Phần đã trả lời được giữ lại; bạn có thể hỏi tiếp về một tệp cụ thể.")

    async def _run_tools(self) -> AsyncIterator[str | StreamChunk]:
        """Chạy các lệnh công cụ của lần gọi vừa xong; mỗi lệnh có đúng một kết quả gửi lại cho mô hình."""
        tool_calls = self.tool_calls
        self.payload_input.extend(self.output_items)
        if self.held:
            yield "\n\n" + "".join(self.held)
            self.held.clear()
        if self.emitted_text and not self.noted:
            # Dịch vụ không báo lúc bắt đầu viết lệnh: chữ trước đó vẫn là câu dẫn.
            yield StreamChunk("note")
        if player_tools.current.get() and any(call.get('name') == player_tools.NAME for call in tool_calls):
            # A draft before a Player action is not a confirmed result. Replace it like a web-search draft.
            draft = self.drop_pre_search_draft()
            if draft is not None:
                yield draft
        for call in tool_calls:
            if not call.get("call_id"):
                raise ProviderError("AI trả về yêu cầu công cụ không hợp lệ. Thử lại nhé.")
            if self.calls_used >= self.max_calls:
                # Mỗi lời gọi vẫn có kết quả tương ứng; lời gọi vượt giới hạn không được thực thi.
                result = {'ok': False, 'error': 'Đã chạm giới hạn tra cứu của lượt này. Công cụ này chưa được chạy; hãy tổng hợp dữ liệu đã có và nêu rõ phần còn thiếu.'}
                self.record_tool_result(result)
                self.payload_input.append({'type': 'function_call_output', 'call_id': call['call_id'],
                                           'output': self.tool_output(result)})
                continue
            self.calls_used += 1
            self.result = None
            async with aclosing(self._dispatch(call)) as chunks:
                async for chunk in chunks:
                    yield chunk
            result = self.result
            self.record_tool_result(result)
            self.payload_input.append({
                "type": "function_call_output", "call_id": call["call_id"],
                "output": self.tool_output(result),
            })

    async def _dispatch(self, call: dict) -> AsyncIterator[StreamChunk]:
        """Chạy một lệnh công cụ đã được phép; đặt ``self.result``."""
        document_session, files = self.document_session, self.files
        if not self.plan.allows(call.get('name')):
            # Một model vẫn có thể bịa lời gọi dù schema không được gửi. Không thực thi ngoài kế hoạch vòng này.
            self.result = {'ok': False, 'error': 'Công cụ không được cấp trong vòng hiện tại; chưa được chạy.',
                           'code': 'tool_not_available'}
        elif call.get('name') == player_tools.NAME and player_tools.current.get():
            async with aclosing(player_tools.current.get().run(call.get('arguments', ''))) as action:
                async for item in action:
                    if isinstance(item, StreamChunk):
                        yield item
                    else:
                        self.result = item
        elif call.get('name') in DOCUMENT_TOOLS and document_session:
            self.watching = False        # Grok đã bắt tay sửa/tạo tệp: không cần nhắc nữa
            status, run = DOCUMENT_TOOLS[call['name']]
            yield StreamChunk('document_status', status)
            result = await getattr(document_session, run)(call.get('arguments', ''))
            # "_ui" là chữ cho nhật ký "Đang làm" (kết quả gọn, các lỗi từng dòng), không gửi cho mô hình.
            ui = result.pop('_ui', None) or {}
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
            yield StreamChunk('tool_result', info={'tool': call['name'], 'ok': bool(result.get('ok')),
                                                   'error': result.get('error'), **ui})
            yield StreamChunk('document_status', '')
            self.result = result
        elif call.get('name') in GITHUB_TOOLS and self.github_schemas:
            yield StreamChunk('connector_lookup', 'Đang đọc GitHub…')
            result = await self.github_session.run(call['name'], call.get('arguments', ''))
            yield StreamChunk('connector_lookup_done', 'Đã đọc GitHub' if result.get('ok') else result.get('error', 'Chưa đọc được GitHub'))
            if result.get('sources'):
                tool_sources = [{**source, 'kind': 'result', 'access': 'tool',
                    **({'partial': True} if result.get('truncated') is True else {})}
                    for source in result['sources'] if isinstance(source, dict)]
                if self.activity_enabled and (display := display_sources(tool_sources)):
                    yield StreamChunk('source_activity', info={'sources': display})
                self.sources = normalize_sources([*self.sources, *tool_sources])
                yield StreamChunk('sources', sources=tuple(self.sources))
            self.result = result
        elif call.get('name') == chat_history_tools.NAME and self.chat_history:
            yield StreamChunk('file_lookup', 'Đang đối chiếu lịch sử gốc…')
            result = await self.chat_history.run(call.get('arguments', ''))
            yield StreamChunk('file_lookup_done', 'Đã đối chiếu lịch sử' if not result.get('error') else result['error'])
            self.result = result
        elif call.get("name") in FILE_TOOLS and self.file_schemas:
            arguments = call.get("arguments", "")
            yield StreamChunk("file_lookup", files.label(call["name"], arguments))
            result = await files.run(call["name"], arguments)
            yield StreamChunk("file_lookup_done", files.label(call["name"], arguments, result))
            self.result = result
        else:
            self.result = execute_tool(call.get("name", ""), call.get("arguments", ""), timezone=self.timezone)

class XAIProvider(ResponsesProvider):
    """Peto: Grok qua tài khoản xAI riêng của web (OAuth, hoặc XAI_API_KEY dự phòng)."""

    name = "xai"
    service = "xAI"
    code_interpreter = True
    # Tài liệu xAI (Responses API): prompt_cache_key được chuyển thành x-grok-conv-id, định tuyến về máy chủ có cache.
    prompt_cache_key = True

    def __init__(self) -> None:
        self._auth = XaiAuth()
        # api_key được thay trước mỗi lượt gọi; giá trị khởi tạo chỉ là chỗ giữ.
        self._client = AsyncOpenAI(api_key="pending", base_url=XAI_API_BASE)
        self.model = XAI_MODEL
        self.max_output_tokens = XAI_MAX_OUTPUT_TOKENS

    async def _prepare(self) -> None:
        try:
            self._client.api_key = await self._auth.get_access_token()
        except XaiAuthError as err:
            raise ProviderError(
                "Peto chưa được kết nối với dịch vụ AI nên chưa trả lời được. "
                "Người quản trị cần chạy lại lệnh đăng nhập."
            ) from err
