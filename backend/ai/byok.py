"""Khóa API của chính người dùng cho bộ não Companion (Cài đặt Companion → Nhà cung cấp; chủ web chọn biến thể "Như AIRI"
ngày 13/10/2026, theo trang Providers của AIRI).

Chủ web chốt:
- Khóa riêng chỉ đổi bộ não của Companion. Tab Trò chuyện vẫn là Peto, Luna, Haiku.
- Lượt dùng khóa riêng không đọc, không ghi Trí nhớ (Trí nhớ của AIRI vẫn đang làm dở). Lịch sử chat vẫn lưu.
- Tra web: nhà cung cấp có sẵn tìm kiếm thì dùng của họ (xAI, OpenAI, Anthropic, Gemini); nhà khác dùng khóa Tavily của
  người dùng.
- Đợt đầu: xAI, Anthropic, OpenAI, DeepSeek, Ollama (bản đám mây), Google Gemini, Azure OpenAI, Mistral.

Khóa đi kèm từng lượt trong header, chỉ sống trong lượt đó: không lưu, không ghi log, chỉ gửi tới đúng nhà cung cấp người
dùng chọn (như đường chuyển tiếp giọng `X-Voice-Key`). Máy chủ chỉ gọi danh sách địa chỉ cố định dưới đây; Azure OpenAI chỉ
nhận đúng tên miền của Azure. Nhờ vậy không ai mượn được máy chủ Peto gọi tới địa chỉ tùy ý.

Lượt dùng khóa riêng ghi số liệu với dịch vụ "byok" và slug "byok/…", nên trang Quản trị không tính nó vào chi phí của chủ
web dù trùng tên model.
"""

from __future__ import annotations

from contextlib import aclosing

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter

import httpx

from core import config, usage_events
from shared.time_tools import TOOL_SCHEMAS, execute_tool
from features.companion import player_tools
from shared.web_search import normalize_sources, search_context

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk

logger = logging.getLogger("peto_web.byok")


@dataclass(frozen=True)
class ByokProvider:
    id: str
    label: str
    # responses: Responses API (xAI, OpenAI); anthropic: Messages API; gemini: API riêng của Google;
    # chat: Chat Completions kiểu OpenAI; ollama: API riêng của Ollama.
    kind: str
    base_url: str
    # native: tìm kiếm của chính nhà cung cấp; tavily: cần khóa Tavily.
    search: str
    # Gửi ảnh cho model. DeepSeek không nhận ảnh; model đám mây của Ollama phần lớn chỉ đọc chữ.
    images: bool


PROVIDERS: dict[str, ByokProvider] = {
    "xai": ByokProvider("xai", "xAI", "responses", "https://api.x.ai/v1", "native", True),
    "anthropic": ByokProvider("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com", "native", True),
    "openai": ByokProvider("openai", "OpenAI", "responses", "https://api.openai.com/v1", "native", True),
    "gemini": ByokProvider("gemini", "Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta",
                           "native", True),
    "deepseek": ByokProvider("deepseek", "DeepSeek", "chat", "https://api.deepseek.com", "tavily", False),
    "mistral": ByokProvider("mistral", "Mistral", "chat", "https://api.mistral.ai/v1", "tavily", True),
    # Địa chỉ lấy từ tài nguyên của người dùng, chỉ nhận đúng tên miền của Azure (AZURE_ENDPOINT).
    "azure-openai": ByokProvider("azure-openai", "Azure OpenAI", "chat", "", "tavily", True),
    "ollama": ByokProvider("ollama", "Ollama", "ollama", "https://ollama.com", "tavily", False),
}

AZURE_ENDPOINT = re.compile(
    r"^https://[a-z0-9][a-z0-9-]{0,62}\.(?:openai\.azure\.com|cognitiveservices\.azure\.com|services\.ai\.azure\.com)/?$")
