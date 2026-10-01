"""Định dạng sự kiện SSE dùng trong stream chat."""

from __future__ import annotations
import json


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

