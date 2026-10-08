"""Claude Messages API qua SDK thật với HTTP giả: không gọi mạng, không dùng khóa hoặc billing thật."""

import json
from types import SimpleNamespace

import pytest
import httpx2
from anthropic import AsyncAnthropic

import ai
from ai import agent, claude, models
from ai.base import ChatAttachment, ChatMessage, ProviderError
from core import config
from conftest import read_events
from test_agent_api import bearer, connect, events_of, login_as


def message_events(blocks, stop="end_turn", *, input_tokens=20, output_tokens=8):
    events = [{"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant",
        "model": "claude-haiku-5-5", "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": 0}}}]
    for index, block in enumerate(blocks):
        kind = block["type"]
        initial = dict(block)
        deltas = []
        if kind == "text":
            initial["text"] = ""
            initial.pop("citations", None)
            deltas.append({"type": "text_delta", "text": block["text"]})
            deltas.extend({"type": "citations_delta", "citation": citation} for citation in block.get("citations", []))
        elif kind == "thinking":
            initial.update(thinking="", signature="")
            deltas = [{"type": "thinking_delta", "thinking": block["thinking"]},
                      {"type": "signature_delta", "signature": block["signature"]}]
        elif kind in {"tool_use", "server_tool_use"}:
            initial["input"] = {}
            deltas = [{"type": "input_json_delta", "partial_json": json.dumps(block["input"])}]
        events.append({"type": "content_block_start", "index": index, "content_block": initial})
        events.extend({"type": "content_block_delta", "index": index, "delta": delta} for delta in deltas)
        events.append({"type": "content_block_stop", "index": index})
    events.extend([{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens}}, {"type": "message_stop"}])
    return events


