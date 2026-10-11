"""Tổng hợp usage_events thành số liệu cho trang Quản trị.

Chỉ trả số đã gộp: không owner, không nội dung, không dòng log thô. Thiếu token hoặc đơn giá thì để trống
(None), không bao giờ coi là 0. Chi phí là ước tính từ token và tệp giá, không phải hóa đơn.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import time
from zoneinfo import ZoneInfo

from ai.models import MODELS
from shared.time_tools import resolve_timezone
from storage.connection import connect

from ops.report import token_cost

from . import rates as rate_file

RANGES = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
SERVICES = ("xai", "openai", "anthropic")
WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
# Nhóm kết quả lượt cho giao diện; nhãn kỹ thuật lạ rơi vào "khác".
OUTCOME_GROUPS = {
    "complete": "complete",
    "stopped": "stopped", "cancelled": "stopped",
    "provider_error": "error", "internal_error": "error",
    "timeout": "timeout",
}
OUTCOME_ORDER = ("complete", "stopped", "error", "timeout", "other")
NOT_COUNTED = ("Tạo ảnh (tính theo ảnh)", "Phí tra web (tính theo lượt)", "Giọng Peto (tính theo ký tự)")

COLUMNS = ("at", "kind", "surface", "purpose", "service", "model", "slug", "outcome", "complete", "elapsed_ms",
           "first_text_ms", "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens", "search_calls",
           "cache_write_tokens")
# Anthropic tính token ghi cache 5 phút bằng 1,25 lần giá đầu vào; phần đầu vào thường đã có trong input_tokens.
ANTHROPIC_CACHE_WRITE_PREMIUM = 0.25


def percentile(values: list[int], share: float) -> int | None:
    """Nearest-rank, giống ops.report: không nội suy giá trị không có thật."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * share) - 1]


def call_cost(row: dict, rates: dict) -> float | None:
    """USD của một lần gọi; None khi thiếu đơn giá hoặc token. Thiếu token cache thì tính như không có cache."""
    rate = rates.get(row.get("slug") or "")
    incoming, outgoing = row.get("input_tokens"), row.get("output_tokens")
    if not rate or incoming is None or outgoing is None:
        return None
    cached = min(row.get("cached_tokens") or 0, incoming)
    if row.get("service") != "anthropic":
        return token_cost(rate, incoming, cached, outgoing)
    return token_cost(rate, incoming, cached, outgoing, row.get("cache_write_tokens") or 0, ANTHROPIC_CACHE_WRITE_PREMIUM)


@dataclass
class _Model:
    key: str
    service: str
    slugs: set = field(default_factory=set)
    surfaces: set = field(default_factory=set)
    calls: int = 0
    side_calls: int = 0
    usage_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_reported: int = 0
    reasoning_tokens: int = 0
    priced_calls: int = 0
    cost: float = 0.0
    turns: int = 0
    complete_turns: int = 0
    totals: list = field(default_factory=list)
    firsts: list = field(default_factory=list)


def _model_key(row: dict) -> str:
    if row.get("model") in MODELS:
        return row["model"]
    if row.get("service") == "xai":
        return "peto"
    return row.get("slug") or row.get("model") or "unknown"


def _bucket_starts(range_key: str, now: float, zone: ZoneInfo) -> list[datetime]:
    local = datetime.fromtimestamp(now, zone)
    if range_key == "24h":
        top = local.replace(minute=0, second=0, microsecond=0)
        return [top - timedelta(hours=23 - index) for index in range(24)]
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    days = RANGES[range_key]
    # Theo ngày lịch: lùi từng ngày rồi gắn lại múi giờ, để ngày đổi giờ mùa hè vẫn bắt đầu lúc 0 giờ.
    return [datetime.combine((midnight - timedelta(days=days - 1 - index)).date(), datetime.min.time(), zone)
            for index in range(days)]


