"""Trang Quản trị: quyền chủ web, bộ ghi số liệu và phép tính thống kê. Không gọi AI thật."""

from datetime import datetime
import json
import time
from zoneinfo import ZoneInfo

import aiosqlite
import pytest

from conftest import TEST_OWNER, read_events
from core import config, usage_events
from features.admin import rates as rate_file, stats
import storage as db

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
RATES = {"gpt-6-luna": {"input": 2, "cached_input": 0.2, "output": 10}}


@pytest.fixture
def recorder():
    usage_events.enable()
    yield usage_events
    usage_events.disable()


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(config, "OWNER_ACCOUNTS", frozenset({TEST_OWNER}))


async def stored_rows():
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM usage_events ORDER BY id") as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def clear_events():
    await db.init_db()
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("DELETE FROM usage_events")
        await conn.commit()


def row(at, kind="call", **values):
    base = dict.fromkeys(stats.COLUMNS)
    base.update(at=at, kind=kind, service="openai", model="luna", slug="gpt-6-luna")
    base.update(values)
    return base


def local(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ZONE).timestamp()


# --- Quyền ----------------------------------------------------------------------------------------------------

async def test_overview_is_hidden_from_anonymous_and_regular_accounts(anon_client, client):
    assert (await anon_client.get("/api/admin/overview")).status_code == 404
    response = await client.get("/api/admin/overview")
    assert response.status_code == 404
    # Khoảng sai cũng 404 với người không phải chủ: không để lộ là trang này có thật.
    assert (await client.get("/api/admin/overview?range=abc")).status_code == 404
    me = (await client.get("/api/auth/me")).json()
    assert me["user"]["is_owner"] is False


async def test_owner_reads_overview_without_cache(client, owner):
    await clear_events()
    response = await client.get("/api/admin/overview?range=7d")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert (await client.get("/api/admin/overview?range=1y")).status_code == 400
    assert (await client.get("/api/auth/me")).json()["user"]["is_owner"] is True


async def test_empty_overview_says_no_data_instead_of_zero(client, owner):
    await clear_events()
    data = (await client.get("/api/admin/overview?range=30d")).json()
    assert data["data_since"] is None and data["calls"] == 0 and data["turns"] == 0
    assert data["success_rate"] is None
    assert data["cost"]["total_usd"] is None and data["cost"]["by_service"] is None
    assert data["latency"] == {"p50_ms": None, "p95_ms": None, "first_p50_ms": None, "first_p95_ms": None}
    assert len(data["buckets"]) == 30 and all(bucket["empty"] for bucket in data["buckets"])
    assert data["covered_buckets"] == 0


async def test_overview_returns_aggregates_only(client, owner, recorder):
    await clear_events()
    recorder.record("call", service="OpenAI", model="luna", slug="gpt-6-luna", purpose="chat",
                    input_tokens=1000, output_tokens=200, cached_tokens=400)
    recorder.record("turn", service="openai", model="luna", surface="chat", outcome="complete", complete=True,
                    elapsed_ms=4000, first_text_ms=900)
    await recorder.flush()
    text = (await client.get("/api/admin/overview?range=24h")).text
    data = json.loads(text)
    assert data["calls"] == 1 and data["turns"] == 1 and data["models"][0]["key"] == "luna"
    assert TEST_OWNER not in text and "discord:" not in text


# --- Bộ ghi -----------------------------------------------------------------------------------------------------

async def test_recorder_stores_no_owner_or_content(recorder):
    await clear_events()
    recorder.record("call", service="xAI", model="peto", slug="grok-4.7", purpose="side", complete=True,
                    elapsed_ms=1200, input_tokens=50, output_tokens=7, cached_tokens=None, search_calls=2)
    recorder.record("call", service="openai", model="luna; DROP TABLE", slug="gpt 6", input_tokens=-5, output_tokens=True)
    assert await recorder.flush() == 2
    first, second = await stored_rows()
    assert first["service"] == "xai" and first["model"] == "peto" and first["purpose"] == "side"
    assert first["input_tokens"] == 50 and first["cached_tokens"] is None and first["search_calls"] == 2
    # Nhãn lạ và số không hợp lệ thành ô trống, không lưu nguyên văn.
    assert second["model"] is None and second["slug"] is None
    assert second["input_tokens"] is None and second["output_tokens"] is None
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute("PRAGMA table_info(usage_events)") as cursor:
            names = {info[1] for info in await cursor.fetchall()}
    assert not names & {"owner", "conversation_id", "content", "message", "title"}


async def test_recorder_is_off_outside_the_server():
    usage_events.disable()
    usage_events.record("call", service="openai", input_tokens=1, output_tokens=1)
    assert await usage_events.flush() == 0


