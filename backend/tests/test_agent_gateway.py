"""Cổng /api/agent/v1 kiểu OpenAI Responses cho ứng dụng desktop Peto Agent (bản fork DeepSeek Harness)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import uuid

import pytest
from PIL import Image

from ai.agent import AgentEvent
from ai.base import ProviderError
from core.config import SESSION_COOKIE, owner_key
from features.accounts import auth
from features.agent import api as agent_api
from features.agent import gateway, gateway_images
import storage as db


@pytest.fixture(autouse=True)
def clear_pending_codes():
    agent_api.pending_codes.clear()
    yield
    agent_api.pending_codes.clear()


async def signed_in(cli, web) -> str:
    """Tài khoản mới tinh và token thiết bị của nó, để số bước không dính sang test khác."""
    owner = owner_key("google", uuid.uuid4().hex)
    await db.upsert_user(owner=owner, provider="google", username="nguoi_moi", display_name="Người Mới", avatar_url="")
    web.cookies.set(SESSION_COOKIE, auth._sign(owner))
    started = (await cli.post("/api/agent/device/start", json={"name": "Peto Harness"})).json()
    assert (await web.post(f"/api/agent/device/{started['user_code']}", json={"allow": True})).status_code == 200
    issued = await cli.post("/api/agent/device/token", json={"device_code": started["device_code"]})
    return issued.json()["token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sse_events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def request(**extra) -> dict:
    return {"model": "peto", "stream": True,
            "input": [{"role": "developer", "content": "You are the app's agent."},
                      {"role": "user", "content": [{"type": "input_text", "text": "Xin chào"}]}], **extra}


async def steps_used(web) -> int:
    return (await web.get("/api/agent/devices")).json()["steps_used"]


async def test_models_need_a_device_token_and_list_the_accounts_models(anon_client, client):
    denied = await anon_client.get("/api/agent/v1/models")
    assert denied.status_code == 401
    assert denied.json()["error"]["type"] == "authentication_error"

    token = await signed_in(anon_client, client)
    listing = (await anon_client.get("/api/agent/v1/models", headers=bearer(token))).json()
    assert listing["object"] == "list"
    peto = next(model for model in listing["data"] if model["id"] == "peto")
    assert peto["owned_by"] == "peto" and peto["display_name"]
    assert peto["context_window"] > 0 and peto["max_output_tokens"] > 0
    assert peto["reasoning_efforts"] and set(peto["reasoning_efforts"]) <= {"none", "low", "medium", "high", "xhigh", "max"}


async def test_a_reply_streams_as_openai_responses_events_and_costs_a_step(anon_client, client):
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert response.status_code == 200
    events = sse_events(response)
    types = [event["type"] for event in events]
    assert types[:2] == ["response.created", "response.in_progress"]
    assert types[-1] == "response.completed"
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    text = "".join(event["delta"] for event in events if event["type"] == "response.output_text.delta")
    done = [event for event in events if event["type"] == "response.output_item.done"]
    message = next(event for event in done if event["item"]["type"] == "message")
    assert text == message["item"]["content"][0]["text"]
    added = next(event for event in events if event["type"] == "response.output_item.added"
                 and event["item"]["type"] == "message")
    assert added["output_index"] == message["output_index"]
    completed = events[-1]["response"]
    assert completed["status"] == "completed" and completed["model"] == "peto"
    assert completed["usage"]["total_tokens"] == completed["usage"]["input_tokens"] + completed["usage"]["output_tokens"]
    assert await steps_used(client) == 1


async def test_the_apps_instructions_tools_and_choices_reach_the_model_unchanged(anon_client, client, monkeypatch):
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("delta", "ok")
        yield AgentEvent("done", output=({"type": "message", "role": "assistant",
                                           "content": [{"type": "output_text", "text": "ok"}]},),
                         usage={"input_tokens": 10, "output_tokens": 1})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    tool = {"type": "function", "name": "read", "description": "Đọc tệp", "strict": False,
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}
    body = request(tools=[tool], tool_choice="auto", reasoning={"effort": "minimal", "summary": "auto"},
                   max_output_tokens=2048, prompt_cache_key="session-1", store=False)
    body["input"].append({"role": "system", "content": "Workspace changed."})
    assert (await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)).status_code == 200
    assert seen["instructions"] == "You are the app's agent."
    assert seen["tools"] == [tool]
    assert seen["tool_choice"] == "auto"
    assert seen["web_search"] is False
    assert seen["max_output_tokens"] == 2048
    # pi-ai có mức "minimal", Peto thì không: làm tròn lên mức gần nhất model hỗ trợ.
    assert seen["effort"] == "low"
    assert seen["input_items"][-1] == {"role": "user", "content": [
        {"type": "input_text", "text": gateway.SYSTEM_UPDATE + "Workspace changed."}]}


async def test_reasoning_text_and_tool_calls_get_their_own_output_slots(anon_client, client, monkeypatch):
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque", "summary": []}
    message = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": "Đọc tệp trước."}]}
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "read",
            "arguments": '{"path": "README.md"}'}

    async def model(**kwargs):
        yield AgentEvent("thinking", "Xem tệp nào")
        yield AgentEvent("delta", "Đọc tệp trước.")
        yield AgentEvent("done", output=(reasoning, message, call),
                         usage={"input_tokens": 120, "output_tokens": 30, "cached_tokens": 100})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    events = sse_events(await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request()))
    added = {event["item"]["type"]: event["output_index"] for event in events
             if event["type"] == "response.output_item.added"}
    assert added == {"reasoning": 0, "message": 1, "function_call": 2}
    done = {event["output_index"]: event["item"] for event in events if event["type"] == "response.output_item.done"}
    assert done == {0: reasoning, 1: message, 2: call}
    arguments = next(event for event in events if event["type"] == "response.function_call_arguments.done")
    assert arguments["output_index"] == 2 and arguments["arguments"] == call["arguments"]
    completed = events[-1]["response"]
    assert completed["output"] == [reasoning, message, call]
    assert completed["usage"]["input_tokens_details"]["cached_tokens"] == 100


async def test_reasoning_moves_to_the_front_of_each_model_turn(anon_client, client, monkeypatch):
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    user = {"role": "user", "content": "Sửa lỗi"}
    text = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Xem đã."}]}
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque", "summary": []}
    call = {"type": "function_call", "call_id": "call_1", "name": "read", "arguments": "{}"}
    result = {"type": "function_call_output", "call_id": "call_1", "output": "nội dung"}
    body = {"model": "peto", "stream": True, "input": [user, text, reasoning, call, result]}
    await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)
    assert seen["input_items"] == [user, reasoning, text, call, result]


async def test_the_gateways_own_empty_items_are_not_sent_back_to_the_model(anon_client, client, monkeypatch):
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    user = {"role": "user", "content": "Tiếp đi"}
    placeholder = {"type": "reasoning", "id": gateway.PLACEHOLDER_REASONING + "abc", "summary": []}
    empty = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ""}]}
    real = {"type": "reasoning", "id": gateway.PLACEHOLDER_REASONING + "def", "encrypted_content": "opaque"}
    body = {"model": "peto", "stream": True, "input": [placeholder, empty, real, user]}
    await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)
    assert seen["input_items"] == [real, user]


async def test_long_sessions_go_past_the_clis_300_item_limit(anon_client, client, monkeypatch):
    """Bản desktop tự tóm tắt theo token chứ không theo số mục, nên cổng không được chặn phiên ở mốc 300 của CLI."""
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    calls = []
    for n in range(400):
        calls += [{"type": "function_call", "call_id": f"call_{n}", "name": "read", "arguments": "{}"},
                  {"type": "function_call_output", "call_id": f"call_{n}", "output": "ok"}]
    body = {"model": "peto", "stream": True, "input": [{"role": "user", "content": "Làm bài"}, *calls]}
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)
    assert response.status_code == 200
    assert len(seen["input_items"]) == 801 > agent_api.MAX_ITEMS


def png_url() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def screenshots(count: int, url: str) -> list[dict]:
    """Một tin người dùng rồi ``count`` lần gọi công cụ, mỗi kết quả là một ảnh, như ảnh chụp màn hình của Peto Agent."""
    items = [{"role": "user", "content": "Chụp màn hình giúp mình"}]
    for n in range(count):
        items += [{"type": "function_call", "call_id": f"call_{n}", "name": "screenshot", "arguments": "{}"},
                  {"type": "function_call_output", "call_id": f"call_{n}",
                   "output": [{"type": "input_image", "detail": "auto", "image_url": url}]}]
    return items


async def test_tool_result_images_reach_the_model_after_the_results(anon_client, client, monkeypatch):
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    shot = png_url()
    body = {"model": "peto", "stream": True, "input": screenshots(1, shot)}
    assert (await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)).status_code == 200
    items = seen["input_items"]
    assert items[2] == {"type": "function_call_output", "call_id": "call_0", "output": gateway_images.IMAGE_ONLY_OUTPUT}
    assert items[3]["role"] == "user"
    assert items[3]["content"][-1]["image_url"] == shot


async def test_up_to_fifty_images_count_tool_results_too_and_no_step_is_taken_beyond(anon_client, client, monkeypatch):
    async def model(**kwargs):
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    shot = png_url()
    fifty = {"model": "peto", "stream": True, "input": screenshots(gateway.MAX_IMAGES, shot)}
    assert (await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=fifty)).status_code == 200
    used = await steps_used(client)
    more = {"model": "peto", "stream": True, "input": screenshots(gateway.MAX_IMAGES + 1, shot)}
    refused = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=more)
    assert refused.status_code == 400
    assert str(gateway.MAX_IMAGES) in refused.json()["error"]["message"]
    assert await steps_used(client) == used


@pytest.mark.parametrize("part", [
    {"type": "input_image", "image_url": "https://example.com/a.png"},
    {"type": "input_file", "file_data": "abc"},
])
async def test_tool_results_carry_only_text_and_data_url_images(anon_client, client, part):
    token = await signed_in(anon_client, client)
    items = screenshots(1, png_url())
    items[2]["output"] = [part]
    refused = await anon_client.post("/api/agent/v1/responses", headers=bearer(token),
                                     json={"model": "peto", "stream": True, "input": items})
    assert refused.status_code == 400
    assert await steps_used(client) == 0


async def test_webp_images_reach_peto_as_png(anon_client, client, monkeypatch):
    seen = {}

    async def model(**kwargs):
        seen.update(kwargs)
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(buffer, "WEBP")
    webp = "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    user = {"role": "user", "content": [{"type": "input_image", "image_url": webp}]}
    await anon_client.post("/api/agent/v1/responses", headers=bearer(token),
                           json={"model": "peto", "stream": True, "input": [user]})
    assert seen["input_items"][0]["content"][0]["image_url"].startswith("data:image/png;base64,")


async def test_the_gateway_takes_bigger_requests_than_the_clis_step(anon_client, client, monkeypatch):
    async def model(**kwargs):
        yield AgentEvent("done", output=(), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    monkeypatch.setattr(agent_api, "AGENT_MAX_REQUEST_BYTES", 2048)
    token = await signed_in(anon_client, client)
    body = request()
    body["input"][1]["content"][0]["text"] = "x" * 4096
    assert (await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)).status_code == 200
    monkeypatch.setattr(gateway, "MAX_REQUEST_BYTES", 2048)
    refused = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=body)
    assert refused.status_code == 413
    assert refused.json()["error"]["message"] == gateway.TOO_LARGE


async def test_too_many_items_asks_for_a_new_session_without_taking_a_step(anon_client, client, monkeypatch):
    monkeypatch.setattr(gateway, "MAX_ITEMS", 2)
    token = await signed_in(anon_client, client)
    turns = [{"role": "user", "content": f"Tin {n}"} for n in range(3)]
    refused = await anon_client.post("/api/agent/v1/responses", headers=bearer(token),
                                     json={"model": "peto", "stream": True, "input": turns})
    assert refused.status_code == 400
    error = refused.json()["error"]
    assert error["code"] == "context_length_exceeded"
    assert "mở phiên mới" in error["message"]
    assert await steps_used(client) == 0


async def test_daily_quota_answers_429_insufficient_quota_without_retry(anon_client, client, monkeypatch):
    monkeypatch.setattr(gateway, "AGENT_DAILY_STEPS", 1)
    token = await signed_in(anon_client, client)
    assert (await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())).status_code == 200
    blocked = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "insufficient_quota"
    assert blocked.headers["x-should-retry"] == "false"


@pytest.mark.parametrize(("failure", "status", "code", "retry"), [
    (ProviderError("tạm lỗi", retryable=True), 503, "server_error", "true"),
    (ProviderError("lỗi hẳn"), 502, "provider_error", "false"),
    (ProviderError("quá dài", code="context_overflow"), 400, "context_length_exceeded", "false"),
])
async def test_failures_before_any_output_are_http_errors_and_refund_the_step(
        anon_client, client, monkeypatch, failure, status, code, retry):
    async def model(**kwargs):
        raise failure
        yield  # pragma: no cover - biến hàm thành async generator

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.headers["x-should-retry"] == retry
    assert await steps_used(client) == 0


async def test_a_failure_after_output_ends_the_stream_with_response_failed(anon_client, client, monkeypatch):
    async def model(**kwargs):
        yield AgentEvent("delta", "Đang làm")
        raise ProviderError("đứt giữa chừng", retryable=True)

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert response.status_code == 200
    events = sse_events(response)
    assert events[-1]["type"] == "response.failed"
    assert events[-1]["response"]["error"]["code"] == "server_error"
    # Đã có phản hồi nên bước không được hoàn.
    assert await steps_used(client) == 1


async def test_a_slow_model_opens_the_stream_and_keeps_it_alive(anon_client, client, monkeypatch):
    monkeypatch.setattr(gateway, "FIRST_EVENT_SECONDS", 0.05)
    monkeypatch.setattr(gateway, "PING_SECONDS", 0.05)

    async def model(**kwargs):
        await asyncio.sleep(0.3)
        yield AgentEvent("delta", "xong")
        yield AgentEvent("done", output=({"type": "message", "role": "assistant",
                                           "content": [{"type": "output_text", "text": "xong"}]},), usage={})

    monkeypatch.setattr(gateway, "agent_step", model)
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request())
    assert response.status_code == 200
    assert ": ping" in response.text
    assert sse_events(response)[-1]["type"] == "response.completed"


@pytest.mark.parametrize(("change", "status", "code"), [
    ({"stream": False}, 400, "stream_required"),
    ({"model": "khong-co"}, 404, "model_not_found"),
    ({"tools": [{"type": "web_search"}]}, 400, None),
    ({"tool_choice": {"type": "function", "name": "read"}}, 400, None),
    ({"input": [{"type": "item_reference", "id": "x"}]}, 400, None),
    ({"input": [{"role": "developer", "content": "Chỉ có chỉ dẫn"}]}, 400, None),
])
async def test_bad_requests_are_refused_before_spending_a_step(anon_client, client, change, status, code):
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/responses", headers=bearer(token), json=request(**change))
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert await steps_used(client) == 0
