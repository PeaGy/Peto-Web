"""Khóa API riêng của người dùng cho bộ não Companion (ai/byok.py, Cài đặt Companion → Nhà cung cấp).

Không gọi nhà cung cấp thật: lượt chat chạy bằng provider giả, còn từng kiểu gọi (Chat Completions, Ollama, Gemini, Tavily,
danh sách model) chạy trên httpx.MockTransport.
"""

import json

import httpx
import pytest

import storage as db
from ai import byok
from ai.base import ChatAttachment, ChatMessage, ProviderError, StreamChunk
from ai.mock import MockProvider
from core import usage_events
from features.companion import memory as companion_memory
from tests.conftest import TEST_OWNER, read_events

KEY = "sk-user-1234567890"
TAVILY = "tvly-user-1234567890"


@pytest.fixture(autouse=True)
async def fresh(client):
    await db.clear_memories(TEST_OWNER)
    await db.set_memory_enabled(TEST_OWNER, True)
    conversation = await db.latest_conversation(TEST_OWNER, "companion")
    while conversation:
        await db.delete_conversation(TEST_OWNER, conversation)
        conversation = await db.latest_conversation(TEST_OWNER, "companion")
    companion_memory._pending_until.clear()
    yield


@pytest.fixture
def calls(monkeypatch):
    """Model, system prompt và chế độ tra web của từng lượt gọi provider giả."""
    seen: list[dict] = []
    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, **kwargs):
        seen.append({"model": self.model, "prompt": system_prompt, "web_search": kwargs.get("web_search")})
        async for chunk in original(self, system_prompt=system_prompt, messages=messages, **kwargs):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    return seen


async def send(client, message: str, provider: dict | None = None, headers: dict | None = None, mode="companion"):
    body = {"message": message, "mode": mode, **({"provider": provider} if provider else {})}
    async with client.stream("POST", "/api/chat", json=body, headers=headers or {}) as response:
        if response.status_code != 200:
            await response.aread()
            return response.status_code, response.json()
        return 200, await read_events(response)


async def test_companion_turn_uses_own_key_without_memory(client, calls, monkeypatch):
    await db.apply_memory_changes(TEST_OWNER, upserts=[companion_memory.new_entry("topic", "Sở thích", "", ["Thích trà sữa"])],
                                  remove=[], limit=companion_memory.MAX_ENTRIES)
    remembered: list[str] = []
    monkeypatch.setattr(companion_memory, "remember", lambda owner, window=0: remembered.append(owner) or _done())
    status, events = await send(client, "hello there", {"id": "deepseek", "model": "deepseek-chat"},
                                {"X-Peto-Provider-Key": KEY})
    assert status == 200
    assert events[-1]["type"] == "done"
    turn = [call for call in calls if call["model"].startswith("byok:")]
    assert turn and turn[0]["model"] == "byok:deepseek:deepseek-chat"
    # Không đọc Trí nhớ, không tra web khi chưa có khóa Tavily, không ghi nhớ sau lượt.
    assert "Thích trà sữa" not in turn[0]["prompt"]
    assert turn[0]["web_search"] == "off"
    assert remembered == []
    assert companion_memory._pending_until.get(TEST_OWNER) is None
    conversation = await db.latest_conversation(TEST_OWNER, "companion")
    rows = await db.get_messages(TEST_OWNER, conversation)
    assert [row.get("provider") for row in rows] == ["deepseek", "deepseek"]
    readable = lambda rows, conversation_id: [row["content"] for row in rows if row["conversation_id"] == conversation_id]
    assert readable(await db.memory_messages_after(TEST_OWNER, 0, 1000), conversation) == []

    # Lượt Peto sau đó vẫn đọc Trí nhớ và chỉ tin của Peto được đem đi ghi nhớ.
    calls.clear()
    status, _ = await send(client, "and now Peto")
    assert status == 200
    assert "Thích trà sữa" in calls[0]["prompt"]
    later = await db.latest_conversation(TEST_OWNER, "companion")
    assert readable(await db.memory_messages_after(TEST_OWNER, 0, 1000), later)[0] == "and now Peto"


async def _done():
    return None


async def test_tavily_key_turns_search_on_for_providers_without_native_search(client, calls):
    status, _ = await send(client, "news?", {"id": "mistral", "model": "mistral-small-latest"},
                           {"X-Peto-Provider-Key": KEY, "X-Peto-Search-Key": TAVILY})
    assert status == 200
    assert calls[0]["web_search"] == "auto"
    calls.clear()
    status, _ = await send(client, "news?", {"id": "openai", "model": "gpt-6-luna"}, {"X-Peto-Provider-Key": KEY})
    assert status == 200
    assert calls[0]["web_search"] == "auto"