async def test_full_queue_drops_oldest_and_counts(recorder, monkeypatch):
    from collections import deque
    monkeypatch.setattr(usage_events, "MAX_PENDING", 2)
    monkeypatch.setattr(usage_events, "_pending", deque(maxlen=2))
    before = usage_events.dropped()
    for _ in range(3):
        recorder.record("turn", service="xai", model="peto")
    assert usage_events.dropped() == before + 1 and len(usage_events._pending) == 2


async def test_flush_failure_never_raises(recorder, monkeypatch):
    def broken():
        raise OSError("đĩa đầy")
    monkeypatch.setattr(usage_events, "connect", broken)
    recorder.record("turn", service="xai", model="peto")
    assert await recorder.flush() == 0


async def test_prune_keeps_only_retention_window(recorder):
    await clear_events()
    now = time.time()
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.executemany("INSERT INTO usage_events (at, kind, service) VALUES (?, 'turn', 'xai')",
                               [(now - 91 * 86400,), (now - 89 * 86400,)])
        await conn.commit()
    await usage_events.prune(now)
    assert len(await stored_rows()) == 1


async def test_chat_turn_is_recorded_after_reply(client, recorder):
    await clear_events()
    events = await read_events(await client.post("/api/chat", json={"message": "Chào Peto"}))
    assert events[-1]["type"] == "done"
    await recorder.flush()
    turns = [item for item in await stored_rows() if item["kind"] == "turn"]
    assert len(turns) == 1
    assert turns[0]["surface"] == "chat" and turns[0]["model"] == "peto" and turns[0]["outcome"] == "complete"
    assert turns[0]["complete"] == 1 and turns[0]["elapsed_ms"] is not None


async def test_agent_step_records_call_and_turn(anon_client, client, recorder):
    from test_agent_api import bearer, connect
    await clear_events()
    token = await connect(anon_client, client)
    response = await anon_client.post("/api/agent/step", headers=bearer(token), json={
        "input": [{"type": "message", "role": "user", "content": "chào"}], "context": {}, "effort": "low"})
    assert response.status_code == 200
    await recorder.flush()
    kinds = {item["kind"]: item for item in await stored_rows()}
    assert kinds["call"]["surface"] == "agent" and kinds["call"]["input_tokens"] is not None
    assert kinds["turn"]["outcome"] == "complete" and kinds["turn"]["model"] == "peto"


# --- Phép tính --------------------------------------------------------------------------------------------------

def test_percentile_is_nearest_rank():
    values = list(range(100, 1100, 100))
    assert stats.percentile(values, .5) == 500 and stats.percentile(values, .95) == 1000
    assert stats.percentile([], .5) is None


def test_cost_uses_cache_price_and_never_guesses_missing_data():
    assert stats.call_cost(row(0, input_tokens=1_000_000, output_tokens=100_000, cached_tokens=400_000), RATES) == pytest.approx(2.28)
    # Không báo cache: tính như không có cache (ước tính cao hơn), không bỏ qua.
    assert stats.call_cost(row(0, input_tokens=1_000_000, output_tokens=0), RATES) == pytest.approx(2.0)
    assert stats.call_cost(row(0, input_tokens=None, output_tokens=5), RATES) is None
    assert stats.call_cost(row(0, slug="grok-4.7", input_tokens=10, output_tokens=5), RATES) is None


def test_summary_marks_unpriced_and_cache_unknown_models():
    now = local(2026, 10, 11, 15)
    rows = [
        row(now - 3600, input_tokens=1_000_000, output_tokens=100_000, cached_tokens=400_000),
        row(now - 3000, input_tokens=1_000_000, output_tokens=0),
        row(now - 2000, service="xai", model="peto", slug="grok-4.7", input_tokens=500, output_tokens=50, cached_tokens=100),
        row(now - 1000, service="anthropic", model="haiku", slug="claude-haiku-5-5"),
    ]
    data = stats.summarize(rows, "7d", now, ZONE, RATES, "ok", data_since=now - 10 * 86400)
    by_key = {item["key"]: item for item in data["models"]}
    assert by_key["luna"]["cost_usd"] == pytest.approx(4.28) and by_key["luna"]["cache_unknown_calls"] == 1
    assert by_key["peto"]["cost_usd"] is None and by_key["peto"]["unpriced_calls"] == 1
    assert by_key["haiku"]["input_tokens"] is None and by_key["haiku"]["missing_usage_calls"] == 1
    assert data["cost"]["total_usd"] == pytest.approx(4.28)
    # xAI và Anthropic có lượt gọi nhưng chưa tính được giá: None, không phải 0.
    assert data["cost"]["by_service"] == {"xai": None, "openai": pytest.approx(4.28), "anthropic": None}
    assert set(data["cost"]["unpriced_models"]) == {"Peto", "Haiku 5.5"}
    assert data["cost"]["cache_unknown_models"] == ["6 Luna"]


