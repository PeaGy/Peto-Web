"""Responses API: stream văn bản và chạy công cụ được đăng ký của web.

xAI (Peto) và OpenAI (dòng GPT-6, ``ai/gpt.py``) dùng cùng dạng Responses API, nên ``ResponsesProvider`` giữ chung
vòng công cụ, tìm web và nguồn tham khảo; mỗi dịch vụ chỉ khác cách lấy khóa, tên model và lời báo lỗi.
"""

from __future__ import annotations

import logging
import json
import anyio
from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from config import MAX_HISTORY_IMAGES, XAI_API_BASE, XAI_MAX_OUTPUT_TOKENS, XAI_MODEL, WEB_SEARCH_ENABLED
from xai_auth import XaiAuth, XaiAuthError
from chat_tools import TOOL_SCHEMAS, execute_tool
from document_tools import current_session, SCHEMA as DOCUMENT_SCHEMA
from web_search import normalize_sources, search_context

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk

# Chỉ lấy bản tóm tắt. reasoning_text là suy nghĩ thô, dài và dễ lộ bước bịa.
_REASONING_DELTA_TYPES = {
    "response.reasoning_summary_text.delta",
}

logger = logging.getLogger("peto_web.xai")

_TEXT_TYPE = {"user": "input_text", "assistant": "output_text"}
MAX_TOOL_ROUNDS = 3
MAX_TOOL_CALLS = 8


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
        candidates.extend({**source, "kind": "result"} for source in (item.get("action") or {}).get("sources") or [] if isinstance(source, dict))
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
                label = "Ảnh" if attachment.kind == "image" else "Tệp"
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


class ResponsesProvider(ChatProvider):
    supported_efforts = ("low", "medium", "high")
    """Phần chung của các dịch vụ dùng Responses API. Lớp con đặt ``_client``, ``model`` và ``max_output_tokens``."""

    name = "responses"
    # Tên dịch vụ trong log máy chủ.
    service = "AI"
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

        def observe_item(item: dict):
            nonlocal sources, search_finished
            if item.get("type") == "web_search_call":
                if item.get("status") == "failed":
                    raise ProviderError("Peto chưa tra cứu web được lượt này. Bạn thử lại nhé.")
                search_finished = search_finished or item.get("status") == "completed"
                yield StreamChunk("search", "completed" if item.get("status") == "completed" else "searching")
            merged = normalize_sources([*sources, *_item_sources(item)])
            if merged != sources:
                sources = merged
                yield StreamChunk("sources", sources=tuple(sources))

        calls_used = 0
        document_session = current_session.get()
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            create_kwargs: dict = {
                "model": self.model,
                "instructions": instructions,
                "input": payload_input,
                "max_output_tokens": self.max_output_tokens if tools_enabled else min(self.max_output_tokens, 1024),
                "reasoning": {
                    "effort": effort if effort in self.supported_efforts else "low"
                },
                "stream": True,
                "tools": [*TOOL_SCHEMAS, *([DOCUMENT_SCHEMA] if document_session else []), *([{"type": "web_search"}] if search_enabled else [])] if tools_enabled else [],
                "include": ["reasoning.encrypted_content"],
                # Tự giữ các item trong lượt này, không cần lưu hội thoại ở dịch vụ AI.
                "store": False,
            }
            if search_enabled:
                create_kwargs["include"].append("web_search_call.action.sources")
                if web_search == "on" and round_index == 0:
                    # Chỉ đưa công cụ tìm web ở lần đầu để 'required' không bị thỏa bởi đồng hồ.
                    create_kwargs["tools"] = [{"type": "web_search"}]
                    create_kwargs["tool_choice"] = "required"
            stream = None
            output_items: list[dict] = []
            completed = False
            emitted_text = False
            dropped_draft = False

            def drop_pre_search_draft() -> StreamChunk | None:
                """Grok hay viết móc câu rồi search rồi viết lại từ đầu — bỏ bản nháp trước search."""
                nonlocal dropped_draft, emitted_text
                if emitted_text and not dropped_draft:
                    dropped_draft = True
                    emitted_text = False
                    return StreamChunk("replace")
                return None

            try:
                stream = await self._client.responses.create(**create_kwargs)
                async for event in stream:
                    event_type = getattr(event, "type", "")
                    if event_type in {"response.web_search_call.in_progress", "response.web_search_call.searching"}:
                        draft = drop_pre_search_draft()
                        if draft is not None:
                            yield draft
                        yield StreamChunk("search", "searching")
                    elif event_type == "response.web_search_call.completed":
                        search_finished = True
                        yield StreamChunk("search", "completed")
                    elif event_type == "response.output_item.added":
                        if getattr(event.item, "type", "") == "web_search_call":
                            draft = drop_pre_search_draft()
                            if draft is not None:
                                yield draft
                            yield StreamChunk("search", "searching")
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
                            yield delta
                    elif event_type == "response.output_item.done":
                        item = _dump(event.item)
                        output_items.append(item)
                        for chunk in observe_item(item):
                            yield chunk
                    elif event_type == "response.completed":
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
                if stream is not None:
                    with anyio.CancelScope(shield=True):
                        await stream.close()

            if not completed:
                raise ProviderError("Kết nối tới AI bị ngắt trước khi trả lời xong.", retryable=True)
            tool_calls = [item for item in output_items if item.get("type") == "function_call"]
            if tool_calls and not tools_enabled:
                raise ProviderError("Tác vụ đặt tên không được gọi công cụ.")
            if not tool_calls:
                if web_search == "on" and not search_finished and not sources:
                    raise ProviderError("Dịch vụ chưa xác nhận đã tra web. Peto chưa thể xem câu trả lời này là đã kiểm chứng; bạn thử lại nhé.")
                return
            calls_used += len(tool_calls)
            if round_index >= MAX_TOOL_ROUNDS or calls_used > MAX_TOOL_CALLS:
                raise ProviderError("Peto chưa hoàn tất việc tra cứu trong lượt này. Bạn thử hỏi lại cụ thể hơn nhé.")
            payload_input.extend(output_items)
            for call in tool_calls:
                if not call.get("call_id"):
                    raise ProviderError("AI trả về yêu cầu công cụ không hợp lệ. Thử lại nhé.")
                if call.get('name') == 'create_document' and document_session:
                    yield StreamChunk('document_status', 'Đang dàn trang và tạo tệp…')
                    result = await document_session.create(call.get('arguments', ''))
                    if result.get('ok'):
                        yield StreamChunk('artifact', artifact=result['artifact'])
                    yield StreamChunk('document_status', '')
                else:
                    result = execute_tool(call.get("name", ""), call.get("arguments", ""), timezone=timezone)
                payload_input.append({
                    "type": "function_call_output", "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                })
            if emitted_text:
                yield "\n\n"


class XAIProvider(ResponsesProvider):
    """Peto: Grok qua tài khoản xAI riêng của web (OAuth, hoặc XAI_API_KEY dự phòng)."""

    name = "xai"
    service = "xAI"

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
