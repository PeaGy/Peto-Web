"""Cổng Chat Completions cho bộ não AIRI (``/api/companion/v1``): cookie phiên, công cụ do trình duyệt chạy, ảnh data
URL, số đo cho trang Quản trị, hủy khi trình duyệt ngắt, luật cố định luôn nối vào, không lưu gì."""

from __future__ import annotations

import asyncio
import base64
import io
import json

import pytest
from PIL import Image

import storage as db
from ai import agent as ai_agent
from ai.base import ProviderError
from conftest import TEST_OWNER
from core import config, usage_events
from core.config import SESSION_COOKIE
from core.rate_limit import Admission, AdmissionDenied
from features.accounts import auth
from features.companion import airi_gateway, airi_request
from main import app
from prompts import COMPANION_CARD_RULE

URL = "/api/companion/v1/chat/completions"
MESSAGES = [
    {"role": "system", "content": "You are a cheerful test character."},
    {"role": "user", "content": "chào bạn"},
]
WEATHER = {"type": "function", "function": {
    "name": "get_weather", "description": "Thời tiết của một thành phố.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "days": {"type": "integer"}},
                   "required": ["city", "days"]}}}


def _png(color: str = "red") -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


async def _lines(response) -> list:
    items = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            payload = line[6:]
            items.append(payload if payload == "[DONE]" else json.loads(payload))
        elif line.startswith(":"):
            items.append(line)
    return items


async def _stream(client, body: dict) -> tuple[int, list]:
    async with client.stream("POST", URL, json={"stream": True, **body}) as response:
        if response.status_code != 200:
            await response.aread()
            return response.status_code, [response.json()]
        assert response.headers["content-type"].startswith("text/event-stream")
        return 200, await _lines(response)


def _assemble(items: list) -> dict:
    """Ghép chunk như ``@xsai/stream-text`` 0.5.1: chữ nối lại, tool_calls theo index, đối số nối từng đoạn."""
    text, calls, finish, usage = "", [], None, None
    for item in items:
        if not isinstance(item, dict) or "choices" not in item:
            continue
        usage = item.get("usage") or usage
        if not item["choices"]:
            continue
        choice = item["choices"][0]
        finish = choice.get("finish_reason") or finish
        delta = choice["delta"]
        if not delta.get("tool_calls"):
            text += delta.get("content") or ""
            continue
        for call in delta["tool_calls"]:
            index = call["index"]
            if index >= len(calls):
                calls.append({**call, "function": {**call["function"],
                                                   "arguments": call["function"].get("arguments") or ""}})
            else:
                calls[index]["function"]["arguments"] += call["function"]["arguments"]
    return {"text": text, "tool_calls": calls, "finish": finish, "usage": usage}


@pytest.fixture(autouse=True)
def airi_enabled(tmp_path, monkeypatch):
    """Cổng chỉ bật khi đặt PETO_AIRI_DIR; các test ở đây coi như trang AIRI đã được phục vụ."""
    monkeypatch.setattr(config, "AIRI_DIR", tmp_path)


@pytest.fixture
def spy(monkeypatch):
    """Ghi lại đối số gọi ``agent_step`` (vá tên trong module cổng, gọi tiếp bản thật với provider giả)."""
    seen: list[dict] = []
    original = ai_agent.agent_step

    def step(**kwargs):
        seen.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(airi_gateway, "agent_step", step)
    return seen


@pytest.fixture
def fake_step(monkeypatch):
    """Thay ``agent_step`` bằng một hàm sinh tùy ý cho các ca thời gian và lỗi giữa chừng."""

    def install(factory):
        monkeypatch.setattr(airi_gateway, "agent_step", lambda **kwargs: factory())

    return install


@pytest.fixture
def recorder():
    usage_events.disable()
    usage_events.enable()
    yield usage_events
    usage_events.disable()


# --- Bật/tắt, xác thực, model ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [("GET", "/api/companion/v1/models"), ("POST", URL)])
async def test_gateway_is_404_without_airi_dir(client, anon_client, monkeypatch, spy, method, path):
    monkeypatch.setattr(config, "AIRI_DIR", None)
    for who in (client, anon_client):
        response = await who.request(method, path, json={"messages": MESSAGES, "stream": True})
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "not_found" and "chưa được bật" in error["message"]
    assert spy == []  # Không gọi model nào.