def test_summary_without_rates_has_no_total():
    now = local(2026, 10, 11, 15)
    data = stats.summarize([row(now - 60, input_tokens=10, output_tokens=5)], "24h", now, ZONE, {}, "missing", now - 600)
    assert data["cost"]["total_usd"] is None and data["cost"]["rates"] == "missing"
    assert data["models"][0]["cost_usd"] is None and data["calls"] == 1


def test_days_follow_local_midnight_and_coverage():
    now = local(2026, 10, 11, 15)
    rows = [row(local(2026, 10, 11, 0, 30), input_tokens=1, output_tokens=1),   # 00:30 giờ VN, tức 17:30 UTC hôm trước
            row(local(2026, 10, 10, 23, 30), input_tokens=1, output_tokens=1),
            row(local(2026, 9, 1), input_tokens=1, output_tokens=1)]            # ngoài 7 ngày
    data = stats.summarize(rows, "7d", now, ZONE, {}, "missing", data_since=local(2026, 10, 9, 8))
    labels = [bucket["label"] for bucket in data["buckets"]]
    assert labels == ["5/10", "6/10", "7/10", "8/10", "9/10", "10/10", "11/10"]
    assert [bucket["calls"] for bucket in data["buckets"]][-2:] == [1, 1] and data["calls"] == 2
    assert [bucket["empty"] for bucket in data["buckets"]] == [True] * 4 + [False] * 3
    assert data["covered_buckets"] == 3
    assert data["buckets"][-1]["full"] == "Chủ Nhật, 11/10"


def test_hourly_range_has_24_buckets_ending_now():
    now = local(2026, 10, 11, 15, 20)
    data = stats.summarize([row(now - 60, input_tokens=1, output_tokens=1)], "24h", now, ZONE, {}, "missing", now - 3 * 86400)
    assert len(data["buckets"]) == 24 and data["buckets"][-1]["label"] == "15h" and data["buckets"][0]["label"] == "16h"
    assert data["buckets"][-1]["calls"] == 1


def test_previous_period_only_when_fully_covered():
    now = local(2026, 10, 11, 15)
    rows = [row(now - 8 * 86400, input_tokens=1_000_000, output_tokens=0),
            row(now - 3600, input_tokens=1_000_000, output_tokens=0)]
    covered = stats.summarize(rows, "7d", now, ZONE, RATES, "ok", data_since=now - 30 * 86400)
    assert covered["cost"]["previous_total_usd"] == pytest.approx(2.0) and covered["previous_calls"] == 1
    partial = stats.summarize(rows, "7d", now, ZONE, RATES, "ok", data_since=now - 9 * 86400)
    assert partial["cost"]["previous_total_usd"] is None and partial["previous_calls"] is None


def test_outcomes_and_latency_use_completed_turns():
    now = local(2026, 10, 11, 15)
    turn = lambda outcome, complete, ms, first=None: row(now - 60, "turn", surface="chat", outcome=outcome,
                                                        complete=complete, elapsed_ms=ms, first_text_ms=first)
    rows = [turn("complete", 1, 2000, 500), turn("complete", 1, 4000, 700), turn("stopped", 0, 900_000, 300),
            turn("timeout", 0, 300_000), turn("provider_error", 0, 100), turn("queue_full", 0, 0),
            turn("complete", 0, 50)]
    data = stats.summarize(rows, "7d", now, ZONE, {}, "missing", now - 86400)
    assert {item["key"]: item["count"] for item in data["outcomes"]} == {
        "complete": 2, "stopped": 1, "error": 1, "timeout": 1, "other": 2}
    assert data["success_rate"] == pytest.approx(2 / 7, abs=1e-4)
    # Lượt dừng hay hết giờ không làm méo thời gian "trả lời xong".
    assert data["latency"]["p50_ms"] == 2000 and data["latency"]["p95_ms"] == 4000
    assert data["latency"]["first_p50_ms"] == 500
    assert data["models"][0]["surfaces"] == ["chat"]


# --- Tệp giá ----------------------------------------------------------------------------------------------------

def test_rates_file_states(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "COST_RATES_FILE", "")
    assert rate_file.load() == ({}, "missing")
    path = tmp_path / "gia.json"
    monkeypatch.setattr(config, "COST_RATES_FILE", str(path))
    assert rate_file.load() == ({}, "invalid")
    path.write_text(json.dumps(RATES), encoding="utf-8")
    assert rate_file.load() == (RATES, "ok")
    path.write_text('{"gpt-6-luna": {"input": -1}}', encoding="utf-8")
    assert rate_file.load() == ({}, "invalid")
