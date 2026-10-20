"""Model limits and bounded request estimates, inspired by OpenCode V2 compaction/model-request.

Catalog verified 2026-10-20; deployment output caps are independent of model maximums.
Unknown/custom slugs use a conservative 200k application budget, explicitly marked unknown.
"""
from __future__ import annotations

import json
import os

from core import config
from ai.models import MODELS
from features.agent import assembly
from features.agent.assembly import CATALOG, ceiling, estimate  # noqa: F401 - nơi khác lấy qua đây


def limits(key: str) -> dict:
    model = MODELS[key]
    slug = config.AGENT_MODEL if key == "peto" else model.slug
    cap = {"openai": config.OPENAI_MAX_OUTPUT_TOKENS,
           "anthropic": config.ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS}.get(model.service, config.XAI_MAX_OUTPUT_TOKENS)
    override = json.loads(os.environ.get("PETO_AGENT_CONTEXT_LIMITS", "{}"))
    return assembly.limits(model.service, slug, cap, override)


def request_budget(key: str, instructions: str, tools: list, items: list, *, compact=False, web_search=False) -> dict:
    return assembly.request_budget(limits(key), key, instructions, tools, items, compact=compact, web_search=web_search,
                                   max_request_bytes=config.AGENT_MAX_REQUEST_BYTES)
