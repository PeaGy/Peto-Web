"""Tìm web: giao thức dịch vụ, nguồn riêng tư, ngắt kết nối và chế độ bật/tắt."""
from features.chat import history as chat_history

import asyncio
import json
from types import SimpleNamespace

import aiosqlite
import httpx
import pytest

from features.accounts import auth
import storage as db
from storage import connection as db_connection
from features.chat import service as chat_service
from ai import ChatMessage, StreamChunk
from ai.base import ProviderError
from ai import xai
from core.config import SESSION_COOKIE
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, Item, call, done, fake_provider
from shared.web_search import SPOKEN_SEARCH_CONTEXT, normalize_sources, spoken_reply

SOURCE = {"url": "https://docs.python.org/3/", "title": "Tài liệu Python"}


def test_citation_promotes_result_and_survives_result_limit():
    results = [{"url": f"https://example.com/{i}", "kind": "result"} for i in range(40)]
    sources = normalize_sources([*results, {**results[-1], "kind": "citation"}])
    assert len(sources) == 30
    assert sources[0]["url"] == results[-1]["url"]
    assert sources[0]["kind"] == "citation"
    assert normalize_sources([*sources, results[-1]])[0]["kind"] == "citation"


def search_call(status="completed"):
    return Item(type="web_search_call", id="web-1", status=status, action={"type": "search", "query": "Python", "sources": [SOURCE]})


def cited_message():
    return Item(type="message", id="msg-1", role="assistant", content=[{"type": "output_text", "text": "Có tài liệu.", "annotations": [{"type": "url_citation", **SOURCE}]}])


async def test_native_search_sources_and_clock_share_one_turn(monkeypatch):
    first = FakeStream([
        SimpleNamespace(type="response.output_item.added", item=search_call("in_progress")),
        SimpleNamespace(type="response.output_item.done", item=search_call()),
        done(search_call(), call()),
    ])
    second = FakeStream([SimpleNamespace(type="response.output_text.delta", delta="Có tài liệu."), done(cited_message())])
    provider, requests = fake_provider(monkeypatch, [first, second])
    chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[ChatMessage("user", "Tìm tài liệu mới")])]
    assert {"type": "web_search"} in requests[0]["tools"]
    assert "web_search_call.action.sources" in requests[0]["include"]
    assert requests[0]["store"] is False and requests[1]["store"] is False
    assert "không đáng tin" in requests[0]["instructions"]
    assert any(item.get("type") == "web_search_call" for item in requests[1]["input"])
    assert requests[1]["input"][-1]["call_id"] == "call_1"
    assert [chunk.sources for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == "sources"] == [
        ({**SOURCE, "kind": "result"},), ({**SOURCE, "kind": "citation"},),
    ]
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == "search" for chunk in chunks)
    assert first.closed and second.closed


async def test_usage_logs_count_search_once_and_do_not_log_content(monkeypatch, caplog):
    completed = done(search_call(), cited_message())
    completed.response.usage = {'input_tokens': 120, 'output_tokens': 30,
        'input_tokens_details': {'cached_tokens': 80}, 'output_tokens_details': {'reasoning_tokens': 10}}
    stream = FakeStream([SimpleNamespace(type='response.output_item.done', item=search_call()), completed])
    provider, _ = fake_provider(monkeypatch, [stream])
    with caplog.at_level('INFO', logger='peto_web.xai'):
        _ = [chunk async for chunk in provider.stream(system_prompt='private instructions', messages=[ChatMessage('user', 'private input')])]
    logs = [r.message for r in caplog.records if r.message.startswith('model_usage')]
    assert len(logs) == 1
    assert 'input_tokens=120' in logs[0] and 'cached_tokens=80' in logs[0]
    assert 'output_tokens=30' in logs[0] and 'reasoning_tokens=10' in logs[0]
    assert 'search_calls_seen=1' in logs[0]
    assert 'private' not in logs[0] and SOURCE['url'] not in logs[0]


