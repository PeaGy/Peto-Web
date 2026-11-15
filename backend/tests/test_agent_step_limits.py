"""Giới hạn một lần gọi model của Agent (15/11/2026): dừng theo khoảng im lặng chứ không theo tổng thời gian, có trần tổng,
lời gọi công cụ đang viết đi ngay về ứng dụng, và lỗi sau khi đã có phản hồi không làm ứng dụng tự gửi lại.

Ca thật dẫn tới thay đổi: Peto viết cả bản báo cáo 30 trang trong một lời gọi công cụ; cổng cắt mỗi lần sau đúng 300
giây, ứng dụng (pi-ai đọc chữ "timeout" thành lỗi đáng thử lại) gửi lại y nguyên 9 lần trong 45 phút.
"""

from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

import pytest

from ai import agent, claude
from ai.agent import AgentEvent
from core import config
from features.agent import api as agent_api
from features.agent import gateway
from test_agent_api import DEMO_TASK, connect, events_of
from test_agent_gateway import bearer, request, signed_in, sse_events, steps_used
from test_claude import SCHEMA, TOOL, USER, message_events, sdk_with_responses
from test_models import FakeStream

CALL = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "write",
        "arguments": '{"path": "bao-cao.py", "content": "print(1)"}'}
MESSAGE = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
           "content": [{"type": "output_text", "text": "Mình viết tệp."}]}


def pi_ai_retries(error: dict) -> bool:
    """Cách ứng dụng phân loại response.failed (llm-pi-ai/src/stream.ts): chữ "timeout", mã 5xx, mất kết nối là thử
    lại; còn lại thì không."""
    message = f"{error['code']}: {error['message']}"
    return bool(re.search(r"\b5\d\d\b|time(?:d)?\s*out|timeout|\b(?:network|connection|socket|fetch)\b|terminated",
                          message, re.IGNORECASE))