MODEL_ID = re.compile(r"^[\w.:/\-]{1,100}$")
# Khóa là chuỗi ký tự in được, không khoảng trắng: chặn xuống dòng lọt vào header.
KEY = re.compile(r"^[\x21-\x7e]{8,512}$")
# Companion trả lời ngắn để đọc thành tiếng; mô hình suy nghĩ tính cả token suy nghĩ vào giới hạn này.
MAX_OUTPUT_TOKENS = 2048
REASONING_OUTPUT_TOKENS = 8192
MAX_TOOL_ROUNDS = 3
TIMEOUT = httpx.Timeout(120.0, connect=10.0)
TAVILY_URL = "https://api.tavily.com/search"
TAVILY_RESULTS = 5
TAVILY_SNIPPET = 1200


class ByokError(ValueError):
    """Lựa chọn hay khóa không hợp lệ; lời báo hiện thẳng cho người dùng (HTTP 400)."""


@dataclass(frozen=True)
class Choice:
    info: ByokProvider
    model: str
    key: str
    base_url: str
    search_key: str = ""


def choose(provider_id: str, model: str, endpoint: str | None, key: str | None, search_key: str | None) -> Choice:
    info = PROVIDERS.get(provider_id or "")
    if info is None:
        raise ByokError("Nhà cung cấp không hợp lệ.")
    key = (key or "").strip()
    if not KEY.match(key):
        raise ByokError(f"Chưa có khóa {info.label} hợp lệ. Nhập khóa trong Cài đặt Companion → Nhà cung cấp.")
    # Tên model nằm trong đường dẫn URL của Gemini: không cho "..", và không cho "/" với Gemini, để không trỏ sang API khác.
    if not MODEL_ID.match(model or "") or ".." in model or (info.kind == "gemini" and "/" in model):
        raise ByokError(f"Chưa chọn model của {info.label}. Chọn trong Cài đặt Companion → Mô-đun → Bộ não.")
    base = info.base_url
    if info.id == "azure-openai":
        endpoint = (endpoint or "").strip().lower()
        if not AZURE_ENDPOINT.match(endpoint):
            raise ByokError("Địa chỉ Azure OpenAI phải có dạng https://<tên>.openai.azure.com.")
        base = endpoint.rstrip("/") + "/openai/v1"
    search_key = (search_key or "").strip()
    if search_key and not KEY.match(search_key):
        raise ByokError("Khóa Tavily không hợp lệ. Kiểm tra lại trong Cài đặt Companion → Mô-đun → Tra web.")
    return Choice(info, model, key, base, search_key)


def build(choice: Choice) -> ChatProvider:
    """Provider cho đúng một lượt; khóa nằm trong đối tượng này và mất khi lượt xong."""
    info = choice.info
    if config.AI_PROVIDER == "mock":
        from .mock import MockProvider

        provider: ChatProvider = MockProvider(f"byok:{info.id}:{choice.model}")
    elif info.kind == "responses":
        provider = _keyed_responses(choice)
    elif info.kind == "anthropic":
        provider = _keyed_claude(choice)
    elif info.kind == "gemini":
        provider = GeminiProvider(choice)
    elif info.kind == "ollama":
        provider = OllamaProvider(choice)
    else:
        provider = ChatCompletionsProvider(choice)
    provider.catalog_key = f"byok:{info.id}"
    return provider


def _messages_text(message: ChatMessage, images: bool) -> tuple[str, list]:
    """Chữ của một tin và các ảnh gửi được; ảnh không gửi được thành nhãn để model biết có ảnh."""
    labels, kept = [], []
    for attachment in message.attachments:
        if attachment.kind == "image" and attachment.data_url and images:
            kept.append(attachment)
        else:
            labels.append(f"[Ảnh đính kèm: {attachment.name}]" if attachment.kind == "image" else f"[Tệp đính kèm: {attachment.name}]")
    text = "\n".join([*labels, message.content] if message.content else labels)
    return text, kept