@pytest.mark.parametrize("mode", ["off", "on", "auto"])
async def test_search_modes_change_available_tools(monkeypatch, mode):
    stream = FakeStream([done(search_call() if mode == "on" else cited_message())])
    provider, requests = fake_provider(monkeypatch, [stream])
    _ = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[], web_search=mode)]
    request = requests[0]
    if mode == "on":
        assert request["tool_choice"] == "required"
        assert request["tools"] == [{"type": "web_search"}]
    elif mode == "off":
        assert all(tool["type"] == "function" for tool in request["tools"])
        assert "max_turns" not in request.get("extra_body", {})
        assert "đang tắt" in request["instructions"]
    else:
        assert "tool_choice" not in request


async def test_forced_search_cannot_silently_return_unsearched_answer(monkeypatch):
    stream = FakeStream([SimpleNamespace(type="response.output_text.delta", delta="Câu chưa xác minh"), done()])
    provider, _ = fake_provider(monkeypatch, [stream])
    with pytest.raises(ProviderError, match="chưa xác nhận"):
        _ = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[], web_search="on")]
    assert stream.closed


async def test_draft_written_before_search_is_dropped(monkeypatch):
    """Grok hay viết móc câu, search, rồi viết lại từ đầu. Bản nháp không được giữ."""
    stream = FakeStream([
        SimpleNamespace(type="response.output_text.delta", delta="Không giống đâu ad. Bản nháp dài."),
        SimpleNamespace(type="response.web_search_call.in_progress"),
        SimpleNamespace(type="response.output_item.added", item=search_call("in_progress")),
        SimpleNamespace(type="response.web_search_call.completed"),
        SimpleNamespace(type="response.output_item.done", item=search_call()),
        SimpleNamespace(type="response.output_text.delta", delta="Không giống đâu ad. Có nguồn.[1]"),
        done(search_call(), cited_message()),
    ])
    provider, _ = fake_provider(monkeypatch, [stream])
    chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[ChatMessage("user", "So sánh")])]
    kept: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, StreamChunk) and chunk.kind == "replace":
            kept = []
        elif isinstance(chunk, str):
            kept.append(chunk)
    assert "".join(kept) == "Không giống đâu ad. Có nguồn.[1]"
    assert "Bản nháp" not in "".join(kept)
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == "replace" for chunk in chunks)
    assert stream.closed


async def test_lead_in_before_a_second_search_is_also_a_draft(monkeypatch):
    """Ảnh chủ dự án 7/10: câu dẫn viết giữa hai lần tra ở lại và dính vào câu trả lời ("phân tích.Ad gửi link")."""
    stream = FakeStream([
        SimpleNamespace(type="response.output_item.added", item=search_call("in_progress")),
        SimpleNamespace(type="response.web_search_call.completed"),
        SimpleNamespace(type="response.output_text.delta", delta="Đúng bài rồi. Peto lấy lời rồi phân tích."),
        SimpleNamespace(type="response.output_item.added", item=search_call("in_progress")),
        SimpleNamespace(type="response.web_search_call.completed"),
        SimpleNamespace(type="response.output_text.delta", delta="Ad gửi link trang tìm kiếm."),
        done(search_call(), cited_message()),
    ])
    provider, _ = fake_provider(monkeypatch, [stream])
    chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[])]
    kept: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, StreamChunk) and chunk.kind == "replace":
            kept = []
        elif isinstance(chunk, str):
            kept.append(chunk)
    assert "".join(kept) == "Ad gửi link trang tìm kiếm."


async def test_short_draft_before_search_moves_to_the_work_log(client, monkeypatch):
    class TwoSearches:
        async def stream(self, **kwargs):
            yield StreamChunk("round")
            yield StreamChunk("search", "searching")
            yield StreamChunk("search", "completed")
            yield "Đúng bài rồi. Peto lấy lời rồi phân tích."
            yield StreamChunk("replace")
            yield StreamChunk("search", "searching")
            yield StreamChunk("search", "completed")
            yield "Ad gửi link trang tìm kiếm."
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": TwoSearches())
    events = await read_events(await client.post("/api/chat", json={"message": "Phân tích bài này"}))
    assert events[-1]["type"] == "done"
    work = next(event["work"] for event in events if event["type"] == "work")
    assert [step["label"] for step in work["steps"] if step["kind"] == "note"] == ["Đúng bài rồi. Peto lấy lời rồi phân tích."]
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()["messages"][-1]
    assert saved["content"] == "Ad gửi link trang tìm kiếm."