async def test_gateway_answers_when_airi_dir_is_set(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AIRI_DIR", tmp_path)
    assert (await client.get("/api/companion/v1/models")).status_code == 200
    assert (await client.post(URL, json={"messages": MESSAGES})).status_code == 200


async def test_models_requires_session(anon_client):
    response = await anon_client.get("/api/companion/v1/models")
    assert response.status_code == 401
    assert "Chưa đăng nhập" in response.json()["error"]["message"]


async def test_models_lists_only_peto(client):
    response = await client.get("/api/companion/v1/models")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == ["peto"]


async def test_completions_require_session_with_openai_error(anon_client):
    response = await anon_client.post(URL, json={"model": "peto", "messages": MESSAGES, "stream": True})
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["type"] == "authentication_error" and "Chưa đăng nhập" in error["message"]


# --- Chữ ------------------------------------------------------------------------------------------------------------

async def test_stream_text_appends_card_rule(client, spy):
    status, items = await _stream(client, {"model": "anything", "messages": MESSAGES})
    assert status == 200 and items[-1] == "[DONE]"
    chunks = [item for item in items if isinstance(item, dict)]
    assert all(item["object"] == "chat.completion.chunk" for item in chunks)
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    result = _assemble(items)
    assert result["text"].strip() and result["finish"] == "stop" and not result["tool_calls"]
    call = spy[0]
    assert call["instructions"].startswith("You are a cheerful test character.")
    assert call["instructions"].endswith(COMPANION_CARD_RULE)
    assert call["input_items"] == [{"role": "user", "content": "chào bạn"}]
    assert call["model"] == "peto" and call["web_search"] is False and call["tools"] == []


async def test_card_rule_added_without_system_message(client, spy):
    response = await client.post(URL, json={"messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]})
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"].strip()
    assert spy[0]["instructions"] == COMPANION_CARD_RULE
    assert spy[0]["input_items"] == [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]


async def test_usage_chunk_when_requested(client):
    status, items = await _stream(client, {"messages": MESSAGES, "stream_options": {"include_usage": True}})
    assert status == 200
    usage_chunks = [item for item in items if isinstance(item, dict) and item.get("usage")]
    assert len(usage_chunks) == 1 and usage_chunks[0]["choices"] == []
    usage = usage_chunks[0]["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"] > 0
    status, items = await _stream(client, {"messages": MESSAGES})
    assert not any(isinstance(item, dict) and item.get("usage") for item in items)


async def test_stores_nothing(client):
    before = await db.list_conversations(TEST_OWNER)
    response = await client.post(URL, json={"messages": MESSAGES, "stream": False})
    assert response.status_code == 200
    assert await db.list_conversations(TEST_OWNER) == before


# --- Công cụ --------------------------------------------------------------------------------------------------------

async def test_tool_round_trip(client, spy):
    first = [{"role": "system", "content": "Character."}, {"role": "user", "content": "thời tiết __congcu__"}]
    status, items = await _stream(client, {"messages": first, "tools": [WEATHER], "tool_choice": "auto"})
    assert status == 200 and items[-1] == "[DONE]"
    result = _assemble(items)
    assert result["finish"] == "tool_calls"
    [call] = result["tool_calls"]
    assert call["type"] == "function" and call["id"] and call["function"]["name"] == "get_weather"
    assert json.loads(call["function"]["arguments"]) == {"city": "thử", "days": 1}
    # Lần đầu xuất hiện, lời gọi có mã, tên và đối số rỗng (xsai đặt mã lúc đó); đối số đi một lần sau.
    tool_deltas = [item["choices"][0]["delta"]["tool_calls"][0] for item in items
                   if isinstance(item, dict) and item.get("choices") and item["choices"][0]["delta"].get("tool_calls")]
    assert tool_deltas[0]["function"] == {"name": "get_weather", "arguments": ""}
    assert all(isinstance(delta["function"].get("arguments"), str) for delta in tool_deltas)
    # Khai báo công cụ chuyển sang dạng Responses; không có công cụ nào chạy ở máy chủ.
    assert spy[0]["tools"] == [{"type": "function", "name": "get_weather",
                                "description": "Thời tiết của một thành phố.",
                                "parameters": WEATHER["function"]["parameters"]}]
    assert spy[0]["tool_choice"] == "auto"

    # Lượt sau: AIRI gửi lại tin assistant có tool_calls (đúng dạng xsai giữ, kèm index) và kết quả công cụ.
    second = [*first,
              {"role": "assistant", "content": result["text"], "tool_calls": result["tool_calls"]},
              {"role": "tool", "tool_call_id": call["id"], "content": "Hà Nội 24 độ"}]
    status, items = await _stream(client, {"messages": second, "tools": [WEATHER]})
    assert status == 200
    reply = _assemble(items)
    assert reply["finish"] == "stop" and "Hà Nội 24 độ" in reply["text"]
    inputs = spy[1]["input_items"]
    assert inputs[-2] == {"type": "function_call", "call_id": call["id"], "name": "get_weather",
                          "arguments": call["function"]["arguments"]}
    assert inputs[-1] == {"type": "function_call_output", "call_id": call["id"], "output": "Hà Nội 24 độ"}
    assert {"role": "assistant", "content": result["text"]} in inputs
    assert spy[1]["tool_choice"] is None


async def test_tool_call_without_stream(client):
    response = await client.post(URL, json={"messages": [{"role": "user", "content": "__congcu__"}], "tools": [WEATHER]})
    assert response.status_code == 200
    choice = response.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "get_weather"


async def test_forced_tool_choice_is_converted(client, spy):
    choice = {"type": "function", "function": {"name": "get_weather"}}
    status, _ = await _stream(client, {"messages": MESSAGES, "tools": [WEATHER], "tool_choice": choice})
    assert status == 200 and spy[0]["tool_choice"] == {"type": "function", "name": "get_weather"}


async def test_tool_result_images_are_lifted_into_a_user_message(client, spy):
    messages = [{"role": "user", "content": "chụp màn hình __congcu__"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1", "content": [
                    {"type": "text", "text": "ảnh đây"}, {"type": "image_url", "image_url": {"url": _png()}}]}]
    status, _ = await _stream(client, {"messages": messages, "tools": [WEATHER]})
    assert status == 200
    items = spy[0]["input_items"]
    assert items[-2] == {"type": "function_call_output", "call_id": "call_1", "output": "ảnh đây"}
    assert items[-1]["role"] == "user" and items[-1]["content"][-1]["type"] == "input_image"


async def test_orphan_tool_calls_are_dropped(client, spy):
    messages = [{"role": "user", "content": "a"},
                {"role": "assistant", "content": "để xem", "tool_calls": [
                    {"id": "call_x", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]},
                {"role": "user", "content": "thôi khỏi"}]
    status, _ = await _stream(client, {"messages": messages, "tools": [WEATHER]})
    assert status == 200
    assert not any(item.get("type") == "function_call" for item in spy[0]["input_items"])


def _tool(name: str, **extra) -> dict:
    return {"type": "function", "function": {"name": name, **extra}}


@pytest.mark.parametrize("tools, fragment", [
    ([{"type": "web_search"}], "dạng function"),
    ([_tool("có dấu")], "Tên công cụ"),
    ([_tool("x" * 65)], "Tên công cụ"),
    ([_tool("a"), _tool("a")], "hai lần"),
    ([_tool(f"t{index}") for index in range(airi_request.MAX_TOOLS + 1)], "tối đa"),
    ([_tool("big", description="x" * (airi_request.MAX_TOOL_SCHEMA_BYTES + 1))], "quá lớn"),
    ([_tool(f"t{index}", description="x" * 20_000) for index in range(14)], "tổng tối đa"),
    ([_tool("a", parameters=[1])], "JSON Schema"),
    ("không phải danh sách", "Danh sách công cụ"),
])
async def test_bad_tools_are_400(client, tools, fragment):
    response = await client.post(URL, json={"messages": MESSAGES, "tools": tools})
    assert response.status_code == 400
    assert fragment in response.json()["error"]["message"]


@pytest.mark.parametrize("messages, extra, fragment", [
    ([], {}, "Thiếu"),
    ([{"role": "assistant", "content": "x"}], {}, "người dùng"),
    ([{"role": "wizard", "content": "x"}], {}, "Vai trò"),
    ([{"role": "user", "content": "a"}, {"role": "tool", "tool_call_id": "call_none", "content": "x"}], {}, "không khớp"),
    (MESSAGES, {"tool_choice": {"type": "function", "function": {"name": "khac"}}, "tools": [WEATHER]}, "không có"),
    (MESSAGES, {"max_tokens": 0}, "max_tokens"),
    ([{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "", "format": "wav"}}]}], {},
     "âm thanh"),
])
async def test_bad_requests_are_400(client, messages, extra, fragment):
    response = await client.post(URL, json={"messages": messages, **extra})
    assert response.status_code == 400
    assert fragment in response.json()["error"]["message"]