@pytest.mark.parametrize("provider, headers, message", [
    ({"id": "deepseek", "model": "deepseek-chat"}, {}, "Chưa có khóa DeepSeek"),
    ({"id": "nope", "model": "x"}, {"X-Peto-Provider-Key": KEY}, "Nhà cung cấp không hợp lệ"),
    ({"id": "openai", "model": "gpt 6"}, {"X-Peto-Provider-Key": KEY}, "Chưa chọn model"),
    ({"id": "gemini", "model": "../files"}, {"X-Peto-Provider-Key": KEY}, "Chưa chọn model"),
    ({"id": "gemini", "model": "tuned/x"}, {"X-Peto-Provider-Key": KEY}, "Chưa chọn model"),
    ({"id": "azure-openai", "model": "my-gpt", "endpoint": "https://evil.example.com"}, {"X-Peto-Provider-Key": KEY},
     "Địa chỉ Azure OpenAI"),
    ({"id": "azure-openai", "model": "my-gpt", "endpoint": "https://x.openai.azure.com.evil.com"},
     {"X-Peto-Provider-Key": KEY}, "Địa chỉ Azure OpenAI"),
    ({"id": "deepseek", "model": "deepseek-chat"}, {"X-Peto-Provider-Key": KEY, "X-Peto-Search-Key": "bad key"},
     "Khóa Tavily không hợp lệ"),
])
async def test_invalid_choices_are_refused_before_anything_is_stored(client, provider, headers, message):
    status, body = await send(client, "hi", provider, headers)
    assert status == 400
    assert message in body["detail"]
    assert await db.latest_conversation(TEST_OWNER, "companion") is None


async def test_own_key_is_only_for_companion(client):
    status, body = await send(client, "hi", {"id": "openai", "model": "gpt-6-luna"}, {"X-Peto-Provider-Key": KEY},
                              mode="chat")
    assert status == 400
    assert "chỉ dùng cho Companion" in body["detail"]


async def test_azure_endpoint_accepts_only_azure_hosts():
    choice = byok.choose("azure-openai", "my-gpt", "https://peto-res.openai.azure.com/", KEY, None)
    assert choice.base_url == "https://peto-res.openai.azure.com/openai/v1"
    for bad in ("http://peto.openai.azure.com", "https://127.0.0.1", "https://peto.openai.azure.com/path",
                "https://user@peto.openai.azure.com"):
        with pytest.raises(byok.ByokError):
            byok.choose("azure-openai", "my-gpt", bad, KEY, None)


async def test_check_endpoint_lists_models_and_refuses_bad_keys(client, anon_client):
    response = await client.post("/api/companion/providers/check", json={"provider": "deepseek"},
                                 headers={"X-Peto-Provider-Key": KEY})
    assert response.status_code == 200
    assert response.json() == {"models": ["deepseek-chat", "deepseek-reasoner"], "deployment": False}
    assert response.headers["cache-control"] == "private, no-store"
    bad = await client.post("/api/companion/providers/check", json={"provider": "deepseek"},
                            headers={"X-Peto-Provider-Key": "sk-__sai__-123456"})
    assert bad.status_code == 400 and "từ chối khóa" in bad.json()["detail"]
    assert (await anon_client.post("/api/companion/providers/check", json={"provider": "deepseek"},
                                   headers={"X-Peto-Provider-Key": KEY})).status_code == 401


# ---------- Kiểu gọi thật, trên httpx.MockTransport ----------

@pytest.fixture
def transport(monkeypatch):
    """Thay mạng của ai/byok.py bằng hàm ``handler`` của từng test; giữ lại mọi request đã gửi."""
    real = httpx.AsyncClient
    state = {"handler": None, "requests": []}

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(byok.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handle), **kwargs))
    return state


@pytest.fixture
def recorded(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(usage_events, "record", lambda kind, **fields: rows.append({"kind": kind, **fields}))
    return rows


def sse(*chunks: dict) -> bytes:
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks).encode() + b"data: [DONE]\n\n"


async def collect(provider, messages=None, web_search="auto"):
    out = []
    async for item in provider.stream(system_prompt="Be Peto.", messages=messages or [ChatMessage("user", "hi")],
                                      web_search=web_search):
        out.append(item)
    return out


