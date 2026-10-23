"""Responses API: stream văn bản và chạy công cụ được đăng ký của web.

xAI (Peto) và OpenAI (dòng GPT-6, ``ai/gpt.py``) dùng cùng dạng Responses API, nên ``ResponsesProvider`` giữ chung
vòng công cụ, tìm web và nguồn tham khảo; mỗi dịch vụ chỉ khác cách lấy khóa, tên model và lời báo lỗi.
"""

from __future__ import annotations

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
from shared.web_search import normalize_sources, search_context
from shared import chat_history_tools
from features.companion import player_tools
from features.chat.context_budget import enforce as enforce_chat_budget, side_output_cap
from features.chat import capabilities, request_context
from prompts.chat import (CODE_PROMPT, FINALIZING_PROMPT, FOLLOW_UP_PROMPT, GITHUB_PROMPT, NO_GITHUB_PROMPT,
                          SEARCH_FALLBACK_PROMPT)

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


def _item_sources(item: dict) -> list[dict]:
    candidates = []
    if item.get("type") == "message":
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                candidates.extend({**annotation, "kind": "citation"} for annotation in part.get("annotations") or [] if annotation.get("type") == "url_citation")
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
    return normalize_sources(candidates)


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

    async def _prepare(self) -> None:
        """Lấy khóa trước mỗi lượt gọi."""

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

        payload_input = build_input_payload(messages)
        search_enabled = tools_enabled and WEB_SEARCH_ENABLED and web_search != "off"
        instructions = f"{system_prompt}\n\n{search_context(web_search, search_enabled)}"
        sources: list[dict] = []
        search_finished = False
        search_ids: set[str] = set()
        # Lần chạy mã đã báo: item về hai lần (output_item.done rồi response.completed), mỗi lần chạy chỉ một bước.
        code_ids: set[str] = set()
        usable_search_sources: list[dict] = []
        search_fallback = False

        def observe_item(item: dict):
            nonlocal sources, search_finished, usable_search_sources
            if item.get("type") == "code_interpreter_call" and item.get("status") not in {None, "in_progress", "interpreting"}:
                key = str(item.get("id") or f"code-{len(code_ids)}")
                if key not in code_ids:
                    code_ids.add(key)
                    yield StreamChunk("code", "done", info=code_result(item))
            if item.get("type") == "web_search_call":
                # Claude đọc trang từ link (action "fetch") không phải một lượt tra web tính phí theo lượt.
                if item.get("id") and (item.get("action") or {}).get("type") != "fetch":
                    search_ids.add(str(item["id"]))
                if item.get("status") == "failed":
                    # Chỉ kết quả tra thành công trong lượt này mới cho phép tổng hợp; nguồn cũ hoặc nguồn
                    # nằm trong chính item bị lỗi không chứng minh đã tra được.
                    if usable_search_sources and not search_fallback and not finalizing:
                        raise _SearchFallback()
                    raise ProviderError("Peto chưa tra cứu web được lượt này. Bạn thử lại nhé.")
                if item.get("status") == "completed":
                    usable_search_sources = normalize_sources([*usable_search_sources, *_item_sources(item)])
                search_finished = search_finished or item.get("status") == "completed"
                if (item.get("action") or {}).get("type") in {'fetch', 'open_page', 'find_in_page'}:
                    yield StreamChunk("page", "fetched" if item.get('status') == 'completed' else 'fetching')
                else:
                    yield StreamChunk("search", "completed" if item.get("status") == "completed" else "searching")
            merged = normalize_sources([*sources, *_item_sources(item)])
            if merged != sources:
                sources = merged
                yield StreamChunk("sources", sources=tuple(sources))

        calls_used = 0
        document_session = current_session.get()
        # Tệp đã gửi trong hội thoại: công cụ tìm/đọc chỉ có khi hội thoại có tệp chữ, PDF, Word hoặc Excel.
        files = current_files.get()
        file_schemas = files.schemas() if files else []
        chat_history = chat_history_tools.current.get()
        github_session = github_session_context.get()
        snapshot = request_context.current.get()
        def record_tool_result(result):
            # Ghi một kết quả dispatch (kể cả từ chối), không ghi args/tên công cụ/nội dung hoặc ID.
            if snapshot is not None:
                usage_events.record('chat_event', service=getattr(self, 'usage_service', self.service),
                    model=snapshot.model, surface='chat', effort=effort, purpose='tool',
                    outcome='error' if result.get('error') or result.get('ok') is False else 'ok')
        github_state, github_reason = (await github_session.availability() if github_session else
                                      (snapshot.github_state, snapshot.github_reason) if snapshot else
                                      ('unauthorized', 'not_connected'))
        github_schemas = github_session.schemas() if github_session and github_state == 'available' else []
        # Chạy mã chỉ ở tab Trò chuyện (có snapshot), không ở Companion hay lượt đặt tên/tóm tắt.
        code_reason = ('provider_unsupported' if not self.code_interpreter else
                       'server_disabled' if not config.XAI_CODE_EXECUTION else
                       'chat_only' if snapshot is None or not tools_enabled else None)
        workbooks = bool(document_session and (getattr(document_session, 'workbooks', None)
                                               or getattr(document_session, 'word_files', None)))
        max_rounds = max(MAX_TOOL_ROUNDS, MAX_GITHUB_TOOL_ROUNDS if github_schemas else 0, MAX_WORKBOOK_TOOL_ROUNDS if workbooks else 0)
        max_calls = max(MAX_TOOL_CALLS, MAX_GITHUB_TOOL_CALLS if github_schemas else 0, MAX_WORKBOOK_TOOL_CALLS if workbooks else 0)
        # Lượt nhờ sửa tệp Excel hay Word còn có thể nhắc làm tiếp: chưa sửa hay tạo tệp nào, và chưa nhắc lần nào.
        watching = bool(self.service == "xAI" and tools_enabled and workbooks and getattr(document_session, "edit_request", False))
        follow_up_next = False
        for round_index in range(max_rounds + 1):
            follow_up, follow_up_next = follow_up_next, False
            # Dành lần gọi cuối để tổng hợp kết quả đã đọc, không mở thêm tra cứu khi hết ngân sách.
            finalizing = tools_enabled and (search_fallback or round_index == max_rounds or calls_used >= max_calls)
            if round_index and github_session:
                github_state, github_reason = await github_session.availability()
            plan = capabilities.select(documents=document_session, files=files, history=chat_history,
                github_state=github_state, github_reason=github_reason, search_enabled=search_enabled,
                web_search=web_search, tools_enabled=tools_enabled, finalizing=finalizing,
                required_search=search_enabled and web_search == 'on' and round_index == 0 and not finalizing,
                search_fallback=search_fallback, code_reason=code_reason)
            round_started = perf_counter()
            if tools_enabled and not follow_up:
                # Mốc cho nhật ký "Đang làm": từ đây tới chữ hay lệnh đầu tiên là lúc mô hình suy nghĩ. Lần gọi nhắc làm
                # tiếp không có mốc riêng: phía chat coi câu báo lần trước vẫn là bản nháp của lần gọi này, để khi Grok gọi
                # công cụ thì câu báo thành câu dẫn trong nhật ký.
                yield StreamChunk("round")
            usage: dict = {}
            create_kwargs: dict = {
                "model": self.model,
                "instructions": instructions + ('\n\n' + (GITHUB_PROMPT if github_state == 'available' else NO_GITHUB_PROMPT) if tools_enabled else '')
                                             + ('\n\n' + CODE_PROMPT if code_reason is None else '')
                                             + ('\n\n' + SEARCH_FALLBACK_PROMPT if search_fallback else
                                                 '\n\n' + FINALIZING_PROMPT if finalizing else ''),
                "input": payload_input,
                "max_output_tokens": self.max_output_tokens if tools_enabled else side_output_cap(self.max_output_tokens),
                "reasoning": {
                    "effort": effort if effort in self.supported_efforts else "low"
                },
                "stream": True,
                "tools": plan.schemas,
                "include": ["reasoning.encrypted_content"],
                # Tự giữ các item trong lượt này, không cần lưu hội thoại ở dịch vụ AI.
                "store": False,
            }
            if not getattr(self, "send_reasoning", True):
                # Khóa riêng của người dùng với model không chỉnh được mức suy nghĩ (ai/byok.py): gửi tham số này thì cả
                # lượt bị từ chối.
                create_kwargs.pop("reasoning")
                create_kwargs["include"] = []
            if finalizing:
                # Danh sách công cụ đã rỗng: không gửi tool_choice, kể cả "none", vì xAI từ chối cặp này.
                logger.info("Kết thúc tra cứu: vòng=%d công_cụ_đã_gọi=%d github=%s", round_index, calls_used, bool(github_schemas))
            if search_enabled:
                create_kwargs["include"].append("web_search_call.action.sources")
                if web_search == "on" and round_index == 0 and not finalizing:
                    # Chỉ đưa công cụ tìm web ở lần đầu để 'required' không bị thỏa bởi đồng hồ.
                    create_kwargs["tool_choice"] = "required"
            if snapshot is not None:
                create_kwargs['instructions'] += '\n\n' + snapshot.render(
                    service=self.service, model=self.model,
                    effort=create_kwargs.get('reasoning', {}).get('effort'),
                    capabilities=plan.manifest(getattr(self._client, 'native_tools', None)), round_index=round_index)
            enforce_chat_budget(create_kwargs)
            stream = None
            output_items: list[dict] = []
            completed = False
            recovering_search = False
            emitted_text = follow_up       # lần gọi nhắc: câu báo lần trước vẫn đang hiện
            noted = False
            written: list[str] = []     # chữ lần gọi này đã phát
            # Chữ của lần gọi nhắc được giữ lại: Grok gọi công cụ thì phát (thành câu dẫn cùng câu báo), không gọi thì đó
            # chỉ là "XONG" hay lời đệm, bỏ đi.
            held: list[str] = []

            def drop_pre_search_draft() -> StreamChunk | None:
                """Grok hay viết móc câu hay câu dẫn rồi search rồi viết tiếp. Mỗi lần tra, chữ viết từ lần tra trước tới giờ
                là bản nháp: tab Trò chuyện đưa câu ngắn vào nhật ký "Đang làm", Companion bỏ đi. Trước đây chỉ lần tra đầu
                được xử lý, nên câu dẫn trước lần tra thứ hai ở lại và dính liền vào câu trả lời ("phân tích.Ad gửi…")."""
                nonlocal emitted_text
                written.clear()
                held.clear()
                if emitted_text:
                    emitted_text = False
                    return StreamChunk("replace")
                return None

            try:
                stream = await self._client.responses.create(**create_kwargs)
                pulse_at = perf_counter() + PULSE_SECONDS
                async for event in stream:
                    event_type = getattr(event, "type", "")
                    if perf_counter() >= pulse_at:
                        pulse_at = perf_counter() + PULSE_SECONDS
                        yield StreamChunk("pulse")
                    if event_type in {"response.web_search_call.in_progress", "response.web_search_call.searching"}:
                        draft = drop_pre_search_draft()
                        if draft is not None:
                            yield draft
                        yield StreamChunk("search", "searching")
                    elif event_type == "response.web_search_call.completed":
                        search_finished = True
                        yield StreamChunk("search", "completed")
                    elif event_type == "response.code_interpreter_call.in_progress":
                        # Câu dẫn viết trước lúc chạy mã xử lý như trước lúc tra web: vào nhật ký, không dính vào câu
                        # trả lời viết sau khi có kết quả.
                        draft = drop_pre_search_draft()
                        if draft is not None:
                            yield draft
                        yield StreamChunk("code", "running")
                    elif event_type == "peto.page_fetch.started":
                        draft = drop_pre_search_draft()
                        if draft is not None:
                            yield draft
                        yield StreamChunk("page", "fetching")
                    elif event_type == "peto.page_fetch.failed":
                        yield StreamChunk("page", "failed")
                    elif event_type == "response.output_item.added":
                        item_type = getattr(event.item, "type", "")
                        if item_type == "web_search_call":
                            draft = drop_pre_search_draft()
                            if draft is not None:
                                yield draft
                            yield StreamChunk("search", "searching")
                        elif item_type == "code_interpreter_call":
                            draft = drop_pre_search_draft()
                            if draft is not None:
                                yield draft
                            yield StreamChunk("code", "running")
                        elif item_type == "function_call":
                            if held:
                                yield "\n\n" + "".join(held)
                                held.clear()
                            # Chữ viết trước lệnh gọi công cụ thường là câu dẫn: phía chat đưa nó vào nhật ký "Đang làm"
                            # (hoặc giữ trong câu trả lời nếu dài). Báo ngay lúc này để các bước tới đúng thứ tự.
                            if emitted_text and not noted:
                                noted = True
                                yield StreamChunk("note")
                            # Bắt đầu viết lệnh gọi công cụ: lệnh sửa Excel dài có thể mất cả phút.
                            yield StreamChunk("tool", str(getattr(event.item, "name", "") or ""))
                    elif event_type == "response.output_text.annotation.added":
                        annotation = _dump(event.annotation)
                        if annotation.get("type") == "url_citation":
                            merged = normalize_sources([*sources, {**annotation, "kind": "citation"}])
                            if merged != sources:
                                sources = merged
                                yield StreamChunk("sources", sources=tuple(sources))
                    elif event_type in _REASONING_DELTA_TYPES:
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield StreamChunk("thinking", delta)
                    elif event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            emitted_text = True
                            if follow_up:
                                held.append(delta)
                            else:
                                written.append(delta)
                                yield delta
                    elif event_type == "response.output_item.done":
                        item = _dump(event.item)
                        output_items.append(item)
                        for chunk in observe_item(item):
                            yield chunk
                    elif event_type == "response.completed":
                        raw_usage = getattr(event.response, "usage", None)
                        usage = _dump(raw_usage) if raw_usage is not None else {}
                        if getattr(event.response, "status", "completed") != "completed":
                            raise ProviderError("Peto chưa trả lời xong. Phần đã viết được giữ lại; bạn có thể yêu cầu tiếp tục.")
                        completed = True
                        if getattr(event.response, "output", None):
                            output_items = [_dump(item) for item in event.response.output]
                            for item in output_items:
                                for chunk in observe_item(item):
                                    yield chunk
                    elif event_type == "response.incomplete":
                        raise ProviderError("Câu trả lời chạm giới hạn của lượt AI. Phần đã viết được giữ lại; bạn có thể yêu cầu tiếp tục.")
                    elif event_type in {"response.failed", "error"}:
                        raise ProviderError("Peto gặp lỗi khi đang trả lời. Thử lại nha.", retryable=True)
            except _SearchFallback:
                recovering_search = True
                logger.warning("%s: lượt tìm bổ sung bị lỗi; tổng hợp từ %d nguồn đã tra thành công",
                               self.service, len(usable_search_sources))
            except AuthenticationError as err:
                raise ProviderError(self.auth_error_message) from err
            except RateLimitError as err:
                # Lời báo giới hạn lượt/hết hạn mức không chứa nội dung hội thoại hay khóa; ghi để biết là hết tiền hay chỉ quá tải.
                logger.warning("%s giới hạn lượt: %s", self.service, _clip(err.message))
                raise ProviderError(self.rate_limit_message, retryable=True) from err
            except APIConnectionError as err:
                raise ProviderError("Peto chưa kết nối được với dịch vụ AI. Thử lại sau chút nhé.", retryable=True) from err
            except APIStatusError as err:
                logger.warning("%s HTTP %s: %s", self.service, err.status_code, _clip(err.message))
                if search_enabled and err.status_code in {400, 403}:
                    raise ProviderError("Peto chưa dùng được tìm web với kết nối AI hiện tại. Mở menu + rồi chọn Tắt tìm kiếm web để chat tiếp, hoặc nhờ người quản trị kiểm tra quyền tìm kiếm của dịch vụ.") from err
                raise ProviderError("Peto gặp lỗi kết nối với dịch vụ AI. Thử lại sau nha.", retryable=err.status_code >= 500) from err
            finally:
                logger.info(
                    "model_usage service=%s model=%s purpose=%s round=%d elapsed_ms=%d complete=%s input_tokens=%s output_tokens=%s cached_tokens=%s reasoning_tokens=%s search_calls_seen=%d code_calls_seen=%d",
                    self.service, self.model, "chat" if tools_enabled else "title", round_index + 1,
                    round((perf_counter() - round_started) * 1000), completed,
                    usage.get("input_tokens"), usage.get("output_tokens"),
                    (usage.get("input_tokens_details") or {}).get("cached_tokens"),
                    (usage.get("output_tokens_details") or {}).get("reasoning_tokens"), len(search_ids), len(code_ids),
                )
                # Khóa riêng của người dùng ghi dịch vụ "byok" và slug "byok/…": trang Quản trị không tính vào chi phí chủ web.
                usage_events.record(
                    "call", service=getattr(self, "usage_service", self.service), model=getattr(self, "catalog_key", None),
                    slug=getattr(self, "usage_slug", self.model),
                    purpose="chat" if tools_enabled else "side", complete=completed,
                    elapsed_ms=round((perf_counter() - round_started) * 1000),
                    input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                    cached_tokens=(usage.get("input_tokens_details") or {}).get("cached_tokens"),
                    cache_write_tokens=(usage.get("input_tokens_details") or {}).get("cache_write_tokens"),
                    reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
                    search_calls=len(search_ids),
                    # xAI tự báo số tiền đã tính cho lần gọi; dịch vụ khác không có trường này.
                    cost_ticks=usage.get("cost_in_usd_ticks"),
                )
                if stream is not None:
                    with anyio.CancelScope(shield=True):
                        await stream.close()

            if recovering_search:
                # Bỏ bản nháp của lần gọi vừa ngắt trước khi mở mốc suy nghĩ mới. Không chạy lệnh công cụ
                # chưa thực thi, không gửi item tra bị lỗi hoặc item đang viết dở sang lượt tổng hợp.
                yield StreamChunk("search", "failed")
                yield StreamChunk("replace")
                payload_input.extend(item for item in output_items
                                     if item.get("status") in {None, "completed"}
                                     and item.get("type") in {"message", "reasoning", "web_search_call"}
                                     and (item.get("type") != "web_search_call" or item.get("status") == "completed"))
                search_fallback = True
                search_enabled = False
                watching = False
                follow_up_next = False
                continue

            if not completed:
                raise ProviderError("Kết nối tới AI bị ngắt trước khi trả lời xong.", retryable=True)
            tool_calls = [item for item in output_items if item.get("type") == "function_call"]
            if tool_calls and not tools_enabled:
                raise ProviderError("Tác vụ đặt tên không được gọi công cụ.")
            if not tool_calls:
                if web_search == "on" and not search_finished and not sources:
                    raise ProviderError("Dịch vụ chưa xác nhận đã tra web. Peto chưa thể xem câu trả lời này là đã kiểm chứng; bạn thử lại nhé.")
                if follow_up:
                    # Nhắc rồi vẫn không gọi công cụ: câu báo giữ nguyên làm câu trả lời. Chữ ngắn thêm vào (như "XONG")
                    # bỏ đi; chữ dài là nội dung thật (danh sách lỗi khi người dùng dặn chờ đồng ý) thì giữ.
                    extra = "".join(held).strip()
                    logger.info("Nhắc làm tiếp: vẫn không gọi công cụ, chữ thêm %d ký tự", len(extra))
                    if len(extra) > FOLLOW_UP_CHARS:
                        yield "\n\n" + extra
                    return
                written_text = "".join(written).strip()
                if watching and not finalizing and round_index + 1 < max_rounds and calls_used < max_calls \
                        and 0 < len(written_text) <= FOLLOW_UP_CHARS:
                    watching = False
                    follow_up_next = True
                    payload_input.extend(output_items)
                    payload_input.append({"role": "user", "content": [{"type": "input_text", "text": FOLLOW_UP}]})
                    logger.info("Nhắc làm tiếp: lần gọi %d chỉ viết %d ký tự, chưa gọi công cụ", round_index + 1,
                                len(written_text))
                    continue
                return
            if finalizing:
                raise ProviderError("Dịch vụ AI vẫn yêu cầu tra cứu sau khi được yêu cầu kết thúc. Phần đã trả lời được giữ lại; bạn có thể hỏi tiếp về một tệp cụ thể.")
            payload_input.extend(output_items)
            if held:
                yield "\n\n" + "".join(held)
                held.clear()
            if emitted_text and not noted:
                # Dịch vụ không báo lúc bắt đầu viết lệnh: chữ trước đó vẫn là câu dẫn.
                yield StreamChunk("note")
            if player_tools.current.get() and any(call.get('name') == player_tools.NAME for call in tool_calls):
                # A draft before a Player action is not a confirmed result. Replace it like a web-search draft.
                draft = drop_pre_search_draft()
                if draft is not None:
                    yield draft
            for call in tool_calls:
                if not call.get("call_id"):
                    raise ProviderError("AI trả về yêu cầu công cụ không hợp lệ. Thử lại nhé.")
                if calls_used >= max_calls:
                    # Mỗi lời gọi vẫn có kết quả tương ứng; lời gọi vượt giới hạn không được thực thi.
                    result = {'ok': False, 'error': 'Đã chạm giới hạn tra cứu của lượt này. Công cụ này chưa được chạy; hãy tổng hợp dữ liệu đã có và nêu rõ phần còn thiếu.'}
                    record_tool_result(result)
                    payload_input.append({'type': 'function_call_output', 'call_id': call['call_id'],
                                          'output': json.dumps(result, ensure_ascii=False)})
                    continue
                calls_used += 1
                if not plan.allows(call.get('name')):
                    # Một model vẫn có thể bịa lời gọi dù schema không được gửi. Không thực thi ngoài kế hoạch vòng này.
                    result = {'ok': False, 'error': 'Công cụ không được cấp trong vòng hiện tại; chưa được chạy.',
                              'code': 'tool_not_available'}
                elif call.get('name') == player_tools.NAME and player_tools.current.get():
                    async with aclosing(player_tools.current.get().run(call.get('arguments', ''))) as action:
                        async for item in action:
                            if isinstance(item, StreamChunk):
                                yield item
                            else:
                                result = item
                elif call.get('name') in DOCUMENT_TOOLS and document_session:
                    watching = False        # Grok đã bắt tay sửa/tạo tệp: không cần nhắc nữa
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
                elif call.get('name') in GITHUB_TOOLS and github_schemas:
                    yield StreamChunk('connector_lookup', 'Đang đọc GitHub…')
                    result = await github_session.run(call['name'], call.get('arguments', ''))
                    yield StreamChunk('connector_lookup_done', 'Đã đọc GitHub' if result.get('ok') else result.get('error', 'Chưa đọc được GitHub'))
                    if result.get('sources'):
                        sources = normalize_sources([*sources, *({**source, 'kind': 'result', 'access': 'tool',
                            **({'partial': True} if result.get('truncated') is True else {})}
                            for source in result['sources'] if isinstance(source, dict))])
                        yield StreamChunk('sources', sources=tuple(sources))
                elif call.get('name') == chat_history_tools.NAME and chat_history:
                    yield StreamChunk('file_lookup', 'Đang đối chiếu lịch sử gốc…')
                    result = await chat_history.run(call.get('arguments', ''))
                    yield StreamChunk('file_lookup_done', 'Đã đối chiếu lịch sử' if not result.get('error') else result['error'])
                elif call.get("name") in FILE_TOOLS and file_schemas:
                    arguments = call.get("arguments", "")
                    yield StreamChunk("file_lookup", files.label(call["name"], arguments))
                    result = await files.run(call["name"], arguments)
                    yield StreamChunk("file_lookup_done", files.label(call["name"], arguments, result))
                else:
                    result = execute_tool(call.get("name", ""), call.get("arguments", ""), timezone=timezone)
                record_tool_result(result)
                payload_input.append({
                    "type": "function_call_output", "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                })


class XAIProvider(ResponsesProvider):
    """Peto: Grok qua tài khoản xAI riêng của web (OAuth, hoặc XAI_API_KEY dự phòng)."""

    name = "xai"
    service = "xAI"
    code_interpreter = True

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
