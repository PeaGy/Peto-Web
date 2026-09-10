"""Tìm web: giao thức dịch vụ, nguồn riêng tư, ngắt kết nối và chế độ bật/tắt."""
import asyncio
import json
from types import SimpleNamespace

import aiosqlite
import httpx
import pytest

import auth
import db
import main
from ai import ChatMessage, StreamChunk
from ai.base import ProviderError
from ai import xai
from config import SESSION_COOKIE
from conftest import read_events
from test_clock_tools import FakeStream, Item, call, done, fake_provider
from web_search import normalize_sources

SOURCE = {"url": "https://docs.python.org/3/", "title": "Tài liệu Python"}


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
    assert [chunk.sources for chunk in chunks if isinstance(chunk, StreamChunk) and chunk.kind == "sources"] == [(SOURCE,)]
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == "search" for chunk in chunks)
    assert first.closed and second.closed


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


async def test_failed_search_is_reported(monkeypatch):
    stream = FakeStream([done(search_call("failed"))])
    provider, _ = fake_provider(monkeypatch, [stream])
    with pytest.raises(ProviderError, match="chưa tra cứu"):
        _ = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[])]
    assert stream.closed


async def test_sources_stream_save_reload_and_stay_private(client, monkeypatch):
    class SearchProvider:
        async def stream(self, **kwargs):
            assert kwargs["web_search"] == "on"
            yield StreamChunk("search", "searching")
            yield StreamChunk("sources", sources=(SOURCE, SOURCE, {"url": "javascript:alert(1)"}))
            yield "Theo tài liệu Python."
    monkeypatch.setattr(main, "get_provider", lambda: SearchProvider())
    events = await read_events(await client.post("/api/chat", json={"message": "Tìm tài liệu Python", "web_search": "on"}))
    assert events[-1]["type"] == "done"
    assert next(event for event in events if event["type"] == "sources")["sources"] == [SOURCE]
    path = f"/api/conversations/{events[0]['conversation_id']}/messages"
    saved = (await client.get(path)).json()["messages"][-1]
    assert saved["sources"] == [SOURCE] and saved["content"] == "Theo tài liệu Python."
    assert "searching" not in saved["content"]
    client.cookies.set(SESSION_COOKIE, auth._sign("guest:nguoi-khac"))
    assert (await client.get(path)).status_code == 404


async def test_partial_answer_keeps_sources_after_failure(client, monkeypatch):
    class Broken:
        async def stream(self, **kwargs):
            yield "Phần đã tra được."
            yield StreamChunk("sources", sources=(SOURCE,))
            raise ProviderError("Mất kết nối khi tìm tiếp")
    monkeypatch.setattr(main, "get_provider", lambda: Broken())
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
    monkeypatch.setattr(main, "get_provider", lambda: Timeout())
    events = await read_events(await client.post("/api/chat", json={"message": "Tìm", "effort": "low"}))
    assert events[-1]["type"] == "error"
    assert len(calls) == 1


async def test_disabled_search_rejected_before_saving(client, monkeypatch):
    monkeypatch.setattr(main, "WEB_SEARCH_ENABLED", False)
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
    messages = main._to_chat_messages([{"role": "assistant", "content": "Câu cũ", "sources": [SOURCE]}])
    payload = xai.build_input_payload(messages)
    assert SOURCE["url"] in payload[0]["content"][-1]["text"]
    assert "không phải kết quả tra mới" in payload[0]["content"][-1]["text"]


async def test_old_messages_migrate_without_losing_text(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
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
    assert any(isinstance(chunk, StreamChunk) and SOURCE in chunk.sources for chunk in chunks)
    assert "Có nguồn." in chunks