@pytest.fixture
def short_limits(monkeypatch):
    monkeypatch.setattr(config, "AGENT_STEP_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(config, "AGENT_STEP_MAX_SECONDS", 30.0)


# --- Lời gọi công cụ đi ngay về ứng dụng ------------------------------------------------------------------------------

async def test_a_tool_call_streams_its_arguments_as_the_model_writes_them(anon_client, client, monkeypatch):
    async def model(**kwargs):
        yield AgentEvent("delta", "Mình viết tệp.")
        yield AgentEvent("tool_start", item={"call_id": "call_1", "id": "fc_1", "name": "write"})
        yield AgentEvent("tool_delta", '{"path": "bao-cao.py", ', item={"call_id": "call_1"})
        yield AgentEvent("pulse")
        yield AgentEvent("tool_delta", '"content": "print(1)"}', item={"call_id": "call_1"})
        yield AgentEvent("done", output=(MESSAGE, CALL), usage={"input_tokens": 10, "output_tokens": 20})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    added = [event for event in events if event["type"] == "response.output_item.added"]
    assert [(event["output_index"], event["item"]["type"]) for event in added] == [(0, "message"), (1, "function_call")]
    # Ô mở ngay khi model bắt đầu viết, với đúng mã của item cuối (pi-ai đặt mã lời gọi lúc mở ô).
    assert added[1]["item"] == {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "write",
                                "arguments": ""}
    deltas = [event["delta"] for event in events if event["type"] == "response.function_call_arguments.delta"]
    assert deltas == ['{"path": "bao-cao.py", ', '"content": "print(1)"}']
    # Các đoạn tới trước khi xong: đoạn đầu nằm trước response.output_item.done của chữ.
    order = [event["type"] for event in events]
    assert order.index("response.function_call_arguments.delta") < order.index("response.output_item.done")
    arguments_done = next(event for event in events if event["type"] == "response.function_call_arguments.done")
    assert arguments_done["output_index"] == 1 and arguments_done["arguments"] == CALL["arguments"]
    done = {event["output_index"]: event["item"] for event in events if event["type"] == "response.output_item.done"}
    assert done == {0: MESSAGE, 1: CALL}
    assert events[-1]["type"] == "response.completed" and events[-1]["response"]["output"] == [MESSAGE, CALL]


async def test_a_claude_tool_call_without_an_item_id_keeps_its_call_id(anon_client, client, monkeypatch):
    call = {"type": "function_call", "call_id": "toolu_1", "name": "read", "arguments": '{"path": "README.md"}'}

    async def model(**kwargs):
        yield AgentEvent("tool_start", item={"call_id": "toolu_1", "name": "read"})
        yield AgentEvent("tool_delta", '{"path": "README.md"}', item={"call_id": "toolu_1"})
        yield AgentEvent("done", output=(call,), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    added = next(event for event in events if event["type"] == "response.output_item.added")
    assert added["item"] == {"type": "function_call", "call_id": "toolu_1", "name": "read", "arguments": ""}
    assert [event["item_id"] for event in events if event["type"].startswith("response.function_call_arguments")] == \
        ["toolu_1", "toolu_1"]
    assert events[-1]["response"]["output"] == [call]


# --- Dừng theo khoảng im lặng, không theo tổng thời gian ---------------------------------------------------------------

async def test_a_model_writing_steadily_past_the_silence_limit_is_not_cut(anon_client, client, monkeypatch, short_limits):
    async def model(**kwargs):
        yield AgentEvent("tool_start", item={"call_id": "call_1", "id": "fc_1", "name": "write"})
        for _ in range(12):  # 0,6 giây tổng, gấp ba khoảng im lặng cho phép
            await asyncio.sleep(0.05)
            yield AgentEvent("tool_delta", "x", item={"call_id": "call_1"})
        yield AgentEvent("done", output=(CALL,), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    assert events[-1]["type"] == "response.completed"


async def test_pulses_count_as_signs_of_life_but_produce_nothing(anon_client, client, monkeypatch, short_limits):
    async def model(**kwargs):
        for _ in range(8):  # chỉ có pulse trong 0,4 giây: dịch vụ AI đang soạn mà chưa có gì để hiện
            await asyncio.sleep(0.05)
            yield AgentEvent("pulse")
        yield AgentEvent("delta", "xong")
        yield AgentEvent("done", output=(MESSAGE,), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    assert events[-1]["type"] == "response.completed"
    assert [event["type"] for event in events].count("response.output_item.added") == 1


async def test_silence_before_any_output_is_a_retryable_timeout_and_refunds_the_step(
        anon_client, client, monkeypatch, short_limits):
    async def model(**kwargs):
        await asyncio.sleep(5)
        yield AgentEvent("delta", "không bao giờ tới")

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert response.status_code == 504
    error = response.json()["error"]
    assert error["code"] == "timeout" and response.headers["x-should-retry"] == "true"
    assert pi_ai_retries(error)
    assert await steps_used(client) == 0


async def test_silence_after_output_stops_without_making_the_app_resend_it(anon_client, client, monkeypatch, short_limits):
    async def model(**kwargs):
        yield AgentEvent("tool_start", item={"call_id": "call_1", "id": "fc_1", "name": "write"})
        yield AgentEvent("tool_delta", '{"path": ', item={"call_id": "call_1"})
        await asyncio.sleep(5)
        yield AgentEvent("done", output=(CALL,), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    failed = events[-1]
    assert failed["type"] == "response.failed"
    error = failed["response"]["error"]
    assert error["code"] == "stalled" and "làm tiếp" in error["message"]
    assert not pi_ai_retries(error)
    assert await steps_used(client) == 1


async def test_the_overall_cap_stops_a_busy_model_and_asks_to_split_the_work(anon_client, client, monkeypatch):
    monkeypatch.setattr(config, "AGENT_STEP_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(config, "AGENT_STEP_MAX_SECONDS", 0.3)

    async def model(**kwargs):
        yield AgentEvent("tool_start", item={"call_id": "call_1", "id": "fc_1", "name": "write"})
        while True:
            await asyncio.sleep(0.05)
            yield AgentEvent("tool_delta", "x", item={"call_id": "call_1"})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    error = events[-1]["response"]["error"]
    assert events[-1]["type"] == "response.failed"
    assert error["code"] == "step_too_long" and "chia việc" in error["message"]
    assert not pi_ai_retries(error)


# --- CLI (/api/agent/step) ---------------------------------------------------------------------------------------------

async def test_cli_steps_get_pings_for_pulses_and_never_see_tool_call_pieces(anon_client, client, monkeypatch):
    async def model(**kwargs):
        yield AgentEvent("pulse")
        yield AgentEvent("tool_start", item={"call_id": "call_1", "name": "write"})
        yield AgentEvent("tool_delta", "{}", item={"call_id": "call_1"})
        yield AgentEvent("done", output=(CALL,), usage={"input_tokens": 1, "output_tokens": 1})

    monkeypatch.setattr(agent_api, "agent_step", model)
    token = await connect(anon_client, client)
    response = await anon_client.post("/api/agent/step", headers=bearer(token), json={"input": [DEMO_TASK]})
    assert ": ping" in response.text
    assert [event["type"] for event in events_of(response)] == ["meta", "done"]


@pytest.mark.parametrize("first", [AgentEvent("delta", "Đang làm"),
                                   AgentEvent("tool_start", item={"call_id": "call_1", "name": "write"})])
async def test_cli_silence_after_output_is_not_marked_retryable(anon_client, client, monkeypatch, short_limits, first):
    async def model(**kwargs):
        yield first
        await asyncio.sleep(5)
        yield AgentEvent("done", output=(MESSAGE,), usage={})

    monkeypatch.setattr(agent_api, "agent_step", model)
    token = await connect(anon_client, client)
    events = events_of(await anon_client.post("/api/agent/step", headers=bearer(token), json={"input": [DEMO_TASK]}))
    assert events[-1]["type"] == "error" and "retryable" not in events[-1]
    assert "làm tiếp" in events[-1]["message"]


# --- Nguồn sự kiện: Responses (xAI, OpenAI) và Claude --------------------------------------------------------------------

async def test_responses_streams_report_tool_calls_as_they_are_written(monkeypatch):
    events = [
        SimpleNamespace(type="response.output_item.added",
                        item=SimpleNamespace(type="function_call", id="fc_1", call_id="call_1", name="write")),
        SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc_1", delta='{"path": '),
        SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc_1", delta='"a.py"}'),
        SimpleNamespace(type="response.function_call_arguments.delta", item_id="khac", delta="bỏ qua"),
        SimpleNamespace(type="response.completed", response=SimpleNamespace(status="completed", output=[CALL],
                                                                            usage=None)),
    ]

    async def create(**kwargs):
        return FakeStream(events)

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = [event async for event in agent._responses_step(fake, "xAI", "grok-4.7", 128000, "system", [], [], "low",
                                                              auth_message="auth", rate_message="rate")]
    assert [(event.kind, event.text, event.item) for event in result[:3]] == [
        ("tool_start", "", {"call_id": "call_1", "name": "write", "id": "fc_1"}),
        ("tool_delta", '{"path": ', {"call_id": "call_1"}),
        ("tool_delta", '"a.py"}', {"call_id": "call_1"}),
    ]
    assert result[-1].kind == "done" and result[-1].output == (CALL,)


async def test_responses_streams_pulse_while_nothing_is_shown(monkeypatch):
    monkeypatch.setattr(agent, "PULSE_SECONDS", 0.0)
    events = [SimpleNamespace(type="response.reasoning_text.delta", delta="ẩn"),
              SimpleNamespace(type="response.reasoning_text.delta", delta="ẩn"),
              SimpleNamespace(type="response.completed", response=SimpleNamespace(status="completed", output=[MESSAGE],
                                                                                  usage=None))]

    async def create(**kwargs):
        return FakeStream(events)

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    kinds = [event.kind async for event in agent._responses_step(fake, "xAI", "grok-4.7", 128000, "system", [], [],
                                                                 "low", auth_message="auth", rate_message="rate")]
    assert kinds.count("pulse") >= 2 and kinds[-1] == "done"


async def test_claude_tool_calls_stream_their_json_with_the_tool_use_id(monkeypatch):
    sdk, calls, _ = sdk_with_responses(message_events([TOOL], "tool_use"))
    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "khoa-gia")
    monkeypatch.setattr(agent, "_claude_client", claude.ClaudeClient(sdk))
    async with sdk:
        events = [event async for event in agent.agent_step(instructions="chỉ dẫn", input_items=[USER],
                                                            tools=[SCHEMA], effort="low", model="haiku")]
    start = next(event for event in events if event.kind == "tool_start")
    assert start.item == {"call_id": "toolu_test", "name": "read_file"}
    pieces = "".join(event.text for event in events if event.kind == "tool_delta")
    assert json.loads(pieces) == TOOL["input"]
    final = events[-1].output[-1]
    assert final["call_id"] == "toolu_test" and json.loads(final["arguments"]) == TOOL["input"]


# --- Trần đầu ra ---------------------------------------------------------------------------------------------------------

async def test_agent_calls_ask_for_the_big_output_cap_and_the_app_sees_it(anon_client, client, monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return FakeStream([SimpleNamespace(type="response.completed", response=SimpleNamespace(
            status="completed", output=[MESSAGE], usage=None))])

    async def fake_xai():
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AI_PROVIDER", "xai")
    monkeypatch.setattr(agent, "xai_client", fake_xai)
    _ = [event async for event in agent.agent_step(instructions="s", input_items=[USER], tools=[], model="peto")]
    assert calls[0]["max_output_tokens"] == config.XAI_AGENT_MAX_OUTPUT_TOKENS == 128000
    token = await signed_in(anon_client, client)
    listing = (await anon_client.get("/api/agent/v1/models", headers=bearer(token))).json()
    assert next(model for model in listing["data"] if model["id"] == "peto")["max_output_tokens"] == 128000