# --- Ảnh ------------------------------------------------------------------------------------------------------------

async def test_data_url_image_reaches_the_model(client, spy):
    messages = [{"role": "user", "content": [{"type": "text", "text": "ảnh gì đây"},
                                             {"type": "image_url", "image_url": {"url": _png(), "detail": "low"}}]}]
    status, items = await _stream(client, {"messages": messages})
    assert status == 200
    assert "1 ảnh" in _assemble(items)["text"]
    part = spy[0]["input_items"][0]["content"][1]
    assert part["type"] == "input_image" and part["image_url"].startswith("data:image/png;base64,")
    assert part["detail"] == "low"


@pytest.mark.parametrize("url, status, fragment", [
    ("https://example.com/a.png", 400, "không tải ảnh từ địa chỉ web"),
    ("http://example.com/a.png", 400, "không tải ảnh từ địa chỉ web"),
    ("data:image/svg+xml;base64,PHN2Zy8+", 400, "PNG, JPEG, GIF hoặc WebP"),
    ("data:image/png;base64," + "A" * (4 * 1024 * 1024 + 4), 413, "3 MB"),
], ids=["https", "http", "svg", "too-big"])
async def test_bad_images_are_refused(client, url, status, fragment):
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}]
    response = await client.post(URL, json={"messages": messages})
    assert response.status_code == status
    assert fragment in response.json()["error"]["message"]


