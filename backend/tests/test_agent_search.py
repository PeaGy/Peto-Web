"""Tra web cho Peto Agent bản desktop: POST /api/agent/v1/search theo dạng API tìm kiếm của DeepSeek."""

from __future__ import annotations

import json

import pytest

from ai import web_lookup
from features.agent import gateway
from tests.test_agent_gateway import bearer, signed_in, steps_used


async def test_search_returns_deepseek_shaped_results_from_the_search_only(anon_client, client):
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/search", headers=bearer(token), json={"query": "python asyncio"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"results": [
        {"url": "https://example.com/python-asyncio", "title": "python asyncio — Example",
         "snippet": "Trang mẫu nói về python asyncio.", "summary": "Trang mẫu nói về python asyncio.", "date": "2026-11-01"},
        {"url": "https://example.org/python-asyncio", "title": "Tìm hiểu python asyncio", "snippet": "", "date": None},
    ]}
    assert await steps_used(client) == 1


async def test_search_honours_count_and_question(anon_client, client, monkeypatch):
    seen = {}

    async def lookup(query, count, question=None):
        seen.update(query=query, count=count, question=question)
        return [{"url": "https://a.example/", "title": "A", "snippet": "", "date": None}], {"input_tokens": 3, "output_tokens": 2}

    monkeypatch.setattr(gateway, "web_lookup", lookup)
    token = await signed_in(anon_client, client)
    body = {"query": "  tin   mới  ", "count": 3, "ori_question": "x" * 200, "need_content": False}
    assert (await anon_client.post("/api/agent/v1/search", headers=bearer(token), json=body)).status_code == 200
    assert seen == {"query": "tin mới", "count": 3, "question": "x" * gateway.MAX_QUESTION_CHARS}


@pytest.mark.parametrize("body", [
    {"query": ""}, {"query": "a" * 501}, {"query": "ok", "count": 0}, {"query": "ok", "count": 21},
    {"query": "ok", "count": True}, {"query": "ok", "ori_question": 3}, [],
])
async def test_invalid_searches_take_no_step(anon_client, client, body):
    token = await signed_in(anon_client, client)
    response = await anon_client.post("/api/agent/v1/search", headers=bearer(token), json=body)
    assert response.status_code == 400
    assert "error" in response.json()
    assert await steps_used(client) == 0


async def test_search_needs_a_device_token(anon_client):
    response = await anon_client.post("/api/agent/v1/search", json={"query": "x"})
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"


async def test_failed_or_disabled_searches_give_the_step_back(anon_client, client, monkeypatch):
    token = await signed_in(anon_client, client)
    failed = await anon_client.post("/api/agent/v1/search", headers=bearer(token), json={"query": "__error__"})
    assert failed.status_code == 503
    assert failed.headers["x-should-retry"] == "true"
    assert await steps_used(client) == 0
    monkeypatch.setattr(gateway, "AGENT_WEB_SEARCH", False)
    off = await anon_client.post("/api/agent/v1/search", headers=bearer(token), json={"query": "x"})
    assert off.status_code == 503
    assert off.json()["error"]["code"] == "search_disabled"
    assert await steps_used(client) == 0


async def test_search_counts_against_the_daily_steps(anon_client, client, monkeypatch):
    monkeypatch.setattr(gateway, "AGENT_DAILY_STEPS", 1)
    token = await signed_in(anon_client, client)
    assert (await anon_client.post("/api/agent/v1/search", headers=bearer(token), json={"query": "x"})).status_code == 200
    blocked = await anon_client.post("/api/agent/v1/search", headers=bearer(token), json={"query": "x"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "insufficient_quota"


def message(text: str, annotations: list[dict] | None = None) -> dict:
    return {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": annotations or []}]}


def test_results_keep_only_pages_the_search_returned():
    search = {"type": "web_search_call", "status": "completed",
              "action": {"type": "search", "sources": [{"url": "https://docs.python.org/3/library/asyncio.html"},
                                                       {"url": "https://example.com/post", "title": "Bài viết"}]}}
    cited = {"type": "url_citation", "url": "https://news.example/a", "title": "Tin A"}
    answer = json.dumps({"results": [
        {"url": "https://docs.python.org/3/library/asyncio.html/#top", "title": "asyncio — Asynchronous I/O",
         "summary": "  Thư viện   chuẩn. " + "x" * 300, "date": "2026-10-01"},
        {"url": "https://made-up.example/", "title": "Bịa", "summary": "Không có thật."},
        {"url": "https://news.example/a", "title": "Khác", "summary": "Tin.", "date": None},
        {"url": "https://news.example/a", "title": "Trùng", "summary": "Lặp."},
    ]})
    results = web_lookup.results_from_output([search, message("```json\n" + answer + "\n```", [cited])], 10)
    assert [row["url"] for row in results] == [
        "https://docs.python.org/3/library/asyncio.html", "https://news.example/a", "https://example.com/post"]
    first = results[0]
    assert first["title"] == "asyncio — Asynchronous I/O"
    assert first["summary"].startswith("Thư viện chuẩn. x") and len(first["snippet"]) <= web_lookup.MAX_SNIPPET_CHARS + 1
    assert first["snippet"].endswith("…") and first["date"] == "2026-10-01"
    assert results[1]["title"] == "Tin A"
    assert results[2] == {"url": "https://example.com/post", "title": "Bài viết", "snippet": "", "date": None}
    assert len(web_lookup.results_from_output([search, message(answer)], 1)) == 1


def test_results_without_a_search_or_with_unreadable_text():
    assert web_lookup.results_from_output([message('{"results": [{"url": "https://a.example/"}]}')], 5) is None
    search = {"type": "web_search_call", "status": "completed", "action": {"type": "search", "sources": []}}
    assert web_lookup.results_from_output([search, message("not json")], 5) == []
    only_sources = {"type": "web_search_call", "action": {"sources": [{"url": "https://a.example/x", "title": "A"}]}}
    assert web_lookup.results_from_output([only_sources, message("{broken")], 5) == [
        {"url": "https://a.example/x", "title": "A", "snippet": "", "date": None}]
