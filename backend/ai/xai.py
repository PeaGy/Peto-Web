"""Grok Responses API: stream văn bản và chạy công cụ được đăng ký của web."""

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

from config import MAX_HISTORY_IMAGES, XAI_API_BASE, XAI_MAX_OUTPUT_TOKENS, XAI_MODEL
from xai_auth import XaiAuth, XaiAuthError
from chat_tools import TOOL_SCHEMAS, execute_tool

from .base import ChatMessage, ChatProvider, ProviderError

logger = logging.getLogger("peto_web.xai")

_TEXT_TYPE = {"user": "input_text", "assistant": "output_text"}
MAX_TOOL_ROUNDS = 3
MAX_TOOL_CALLS = 8


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


class XAIProvider(ChatProvider):
    name = "xai"

    def __init__(self) -> None:
        self._auth = XaiAuth()
        # api_key được thay trước mỗi lượt gọi; giá trị khởi tạo chỉ là chỗ giữ.
        self._client = AsyncOpenAI(api_key="pending", base_url=XAI_API_BASE)

    async def _prepare(self) -> None:
        try:
            self._client.api_key = await self._auth.get_access_token()
        except XaiAuthError as err:
            raise ProviderError(
                "Máy chủ chưa đăng nhập xAI nên Peto chưa trả lời được. "
                "Người quản trị cần chạy lại lệnh đăng nhập."
            ) from err

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
        timezone: str | None = None,
    ) -> AsyncIterator[str]:
        await self._prepare()

        payload_input = build_input_payload(messages)
        calls_used = 0
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            create_kwargs: dict = {
                "model": XAI_MODEL,
                "instructions": system_prompt,
                "input": payload_input,
                "max_output_tokens": XAI_MAX_OUTPUT_TOKENS,
                "reasoning": {
                    "effort": effort if effort in {"low", "medium", "high"} else "low"
                },
                "stream": True,
                "tools": TOOL_SCHEMAS,
                "include": ["reasoning.encrypted_content"],
                # Tự giữ các item trong lượt này, không cần lưu hội thoại ở xAI.
                "store": False,
            }
            stream = None
            output_items: list[dict] = []
            completed = False
            emitted_text = False
            try:
                stream = await self._client.responses.create(**create_kwargs)
                async for event in stream:
                    event_type = getattr(event, "type", "")
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            emitted_text = True
                            yield delta
                    elif event_type == "response.output_item.done":
                        item = event.item
                        output_items.append(item.model_dump(mode="json", exclude_none=True))
                    elif event_type == "response.completed":
                        if getattr(event.response, "status", "completed") != "completed":
                            raise ProviderError("Peto chưa trả lời xong. Phần đã viết được giữ lại; cậu có thể yêu cầu tiếp tục.")
                        completed = True
                        if getattr(event.response, "output", None):
                            output_items = [item.model_dump(mode="json", exclude_none=True) for item in event.response.output]
                    elif event_type == "response.incomplete":
                        raise ProviderError("Câu trả lời chạm giới hạn của lượt AI. Phần đã viết được giữ lại; cậu có thể yêu cầu tiếp tục.")
                    elif event_type in {"response.failed", "error"}:
                        raise ProviderError("xAI báo lỗi giữa chừng. Thử lại nha.", retryable=True)
            except AuthenticationError as err:
                raise ProviderError("Token xAI không còn hợp lệ. Người quản trị cần đăng nhập lại.") from err
            except RateLimitError as err:
                raise ProviderError("xAI đang giới hạn tần suất. Đợi chút rồi thử lại nha.", retryable=True) from err
            except APIConnectionError as err:
                raise ProviderError("Không kết nối được tới xAI. Kiểm tra mạng giúp nha.", retryable=True) from err
            except APIStatusError as err:
                logger.warning("xAI HTTP %s", err.status_code)
                raise ProviderError(f"xAI trả lỗi {err.status_code}. Thử lại sau nha.", retryable=err.status_code >= 500) from err
            finally:
                if stream is not None:
                    with anyio.CancelScope(shield=True):
                        await stream.close()

            if not completed:
                raise ProviderError("Kết nối tới AI bị ngắt trước khi trả lời xong.", retryable=True)
            tool_calls = [item for item in output_items if item.get("type") == "function_call"]
            if not tool_calls:
                return
            calls_used += len(tool_calls)
            if round_index >= MAX_TOOL_ROUNDS or calls_used > MAX_TOOL_CALLS:
                raise ProviderError("Peto chưa hoàn tất việc tra cứu trong lượt này. Cậu thử hỏi lại cụ thể hơn nhé.")
            payload_input.extend(output_items)
            for call in tool_calls:
                if not call.get("call_id"):
                    raise ProviderError("AI trả về yêu cầu công cụ không hợp lệ. Thử lại nhé.")
                result = execute_tool(call.get("name", ""), call.get("arguments", ""), timezone=timezone)
                payload_input.append({
                    "type": "function_call_output", "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                })
            if emitted_text:
                yield "\n\n"
