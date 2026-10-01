"""Tổng hợp log vận hành; không xuất nội dung chat, tài khoản hay credential."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import sys

MARKER = re.compile(r"\b(chat_timing|agent_timing|model_usage)\s+")
FIELD = re.compile(r"([a-z_]+)=([^\s]+)")
LABEL = re.compile(r"[a-zA-Z0-9_.:-]{1,100}\Z")


def number(value):
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def distribution(values):
    values = sorted(values)
    if not values:
        return {"samples": 0, "p50_ms": None, "p95_ms": None}
    return {"samples": len(values), "p50_ms": values[math.ceil(len(values) * .5) - 1],
            "p95_ms": values[math.ceil(len(values) * .95) - 1]}


def validate_rates(raw):
    """Đơn giá do người vận hành cung cấp, USD trên một triệu token."""
    if not isinstance(raw, dict):
        raise ValueError("Bảng đơn giá phải là đối tượng JSON.")
    for model, prices in raw.items():
        if not LABEL.fullmatch(model) or not isinstance(prices, dict):
            raise ValueError("Tên model hoặc đơn giá không hợp lệ.")
        if set(prices) != {"input", "cached_input", "output"}:
            raise ValueError("Mỗi model cần input, cached_input và output.")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in prices.values()):
            raise ValueError("Đơn giá phải là số hữu hạn, không âm.")
    return raw


def summarize(lines, rates=None):
    rates = validate_rates({} if rates is None else rates)
    timings, usage = {}, {}
    malformed = 0
    for line in lines:
        match = MARKER.search(line)
        if not match:
            continue
        kind = match[1]
        fields = dict(FIELD.findall(line[match.end():]))
        labels = (fields.get("model"), fields.get("effort"), fields.get("mode", "agent")) if kind != "model_usage" else (
            fields.get("service"), fields.get("model"), fields.get("purpose"))
        if not all(isinstance(label, str) and LABEL.fullmatch(label) for label in labels):
            malformed += 1
            continue
        if kind != "model_usage":
            total = number(fields.get("total_ms"))
            if total is None or fields.get("complete") not in {"True", "False"}:
                malformed += 1
                continue
            key = (kind, *labels)
            group = timings.setdefault(key, {"kind": kind, "model": labels[0], "effort": labels[1], "mode": labels[2],
                                             "turns": 0, "complete": 0, "outcomes": defaultdict(int), "samples": defaultdict(list)})
            group["turns"] += 1
            group["complete"] += fields["complete"] == "True"
            outcome = fields.get("outcome", "complete" if fields["complete"] == "True" else "incomplete")
            if outcome not in {"complete", "incomplete", "timeout", "provider_error", "internal_error", "cancelled", "empty", "cooldown", "queue_full", "queue_timeout"}:
                outcome = "incomplete"
            group["outcomes"][outcome] += 1
            for field in ("total_ms", "first_text_ms", "queue_ms", "prepare_ms"):
                value = number(fields.get(field))
                if value is not None:
                    group["samples"][field].append(value)
        else:
            group = usage.setdefault(labels, {"service": labels[0], "model": labels[1], "purpose": labels[2],
                                              "calls": 0, "calls_with_usage": 0, "missing_usage": 0,
                                              "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0,
                                              "search_calls_seen": 0, "priced_calls": 0, "estimated_token_usd": None})
            group["calls"] += 1
            group["search_calls_seen"] += number(fields.get("search_calls_seen")) or 0
            incoming, outgoing, cached = (number(fields.get(k)) for k in ("input_tokens", "output_tokens", "cached_tokens"))
            if incoming is None or outgoing is None:
                group["missing_usage"] += 1
                continue
            group["calls_with_usage"] += 1
            group["input_tokens"] += incoming
            group["output_tokens"] += outgoing
            group["cached_tokens"] += cached or 0
            rate = rates.get(labels[1])
            if rate and cached is not None and cached <= incoming:
                cost = ((incoming - cached) * rate["input"] + cached * rate["cached_input"] + outgoing * rate["output"]) / 1_000_000
                group["estimated_token_usd"] = (group["estimated_token_usd"] or 0) + cost
                group["priced_calls"] += 1
    timing_rows = []
    for key in sorted(timings):
        group = timings[key]
        samples = group.pop("samples")
        group["outcomes"] = dict(group["outcomes"])
        group["incomplete"] = group["turns"] - group["complete"]
        group["latency"] = {field: distribution(samples[field]) for field in ("total_ms", "first_text_ms", "queue_ms", "prepare_ms")}
        timing_rows.append(group)
    usage_rows = [usage[key] for key in sorted(usage)]
    for group in usage_rows:
        if group["estimated_token_usd"] is not None:
            group["estimated_token_usd"] = round(group["estimated_token_usd"], 8)
    return {"timings": timing_rows, "model_usage": usage_rows, "malformed_records": malformed,
            "notes": ["Chỉ tổng hợp phạm vi log đầu vào; lượt bị ngắt không đồng nghĩa lỗi mô hình.",
                      "Token chỉ tính phần nhà cung cấp báo lại; thiếu usage hoặc đơn giá không được coi là 0 USD.",
                      "Ước tính chỉ gồm token đã đủ dữ liệu và đơn giá được cung cấp; không phải hóa đơn, không gồm phí tìm web, ảnh, TTS hay thuế.",
                      "purpose trong log provider là nhãn kỹ thuật, không dùng để suy ra tính năng người dùng."]}


def format_report(report):
    lines = ["Báo cáo vận hành Peto — phạm vi log đã cung cấp"]
    for row in report["timings"]:
        total = row["latency"]["total_ms"]
        first = row["latency"]["first_text_ms"]
        lines.append(f"{row['mode']} / {row['model']} / {row['effort']}: {row['turns']} lượt, "
                     f"{row['complete']} hoàn tất, {row['incomplete']} chưa hoàn tất; "
                     f"tổng p50/p95 {total['p50_ms']}/{total['p95_ms']} ms, phản hồi đầu p95 {first['p95_ms']} ms; {row['outcomes']}")
    for row in report["model_usage"]:
        cost = row["estimated_token_usd"]
        lines.append(f"{row['service']} / {row['model']} / {row['purpose']}: {row['calls']} lần gọi, "
                     f"token vào/ra {row['input_tokens']}/{row['output_tokens']}, cache {row['cached_tokens']}; "
                     f"thiếu usage {row['missing_usage']}; USD token ước tính {cost if cost is not None else 'chưa đủ dữ liệu'} "
                     f"({row['priced_calls']}/{row['calls']} lần gọi có giá).")
    if not report["timings"] and not report["model_usage"]:
        lines.append("Chưa có bản ghi vận hành hợp lệ trong log này.")
    lines.append(f"Bản ghi không hợp lệ đã bỏ qua: {report['malformed_records']}")
    if "stored_usage" in report:
        lines.append("Quota đã lưu trong database (toàn bộ ngày/tháng, độc lập phạm vi log):")
        lines.append(json.dumps(report["stored_usage"], ensure_ascii=False))
    lines.extend(report["notes"])
    return "\n".join(lines)


def stored_usage(path):
    """Đọc tổng theo ngày/tháng, không xuất khóa tài khoản và không tạo database mới."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        if "agent_usage" in tables:
            result["agent_daily"] = [dict(row) for row in db.execute(
                "SELECT day, SUM(steps) AS steps, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
                "FROM agent_usage GROUP BY day ORDER BY day")]
        if "voice_usage" in tables:
            result["voice_monthly"] = [dict(row) for row in db.execute(
                "SELECT month, SUM(chars) AS chars FROM voice_usage GROUP BY month ORDER BY month")]
        if "speech_budget" in tables:
            result["speech_reserved"] = [dict(row) for row in db.execute(
                "SELECT month, micros / 1000000.0 AS reserved_usd FROM speech_budget ORDER BY month")]
        return result


def main():
    parser = argparse.ArgumentParser(description="Tổng hợp tốc độ, kết quả và token từ log Peto.")
    parser.add_argument("logs", nargs="*", type=Path, help="Tệp log; bỏ trống để đọc từ đầu vào chuẩn.")
    parser.add_argument("--rates", type=Path, help="JSON đơn giá của từng model, USD trên một triệu token.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", type=Path, help="Tùy chọn đọc tổng quota Agent/TTS từ database, chỉ đọc.")
    args = parser.parse_args()
    try:
        rates = json.loads(args.rates.read_text(encoding="utf-8")) if args.rates else None
        def lines():
            if not args.logs:
                yield from sys.stdin
            for path in args.logs:
                with path.open(encoding="utf-8", errors="replace") as stream:
                    yield from stream
        report = summarize(lines(), rates)
        if args.db:
            report["stored_usage"] = stored_usage(args.db)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Không tạo được báo cáo: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