async def test_search_after_answer_does_not_erase_the_final_text(monkeypatch):
    """Sự kiện search completed lúc cuối không được xóa câu đã viết sau khi tra xong."""
    stream = FakeStream([
        SimpleNamespace(type="response.output_item.added", item=search_call("in_progress")),
        SimpleNamespace(type="response.web_search_call.completed"),
        SimpleNamespace(type="response.output_text.delta", delta="Câu đã kiểm chứng."),
        SimpleNamespace(type="response.output_item.done", item=search_call()),
        done(search_call(), cited_message()),
    ])
    provider, _ = fake_provider(monkeypatch, [stream])
    chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[])]
    assert not any(isinstance(chunk, StreamChunk) and chunk.kind == "replace" for chunk in chunks)
    assert "Câu đã kiểm chứng." in "".join(chunk for chunk in chunks if isinstance(chunk, str))


async def test_failed_search_is_reported(monkeypatch):
    stream = FakeStream([done(search_call("failed"))])
    provider, _ = fake_provider(monkeypatch, [stream])
    with pytest.raises(ProviderError, match="chưa tra cứu"):
        _ = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[])]
    assert stream.closed


async def test_replaced_draft_is_not_saved(client, monkeypatch):
    class RestartProvider:
        async def stream(self, **kwargs):
            yield "Không giống đâu ad. Bản nháp."
            yield StreamChunk("replace")
            yield StreamChunk("search", "searching")
            yield StreamChunk("search", "completed")
            yield "Không giống đâu ad. Có nguồn."
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": RestartProvider())
    events = await read_events(await client.post("/api/chat", json={"message": "So sánh", "web_search": "on"}))
    assert any(event["type"] == "replace" for event in events)
    text = "".join(event["text"] for event in events if event["type"] == "delta")
    # SSE vẫn có bản nháp trước replace; tin lưu chỉ giữ bản sau.
    assert "Bản nháp" in text
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()["messages"][-1]
    assert saved["content"] == "Không giống đâu ad. Có nguồn."
    assert "Bản nháp" not in saved["content"]


async def test_sources_stream_save_reload_and_stay_private(client, monkeypatch):
    class SearchProvider:
        async def stream(self, **kwargs):
            assert kwargs["web_search"] == "on"
            yield StreamChunk("search", "searching")
            yield StreamChunk("sources", sources=(SOURCE, SOURCE, {"url": "javascript:alert(1)"}))
            yield "Theo tài liệu Python."
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": SearchProvider())
    events = await read_events(await client.post("/api/chat", json={"message": "Tìm tài liệu Python", "web_search": "on"}))
    assert events[-1]["type"] == "done"
    assert next(event for event in events if event["type"] == "sources")["sources"] == [SOURCE]
    path = f"/api/conversations/{events[0]['conversation_id']}/messages"
    saved = (await client.get(path)).json()["messages"][-1]
    assert saved["sources"] == [SOURCE] and saved["content"] == "Theo tài liệu Python."
    assert "searching" not in saved["content"]
    client.cookies.set(SESSION_COOKIE, auth._sign("github:nguoi-khac"))
    assert (await client.get(path)).status_code == 404


async def test_partial_answer_keeps_sources_after_failure(client, monkeypatch):
    class Broken:
        async def stream(self, **kwargs):
            yield "Phần đã tra được."
            yield StreamChunk("sources", sources=(SOURCE,))
            raise ProviderError("Mất kết nối khi tìm tiếp")
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": Broken())
    events = await read_events(await client.post("/api/chat", json={"message": "Tra cứu"}))
    assert events[-1]["type"] == "error"
    saved = (await client.get(f"/api/conversations/{events[0]['conversation_id']}/messages")).json()["messages"][-1]
    assert saved["status"] == "incomplete" and saved["sources"] == [SOURCE]


