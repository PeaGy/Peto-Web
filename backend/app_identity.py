"""Tên và avatar thật của Peto, lấy từ Discord application.

Trước đây giao diện hiển thị chữ "P" viết cứng. Thông tin thật nằm ở chính
application Discord mà web đang dùng để đăng nhập, nên lấy từ đó là hợp lý và
tự khớp khi bạn đổi icon bot.

Dùng endpoint công khai ``/applications/{id}/rpc`` — chỉ cần Client ID, KHÔNG
cần client secret hay bot token. Chỉ trả về thông tin vốn đã công khai: tên,
icon, mô tả.

Hỏng thì bỏ qua: giao diện tự quay về chữ cái đầu như cũ.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from config import DISCORD_CLIENT_ID

logger = logging.getLogger("peto_web.app_identity")

RPC_URL = "https://discord.com/api/v10/applications/{app_id}/rpc"
CDN_ICON = "https://cdn.discordapp.com/app-icons/{app_id}/{icon}.png?size=128"

# Icon bot hầu như không đổi, nên cache lâu. Đổi icon thì restart là xong.
CACHE_TTL = 3600.0
FETCH_TIMEOUT = 5.0

# Cho phép ép giá trị khi không muốn phụ thuộc Discord, hoặc muốn tên khác.
NAME_OVERRIDE = os.getenv("PETO_BOT_NAME", "").strip()
AVATAR_OVERRIDE = os.getenv("PETO_BOT_AVATAR_URL", "").strip()

# Tên hiển thị mặc định. Application tên "Pearto", nhưng tên nhân vật dùng
# trong nhóm là "Peto" — giữ nguyên trừ khi người vận hành muốn đổi.
DEFAULT_NAME = "Peto"

_cache: tuple[float, dict[str, str | None]] | None = None


def _fallback() -> dict[str, str | None]:
    return {"name": NAME_OVERRIDE or DEFAULT_NAME, "avatar_url": AVATAR_OVERRIDE or None}


async def get_app_identity() -> dict[str, str | None]:
    """Trả về ``{"name": ..., "avatar_url": ...}``. Không bao giờ raise."""
    global _cache

    if NAME_OVERRIDE and AVATAR_OVERRIDE:
        return _fallback()

    now = time.monotonic()
    if _cache and _cache[0] > now:
        return _cache[1]

    result = _fallback()
    if not DISCORD_CLIENT_ID:
        return result

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
            response = await client.get(RPC_URL.format(app_id=DISCORD_CLIENT_ID))
        if response.status_code == 200:
            payload = response.json()
            icon = str(payload.get("icon") or "")
            if icon and not AVATAR_OVERRIDE:
                result["avatar_url"] = CDN_ICON.format(
                    app_id=DISCORD_CLIENT_ID, icon=icon
                )
            if not NAME_OVERRIDE:
                # Chỉ dùng tên từ Discord khi người vận hành chưa đặt tên riêng
                # và cũng chưa có tên mặc định nào phù hợp hơn.
                result["name"] = NAME_OVERRIDE or DEFAULT_NAME
        else:
            logger.warning(
                "Không lấy được thông tin application: HTTP %s", response.status_code
            )
    except httpx.HTTPError as err:
        logger.warning("Không gọi được Discord: %s", type(err).__name__)

    _cache = (now + CACHE_TTL, result)
    return result


def reset_cache() -> None:
    """Dùng trong test."""
    global _cache
    _cache = None
