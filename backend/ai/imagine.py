"""Peto tạo ảnh — chỉ gọi từ tab Tạo ảnh, không phải từ chat.

Dùng REST ``/v1/images/generations`` hoặc ``/v1/images/edits`` của xAI. Chat thường cố ý không có công
cụ tạo ảnh để tránh vẽ nhầm khi người dùng chỉ đang nói chuyện.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import httpx

from attachments import sniff_image_mime
from config import (
    AI_PROVIDER,
    IMAGINE_MODEL,
    IMAGINE_TIMEOUT_SECONDS,
    XAI_API_BASE,
)
from xai_auth import XaiAuth, XaiAuthError

from .base import ProviderError

logger = logging.getLogger("peto_web.imagine")

QUALITIES = {"low", "medium"}
RESOLUTIONS = {"1k", "2k"}
ASPECT_RATIOS = {
    "auto",
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "2:1",
    "1:2",
}

# PNG 1×1 — chỉ dùng khi PETO_AI_PROVIDER=mock, không gọi mạng.
_MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str


def _friendly_http_error(status: int, body: str) -> str:
    lowered = (body or "").casefold()
    if status in {401, 403}:
        return "Peto cần được kết nối lại với dịch vụ tạo ảnh. Báo người quản trị giúp nhé."
    if status == 429:
        return "Peto đang tạo nhiều ảnh quá. Đợi chút rồi thử lại nha."
    if status == 400:
        if "moderat" in lowered or "content policy" in lowered:
            return "Peto chưa thể tạo ảnh từ mô tả này. Đổi mô tả rồi thử lại nhé."
        return "Yêu cầu tạo ảnh không hợp lệ. Thử đổi mô tả hoặc tùy chọn."
    return "Peto gặp lỗi khi tạo ảnh. Thử lại sau nha."


def _decode_payload(item: dict) -> GeneratedImage | None:
    raw = b""
    if item.get("b64_json"):
        try:
            raw = base64.b64decode(item["b64_json"], validate=True)
        except (ValueError, TypeError):
            return None
    if not raw:
        return None
    mime = sniff_image_mime(raw)
    if mime is None:
        return None
    return GeneratedImage(data=raw, mime=mime)


async def _download_url(client: httpx.AsyncClient, url: str) -> GeneratedImage | None:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Không tải được ảnh từ URL tạm")
        return None
    raw = response.content
    mime = sniff_image_mime(raw)
    if mime is None:
        return None
    return GeneratedImage(data=raw, mime=mime)


async def generate_images(
    *,
    prompt: str,
    quality: str,
    resolution: str,
    aspect_ratio: str,
    n: int,
    source_image: GeneratedImage | None = None,
) -> list[GeneratedImage]:
    """Gọi xAI (hoặc mock) và trả về bytes ảnh đã sẵn sàng để lưu."""
    if AI_PROVIDER == "mock":
        if "__error__" in prompt:
            raise ProviderError("Nhà cung cấp ảnh đang lỗi (giả lập). Thử lại sau nhé.")
        return [GeneratedImage(data=_MOCK_PNG, mime="image/png") for _ in range(n)]

    try:
        token = await XaiAuth().get_access_token()
    except XaiAuthError as err:
        raise ProviderError(
            "Peto chưa được kết nối với dịch vụ tạo ảnh. "
            "Báo người quản trị giúp nhé."
        ) from err

    payload = {
        "model": IMAGINE_MODEL,
        "prompt": prompt,
        "n": n,
        "response_format": "b64_json",
        "quality": quality,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
    }
    endpoint = "edits" if source_image is not None else "generations"
    if source_image is not None:
        encoded = base64.b64encode(source_image.data).decode("ascii")
        payload["image"] = {"url": f"data:{source_image.mime};base64,{encoded}", "type": "image_url"}
    url = f"{XAI_API_BASE.rstrip('/')}/images/{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=IMAGINE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise ProviderError(
                    _friendly_http_error(response.status_code, response.text),
                    retryable=response.status_code >= 500 or response.status_code == 429,
                )
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise ProviderError("Peto nhận được dữ liệu ảnh không hợp lệ. Thử lại nhé.", retryable=True)
            images: list[GeneratedImage] = []
            for item in body["data"][:n]:
                if not isinstance(item, dict):
                    continue
                decoded = _decode_payload(item)
                if decoded is None and item.get("url"):
                    decoded = await _download_url(client, str(item["url"]))
                if decoded is not None:
                    images.append(decoded)
    except ProviderError:
        raise
    except httpx.TimeoutException as err:
        raise ProviderError("Tạo ảnh lâu quá nên bỏ lượt này. Thử lại nha.", retryable=True) from err
    except httpx.HTTPError as err:
        raise ProviderError("Peto chưa kết nối được với dịch vụ tạo ảnh. Thử lại sau chút nhé.", retryable=True) from err
    except ValueError as err:
        raise ProviderError("Peto nhận được dữ liệu ảnh không hợp lệ. Thử lại nha.", retryable=True) from err

    if not images:
        raise ProviderError("Peto chưa tạo được ảnh nào. Đổi mô tả rồi thử lại nhé.")
    return images