async def test_image_count_cap(client):
    image = {"type": "image_url", "image_url": {"url": _png()}}
    messages = [{"role": "user", "content": [image] * (airi_request.MAX_IMAGES + 1)}]
    response = await client.post(URL, json={"messages": messages})
    assert response.status_code == 400 and f"{airi_request.MAX_IMAGES} ảnh" in response.json()["error"]["message"]


# --- Lỗi, thời gian -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word, status", [("__error__", 502), ("__tamloi__", 503)])
async def test_provider_error_before_first_byte_is_http_status(client, word, status):
    async with client.stream("POST", URL, json={"messages": [{"role": "user", "content": word}], "stream": True}) as response:
        await response.aread()
    assert response.status_code == status
    error = response.json()["error"]
    assert error["type"] == "server_error" and "giả lập" in error["message"]


async def test_mock_word_fails_after_some_text(client):
    """``__loigiua__`` của Agent giả lập: có chữ trước, rồi một dòng lỗi, không [DONE] (để thử lỗi giữa chừng ở AIRI)."""
    status, items = await _stream(client, {"messages": [{"role": "user", "content": "thử __loigiua__"}]})
    assert status == 200 and "[DONE]" not in items
    assert _assemble(items)["text"] == "Peto đang trả lời dở thì "
    assert items[-1]["error"]["message"] == "Nhà cung cấp AI ngắt giữa chừng (giả lập). Thử lại sau nhé."


async def test_provider_error_mid_stream_is_an_error_chunk(client, fake_step):
    async def events():
        yield ai_agent.AgentEvent("delta", "Đang nói dở")
        raise ProviderError("Mô hình gặp lỗi ở bước này. Thử lại nhé.", retryable=True)

    fake_step(events)
    status, items = await _stream(client, {"messages": MESSAGES})
    assert status == 200 and "[DONE]" not in items
    assert _assemble(items)["text"] == "Đang nói dở"
    assert items[-1]["error"]["message"] == "Mô hình gặp lỗi ở bước này. Thử lại nhé."