def summarize(rows: list[dict], range_key: str, now: float, zone: ZoneInfo, rates: dict, rates_status: str,
              data_since: float | None, accounts: int | None = None, dropped: int = 0) -> dict:
    starts = _bucket_starts(range_key, now, zone)
    edges = [start.timestamp() for start in starts]
    window_start = edges[0]
    window_end = now
    previous_start = window_start - (window_end - window_start)
    hourly = range_key == "24h"
    buckets = [{"start": edge, "label": f"{start.hour}h" if hourly else f"{start.day}/{start.month}",
                "full": (f"{start.hour}:00–{start.hour}:59, {start.day}/{start.month}" if hourly
                         else f"{WEEKDAYS[start.weekday()]}, {start.day}/{start.month}"),
                "cost": {service: 0.0 for service in SERVICES}, "calls": 0,
                "empty": data_since is None or (edges[index + 1] if index + 1 < len(edges) else window_end) <= data_since}
               for index, (start, edge) in enumerate(zip(starts, edges))]

    models: dict[str, _Model] = {}
    outcomes = {name: 0 for name in OUTCOME_ORDER}
    totals_ms, firsts_ms = [], []
    previous = {"calls": 0, "cost": 0.0}
    searches = 0
    for row in rows:
        at = row["at"]
        if at < previous_start or at >= window_end:
            continue
        cost = call_cost(row, rates) if row["kind"] == "call" else None
        if at < window_start:
            if row["kind"] == "call":
                previous["calls"] += 1
                previous["cost"] += cost or 0.0
            continue
        key = _model_key(row)
        model = models.setdefault(key, _Model(key, row.get("service") or "unknown"))
        if row["kind"] == "call":
            model.calls += 1
            model.side_calls += row.get("purpose") == "side"
            if row.get("slug"):
                model.slugs.add(row["slug"])
            searches += row.get("search_calls") or 0
            if row.get("input_tokens") is not None and row.get("output_tokens") is not None:
                model.usage_calls += 1
                model.input_tokens += row["input_tokens"]
                model.output_tokens += row["output_tokens"]
                model.reasoning_tokens += row.get("reasoning_tokens") or 0
                if row.get("cached_tokens") is not None:
                    model.cache_reported += 1
                    model.cached_tokens += row["cached_tokens"]
            index = max(0, bisect_right(edges, at) - 1)
            buckets[index]["calls"] += 1
            if cost is not None:
                model.priced_calls += 1
                model.cost += cost
                service = row.get("service")
                if service in buckets[index]["cost"]:
                    buckets[index]["cost"][service] += cost
        else:
            model.turns += 1
            if row.get("surface"):
                model.surfaces.add(row["surface"])
            group = OUTCOME_GROUPS.get(row.get("outcome") or "", "other")
            if group == "complete" and not row.get("complete"):
                group = "other"
            outcomes[group] += 1
            if group == "complete":
                model.complete_turns += 1
                if row.get("elapsed_ms") is not None:
                    model.totals.append(row["elapsed_ms"])
                    totals_ms.append(row["elapsed_ms"])
            if row.get("first_text_ms") is not None:
                model.firsts.append(row["first_text_ms"])
                firsts_ms.append(row["first_text_ms"])

    def priced(model: _Model) -> float | None:
        return round(model.cost, 6) if model.priced_calls else None

    model_rows = []
    for model in sorted(models.values(), key=lambda item: (-item.calls, -item.turns, item.key)):
        info = MODELS.get(model.key)
        unpriced_calls = model.calls - model.priced_calls
        model_rows.append({
            "key": model.key, "label": info.label if info else model.key, "service": model.service,
            "slug": ", ".join(sorted(model.slugs)) or (info.slug if info else ""),
            "surfaces": sorted(model.surfaces), "calls": model.calls, "side_calls": model.side_calls,
            "turns": model.turns,
            "success_rate": round(model.complete_turns / model.turns, 4) if model.turns else None,
            "p50_ms": percentile(model.totals, .5), "p95_ms": percentile(model.totals, .95),
            "first_p50_ms": percentile(model.firsts, .5), "first_p95_ms": percentile(model.firsts, .95),
            "input_tokens": model.input_tokens if model.usage_calls else None,
            "cached_tokens": model.cached_tokens if model.cache_reported else None,
            "output_tokens": model.output_tokens if model.usage_calls else None,
            "reasoning_tokens": model.reasoning_tokens if model.usage_calls else None,
            "missing_usage_calls": model.calls - model.usage_calls,
            "cache_unknown_calls": model.usage_calls - model.cache_reported,
            "cost_usd": priced(model), "unpriced_calls": unpriced_calls,
        })

    turns = sum(outcomes.values())
    priced_any = any(row["cost_usd"] is not None for row in model_rows)
    # Có lượt gọi mà không lần nào tính được giá (Peto dùng gói thuê bao xAI): None, không phải $0.
    unpriced_services = {row["service"] for row in model_rows if row["calls"]} - {
        row["service"] for row in model_rows if row["cost_usd"] is not None}
    total = round(sum(sum(b["cost"][service] for b in buckets) for service in SERVICES), 6)
    cost_by_service = {service: None if service in unpriced_services else round(sum(b["cost"][service] for b in buckets), 6)
                       for service in SERVICES}
    covered = 0 if data_since is None else sum(1 for bucket in buckets if not bucket["empty"])
    full_previous = data_since is not None and data_since <= previous_start
    for bucket in buckets:
        bucket["cost"] = {service: round(value, 6) for service, value in bucket["cost"].items()}
    return {
        "range": range_key,
        "timezone": zone.key,
        "generated_at": now,
        "data_since": data_since,
        "buckets": buckets,
        "bucket_unit": "hour" if hourly else "day",
        "covered_buckets": covered,
        "calls": sum(row["calls"] for row in model_rows),
        "turns": turns,
        "success_rate": round(outcomes["complete"] / turns, 4) if turns else None,
        "outcomes": [{"key": name, "count": outcomes[name]} for name in OUTCOME_ORDER],
        "latency": {"p50_ms": percentile(totals_ms, .5), "p95_ms": percentile(totals_ms, .95),
                    "first_p50_ms": percentile(firsts_ms, .5), "first_p95_ms": percentile(firsts_ms, .95)},
        "cost": {
            "total_usd": total if priced_any else None,
            "by_service": cost_by_service if priced_any else None,
            "rates": rates_status,
            "unpriced_models": [row["label"] for row in model_rows if row["unpriced_calls"]],
            "cache_unknown_models": [row["label"] for row in model_rows if row["cache_unknown_calls"] and row["cost_usd"] is not None],
            "previous_total_usd": round(previous["cost"], 6) if full_previous and priced_any else None,
            "not_counted": list(NOT_COUNTED),
        },
        "previous_calls": previous["calls"] if full_previous else None,
        "models": model_rows,
        "searches": searches,
        "accounts": accounts,
        "dropped_events": dropped,
    }


