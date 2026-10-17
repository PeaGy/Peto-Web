"""Đối chiếu lời gọi/kết quả theo thứ tự, không phát lại công cụ khi khôi phục phiên."""

INTERRUPTED_RESULT = {"error": "Peto bị ngắt giữa chừng (lỗi chương trình, đóng terminal hoặc máy tắt) trước khi có kết quả này. "
                               "Công cụ có thể đã chạy một phần: đọc lại tệp hoặc kiểm tra trạng thái trước khi làm tiếp."}


def interrupted_items(items):
    """Trả bản sao kèm kết quả bị ngắt cho các lời gọi thiếu kết quả; call_id có thể dùng lại ở bước sau."""
    import json

    pending = []
    for item in items:
        if item.get("type") == "function_call":
            pending.append(item)
        elif item.get("type") == "function_call_output":
            for index, call in enumerate(pending):
                if call.get("call_id") == item.get("call_id"):
                    pending.pop(index)
                    break
    result = list(items)
    for call in pending:
        result.append({"type": "function_call_output", "call_id": call.get("call_id", ""),
                       "output": json.dumps(INTERRUPTED_RESULT, ensure_ascii=False)})
    return result, len(pending)
