"""Compaction boundaries must never split a tool call from its result."""
import copy
import json


def text_of(item):
    content = item.get("content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(part["text"] for part in content
                     if isinstance(part, dict) and isinstance(part.get("text"), str))


def compact_prefix(items, keep=24):
    pending = set()
    boundary = 0
    for index, item in enumerate(items[:max(0, len(items) - keep)]):
        if item.get("type") == "function_call":
            pending.add(item.get("call_id"))
        elif item.get("type") == "function_call_output":
            pending.discard(item.get("call_id"))
        if not pending:
            boundary = index + 1
    if boundary < 4:
        return [], items
    prefix = copy.deepcopy(items[:boundary])
    for item in prefix:
        if isinstance(item.get("content"), list):
            item["content"] = [
                {"type": "input_text", "text": "[Ảnh cũ: xem lại ảnh gốc nếu cần; không suy đoán chi tiết.]"}
                if isinstance(part, dict) and part.get("type") == "input_image" else part for part in item["content"]]
    return prefix, items[boundary:]


def context_size(items):
    # Image bytes are not text tokens; request byte limits are checked separately on the server.
    return sum(len(json.dumps(item, ensure_ascii=False)) if not isinstance(item.get("content"), list)
               else len(text_of(item)) for item in items)