async def test_chat_completions_runs_tavily_search_and_drops_the_draft(transport, recorded):
    rounds = iter([
        sse({"choices": [{"delta": {"content": "Let me check. "}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "web_search", "arguments": '{"que'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ry": "peto news"}'}}]}, "finish_reason": "tool_calls"}]}),
        sse({"choices": [{"delta": {"content": "It rained today."}}]}, {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 4}}),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.tavily.com":
            assert request.headers["authorization"] == f"Bearer {TAVILY}"
            assert json.loads(request.content)["query"] == "peto news"
            return httpx.Response(200, json={"results": [{"title": "Rain", "url": "https://news.example/rain", "content": "It rained."}]})
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, content=next(rounds), headers={"content-type": "text/event-stream"})

    transport["handler"] = handler
    provider = byok.ChatCompletionsProvider(byok.choose("deepseek", "deepseek-chat", None, KEY, TAVILY))
    out = await collect(provider)
    kinds = [item.kind if isinstance(item, StreamChunk) else "text" for item in out]
    assert kinds == ["text", "replace", "search", "search", "sources", "text"]
    assert out[-1] == "It rained today."
    second = json.loads(transport["requests"][2].content)
    assert second["messages"][-2]["tool_calls"][0]["function"]["arguments"] == '{"query": "peto news"}'
    assert second["messages"][-1]["role"] == "tool" and "It rained." in second["messages"][-1]["content"]
    assert {row["service"] for row in recorded} == {"byok"}
    assert all(row["slug"] == "byok/deepseek/deepseek-chat" for row in recorded)
    # Không có khóa Tavily thì không đưa công cụ tra web; ảnh của DeepSeek thành nhãn chữ.
    transport["requests"].clear()
    transport["handler"] = lambda request: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "Hi"}}]}))
    image = ChatAttachment("image", "cat.png", "image/png", data_url="data:image/png;base64,AAAA")
    await collect(byok.ChatCompletionsProvider(byok.choose("deepseek", "deepseek-chat", None, KEY, None)),
                  [ChatMessage("user", "look", (image,))])
    body = json.loads(transport["requests"][0].content)
    assert [tool["function"]["name"] for tool in body.get("tools", [])] == ["get_current_datetime"]
    assert body["messages"][1]["content"] == "[Ảnh đính kèm: cat.png]\nlook"


async def test_azure_and_mistral_request_shapes(transport):
    transport["handler"] = lambda request: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "Hi"}}]}))
    image = ChatAttachment("image", "cat.png", "image/png", data_url="data:image/png;base64,AAAA")
    azure = byok.choose("azure-openai", "my-deploy", "https://res.openai.azure.com", KEY, None)
    await collect(byok.ChatCompletionsProvider(azure), [ChatMessage("user", "look", (image,))])
    request = transport["requests"][0]
    assert str(request.url) == "https://res.openai.azure.com/openai/v1/chat/completions"
    assert request.headers["api-key"] == KEY and "authorization" not in request.headers
    body = json.loads(request.content)
    assert body["model"] == "my-deploy"
    assert body["messages"][1]["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    transport["requests"].clear()
    await collect(byok.ChatCompletionsProvider(byok.choose("mistral", "mistral-small-latest", None, KEY, None)),
                  [ChatMessage("user", "look", (image,))])
    body = json.loads(transport["requests"][0].content)
    assert body["messages"][1]["content"][1] == {"type": "image_url", "image_url": "data:image/png;base64,AAAA"}
    assert "stream_options" not in body


@pytest.mark.parametrize("status, text", [(401, "từ chối khóa"), (429, "giới hạn lượt"), (404, "không có model"),
                                          (402, "hết hạn mức")])
async def test_provider_errors_are_vietnamese(transport, status, text):
    transport["handler"] = lambda request: httpx.Response(status, json={"error": {"message": "nope"}})
    with pytest.raises(ProviderError, match=text):
        await collect(byok.ChatCompletionsProvider(byok.choose("deepseek", "deepseek-chat", None, KEY, None)))


async def test_tavily_bad_key_is_reported(transport):
    rounds = iter([sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {
        "name": "web_search", "arguments": '{"query": "x"}'}}]}}]})])

    def handler(request):
        if request.url.host == "api.tavily.com":
            return httpx.Response(401, json={"detail": "bad"})
        return httpx.Response(200, content=next(rounds))

    transport["handler"] = handler
    with pytest.raises(ProviderError, match="Tavily từ chối khóa"):
        await collect(byok.ChatCompletionsProvider(byok.choose("deepseek", "deepseek-chat", None, KEY, TAVILY)))


async def test_ollama_cloud_streams_lines_and_calls_tools(transport):
    lines = iter([
        b'{"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "web_search", "arguments": {"query": "weather"}}}]}, "done": false}\n'
        b'{"message": {"role": "assistant", "content": ""}, "done": true, "prompt_eval_count": 5, "eval_count": 2}\n',
        b'{"message": {"role": "assistant", "content": "Sunny"}, "done": false}\n{"message": {"content": "!"}, "done": true}\n',
    ])

    def handler(request):
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": []})
        assert str(request.url) == "https://ollama.com/api/chat"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, content=next(lines))

    transport["handler"] = handler
    out = await collect(byok.OllamaProvider(byok.choose("ollama", "gpt-oss:120b", None, KEY, TAVILY)))
    assert [item for item in out if isinstance(item, str)] == ["Sunny", "!"]
    second = json.loads(transport["requests"][2].content)
    assert second["messages"][-2]["tool_calls"][0]["function"] == {"name": "web_search", "arguments": {"query": "weather"}}
    assert second["messages"][-1]["role"] == "tool" and second["messages"][-1]["tool_name"] == "web_search"


