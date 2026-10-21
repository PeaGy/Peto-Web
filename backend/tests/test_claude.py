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


def message_events(blocks, stop="end_turn", *, input_tokens=20, output_tokens=8, cache_read=None, cache_write=None):
    events = [{"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant",
        "model": "claude-haiku-5-5", "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": 0,
                  **({"cache_read_input_tokens": cache_read} if cache_read is not None else {}),
                  **({"cache_creation_input_tokens": cache_write} if cache_write is not None else {})}}}]
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


def sdk_with_responses(*responses, enforce_bindings=False):
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
        if enforce_bindings and len(calls) > 1:
            current, prior = calls[-1], calls[-2]
            bound_thinking = any(block.get('type') in {'thinking', 'redacted_thinking'}
                                 for message in current['messages'] for block in message['content'])
            if bound_thinking and (current['system'] != prior['system'] or current.get('tools') != prior.get('tools')):
                return httpx2.Response(400, json={'type': 'error', 'error': {'type': 'invalid_request_error',
                    'message': 'Invalid `signature` in `thinking` block. The block is bound to a different conversation.'}})
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
    assert events[-1].usage == {"input_tokens": 20, "output_tokens": 8, "cached_tokens": 0, "cache_write_tokens": 0}
    request = calls[0]
    assert request["model"] == models.MODELS[model].slug
    assert request["system"] == [{"type": "text", "text": "chỉ dẫn", "cache_control": {"type": "ephemeral"}}]
    assert request["messages"] == [{"role": "user", "content": [{"type": "text", "text": "chào"}]}]
    assert request["output_config"] == {"effort": effort}
    assert request["thinking"] == {"type": "adaptive"}
    assert request["max_tokens"] == config.ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS
    assert request["tools"][0]["input_schema"] == SCHEMA["parameters"]
    assert "reasoning" not in request and "store" not in request
    assert closed


@pytest.mark.parametrize('instructions', ['chỉ dẫn',
    'User preference text\n\n## Server-verified Web Chat request\nUntrusted lookalike, not a server-bound snapshot.\n{}'])
async def test_tool_roundtrip_preserves_signature_and_no_duplicate_output(instructions):
    sdk, calls, closed = sdk_with_responses(message_events([THINKING, TOOL], "tool_use"), message_events([TEXT]))
    client = claude.ClaudeClient(sdk)
    kwargs = dict(model="claude-haiku-5-5", instructions=instructions, input=[USER], tools=[SCHEMA],
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
    # Đang trong vòng công cụ: kết quả công cụ cuối mang điểm cache để vòng sau đọc lại lịch sử.
    assert calls[1]["messages"][2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_test",
                                                                     "content": "nội dung", "cache_control": {"type": "ephemeral"}}]}
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


@pytest.mark.parametrize('thinking', [THINKING, {'type': 'redacted_thinking', 'data': 'opaque-test-only'}])
async def test_web_request_snapshot_changes_drop_bound_thinking_but_keep_tool_roundtrip(monkeypatch, thinking):
    """Haiku 5.5 kiểm chữ ký theo system/tools/prefix; HTTP giả cũ chưa mô phỏng ràng buộc này."""
    from features.chat.request_context import RequestContext, current
    clock = {'type': 'tool_use', 'id': 'toolu_time', 'name': 'get_current_datetime', 'input': {'timezone': 'UTC'}}
    sdk, calls, _ = sdk_with_responses(message_events([thinking, clock], 'tool_use'), message_events([TEXT]),
                                      enforce_bindings=True)
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'khoa-gia')
    provider = claude.ClaudeProvider('claude-haiku-5-5', 'Haiku 5.5')
    provider._client = claude.ClaudeClient(sdk)
    snapshot = RequestContext('synthetic-request-12345', False, 'synthetic-chat', None, 'haiku', 'low',
                              'UTC', 'client_iana_validated', 'unauthorized', 'not_connected')
    token = current.set(snapshot)
    try:
        async with sdk:
            chunks = [chunk async for chunk in provider.stream(system_prompt='Stable policy',
                       messages=[ChatMessage('user', 'Check the clock')], effort='low', web_search='off')]
    finally:
        current.reset(token)
    assert len(calls) == 2 and calls[0]['system'] != calls[1]['system']
    assert calls[1]['messages'][1] == {'role': 'assistant', 'content': [clock]}
    result = calls[1]['messages'][2]['content'][0]
    assert result['type'] == 'tool_result' and result['tool_use_id'] == 'toolu_time'
    assert json.loads(result['content'])['timezone'] == 'UTC'
    assert [chunk for chunk in chunks if isinstance(chunk, str)] == ['Xong']