async def overview(range_key: str, now: float | None = None) -> dict:
    from core import usage_events

    now = time.time() if now is None else now
    zone = ZoneInfo(resolve_timezone())
    first_edge = _bucket_starts(range_key, now, zone)[0].timestamp()
    since = first_edge - (now - first_edge)
    async with connect() as db:
        async with db.execute(f"SELECT {', '.join(COLUMNS)} FROM usage_events WHERE at >= ? AND at < ? ORDER BY at",
                              (since, now)) as cursor:
            rows = [dict(zip(COLUMNS, record)) for record in await cursor.fetchall()]
        async with db.execute("SELECT MIN(at) FROM usage_events") as cursor:
            data_since = (await cursor.fetchone())[0]
        # Số tài khoản có hoạt động (tin nhắn chat/Companion hoặc bước Agent): chỉ một con số, không danh sách.
        first_day = datetime.fromtimestamp(first_edge, zone).date().isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM (SELECT c.owner FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            "WHERE m.role = 'user' AND m.created_at >= ? UNION SELECT owner FROM agent_usage WHERE day >= ? AND steps > 0)",
            (first_edge, first_day),
        ) as cursor:
            accounts = (await cursor.fetchone())[0]
    rates, status = rate_file.load()
    return summarize(rows, range_key, now, zone, rates, status, data_since, accounts, usage_events.dropped())
