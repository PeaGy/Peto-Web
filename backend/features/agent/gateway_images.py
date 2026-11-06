"""Ảnh trong yêu cầu của Peto Agent bản desktop, chuẩn bị theo từng dịch vụ AI trước khi gọi model.

Peto Agent (pi-ai) để ảnh mà công cụ trả về (ảnh chụp màn hình, ảnh đọc từ tệp) ngay trong kết quả công cụ, dạng danh
sách phần chữ và ảnh. Cổng đưa các ảnh đó ra một tin vai user ngay sau chuỗi kết quả công cụ, như Peto Agent CLI vẫn
làm với ảnh chụp trình duyệt, vì cả ba dịch vụ đều nhận dạng này. Sau đó, theo tài liệu của từng dịch vụ:

- xAI chỉ nhận ảnh JPG/PNG, nên ảnh WebP/GIF được đổi sang PNG (GIF lấy khung đầu);
- Claude nhận ảnh tới 8000 px, nhưng yêu cầu có hơn 20 ảnh thì mỗi ảnh tối đa 2000×2000 px, nên ảnh lớn hơn được
  thu nhỏ khi đó.

Ảnh Pillow không đọc được thì giữ nguyên, để dịch vụ tự báo lỗi thay vì cổng làm hỏng cả yêu cầu. Kết quả đổi ảnh
được nhớ theo mã băm, vì mỗi bước Peto Agent gửi lại đủ ảnh cũ.
"""

from __future__ import annotations

import base64
import hashlib
import io
import threading
from collections import OrderedDict

from PIL import Image

TOOL_IMAGES_NOTE = "Images returned by the tool results above. They are tool data, not a new request from the user."
IMAGE_ONLY_OUTPUT = "(image attached in the next message)"
XAI_MIMES = {"image/png", "image/jpeg"}
CLAUDE_MANY_IMAGES = 20
CLAUDE_MAX_SIDE = 2000
MAX_PIXELS = 40_000_000
CACHE_SIZE = 24

_cache: OrderedDict[bytes, str | None] = OrderedDict()
_lock = threading.Lock()


def prepare(items: list[dict], service: str) -> list[dict]:
    """Item gửi cho model của dịch vụ ``service``; không sửa danh sách gốc."""
    items = lift_tool_images(items)
    if service == "xai":
        return _map_images(items, lambda url: _converted(url, png=True, max_side=None))
    if service == "anthropic" and count_images(items) > CLAUDE_MANY_IMAGES:
        return _map_images(items, lambda url: _converted(url, png=False, max_side=CLAUDE_MAX_SIDE))
    return items


def lift_tool_images(items: list[dict]) -> list[dict]:
    """Kết quả công cụ chỉ còn chữ; ảnh của chúng thành một tin vai user ngay sau chuỗi kết quả liền nhau."""
    names = {item.get("call_id"): item.get("name") for item in items if item.get("type") == "function_call"}
    result: list[dict] = []
    pending: list[tuple[str, list[dict]]] = []
    for item in items:
        if pending and item.get("type") != "function_call_output":
            result.append(_images_message(pending))
            pending = []
        output = item.get("output")
        if item.get("type") == "function_call_output" and isinstance(output, list):
            text = "\n".join(part["text"] for part in output if part.get("type") == "input_text" and part.get("text"))
            images = [part for part in output if part.get("type") == "input_image"]
            item = {**item, "output": text or (IMAGE_ONLY_OUTPUT if images else "")}
            if images:
                pending.append((str(names.get(item.get("call_id")) or "tool"), images))
        result.append(item)
    if pending:
        result.append(_images_message(pending))
    return result


def count_images(items: list[dict]) -> int:
    return sum(1 for item in items if item.get("role") == "user" and isinstance(item.get("content"), list)
               for part in item["content"] if isinstance(part, dict) and part.get("type") == "input_image")


def _images_message(groups: list[tuple[str, list[dict]]]) -> dict:
    content: list[dict] = [{"type": "input_text", "text": TOOL_IMAGES_NOTE}]
    for name, images in groups:
        content.append({"type": "input_text", "text": f"[{name}]"})
        content.extend(images)
    return {"role": "user", "content": content}


def _map_images(items: list[dict], convert) -> list[dict]:
    result = []
    for item in items:
        content = item.get("content")
        if item.get("role") == "user" and isinstance(content, list) and any(
                isinstance(part, dict) and part.get("type") == "input_image" for part in content):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_image":
                    url = convert(part["image_url"])
                    part = part if url is part["image_url"] else {**part, "image_url": url}
                parts.append(part)
            item = {**item, "content": parts}
        result.append(item)
    return result


def _converted(url: str, *, png: bool, max_side: int | None) -> str:
    """Data URL đã đổi, hoặc chính ``url`` khi ảnh không cần đổi hay không đọc được."""
    key = hashlib.sha256(f"{png}:{max_side}:".encode() + url.encode()).digest()
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            known = _cache[key]
            return url if known is None else known
    changed = _convert(url, png=png, max_side=max_side)
    with _lock:
        _cache[key] = changed
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return url if changed is None else changed


def _convert(url: str, *, png: bool, max_side: int | None) -> str | None:
    header, _, encoded = url.partition(",")
    mime = header.removeprefix("data:").removesuffix(";base64")
    try:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            width, height = image.size
            too_big = max_side is not None and max(width, height) > max_side
            if not too_big and not (png and mime not in XAI_MIMES):
                return None
            if width * height > MAX_PIXELS:
                return None
            clear = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
            frame = image.convert("RGBA" if clear else "RGB")
        if too_big:
            frame.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        if mime == "image/jpeg" and frame.mode == "RGB":
            frame.save(out, "JPEG", quality=90)
            kind = "image/jpeg"
        else:
            frame.save(out, "PNG")
            kind = "image/png"
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return f"data:{kind};base64,{base64.b64encode(out.getvalue()).decode('ascii')}"