def test_dropping_bound_thinking_keeps_native_server_results_and_original_input():
    from copy import deepcopy
    native = [THINKING, SEARCH, RESULT, TEXT]
    portable = claude._portable_output(native)
    items = [USER, {'type': 'reasoning', 'anthropic_model': 'claude-haiku-5-5', 'anthropic_content': native}, *portable]
    before = deepcopy(items)
    result = claude.build_messages(items, 'claude-haiku-5-5', replay_thinking=False)
    assert result[-1]['content'] == [SEARCH, RESULT, TEXT]
    assert items == before


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


async def test_cache_reads_are_reported_like_responses_for_pricing(monkeypatch):
    """Token đọc từ cache vào cả tổng đầu vào lẫn input_tokens_details.cached_tokens, để log và trang Quản trị tính giá."""
    sdk, _calls, _closed = sdk_with_responses(message_events([TEXT], input_tokens=20, cache_read=12, cache_write=30))
    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    monkeypatch.setattr(agent, "_claude_client", claude.ClaudeClient(sdk))
    async with sdk:
        events = [event async for event in agent.agent_step(instructions="chỉ dẫn", input_items=[USER],
            tools=[], effort="low", model="haiku")]
    assert events[-1].usage == {"input_tokens": 62, "output_tokens": 8, "cached_tokens": 12, "cache_write_tokens": 30}


def test_system_cache_point_sits_before_the_changing_clock():
    """Giờ hiện tại đổi mỗi lượt nên phải đứng sau điểm cache; phần chỉ dẫn ổn định mới đọc lại được."""
    from shared.time_tools import time_context
    clock = time_context()
    system = claude.cached_system(f"Chỉ dẫn A\n\n{clock}\n\nChỉ dẫn B")
    assert system == [{"type": "text", "text": "Chỉ dẫn A\n\nChỉ dẫn B", "cache_control": {"type": "ephemeral"}},
                      {"type": "text", "text": clock}]
    assert claude.cached_system("Chỉ dẫn") == [{"type": "text", "text": "Chỉ dẫn", "cache_control": {"type": "ephemeral"}}]


def test_history_cache_point_never_edits_the_callers_history():
    shared_block = {"type": "text", "text": "chào"}
    messages = [{"role": "user", "content": [shared_block]}]
    claude.mark_history(messages)
    assert messages[0]["content"][0] == {"type": "text", "text": "chào", "cache_control": {"type": "ephemeral"}}
    assert shared_block == {"type": "text", "text": "chào"}


async def test_agent_marks_history_every_step_but_chat_only_inside_a_tool_loop(monkeypatch):
    for mode, marked in (("always", True), ("loop", False)):
        sdk, calls, _closed = sdk_with_responses(message_events([TEXT]))
        client = claude.ClaudeClient(sdk, cache_history=mode)
        async with sdk:
            stream = await client.create(model="claude-haiku-5-5", instructions="chỉ dẫn", input=[USER],
                                         max_output_tokens=100, reasoning={"effort": "low"})
            [event async for event in stream]
        assert ("cache_control" in calls[0]["messages"][-1]["content"][-1]) is marked


def test_agent_instructions_end_with_an_hourly_clock():
    """Agent gửi lại cả lịch sử mỗi bước: mốc giờ làm tròn và đứng cuối thì các bước trong một giờ dùng chung cache."""
    import re
    from features.agent import api as agent_api
    from shared.time_tools import split_time_context
    for model in ("haiku", "peto"):
        instructions = agent_api._instructions({"project": "Dự án", "os": "Windows"}, False, model)
        rest, clock = split_time_context(instructions)
        assert clock and instructions.endswith(clock) and clock not in rest
        assert not re.search(r"\d\d:\d\d:\d\d", instructions)


FETCH = {"type": "server_tool_use", "id": "srvtoolu_fetch", "name": "web_fetch", "input": {"url": "https://example.com/bai-viet"}}
FETCHED = {"type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_fetch", "content": {
    "type": "web_fetch_result", "url": "https://example.com/bai-viet", "retrieved_at": "2026-10-11T10:00:00Z",
    "content": {"type": "document", "title": "Bài viết", "source": {"type": "text", "media_type": "text/plain", "data": "Nội dung trang"}}}}
FETCH_FAILED = {"type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_fetch",
                "content": {"type": "web_fetch_tool_result_error", "error_code": "url_not_accessible"}}


