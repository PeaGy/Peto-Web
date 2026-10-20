"""Model limits and bounded request estimates, inspired by OpenCode V2 compaction/model-request.

Catalog verified 2026-10-20; deployment output caps are independent of model maximums.
Unknown/custom slugs use a conservative 200k application budget, explicitly marked unknown.
"""
from __future__ import annotations

import json
import math
import os

from core import config
from ai.models import MODELS

# Sources and exact reference commit are recorded in agent-cli/docs/context-budget-0.30.0.md.
CATALOG = {
    "grok-4.7": (500_000, 0),
    "gpt-6-luna": (1_050_000, 128_000),
    "gpt-5.6-terra": (1_050_000, 128_000),
    "gpt-6.1-sol": (1_050_000, 128_000),
    "claude-haiku-5-5": (1_000_000, 128_000),
    "claude-sonnet-5-5": (1_000_000, 128_000),
}


def limits(key: str) -> dict:
    model = MODELS[key]
    slug = config.AGENT_MODEL if key == "peto" else model.slug
    window, maximum = CATALOG.get(slug, (200_000, 0))
    cap = {"openai": config.OPENAI_MAX_OUTPUT_TOKENS,
           "anthropic": config.ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS}.get(model.service, config.XAI_MAX_OUTPUT_TOKENS)
    override = json.loads(os.environ.get("PETO_AGENT_CONTEXT_LIMITS", "{}"))
    entry = override.get(slug, {}) if isinstance(override, dict) else None
    if not isinstance(entry, dict) or any(name not in {"context", "input", "output"} or type(value) is not int
                                         or not 1024 <= value <= 10_000_000 for name, value in entry.items()):
        raise ValueError("PETO_AGENT_CONTEXT_LIMITS must map API model IDs to positive context/input/output token limits")
    window = entry.get("context", window)
    return {"identity": f"{model.service}/{slug}", "context": window,
            "input": min(window, entry.get("input", window)),
            "output": min(cap, entry.get("output", maximum or cap), maximum or 10_000_000, max(1, window - 1024)),
            "known": slug in CATALOG or bool(entry)}


def estimate(value) -> int:
    """UTF-8 bytes / 4 approximation; image bytes and opaque reasoning are not plaintext tokens."""
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


def request_budget(key: str, instructions: str, tools: list, items: list, *, compact=False, web_search=False) -> dict:
    info = limits(key)
    overhead = estimate(instructions) + estimate(tools) + (256 if web_search else 0)
    tokens = math.ceil((overhead + estimate(items)) * 1.15)
    room = info["context"] - tokens
    return {**info, "model": key, "ceiling": ceiling(info), "overhead_tokens": overhead,
            "request_tokens": tokens,
            "max_output_tokens": max(1, min(info["output"], 32_000 if compact else info["output"], room)),
            "max_items": 300, "max_request_bytes": config.AGENT_MAX_REQUEST_BYTES,
            "keep_tokens": 15_000}