async def test_no_automatic_retry_after_search_has_started(client, monkeypatch):
    calls = []
    class Timeout:
        async def stream(self, **kwargs):
            calls.append(1)
            yield StreamChunk("search", "searching")
            raise TimeoutError()
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": Timeout())
    events = await read_events(await client.post("/api/chat", json={"message": "Tìm", "effort": "low"}))
    assert events[-1]["type"] == "error"
    assert len(calls) == 1


async def test_disabled_search_rejected_before_saving(client, monkeypatch):
    monkeypatch.setattr(chat_service, "WEB_SEARCH_ENABLED", False)
    response = await client.post("/api/chat", json={"message": "Tìm", "web_search": "on"})
    assert response.status_code == 400 and "đang tắt" in response.json()["detail"]
    assert (await client.post("/api/chat", json={"message": "chào", "web_search": "invalid"})).status_code == 422


async def test_mock_does_not_fabricate_search_results(client):
    events = await read_events(await client.post("/api/chat", json={"message": "Tin mới nhất", "web_search": "on"}))
    text = "".join(event["text"] for event in events if event["type"] == "delta")
    assert "chưa tìm web thật" in text
    assert not any(event["type"] in {"sources", "search"} for event in events)


def test_source_links_are_safe_bounded_and_deduplicated():
    assert normalize_sources([SOURCE, SOURCE, {"url": "data:text/html,hi"}, {"url": "https://name:secret@example.com"}, {"url": "https://[broken"}, {"url": "https://example.com/\n"}]) == [SOURCE]
    assert normalize_sources([{"url": SOURCE["url"], "title": "1"}])[0]["title"] == "docs.python.org"
    assert len(normalize_sources([{"url": f"https://example.com/{i}"} for i in range(100)])) == 30


def test_saved_sources_are_available_for_followup_questions():
    messages = chat_history._to_chat_messages([{"role": "assistant", "content": "Câu cũ", "sources": [SOURCE]}])
    payload = xai.build_input_payload(messages)
    assert SOURCE["url"] in payload[0]["content"][-1]["text"]
    assert "không phải kết quả tra mới" in payload[0]["content"][-1]["text"]


async def test_old_messages_migrate_without_losing_text(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setattr(db_connection, "DB_PATH", path)
    async with aiosqlite.connect(path) as connection:
        await connection.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, created_at REAL)")
        await connection.execute("INSERT INTO messages VALUES (1, 'cu', 'assistant', 'Tin cũ', 1)")
        await connection.commit()
    await db.init_db()
    await db.init_db()
    async with aiosqlite.connect(path) as connection:
        assert await (await connection.execute("SELECT content, sources, status FROM messages")).fetchone() == ("Tin cũ", "[]", "complete")


async def test_real_sdk_parses_search_events_and_annotations(monkeypatch):
    requests = []
    events = [
        {"type": "response.web_search_call.searching", "item_id": "web-1", "output_index": 0, "sequence_number": 1},
        {"type": "response.output_text.annotation.added", "annotation": {"type": "url_citation", **SOURCE, "start_index": 0, "end_index": 2}, "item_id": "msg-1", "output_index": 1, "content_index": 0, "annotation_index": 0, "sequence_number": 2},
        {"type": "response.output_text.delta", "delta": "Có nguồn.", "item_id": "msg-1", "output_index": 1, "content_index": 0, "sequence_number": 3},
        {"type": "response.completed", "sequence_number": 4, "response": {"id": "resp-1", "object": "response", "created_at": 1, "status": "completed", "output": [vars(search_call()), vars(cited_message())]}},
    ]
    def handle(request):
        requests.append(json.loads(request.content))
        data = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
        return httpx.Response(200, content=data, headers={"content-type": "text/event-stream"})
    provider = xai.XAIProvider()
    monkeypatch.setattr(provider._auth, "get_access_token", lambda: asyncio.sleep(0, result="token-gia"))
    await provider._client.close()
    provider._client = xai.AsyncOpenAI(api_key="gia", base_url="https://example.test/v1", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[], web_search="on")]
    finally:
        await provider._client.close()
    assert requests[0]["tool_choice"] == "required"
    assert any(isinstance(chunk, StreamChunk) and {**SOURCE, "kind": "citation"} in chunk.sources for chunk in chunks)
    assert "Có nguồn." in chunks