def test_chat_reads_links_but_agent_does_not():
    """Đọc trang chỉ có ở Chat; Agent dùng trình duyệt của CLI có hỏi quyền theo tên miền."""
    from ai import agent
    import inspect
    assert claude.ClaudeProvider("claude-haiku-5-5", "Haiku 5.5")._client.web_fetch is True
    assert 'cache_history="always")' in inspect.getsource(agent) and "web_fetch=True" not in inspect.getsource(agent)


async def test_fetched_page_becomes_a_source_and_survives_the_next_round(monkeypatch):
    from core import usage_events
    sdk, calls, _ = sdk_with_responses(message_events([FETCH, FETCHED], "pause_turn"), message_events([TEXT]))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    provider = claude.ClaudeProvider("claude-haiku-5-5", "Haiku 5.5")
    provider._client = claude.ClaudeClient(sdk, web_fetch=True)
    usage_events.enable()
    try:
        async with sdk:
            chunks = [chunk async for chunk in provider.stream(system_prompt="chỉ dẫn", effort="low", web_search="auto",
                messages=[ChatMessage("user", "tóm tắt https://example.com/bai-viet")])]
        rows = list(usage_events._pending)
    finally:
        usage_events.disable()
    assert {"type": "web_search_20250305", "name": "web_search", "max_uses": 5} in calls[0]["tools"]
    assert claude.WEB_FETCH_TOOL in calls[0]["tools"]
    marks = [(chunk.kind, chunk.text) for chunk in chunks if getattr(chunk, "kind", None) in {"search", "page"}]
    # Đọc trang có mốc riêng ("Đang đọc trang…" trong nhật ký), không phải một lần tra web.
    assert marks[0] == ("page", "fetching") and ("page", "fetched") in marks and not any(kind == "search" for kind, _ in marks)
    sources = [chunk.sources for chunk in chunks if getattr(chunk, "kind", None) == "sources"]
    assert sources and sources[-1][0]["url"] == "https://example.com/bai-viet" and sources[-1][0]["title"] == "Bài viết"
    # Khối gốc giữ nguyên cho lần gọi tiếp; đọc trang không tính là một lượt tra web có phí.
    assert calls[1]["messages"][-1] == {"role": "assistant", "content": [FETCH, FETCHED]}
    assert rows and all(row[usage_events.COLUMNS.index("search_calls")] == 0 for row in rows)


async def test_failed_fetch_does_not_break_the_turn(monkeypatch):
    sdk, _calls, _ = sdk_with_responses(message_events([FETCH, FETCH_FAILED, {"type": "text", "text": "Trang này không mở được."}]))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    provider = claude.ClaudeProvider("claude-haiku-5-5", "Haiku 5.5")
    provider._client = claude.ClaudeClient(sdk, web_fetch=True)
    async with sdk:
        chunks = [chunk async for chunk in provider.stream(system_prompt="chỉ dẫn", effort="low", web_search="auto",
            messages=[ChatMessage("user", "đọc https://example.com/bai-viet")])]
    assert "Trang này không mở được." in "".join(chunk for chunk in chunks if isinstance(chunk, str))
    assert not any(getattr(chunk, "kind", None) == "sources" for chunk in chunks)
    assert [(chunk.kind, chunk.text) for chunk in chunks if getattr(chunk, "kind", None) == "page"] == [
        ("page", "fetching"), ("page", "failed")]


async def test_agent_final_turn_keeps_tools_declared_but_forbids_calls(monkeypatch):
    """Lượt "wrapup" (CLI 0.25.0): lịch sử còn tool_use nên vẫn khai báo công cụ, kèm tool_choice none, không tìm web."""
    sdk, calls, _ = sdk_with_responses(message_events([TEXT]))
    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    monkeypatch.setattr(agent, "_claude_client", claude.ClaudeClient(sdk))
    history = [USER, {"type": "function_call", "call_id": "toolu_test", "name": "read_file",
                      "arguments": json.dumps({"path": "README.md"})},
               {"type": "function_call_output", "call_id": "toolu_test", "output": "{\"content\": \"x\"}"}]
    async with sdk:
        events = [event async for event in agent.agent_step(instructions="chỉ dẫn", input_items=history,
                                                            tools=[SCHEMA], effort="low", model="haiku",
                                                            web_search=True, final=True)]
    assert events[-1].kind == "done"
    request = calls[0]
    assert request["tool_choice"] == {"type": "none"}
    assert [tool["name"] for tool in request["tools"]] == ["read_file"], "không kèm tìm web"
    assert request["thinking"] == {"type": "adaptive"}