async def test_gemini_uses_google_search_and_keeps_the_key_out_of_the_url(transport, recorded):
    body = sse(
        {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "Rain today."}]},
                         "groundingMetadata": {"webSearchQueries": ["rain"], "groundingChunks": [
                             {"web": {"uri": "https://example.com/rain", "title": "example.com"}}]}}],
         "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}},
    )
    transport["handler"] = lambda request: httpx.Response(200, content=body)
    image = ChatAttachment("image", "cat.png", "image/png", data_url="data:image/png;base64,AAAA")
    out = await collect(byok.GeminiProvider(byok.choose("gemini", "gemini-flash-latest", None, KEY, None)),
                        [ChatMessage("user", "look", (image,)), ChatMessage("assistant", "a cat"), ChatMessage("user", "rain?")])
    assert [item for item in out if isinstance(item, str)] == ["Rain today."]
    assert [item.kind for item in out if isinstance(item, StreamChunk)] == ["search", "sources"]
    request = transport["requests"][0]
    assert KEY not in str(request.url)
    assert request.headers["x-goog-api-key"] == KEY
    sent = json.loads(request.content)
    assert sent["tools"] == [{"google_search": {}}]
    assert sent["contents"][0]["parts"][1] == {"inline_data": {"mime_type": "image/png", "data": "AAAA"}}
    assert [item["role"] for item in sent["contents"]] == ["user", "model", "user"]
    assert recorded[0]["service"] == "byok" and recorded[0]["slug"] == "byok/gemini/gemini-flash-latest"
    # Tắt tra web thì không gửi công cụ tìm kiếm.
    transport["requests"].clear()
    await collect(byok.GeminiProvider(byok.choose("gemini", "gemini-flash-latest", None, KEY, None)), web_search="off")
    assert "tools" not in json.loads(transport["requests"][0].content)


async def test_check_filters_models_per_provider(transport, monkeypatch):
    monkeypatch.setattr(byok.config, "AI_PROVIDER", "xai")
    transport["handler"] = lambda request: httpx.Response(200, json={"data": [
        {"id": "gpt-6-luna"}, {"id": "text-embedding-3-small"}, {"id": "gpt-realtime"}, {"id": "o4-mini"}]})
    assert await byok.check(byok.choose("openai", "x", None, KEY, None)) == ["gpt-6-luna", "o4-mini"]
    transport["handler"] = lambda request: httpx.Response(200, json={"models": [
        {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]})
    assert await byok.check(byok.choose("gemini", "x", None, KEY, None)) == ["gemini-flash-latest"]
    transport["handler"] = lambda request: httpx.Response(200, json={"data": []})
    assert await byok.check(byok.choose("azure-openai", "x", "https://res.openai.azure.com", KEY, None)) == []
    assert transport["requests"][-1].headers["api-key"] == KEY
    transport["handler"] = lambda request: httpx.Response(401, json={})
    with pytest.raises(ProviderError, match="từ chối khóa này"):
        await byok.check(byok.choose("anthropic", "x", None, KEY, None))
    assert transport["requests"][-1].headers["x-api-key"] == KEY


async def test_keyed_responses_drops_reasoning_for_models_without_it(monkeypatch):
    monkeypatch.setattr(byok.config, "AI_PROVIDER", "xai")
    sent: list[dict] = []

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def close(self):
            pass

    provider = byok.build(byok.choose("openai", "gpt-4.1-mini", None, KEY, None))
    assert provider.send_reasoning is False and provider.usage_service == "byok"

    async def create(**kwargs):
        sent.append(kwargs)
        return Stream()

    monkeypatch.setattr(provider._client.responses, "create", create)
    with pytest.raises(ProviderError):
        await collect(provider)
    assert "reasoning" not in sent[0] and "reasoning.encrypted_content" not in sent[0]["include"]
    assert byok.build(byok.choose("openai", "gpt-6-luna", None, KEY, None)).send_reasoning is True


async def test_old_claude_models_skip_adaptive_thinking(monkeypatch):
    monkeypatch.setattr(byok.config, "AI_PROVIDER", "xai")
    old = byok.build(byok.choose("anthropic", "claude-3-5-haiku-latest", None, KEY, None))
    new = byok.build(byok.choose("anthropic", "claude-haiku-5-5", None, KEY, None))
    kwargs = {"model": "m", "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
              "max_output_tokens": 100, "reasoning": {"effort": "low"}, "tools": []}
    assert "thinking" not in (await old._client.create(**kwargs)).request
    assert (await new._client.create(**kwargs)).request["thinking"] == {"type": "adaptive"}