async def test_companion_searches_when_needed_with_spoken_instructions(client, monkeypatch):
    """Chủ web chọn ngày 2026-09-28: Companion tra web khi cần, như mô-đun tra web của AIRI. Chỉ dẫn tra web của lượt
    Companion dặn nói tiếng Anh, không chèn đường dẫn hay dấu trích dẫn; tab Trò chuyện giữ chỉ dẫn cũ."""
    streams = [FakeStream([SimpleNamespace(type="response.output_text.delta", delta=text), done()])
               for text in ("<|EMOTE_HAPPY|> Sunny.", "<|EMOTE_HAPPY|> Sunny.", "<|EMOTE_HAPPY|> Sunny.", "Nắng.")]
    provider, requests = fake_provider(monkeypatch, streams)
    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": provider)
    for web_search in ("auto", "on", "off"):
        events = await read_events(await client.post("/api/chat", json={
            "message": "What's the weather in Saigon today?", "mode": "companion", "web_search": web_search}))
        assert events[-1]["type"] == "done"
    auto, forced, off = requests[:3]
    for request in (auto, forced):
        # Companion không có kiểu "luôn tìm": trang gửi "on" cũng chỉ là tự quyết.
        assert {"type": "web_search"} in request["tools"] and "tool_choice" not in request
        assert SPOKEN_SEARCH_CONTEXT in request["instructions"]
        assert "dẫn liên kết nguồn" not in request["instructions"]
    # Trang cũ còn gửi "off" thì vẫn tắt.
    assert all(tool["type"] == "function" for tool in off["tools"]) and "đang tắt" in off["instructions"]

    await read_events(await client.post("/api/chat", json={"message": "Thời tiết Sài Gòn hôm nay?"}))
    assert "dẫn liên kết nguồn" in requests[3]["instructions"]
    assert SPOKEN_SEARCH_CONTEXT not in requests[3]["instructions"]
    assert spoken_reply.get() is False


async def test_companion_keeps_its_emotion_when_the_draft_before_a_search_is_dropped(client, monkeypatch):
    """Tra web thì phần Peto viết trước lúc tra bị bỏ (replace), thường chỉ có thẻ cảm xúc. Câu sau lúc tra không gắn lại
    thẻ thì tin lưu vẫn giữ cảm xúc đã gửi tới nhân vật, để nghe lại tin cũ nhân vật làm đúng mặt."""
    class Searching:
        async def stream(self, **kwargs):
            yield "<|EMOTE_THINK|> Let me check."
            yield StreamChunk("replace")
            yield StreamChunk("search", "searching")
            yield StreamChunk("search", "completed")
            yield "It's sunny in Saigon."

    monkeypatch.setattr(chat_service, "get_provider", lambda model="peto": Searching())
    events = await read_events(await client.post("/api/chat", json={"message": "Weather in Saigon?", "mode": "companion"}))
    kinds = [event["type"] for event in events]
    assert kinds[-1] == "done" and kinds.index("replace") < kinds.index("search")
    assert [event["emotion"] for event in events if event["type"] == "emotion"] == ["think"]
    after = "".join(event["text"] for event in events[kinds.index("replace"):] if event["type"] == "delta")
    assert after == "It's sunny in Saigon."
    stored = await db.get_messages(TEST_OWNER, events[0]["conversation_id"])
    assert stored[-1]["content"] == "<|EMOTE_THINK|> It's sunny in Saigon."
    reply = [item for item in (await client.get("/api/companion")).json()["messages"] if item["role"] == "assistant"][-1]
    assert reply["content"] == "It's sunny in Saigon." and reply["emotion"] == "think"
