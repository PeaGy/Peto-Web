"""Claude qua Messages API; đổi giao thức để dùng chung vòng công cụ sẵn có của Peto.

Không gửi Responses API tới Anthropic. Lớp cầu nối chỉ đổi input và sự kiện nội bộ; SDK Anthropic giữ nguyên các
block suy nghĩ có chữ ký, lời gọi công cụ và kết quả tìm web cho lượt tiếp theo.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import anyio
from anthropic import AsyncAnthropic, APIError, APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

from core import config
from .base import ProviderError
from .models import CLAUDE_EFFORTS
from .xai import ResponsesProvider

logger = logging.getLogger("peto_web.claude")
MAX_SEARCH_PAUSES = 3
NATIVE_BLOCK_TYPES = {"text", "thinking", "redacted_thinking", "tool_use", "server_tool_use", "web_search_tool_result"}


def _citation(value: dict) -> dict | None:
    if value.get("type") == "web_search_result_location" and value.get("url"):
        return {"type": "url_citation", "url": value["url"], "title": value.get("title") or value["url"]}
    return None


def _portable_output(content: list[dict]) -> list[dict]:
    """Bản chữ và công cụ để CLI chạy được, đồng thời chuyển hội thoại sang nhà cung cấp khác được."""
    output = []
    for block in content:
        kind = block.get("type")
        if kind == "text" and block.get("text"):
            output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text",
                "text": block["text"], "annotations": [citation for raw in block.get("citations") or []
                                                       if (citation := _citation(raw))]}]})
        elif kind == "tool_use":
            output.append({"type": "function_call", "call_id": block["id"], "name": block["name"],
                           "arguments": json.dumps(block["input"], ensure_ascii=False)})
        elif kind == "web_search_tool_result":
            results = block.get("content")
            failed = isinstance(results, dict) and results.get("type") == "web_search_tool_result_error"
            output.append({"type": "web_search_call", "id": block["tool_use_id"],
                "status": "failed" if failed else "completed", "action": {"type": "search", "sources": [
                    {"url": result["url"], "title": result.get("title") or result["url"]}
                    for result in results if isinstance(result, dict) and result.get("url")]
                    if isinstance(results, list) else []}})
    return output


def build_messages(items: list[dict], model: str) -> list[dict]:
    """Chỉ nhận vai user/assistant; khôi phục block gốc khi còn đủ nhóm item của cùng model."""
    messages: list[dict] = []

    def append(role: str, blocks: list[dict]):
        if not blocks:
            return
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})

    index = 0
    while index < len(items):
        item = items[index]
        index += 1
        kind = item.get("type", "message")
        if kind == "reasoning":
            content = item.get("anthropic_content")
            if (item.get("anthropic_model") == model and isinstance(content, list) and content
                    and all(isinstance(block, dict) and block.get("type") in NATIVE_BLOCK_TYPES for block in content)):
                normalized = _portable_output(content)
                if items[index:index + len(normalized)] == normalized:
                    append("assistant", content)
                    index += len(normalized)
            continue
        if kind == "function_call":
            try:
                arguments = json.loads(item.get("arguments") or "{}")
            except (ValueError, TypeError) as err:
                raise ProviderError("Lịch sử gọi công cụ không hợp lệ. Bắt đầu hội thoại mới nhé.") from err
            append("assistant", [{"type": "tool_use", "id": item["call_id"], "name": item["name"], "input": arguments}])
        elif kind == "function_call_output":
            append("user", [{"type": "tool_result", "tool_use_id": item["call_id"], "content": item.get("output") or ""}])
        elif kind == "message":
            role = item.get("role")
            if role not in {"user", "assistant"}:
                raise ProviderError("Lịch sử Claude chỉ được có tin của bạn và Peto.")
            content = item.get("content", "")
            if isinstance(content, str):
                content = [{"type": "input_text", "text": content}]
            blocks = []
            for part in content:
                if part.get("type") in {"input_text", "output_text", "text"} and part.get("text"):
                    blocks.append({"type": "text", "text": part["text"]})
                elif part.get("type") == "input_image" and role == "user":
                    header, separator, data = str(part.get("image_url", "")).partition(",")
                    mime = header.removeprefix("data:").removesuffix(";base64")
                    if not separator or not header.startswith("data:") or not header.endswith(";base64") or mime not in {
                            "image/jpeg", "image/png", "image/gif", "image/webp"}:
                        raise ProviderError("Ảnh gửi tới Claude không đúng định dạng.")
                    blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
            append(role, blocks)
    return messages


def _failure(err: Exception) -> ProviderError:
    # Chỉ ghi mã HTTP: lời lỗi của dịch vụ có thể chứa khóa hoặc nội dung người dùng.
    if isinstance(err, AuthenticationError):
        return ProviderError("Khóa Claude của máy chủ không dùng được. Chọn Peto hoặc gõ /model peto để tiếp tục nhé.")
    if isinstance(err, RateLimitError):
        return ProviderError("Claude đang giới hạn lượt hoặc đã hết hạn mức. Thử lại sau nhé.", retryable=True)
    if isinstance(err, APIConnectionError):
        return ProviderError("Peto chưa kết nối được Claude. Thử lại sau nhé.", retryable=True)
    if isinstance(err, APIStatusError):
        logger.warning("Claude trả HTTP %s", err.status_code)
        if err.status_code in {400, 403, 404}:
            return ProviderError("Claude chưa nhận được yêu cầu này. Kiểm tra quyền model và tìm web trong Claude Console; "
                                 "thử tắt tìm web hoặc bắt đầu hội thoại mới nhé.")
        return ProviderError("Claude gặp lỗi dịch vụ. Thử lại sau nhé.", retryable=err.status_code >= 500)
    return ProviderError("Kết nối Claude bị ngắt trước khi trả lời xong. Thử lại nhé.", retryable=True)


class ClaudeClient:
    """Giao diện nội bộ giống Responses; bên ngoài luôn gọi SDK Messages của Anthropic."""

    def __init__(self, sdk=None):
        self.sdk = sdk or AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY or "chua-co-khoa", max_retries=0,
                                        timeout=config.AGENT_STEP_TIMEOUT_SECONDS)
        self.responses = self

    async def create(self, **kwargs):
        effort = kwargs.get("reasoning", {}).get("effort", "low")
        if effort not in CLAUDE_EFFORTS:
            raise ProviderError("Mức suy nghĩ này không được Claude hỗ trợ.")
        tools = []
        for tool in kwargs.get("tools", []):
            if tool.get("type") == "web_search":
                # Tìm trực tiếp, giới hạn phí công cụ; không mở thêm môi trường chạy mã ở Anthropic.
                tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 5})
            elif tool.get("type") == "function":
                tools.append({"name": tool["name"], "description": tool.get("description", ""),
                              "input_schema": tool.get("parameters") or {"type": "object", "properties": {}}})
        request = {"model": kwargs["model"], "system": kwargs.get("instructions", ""),
                   "messages": build_messages(kwargs["input"], kwargs["model"]),
                   "max_tokens": kwargs["max_output_tokens"], "thinking": {"type": "adaptive"},
                   "output_config": {"effort": effort}}
        if tools:
            # Ép tool_choice không tương thích adaptive thinking. Lượt bắt buộc tìm web đã có chỉ dẫn và kiểm chứng
            # sau khi stream xong trong ResponsesProvider; không tự nhận đã tra nếu Claude chưa chạy công cụ.
            request["tools"] = tools
        return ClaudeStream(self.sdk, request)


class ClaudeStream:
    def __init__(self, sdk, request):
        self.sdk = sdk
        self.request = request
        self.stream = None
        self.closed = False

    def __aiter__(self):
        return self._events()

    async def close(self):
        self.closed = True
        if self.stream is not None:
            with anyio.CancelScope(shield=True):
                await self.stream.close()
            self.stream = None

    async def _events(self):
        output: list[dict] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        try:
            for pause in range(MAX_SEARCH_PAUSES + 1):
                if self.closed:
                    return
                manager = self.sdk.messages.stream(**self.request)
                async with manager as stream:
                    self.stream = stream
                    stopped = False
                    async for event in stream:
                        kind = event.type
                        if kind == "message_stop":
                            stopped = True
                        elif kind == "content_block_start":
                            block = event.content_block
                            if block.type == "tool_use":
                                yield SimpleNamespace(type="response.output_item.added",
                                    item=SimpleNamespace(type="function_call", name=block.name))
                            elif block.type == "server_tool_use" and block.name == "web_search":
                                yield SimpleNamespace(type="response.web_search_call.searching")
                        elif kind == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                yield SimpleNamespace(type="response.output_text.delta", delta=delta.text)
                            elif delta.type == "thinking_delta":
                                yield SimpleNamespace(type="response.reasoning_summary_text.delta", delta=delta.thinking)
                            elif delta.type == "citations_delta":
                                citation = _citation(delta.citation.model_dump(mode="json", exclude_none=True))
                                if citation:
                                    yield SimpleNamespace(type="response.output_text.annotation.added", annotation=citation)
                            else:
                                # Dấu hiệu stream còn chạy khi Claude đang soạn JSON công cụ dài.
                                yield SimpleNamespace(type="peto.pulse")
                        elif kind == "content_block_stop":
                            block = stream.current_message_snapshot.content[event.index]
                            if block.type == "web_search_tool_result":
                                for item in _portable_output([block.model_dump(mode="json", exclude_none=True)]):
                                    yield SimpleNamespace(type="response.output_item.done", item=item)
                    if not stopped:
                        raise ProviderError("Kết nối Claude bị ngắt trước khi trả lời xong. Thử lại nhé.", retryable=True)
                    message = await stream.get_final_message()
                self.stream = None
                content = [block.model_dump(mode="json", exclude_none=True) for block in message.content]
                normalized = _portable_output(content)
                output.extend([{"type": "reasoning", "anthropic_model": self.request["model"],
                                "anthropic_content": content, "anthropic_output_count": len(normalized), "summary": []},
                               *normalized])
                # Tiếp tục pause_turn là một request mới, tính đủ token của mọi request.
                usage["input_tokens"] += (message.usage.input_tokens + (message.usage.cache_read_input_tokens or 0)
                                          + (message.usage.cache_creation_input_tokens or 0))
                usage["output_tokens"] += message.usage.output_tokens
                if message.stop_reason == "pause_turn":
                    if pause == MAX_SEARCH_PAUSES:
                        raise ProviderError("Claude chưa tra cứu xong trong giới hạn lượt này. Thử thu gọn yêu cầu nhé.")
                    self.request["messages"].append({"role": "assistant", "content": content})
                    continue
                if message.stop_reason == "max_tokens":
                    yield SimpleNamespace(type="response.incomplete")
                    return
                if message.stop_reason not in {"end_turn", "tool_use", "refusal"}:
                    raise ProviderError("Claude chưa hoàn tất lượt này. Thử lại nhé.")
                if not any(item.get("type") in {"message", "function_call"} for item in output):
                    raise ProviderError("Claude chưa trả nội dung câu trả lời. Thử mức suy nghĩ thấp hơn nhé.")
                # Usage của SDK giữ dạng model để phần chat và Agent đọc cùng một cách.
                final_usage = message.usage.model_copy(update=usage)
                yield SimpleNamespace(type="response.completed",
                    response=SimpleNamespace(status="completed", output=output, usage=final_usage))
                return
        except ProviderError:
            raise
        except (APIError, ValueError, AssertionError) as err:
            raise _failure(err) from err
        finally:
            await self.close()


class ClaudeProvider(ResponsesProvider):
    supported_efforts = CLAUDE_EFFORTS
    name = "anthropic"
    service = "Anthropic"

    def __init__(self, slug: str, label: str):
        self.model = slug
        self.max_output_tokens = config.ANTHROPIC_MAX_OUTPUT_TOKENS
        self._client = ClaudeClient()

    async def _prepare(self):
        if not config.ANTHROPIC_API_KEY:
            raise ProviderError("Máy chủ Peto chưa có khóa Claude. Chọn Peto để tiếp tục nhé.")