def _recent_images(messages: list[ChatMessage]) -> set[int]:
    """Chỉ gửi ảnh của vài tin gần nhất, như MAX_HISTORY_IMAGES ở các provider khác."""
    keep: set[int] = set()
    count = 0
    for index in range(len(messages) - 1, -1, -1):
        images = sum(1 for item in messages[index].attachments if item.kind == "image" and item.data_url)
        if images and count < config.MAX_HISTORY_IMAGES:
            keep.add(index)
            count += images
    return keep


def _split_data_url(data_url: str) -> tuple[str, str]:
    head, _, data = data_url.partition(",")
    return head.removeprefix("data:").split(";")[0] or "image/png", data


def _function_tools(search: bool) -> list[dict]:
    """Công cụ dạng Chat Completions: đồng hồ của Peto, cộng tra web qua Tavily khi có khóa."""
    tools = [{"type": "function", "function": {key: schema[key] for key in ("name", "description", "parameters") if key in schema}}
             for schema in TOOL_SCHEMAS]
    if search:
        tools.append({"type": "function", "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use one short, specific query.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}},
                           "required": ["query"], "additionalProperties": False},
        }})
    if player_tools.current.get() is not None:
        schema = player_tools.current.get().schema
        tools.append({'type': 'function', 'function': {key: schema[key] for key in ('name', 'description', 'parameters')}})
    return tools


def _status_error(label: str, status: int, body: str) -> ProviderError:
    """Lời báo tiếng Việt theo mã lỗi; không đưa nguyên văn lời nhà cung cấp (có thể dài, tiếng Anh)."""
    logger.warning("%s (khóa riêng) HTTP %s: %s", label, status, " ".join(body.split())[:300])
    lowered = body.lower()
    if status in {401, 403} or "api_key_invalid" in lowered or "api key not valid" in lowered:
        return ProviderError(f"{label} từ chối khóa của bạn. Kiểm tra khóa trong Cài đặt Companion → Nhà cung cấp.")
    if status == 402 or "insufficient" in lowered or "quota" in lowered:
        return ProviderError(f"Tài khoản {label} của bạn đã hết hạn mức hoặc số dư. Nạp thêm, hoặc chọn Peto trong "
                             "Cài đặt Companion → Mô-đun → Bộ não.")
    if status == 429:
        return ProviderError(f"{label} đang giới hạn lượt của bạn. Đợi chút rồi thử lại.", retryable=True)
    if status == 404:
        return ProviderError(f"{label} không có model này. Chọn model khác trong Cài đặt Companion → Mô-đun → Bộ não.")
    if status >= 500:
        return ProviderError(f"{label} đang gặp sự cố. Thử lại sau chút nhé.", retryable=True)
    return ProviderError(f"{label} không nhận yêu cầu này (HTTP {status}). Model có thể không hỗ trợ ảnh hay công cụ; "
                         "thử model khác trong Cài đặt Companion → Mô-đun → Bộ não.")