def sdk_with_responses(*responses):
    calls = []
    closed = []

    class Body(httpx2.AsyncByteStream):
        def __init__(self, data):
            self.data = data

        async def __aiter__(self):
            for event in self.data:
                yield ("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode()

        async def aclose(self):
            closed.append(True)

    async def handler(request):
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "khoa-gia"
        calls.append(json.loads(request.content))
        response = responses[len(calls) - 1]
        if isinstance(response, int):
            return httpx2.Response(response, json={"type": "error", "error": {
                "type": "authentication_error" if response == 401 else "rate_limit_error",
                "message": "không được hiện khoa-gia"}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Body(response))

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    sdk = AsyncAnthropic(api_key="khoa-gia", max_retries=0, http_client=http)
    return sdk, calls, closed


USER = {"type": "message", "role": "user", "content": "chào"}
THINKING = {"type": "thinking", "thinking": "Đang cân nhắc", "signature": "chu-ky-nguyen-ven"}
TOOL = {"type": "tool_use", "id": "toolu_test", "name": "read_file", "input": {"path": "README.md"}}
TEXT = {"type": "text", "text": "Xong"}
SCHEMA = {"type": "function", "name": "read_file", "description": "Đọc tệp",
          "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}


@pytest.mark.parametrize("model", ["haiku", "sonnet"])
@pytest.mark.parametrize("effort", models.CLAUDE_EFFORTS)
async def test_agent_native_api_efforts_and_usage(monkeypatch, model, effort):
    sdk, calls, closed = sdk_with_responses(message_events([THINKING, TEXT]))
    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    monkeypatch.setattr(agent, "_claude_client", claude.ClaudeClient(sdk))
    async with sdk:
        events = [event async for event in agent.agent_step(instructions="chỉ dẫn", input_items=[USER],
            tools=[SCHEMA], effort=effort, model=model)]
    assert [event.kind for event in events] == ["thinking", "delta", "done"]
    assert events[-1].usage == {"input_tokens": 20, "output_tokens": 8}
    request = calls[0]
    assert request["model"] == models.MODELS[model].slug
    assert request["system"] == "chỉ dẫn" and request["messages"] == [{"role": "user", "content": [{"type": "text", "text": "chào"}]}]
    assert request["output_config"] == {"effort": effort}
    assert request["thinking"] == {"type": "adaptive"}
    assert request["max_tokens"] == config.ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS
    assert request["tools"][0]["input_schema"] == SCHEMA["parameters"]
    assert "reasoning" not in request and "store" not in request
    assert closed


async def test_tool_roundtrip_preserves_signature_and_no_duplicate_output():
    sdk, calls, closed = sdk_with_responses(message_events([THINKING, TOOL], "tool_use"), message_events([TEXT]))
    client = claude.ClaudeClient(sdk)
    kwargs = dict(model="claude-haiku-5-5", instructions="chỉ dẫn", input=[USER], tools=[SCHEMA],
                  reasoning={"effort": "max"}, max_output_tokens=128000)
    async with sdk:
        first = await client.create(**kwargs)
        events = [event async for event in first]
        output = events[-1].response.output
        assert output[0]["anthropic_content"] == [THINKING, TOOL]
        assert output[1] == {"type": "function_call", "call_id": "toolu_test", "name": "read_file",
                             "arguments": '{"path": "README.md"}'}
        kwargs["input"] = [USER, *output, {"type": "function_call_output", "call_id": "toolu_test", "output": "nội dung"}]
        second = await client.create(**kwargs)
        assert [event async for event in second][-1].type == "response.completed"
    assert calls[1]["messages"][1] == {"role": "assistant", "content": [THINKING, TOOL]}
    assert calls[1]["messages"][2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_test", "content": "nội dung"}]}
    assert len(calls[1]["messages"]) == 3 and len(closed) >= 2
    # Đổi model bỏ phần chữ ký nhưng giữ lời gọi để tiếp tục được với kết quả vừa chạy.
    other = claude.build_messages(kwargs["input"], "claude-sonnet-5-5")
    assert other[1]["content"] == [TOOL]


async def test_web_uses_shared_tool_loop_and_image_payload(monkeypatch):
    clock = {"type": "tool_use", "id": "toolu_time", "name": "get_current_datetime", "input": {"timezone": "UTC"}}
    sdk, calls, _ = sdk_with_responses(message_events([THINKING, clock], "tool_use"), message_events([TEXT]))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    monkeypatch.setattr(ai, "AI_PROVIDER", "xai")
    monkeypatch.setattr(ai, "_instances", {})
    provider = ai.get_provider("haiku")
    assert isinstance(provider, claude.ClaudeProvider)
    provider._client = claude.ClaudeClient(sdk)
    attachment = ChatAttachment("image", "ảnh.png", "image/png", data_url="data:image/png;base64,aGVsbG8=", number=1)
    async with sdk:
        chunks = [chunk async for chunk in provider.stream(system_prompt="chỉ dẫn", messages=[ChatMessage("user", "xem ảnh", (attachment,))],
            effort="xhigh", web_search="off")]
    assert [chunk for chunk in chunks if isinstance(chunk, str)] == ["Xong"]
    assert len(calls) == 2
    parts = calls[0]["messages"][0]["content"]
    assert parts[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}}
    result = calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_time"
    assert json.loads(result["content"])["timezone"] == "UTC"
    assert calls[1]["messages"][1]["content"] == [THINKING, clock]


SEARCH = {"type": "server_tool_use", "id": "srvtoolu_search", "name": "web_search", "input": {"query": "tin mới"}}
RESULT = {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_search", "content": [{"type": "web_search_result",
    "url": "https://example.com/news", "title": "Tin mới", "encrypted_content": "ket-qua-ma-hoa", "page_age": "hôm nay"}]}
CITATION = {"type": "web_search_result_location", "url": "https://example.com/news", "title": "Tin mới",
            "cited_text": "nội dung", "encrypted_index": "chi-muc"}


async def test_web_search_sources_and_pause_continuation(monkeypatch):
    sdk, calls, _ = sdk_with_responses(message_events([SEARCH, RESULT], "pause_turn"),
                                     message_events([{**TEXT, "citations": [CITATION]}]))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    provider = claude.ClaudeProvider("claude-haiku-5-5", "Haiku 5.5")
    provider._client = claude.ClaudeClient(sdk)
    async with sdk:
        chunks = [chunk async for chunk in provider.stream(system_prompt="chỉ dẫn", messages=[ChatMessage("user", "tra web")],
                                                           effort="max", web_search="on")]
    assert any(getattr(chunk, "kind", None) == "search" and chunk.text == "searching" for chunk in chunks)
    assert any(getattr(chunk, "kind", None) == "sources" and chunk.sources[0]["url"] == "https://example.com/news" for chunk in chunks)
    assert calls[0]["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    assert "tool_choice" not in calls[0]
    assert calls[1]["messages"][-1] == {"role": "assistant", "content": [SEARCH, RESULT]}


@pytest.mark.parametrize("status, phrase", [(401, "Khóa Claude"), (429, "giới hạn"), (529, "lỗi dịch vụ"), (400, "chưa nhận")])
async def test_errors_are_safe_and_no_automatic_billed_retry(status, phrase):
    sdk, calls, _ = sdk_with_responses(status)
    async with sdk:
        stream = await claude.ClaudeClient(sdk).create(model="claude-haiku-5-5", instructions="", input=[USER], tools=[],
                                                     max_output_tokens=32768, reasoning={"effort": "low"})
        with pytest.raises(ProviderError, match=phrase) as error:
            _ = [event async for event in stream]
    assert "khoa-gia" not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize("stop", ["max_tokens", "disconnect"])
async def test_truncated_stream_is_not_done(stop):
    events = message_events([TEXT], "max_tokens" if stop == "max_tokens" else "end_turn")
    if stop == "disconnect":
        events.pop()
    sdk, _, closed = sdk_with_responses(events)
    async with sdk:
        stream = await claude.ClaudeClient(sdk).create(model="claude-haiku-5-5", input=[USER], max_output_tokens=1024)
        if stop == "disconnect":
            with pytest.raises(ProviderError, match="bị ngắt"):
                _ = [event async for event in stream]
        else:
            result = [event async for event in stream]
            assert result[-1].type == "response.incomplete"
    assert closed


async def test_availability_and_efforts_on_web(client, monkeypatch):
    for effort in models.CLAUDE_EFFORTS:
        response = await client.post("/api/chat", json={"message": "chào", "model": "haiku", "effort": effort})
        events = await read_events(response)
        assert events[0]["effort"] == effort and events[-1]["type"] == "done"
    assert (await client.post("/api/chat", json={"message": "chào", "model": "haiku", "effort": "none"})).status_code == 400
    assert (await client.post("/api/chat", json={"message": "chào", "model": "sonnet"})).status_code == 400
    monkeypatch.setattr(config, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    assert "haiku" not in [m["key"] for m in (await client.get("/api/auth/me")).json()["user"]["models"]]
    assert (await client.post("/api/chat", json={"message": "chào", "model": "haiku"})).status_code == 503
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    assert "haiku" in [m["key"] for m in (await client.get("/api/auth/me")).json()["user"]["models"]]
    with pytest.raises(models.ModelUnavailable, match="đã đăng nhập"):
        models.resolve("anon:test", "haiku", "agent")


async def test_agent_sonnet_owner_gate_and_claude_step_costs(client, anon_client, monkeypatch):
    owner = await login_as(client, "discord")
    token = await connect(anon_client, client)

    async def step(model, effort):
        return await anon_client.post("/api/agent/step", headers=bearer(token), json={"input": [USER], "model": model, "effort": effort})

    assert (await step("sonnet", "low")).status_code == 403
    assert (await step("haiku", "none")).status_code == 400
    assert (await client.get("/api/agent/devices")).json()["steps_used"] == 0
    monkeypatch.setattr(config, "OWNER_ACCOUNTS", frozenset({owner}))
    for model, effort, used in [("haiku", "low", 1), ("haiku", "max", 3), ("sonnet", "medium", 5), ("sonnet", "xhigh", 9)]:
        response = await step(model, effort)
        assert response.status_code == 200 and events_of(response)[-1]["type"] == "done"
        assert (await client.get("/api/agent/devices")).json()["steps_used"] == used