async def test_pings_during_silence_and_idle_timeout(client, fake_step, monkeypatch):
    monkeypatch.setattr(airi_gateway, "FIRST_EVENT_SECONDS", 0.05)
    monkeypatch.setattr(airi_gateway, "PING_SECONDS", 0.05)

    async def events():
        await asyncio.sleep(0.3)
        yield ai_agent.AgentEvent("delta", "xong")
        yield ai_agent.AgentEvent("done", output=(), usage={"input_tokens": 1, "output_tokens": 1})

    fake_step(events)
    status, items = await _stream(client, {"messages": MESSAGES})
    assert status == 200 and items[-1] == "[DONE]"
    assert ": ping" in items and _assemble(items)["text"] == "xong"

    monkeypatch.setattr(airi_gateway, "RESPONSE_TIMEOUTS", {"low": 0.1})

    async def silent():
        await asyncio.sleep(30)
        yield ai_agent.AgentEvent("delta", "không bao giờ tới")

    fake_step(silent)
    status, items = await _stream(client, {"messages": MESSAGES})
    assert status == 200 and items[-1]["error"]["code"] == "timeout"


async def test_idle_timeout_before_first_byte_is_504(client, fake_step, monkeypatch):
    monkeypatch.setattr(airi_gateway, "RESPONSE_TIMEOUTS", {"low": 0.05})

    async def silent():
        await asyncio.sleep(30)
        yield ai_agent.AgentEvent("delta", "không bao giờ tới")

    fake_step(silent)
    response = await client.post(URL, json={"messages": MESSAGES, "stream": True})
    assert response.status_code == 504 and response.json()["error"]["code"] == "timeout"


# --- Suất chạy, chờ giữa hai tin -------------------------------------------------------------------------------------

async def test_admission_denial_is_429(client, monkeypatch):
    class Denied:
        async def __aenter__(self):
            raise AdmissionDenied("queue_full")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(airi_gateway.admission, "slot", lambda owner, **kwargs: Denied())
    response = await client.post(URL, json={"messages": MESSAGES})
    assert response.status_code == 429
    assert response.json()["error"]["message"] == AdmissionDenied("queue_full").message


async def test_no_cooldown_on_the_gateway_and_none_left_for_chat(client, monkeypatch):
    gate = Admission(max_concurrent=2, max_queue=2, cooldown=60)
    monkeypatch.setattr(airi_gateway, "admission", gate)
    # Bộ não AIRI gửi liền nhau: lượt chính, lần gọi phụ, tin mới; không lần nào phải chờ.
    for _ in range(3):
        status, _ = await _stream(client, {"messages": MESSAGES})
        assert status == 200
    # Lượt của cổng không ghi mốc chờ, nên tin Chat kế tiếp của cùng người (cùng suất, cùng khóa owner) không bị chặn.
    async with gate.slot(TEST_OWNER):
        pass
    # Còn Chat thì vẫn chờ giữa hai tin như trước.
    with pytest.raises(AdmissionDenied) as denied:
        async with gate.slot(TEST_OWNER):
            pass
    assert denied.value.reason == "cooldown"


async def test_gateway_still_respects_concurrency_and_queue(client, monkeypatch):
    gate = Admission(max_concurrent=1, max_queue=0, cooldown=0)
    monkeypatch.setattr(airi_gateway, "admission", gate)
    async with gate.slot("someone-else"):
        response = await client.post(URL, json={"messages": MESSAGES})
    assert response.status_code == 429 and response.json()["error"]["code"] == "queue_full"