async def _tavily(key: str, query: str) -> list[dict]:
    """Tra web bằng khóa Tavily của người dùng. Khóa sai thì báo rõ; lỗi mạng thì trả lỗi cho model tự nói."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=False) as client:
        response = await client.post(TAVILY_URL, headers={"Authorization": f"Bearer {key}"},
                                     json={"query": query[:400], "max_results": TAVILY_RESULTS, "search_depth": "basic"})
    if response.status_code in {401, 403}:
        raise ProviderError("Tavily từ chối khóa của bạn. Kiểm tra khóa trong Cài đặt Companion → Mô-đun → Tra web.")
    if response.status_code in {429, 432, 433}:
        raise ProviderError("Khóa Tavily của bạn đã hết lượt tra. Đợi sang tháng hoặc nâng gói ở tavily.com.")
    response.raise_for_status()
    results = response.json().get("results") or []
    return [{"title": str(item.get("title") or item.get("url") or "")[:200], "url": str(item.get("url") or ""),
             "content": str(item.get("content") or "")[:TAVILY_SNIPPET]}
            for item in results if isinstance(item, dict) and item.get("url")]


class _ToolLoopProvider(ChatProvider):
    """Vòng công cụ chung cho Chat Completions và Ollama: tối đa MAX_TOOL_ROUNDS lần gọi công cụ, lần cuối không có
    công cụ. Chữ viết trước khi tra là bản nháp ("replace"), như các provider khác."""

    def __init__(self, choice: Choice):
        self.choice = choice
        self.model = choice.model
        self.name = f"byok-{choice.info.id}"

    async def _round(self, client: httpx.AsyncClient, messages: list[dict], tools: list[dict]
                     ) -> AsyncIterator[tuple[str, object]]:
        """Một lần gọi model; phát ("text", chữ), ("call", {id, name, arguments}) và ("usage", dict)."""
        raise NotImplementedError
        yield "", None  # pragma: no cover

    def _assistant_with_calls(self, text: str, calls: list[dict]) -> dict:
        raise NotImplementedError

    def _tool_message(self, call: dict, content: str) -> dict:
        raise NotImplementedError

    def _history(self, messages: list[ChatMessage]) -> list[dict]:
        raise NotImplementedError

    async def stream(self, *, system_prompt: str, messages: list[ChatMessage], effort: str = "low",
                     timezone: str | None = None, web_search: str = "auto", tools_enabled: bool = True,
                     ) -> AsyncIterator[str | StreamChunk]:
        label = self.choice.info.label
        searchable = (tools_enabled and config.WEB_SEARCH_ENABLED and web_search != "off" and bool(self.choice.search_key))
        payload = [{"role": "system", "content": f"{system_prompt}\n\n{search_context(web_search, searchable)}"},
                   *self._history(messages)]
        sources: list[dict] = []
        searches = 0
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            for round_index in range(MAX_TOOL_ROUNDS + 1):
                final = round_index == MAX_TOOL_ROUNDS
                tools = _function_tools(searchable) if tools_enabled and not final else []
                text: list[str] = []
                calls: list[dict] = []
                usage: dict = {}
                started = perf_counter()
                complete = False
                try:
                    async for kind, value in self._round(client, payload, tools):
                        if kind == "text":
                            text.append(value)
                            yield value
                        elif kind == "call":
                            calls.append(value)
                        elif kind == "usage":
                            usage = value
                    complete = True
                except httpx.HTTPError as err:
                    logger.warning("%s (khóa riêng) lỗi mạng: %s", label, type(err).__name__)
                    raise ProviderError(f"Chưa kết nối được tới {label}. Thử lại sau chút nhé.", retryable=True) from err
                finally:
                    usage_events.record(
                        "call", service="byok", model=f"byok:{self.choice.info.id}",
                        slug=f"byok/{self.choice.info.id}/{self.model}", purpose="chat", complete=complete,
                        elapsed_ms=round((perf_counter() - started) * 1000),
                        input_tokens=usage.get("input"), output_tokens=usage.get("output"), search_calls=searches,
                    )
                if not calls:
                    return
                if final:
                    raise ProviderError(f"{label} vẫn gọi công cụ sau lượt cuối. Phần đã trả lời được giữ lại.")
                if text:
                    # Chữ trước lệnh tra là bản nháp: Companion bỏ đi, như lúc Grok viết rồi mới tra web.
                    yield StreamChunk("replace")
                payload.append(self._assistant_with_calls("".join(text), calls))
                for call in calls:
                    name = call.get("name")
                    if name == "web_search" and searchable:
                        try:
                            query = str(json.loads(call.get("arguments") or "{}").get("query") or "").strip()
                        except (ValueError, AttributeError):
                            query = ""
                        yield StreamChunk("search", "searching")
                        searches += 1
                        try:
                            results = await _tavily(self.choice.search_key, query) if query else []
                            result = {"ok": True, "results": results}
                            sources = normalize_sources([*sources, *({"url": item["url"], "title": item["title"], "kind": "result"}
                                                                     for item in results)])
                            yield StreamChunk("search", "completed")
                            if sources:
                                yield StreamChunk("sources", sources=tuple(sources))
                        except httpx.HTTPError as err:
                            logger.warning("Tavily lỗi: %s", type(err).__name__)
                            result = {"ok": False, "error": "Web search failed. Say you could not look it up right now."}
                            yield StreamChunk("search", "failed")
                    elif name == player_tools.NAME and player_tools.current.get():
                        async with aclosing(player_tools.current.get().run(call.get('arguments') or '')) as action:
                            async for item in action:
                                if isinstance(item, StreamChunk):
                                    yield item
                                else:
                                    result = item
                    else:
                        result = execute_tool(name or "", call.get("arguments") or "", timezone=timezone)
                    payload.append(self._tool_message(call, json.dumps(result, ensure_ascii=False)))


class ChatCompletionsProvider(_ToolLoopProvider):
    """DeepSeek, Mistral và Azure OpenAI: Chat Completions kiểu OpenAI, stream SSE."""

    def _headers(self) -> dict:
        if self.choice.info.id == "azure-openai":
            return {"api-key": self.choice.key}
        return {"Authorization": f"Bearer {self.choice.key}"}

    def _history(self, messages: list[ChatMessage]) -> list[dict]:
        images_ok = self.choice.info.images
        recent = _recent_images(messages)
        payload = []
        for index, message in enumerate(messages):
            text, images = _messages_text(message, images_ok and index in recent)
            if message.role == "user" and images:
                # Mistral nhận image_url là chuỗi; OpenAI và Azure nhận dạng {"url": …}.
                parts = [{"type": "text", "text": text or "(ảnh)"}, *(
                    {"type": "image_url", "image_url": item.data_url if self.choice.info.id == "mistral" else {"url": item.data_url}}
                    for item in images)]
                payload.append({"role": "user", "content": parts})
            else:
                payload.append({"role": message.role, "content": text or "…"})
        return payload

    def _assistant_with_calls(self, text: str, calls: list[dict]) -> dict:
        return {"role": "assistant", "content": text or None, "tool_calls": [
            {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"] or "{}"}}
            for call in calls]}

    def _tool_message(self, call: dict, content: str) -> dict:
        message = {"role": "tool", "tool_call_id": call["id"], "content": content}
        if self.choice.info.id == "mistral":
            message["name"] = call["name"]
        return message

    async def _round(self, client, messages, tools):
        body: dict = {"model": self.model, "messages": messages, "stream": True, "max_tokens": MAX_OUTPUT_TOKENS}
        if tools:
            body["tools"] = tools
        if self.choice.info.id != "mistral":
            body["stream_options"] = {"include_usage": True}
        pending: dict[int, dict] = {}
        async with client.stream("POST", f"{self.choice.base_url}/chat/completions", headers=self._headers(),
                                 json=body) as response:
            if response.status_code >= 400:
                raise _status_error(self.choice.info.label, response.status_code, (await response.aread()).decode(errors="replace"))
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("usage"):
                    yield "usage", {"input": chunk["usage"].get("prompt_tokens"), "output": chunk["usage"].get("completion_tokens")}
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield "text", delta["content"]
                    for position, call in enumerate(delta.get("tool_calls") or []):
                        index = call.get("index", position)
                        slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        function = call.get("function") or {}
                        slot["id"] = call.get("id") or slot["id"]
                        slot["name"] = function.get("name") or slot["name"]
                        slot["arguments"] += function.get("arguments") or ""
        for index in sorted(pending):
            call = pending[index]
            if call["name"]:
                yield "call", {**call, "id": call["id"] or f"call_{index}"}


class OllamaProvider(_ToolLoopProvider):
    """Ollama bản đám mây (ollama.com, chủ web chọn bản đám mây ngày 13/10/2026): API /api/chat, stream từng dòng JSON."""

    def _history(self, messages: list[ChatMessage]) -> list[dict]:
        payload = []
        for message in messages:
            text, _ = _messages_text(message, False)
            payload.append({"role": message.role, "content": text or "…"})
        return payload

    def _assistant_with_calls(self, text: str, calls: list[dict]) -> dict:
        return {"role": "assistant", "content": text, "tool_calls": [
            {"function": {"name": call["name"], "arguments": json.loads(call["arguments"] or "{}")}} for call in calls]}

    def _tool_message(self, call: dict, content: str) -> dict:
        return {"role": "tool", "tool_name": call["name"], "content": content}

    async def _round(self, client, messages, tools):
        body: dict = {"model": self.model, "messages": messages, "stream": True, "options": {"num_predict": MAX_OUTPUT_TOKENS}}
        if tools:
            body["tools"] = tools
        count = 0
        async with client.stream("POST", f"{self.choice.base_url}/api/chat",
                                 headers={"Authorization": f"Bearer {self.choice.key}"}, json=body) as response:
            if response.status_code >= 400:
                raise _status_error("Ollama", response.status_code, (await response.aread()).decode(errors="replace"))
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise ProviderError("Ollama báo lỗi khi đang trả lời. Thử lại hoặc chọn model khác.")
                message = chunk.get("message") or {}
                if message.get("content"):
                    yield "text", message["content"]
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    if function.get("name"):
                        count += 1
                        arguments = function.get("arguments")
                        yield "call", {"id": f"call_{count}", "name": function["name"],
                                       "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments or {})}
                if chunk.get("done"):
                    yield "usage", {"input": chunk.get("prompt_eval_count"), "output": chunk.get("eval_count")}


class GeminiProvider(ChatProvider):
    """Google Gemini qua API riêng (không qua lớp tương thích OpenAI): chỉ API riêng mới có tìm kiếm Google."""

    def __init__(self, choice: Choice):
        self.choice = choice
        self.model = choice.model
        self.name = "byok-gemini"

    def _contents(self, messages: list[ChatMessage]) -> list[dict]:
        recent = _recent_images(messages)
        contents = []
        for index, message in enumerate(messages):
            text, images = _messages_text(message, index in recent)
            parts: list[dict] = [{"text": text or "…"}]
            for image in images:
                mime, data = _split_data_url(image.data_url)
                parts.append({"inline_data": {"mime_type": mime, "data": data}})
            contents.append({"role": "model" if message.role == "assistant" else "user", "parts": parts})
        return contents

    async def stream(self, *, system_prompt: str, messages: list[ChatMessage], effort: str = "low",
                     timezone: str | None = None, web_search: str = "auto", tools_enabled: bool = True,
                     ) -> AsyncIterator[str | StreamChunk]:
        searchable = tools_enabled and config.WEB_SEARCH_ENABLED and web_search != "off"
        body: dict = {
            "systemInstruction": {"parts": [{"text": f"{system_prompt}\n\n{search_context(web_search, searchable)}"}]},
            "contents": self._contents(messages),
            "generationConfig": {"maxOutputTokens": REASONING_OUTPUT_TOKENS},
        }
        if searchable:
            body["tools"] = [{"google_search": {}}]
        started = perf_counter()
        usage: dict = {}
        complete = False
        searched = False
        sources: list[dict] = []
        url = f"{self.choice.base_url}/models/{self.model}:streamGenerateContent?alt=sse"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
                async with client.stream("POST", url, headers={"x-goog-api-key": self.choice.key}, json=body) as response:
                    if response.status_code >= 400:
                        raise _status_error("Google Gemini", response.status_code,
                                            (await response.aread()).decode(errors="replace"))
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            chunk = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        if chunk.get("usageMetadata"):
                            usage = chunk["usageMetadata"]
                        for candidate in chunk.get("candidates") or []:
                            for part in (candidate.get("content") or {}).get("parts") or []:
                                if part.get("text") and not part.get("thought"):
                                    yield part["text"]
                            grounding = candidate.get("groundingMetadata") or {}
                            if grounding.get("webSearchQueries") and not searched:
                                searched = True
                                yield StreamChunk("search", "completed")
                            found = [{"url": (item.get("web") or {}).get("uri"), "title": (item.get("web") or {}).get("title"),
                                      "kind": "result"} for item in grounding.get("groundingChunks") or []]
                            merged = normalize_sources([*sources, *found])
                            if merged != sources:
                                sources = merged
                                yield StreamChunk("sources", sources=tuple(sources))
                            reason = candidate.get("finishReason")
                            if reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}:
                                raise ProviderError("Google Gemini chặn câu trả lời này. Thử hỏi cách khác hoặc chọn Peto.")
                            if reason == "MAX_TOKENS":
                                raise ProviderError("Câu trả lời chạm giới hạn độ dài. Phần đã viết được giữ lại.")
            complete = True
        except httpx.HTTPError as err:
            logger.warning("Gemini (khóa riêng) lỗi mạng: %s", type(err).__name__)
            raise ProviderError("Chưa kết nối được tới Google Gemini. Thử lại sau chút nhé.", retryable=True) from err
        finally:
            usage_events.record(
                "call", service="byok", model="byok:gemini", slug=f"byok/gemini/{self.model}", purpose="chat",
                complete=complete, elapsed_ms=round((perf_counter() - started) * 1000),
                input_tokens=usage.get("promptTokenCount"), output_tokens=usage.get("candidatesTokenCount"),
                reasoning_tokens=usage.get("thoughtsTokenCount"), search_calls=int(searched),
            )


def _reasoning_model(choice: Choice) -> bool:
    """Mô hình có nhận reasoning.effort không. Gửi cho model không nhận thì cả lượt bị từ chối (HTTP 400)."""
    model = choice.model.lower()
    if choice.info.id == "openai":
        return model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6"))
    # xAI: chỉ model Peto đang dùng (đã chạy thật) và dòng mini có suy nghĩ chỉnh được.
    return model == config.XAI_MODEL.lower() or "grok-3-mini" in model


def _keyed_responses(choice: Choice) -> ChatProvider:
    from openai import AsyncOpenAI

    from .xai import ResponsesProvider

    class KeyedResponsesProvider(ResponsesProvider):
        usage_service = "byok"

        def __init__(self) -> None:
            label = choice.info.label
            self.name = f"byok-{choice.info.id}"
            self.service = label
            self.model = choice.model
            self.send_reasoning = _reasoning_model(choice)
            self.max_output_tokens = REASONING_OUTPUT_TOKENS if self.send_reasoning else MAX_OUTPUT_TOKENS
            self.usage_slug = f"byok/{choice.info.id}/{choice.model}"
            self.auth_error_message = f"{label} từ chối khóa của bạn. Kiểm tra khóa trong Cài đặt Companion → Nhà cung cấp."
            self.rate_limit_message = (f"{label} đang giới hạn lượt, hoặc tài khoản của bạn đã hết hạn mức. Thử lại sau, "
                                       "hoặc chọn Peto trong Cài đặt Companion → Mô-đun → Bộ não.")
            self._client = AsyncOpenAI(api_key=choice.key, base_url=choice.base_url, max_retries=0, timeout=120.0)

    return KeyedResponsesProvider()


def _keyed_claude(choice: Choice) -> ChatProvider:
    from anthropic import AsyncAnthropic

    from . import claude

    major = re.search(r"claude-(?:haiku|sonnet|opus)-(\d+)", choice.model)

    class KeyedClaudeProvider(claude.ClaudeProvider):
        usage_service = "byok"

        def __init__(self) -> None:
            self.name = "byok-anthropic"
            self.service = "Anthropic"
            self.model = choice.model
            self.max_output_tokens = REASONING_OUTPUT_TOKENS
            self.usage_slug = f"byok/anthropic/{choice.model}"
            self.auth_error_message = "Anthropic từ chối khóa của bạn. Kiểm tra khóa trong Cài đặt Companion → Nhà cung cấp."
            self.rate_limit_message = ("Anthropic đang giới hạn lượt, hoặc tài khoản của bạn đã hết hạn mức. Thử lại sau, "
                                       "hoặc chọn Peto trong Cài đặt Companion → Mô-đun → Bộ não.")
            # Suy nghĩ tự điều chỉnh chỉ có ở Claude đời 5 trở đi; model cũ hơn thì gửi yêu cầu thường.
            self._client = claude.ClaudeClient(AsyncAnthropic(api_key=choice.key, max_retries=0, timeout=120.0),
                                               adaptive=bool(major and int(major.group(1)) >= 5))

        async def _prepare(self) -> None:
            """Khóa của người dùng đã có sẵn; không cần khóa Claude của máy chủ."""

    return KeyedClaudeProvider()


# ---------- Kiểm tra khóa và lấy danh sách model ----------

_EXCLUDE = ("embed", "embedding", "tts", "audio", "realtime", "transcribe", "whisper", "dall-e", "image", "imagen", "veo",
            "moderation", "ocr", "search", "aqa", "babbage", "davinci", "computer-use", "codex")


def _chat_models(ids: list[str]) -> list[str]:
    seen, kept = set(), []
    for item in ids:
        if not item or item in seen or any(word in item.lower() for word in _EXCLUDE):
            continue
        seen.add(item)
        kept.append(item)
    return sorted(kept)


MOCK_MODELS = {
    "xai": ["grok-4.7", "grok-4.7-fast"], "anthropic": ["claude-haiku-5-5", "claude-sonnet-5-5"],
    "openai": ["gpt-6-luna", "gpt-6-sol"], "gemini": ["gemini-flash-latest", "gemini-pro-latest"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"], "mistral": ["mistral-medium-latest", "mistral-small-latest"],
    "azure-openai": [], "ollama": ["gpt-oss:120b", "qwen3-coder:480b"],
}


async def check(choice: Choice) -> list[str]:
    """Gọi danh sách model bằng khóa của người dùng: kiểm tra khóa và cho trang Bộ não chọn model. Azure OpenAI trả
    danh sách rỗng: người dùng gõ tên bản triển khai của mình."""
    info = choice.info
    if config.AI_PROVIDER == "mock":
        if "__sai__" in choice.key:
            raise ProviderError(f"{info.label} từ chối khóa này. Kiểm tra lại khóa rồi thử lại.")
        return MOCK_MODELS[info.id]
    if info.kind in {"responses", "chat"}:
        url = f"{choice.base_url}/models"
        headers = {"api-key": choice.key} if info.id == "azure-openai" else {"Authorization": f"Bearer {choice.key}"}
    elif info.kind == "anthropic":
        url, headers = f"{info.base_url}/v1/models?limit=100", {"x-api-key": choice.key, "anthropic-version": "2023-06-01"}
    elif info.kind == "gemini":
        url, headers = f"{info.base_url}/models?pageSize=200", {"x-goog-api-key": choice.key}
    else:
        url, headers = f"{info.base_url}/api/tags", {"Authorization": f"Bearer {choice.key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as err:
        raise ProviderError(f"Chưa kết nối được tới {info.label}. Thử lại sau chút nhé.") from err
    if response.status_code >= 400:
        error = _status_error(info.label, response.status_code, response.text)
        if response.status_code in {401, 403}:
            error = ProviderError(f"{info.label} từ chối khóa này. Kiểm tra lại khóa rồi thử lại.")
        raise error
    data = response.json()
    if info.id == "azure-openai":
        return []
    if info.kind == "gemini":
        return _chat_models([str(item.get("name", "")).removeprefix("models/") for item in data.get("models") or []
                             if "generateContent" in (item.get("supportedGenerationMethods") or [])])
    if info.kind == "ollama":
        return _chat_models([str(item.get("name") or item.get("model") or "") for item in data.get("models") or []])
    if info.id == "mistral":
        return _chat_models([str(item.get("id", "")) for item in data.get("data") or []
                             if (item.get("capabilities") or {}).get("completion_chat", True)])
    return _chat_models([str(item.get("id", "")) for item in data.get("data") or []])
