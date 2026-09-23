"""Compaction boundaries must never split a tool call from its result."""
import copy
import json
from .runner import cap_text

# Công cụ trình duyệt trả danh sách phần tử của trang (xem context.efficient_input).
BROWSER_PAGE_TOOLS = {"browser_open", "browser_click", "browser_type", "browser_press", "browser_login"}


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


def efficient_input(items):
    """Build a transport copy. Keep local history intact and retain every call/result pair."""
    result = copy.deepcopy(items)
    calls = {item.get("call_id"): item.get("name") for item in result if item.get("type") == "function_call"}
    seen_reads = {}
    tool_results = 0
    for item in reversed(result):
        if item.get("type") != "function_call_output":
            continue
        tool_results += 1
        try:
            value = json.loads(item.get("output", ""))
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        name = calls.get(item.get("call_id"))
        if name == "read_file" and isinstance(value.get("content"), str) and not value.get("error"):
            # Entire metadata (including guidance and ranges) must match, not just path or a substring.
            signature = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if signature in seen_reads:
                value.pop("content")
                value["content_reference"] = seen_reads[signature]
                value["note"] = "Nội dung giống hệt kết quả read_file mới hơn có call_id này; xem bản đó trong ngữ cảnh."
            else:
                seen_reads[signature] = item.get("call_id")
        elif name == "run_command" and tool_results > 6 and isinstance(value.get("output"), str):
            output = value["output"]
            if len(output) > 4000:
                value["output"] = cap_text(output, 4000)
                value["output_truncated_for_context"] = True
                value["note"] = "Output cũ đã thu gọn; bản đầy đủ còn trong lịch sử cục bộ. Không suy đoán phần bị bỏ."
        elif name == "browser_read" and tool_results > 6 and isinstance(value.get("text"), str):
            # Chữ của một trang có thể tới 20.000 ký tự; lần đọc cũ thì trang thường đã đổi, gửi lại đủ là phí.
            if len(value["text"]) > 4000:
                value["text"] = cap_text(value["text"], 4000)
                value["text_truncated_for_context"] = True
                value["note"] = "Chữ cũ đã thu gọn; đọc lại trang nếu cần phần bị bỏ."
        elif name in BROWSER_PAGE_TOOLS and tool_results > 6:
            # Danh sách phần tử (tới 80 mục mỗi lần mở trang) của những lần xem, thao tác cũ: trang đã đổi, số trong
            # ngoặc có thể không còn, nên chỉ giữ phần đầu cho ngữ cảnh.
            for key, keep in (("outline", 10), ("elements", 10), ("appeared", 5)):
                if isinstance(value.get(key), list) and len(value[key]) > keep:
                    value[key] = value[key][:keep] + [f"… (bỏ {len(value[key]) - keep} mục cũ)"]
                    value["note"] = "Kết quả cũ đã thu gọn; số trong ngoặc có thể đã đổi, xem kết quả mới nhất."
        encoded = json.dumps(value, ensure_ascii=False)
        # A reference note can cost more than a tiny file. Optimize only when it actually shrinks the payload.
        if len(encoded) < len(item["output"]):
            item["output"] = encoded
    return result
