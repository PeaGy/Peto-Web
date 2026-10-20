"""Model-aware context accounting; provider usage anchors estimates, never execution permissions."""
from __future__ import annotations

import math


def estimate(value) -> int:
    if isinstance(value, dict):
        if value.get("type") == "input_image":
            return 1500
        return sum(estimate(key) + estimate(child) for key, child in value.items()
                   if key not in {"encrypted_content", "id", "status", "image_url"}) + 4
    if isinstance(value, list):
        return sum(estimate(child) for child in value)
    return math.ceil(len(str(value).encode("utf-8")) / 4) if value is not None else 0


def ceiling(info: dict) -> int:
    window = info.get("input") or info["context"]
    reserve = max(window // 10, 16_000 if window >= 32_000 else 0)
    return max(1, min(window - reserve, info["context"] - min(info["output"], reserve)))


def clean(value) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("identity"), str) or not value["identity"]:
        return None
    if any(type(value.get(key)) is not int or not 1024 <= value[key] <= 10_000_000
           for key in ("context", "input", "output")):
        return None
    if value["input"] > value["context"] or value["output"] >= value["context"]:
        return None
    return {key: value[key] for key in ("identity", "context", "input", "output")}


class Tracker:
    def __init__(self):
        self.catalog = {}
        self.overhead = {}
        self.context = {}
        self.anchor = None
        self.max_request_bytes = 16 * 1024 * 1024

    def configure(self, models, transport=None):
        self.catalog = {row["key"]: info for row in models if isinstance(row, dict) and isinstance(row.get("key"), str)
                        and (info := clean(row.get("context_limits")))}
        self.reset()
        self.transport(transport)

    def transport(self, value):
        size = value.get('max_request_bytes') if isinstance(value, dict) else None
        if type(size) is int and 64 * 1024 <= size <= 32 * 1024 * 1024:
            self.max_request_bytes = size

    def reset(self):
        self.anchor = None

    def observe(self, model, value, context=None, *, key=None):
        # key: khóa trong danh mục (Selection.budget_key); nguồn Peto dùng đúng khóa model của máy chủ.
        key = key or model
        if not (info := clean(value)) or value.get("model") != model:
            return
        if self.catalog.get(key) != info:
            self.reset()
        self.catalog[key] = info
        self.context[key] = estimate(context or {})
        overhead = value.get("overhead_tokens")
        if type(overhead) is int and 0 <= overhead <= 10_000_000:
            self.overhead[key] = overhead
        self.transport(value)

    def measured(self, model, items, usage):
        if model not in self.catalog:
            return
        values = (usage.get("input_tokens"), usage.get("output_tokens"))
        if any(type(value) is not int or value < 0 for value in values) or not values[0]:
            return
        # input_tokens already includes cache reads; output_tokens already includes reasoning on Responses.
        self.anchor = (model, sum(values), estimate(items), self.overhead.get(model, 8000), len(items))

    def tokens(self, model, items, extra=0):
        raw, overhead = estimate(items), self.overhead.get(model, 8000) + extra
        if self.anchor and self.anchor[0] == model and len(items) >= self.anchor[4]:
            _, measured, baseline, previous_overhead, _ = self.anchor
            return measured + math.ceil(1.15 * (max(0, raw - baseline) + max(0, overhead - previous_overhead)))
        return math.ceil(1.15 * (raw + overhead))

    def share(self, model, items, extra=0):
        info = self.catalog.get(model)
        return self.tokens(model, items, extra) / ceiling(info) if info else None