async def test_long_sessions_fit_under_the_text_caps(client, spy):
    turns = []
    for index in range(airi_request.MAX_MESSAGES // 2 - 1):
        turns += [{"role": "user", "content": f"câu {index}"}, {"role": "assistant", "content": "ừ"}]
    messages = [{"role": "system", "content": "x" * 400_000}, *turns, {"role": "user", "content": "tiếp"}]
    assert len(messages) == airi_request.MAX_MESSAGES
    response = await client.post(URL, json={"messages": messages})
    assert response.status_code == 200
    too_many = await client.post(URL, json={"messages": [*messages, {"role": "user", "content": "nữa"}]})
    assert too_many.status_code == 400 and "2.000" in too_many.json()["error"]["message"]
    too_long = await client.post(URL, json={"messages": [{"role": "user", "content": "x" * 1_000_001}]})
    assert too_long.status_code == 400 and "1.000.000" in too_long.json()["error"]["message"]


async def test_context_overflow_is_400_before_the_first_byte(client, fake_step):
    async def events():
        raise ProviderError("Ngữ cảnh vượt giới hạn model; cần tóm tắt trước khi tiếp tục.", code="context_overflow")
        yield  # pragma: no cover - để đây là hàm sinh

    fake_step(events)
    async with client.stream("POST", URL, json={"messages": MESSAGES, "stream": True}) as response:
        await response.aread()
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "context_length_exceeded" and error["type"] == "invalid_request_error"
    assert "Ngữ cảnh vượt giới hạn" in error["message"]


# --- Hủy khi trình duyệt ngắt ----------------------------------------------------------------------------------------

async def _call_and_disconnect(monkeypatch, events, *, after_text: str | None) -> tuple[list[dict], Admission]:
    """Gọi app ASGI trực tiếp (như uvicorn, ASGI spec 2.3) và gửi ``http.disconnect`` thật: ngay khi chunk chứa
    ``after_text`` tới trình duyệt, hoặc ngay từ đầu nếu ``after_text`` là None (nút dừng của AIRI)."""
    gate = Admission(max_concurrent=1, max_queue=0, cooldown=0)
    monkeypatch.setattr(airi_gateway, "admission", gate)
    monkeypatch.setattr(airi_gateway, "DISCONNECT_POLL_SECONDS", 0.05)
    monkeypatch.setattr(airi_gateway, "agent_step", lambda **kwargs: events())
    body = json.dumps({"messages": MESSAGES, "stream": True}).encode()
    disconnect = asyncio.Event()
    if after_text is None:
        disconnect.set()
    sent: list[dict] = []
    requested = False

    async def receive():
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if after_text and message["type"] == "http.response.body" and after_text in message.get("body", b"").decode():
            disconnect.set()

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": URL, "raw_path": URL.encode(), "root_path": "",
             "query_string": b"", "client": ("127.0.0.1", 1), "server": ("test", 80),
             "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                         (b"cookie", f"{SESSION_COOKIE}={auth._sign(TEST_OWNER)}".encode())]}
    await asyncio.wait_for(app(scope, receive, send), 5)
    return sent, gate


async def test_disconnect_mid_stream_closes_the_model_call_and_frees_the_slot(client, monkeypatch):
    closed = asyncio.Event()

    async def events():
        try:
            yield ai_agent.AgentEvent("delta", "Bắt đầu")
            await asyncio.sleep(60)
            yield ai_agent.AgentEvent("delta", "không bao giờ tới")
        finally:
            closed.set()

    sent, gate = await _call_and_disconnect(monkeypatch, events, after_text="Bắt đầu")
    assert sent[0]["status"] == 200
    assert "không bao giờ tới" not in b"".join(message.get("body", b"") for message in sent[1:]).decode()
    await asyncio.wait_for(closed.wait(), 2)
    # Suất chạy đã trả: lượt kế tiếp vào được ngay dù trần đồng thời là 1 và hàng chờ 0.
    async with gate.slot(TEST_OWNER):
        pass


async def test_disconnect_before_first_byte_closes_the_model_call(client, monkeypatch):
    closed = asyncio.Event()

    async def events():
        try:
            await asyncio.sleep(60)
            yield ai_agent.AgentEvent("delta", "không bao giờ tới")
        finally:
            closed.set()

    sent, gate = await _call_and_disconnect(monkeypatch, events, after_text=None)
    assert sent[0]["status"] == 499
    await asyncio.wait_for(closed.wait(), 2)
    async with gate.slot(TEST_OWNER):
        pass


# --- Số đo cho trang Quản trị ---------------------------------------------------------------------------------------

async def test_turns_are_recorded_as_airi(client, recorder):
    status, _ = await _stream(client, {"messages": MESSAGES})
    assert status == 200
    rows = [dict(zip(usage_events.COLUMNS, row)) for row in usage_events._pending]
    call = next(row for row in rows if row["kind"] == "call")
    turn = next(row for row in rows if row["kind"] == "turn")
    assert call["surface"] == turn["surface"] == "airi" and call["purpose"] == "airi"
    assert call["service"] == "xai" and call["model"] == "peto" and call["input_tokens"] > 0
    assert turn["outcome"] == "complete" and turn["complete"] == 1 and turn["effort"] == "low"

    usage_events._pending.clear()
    response = await client.post(URL, json={"messages": [{"role": "user", "content": "__error__"}]})
    assert response.status_code == 502
    rows = [dict(zip(usage_events.COLUMNS, row)) for row in usage_events._pending]
    assert [(row["kind"], row["outcome"], row["complete"]) for row in rows] == [("turn", "provider_error", 0)]
