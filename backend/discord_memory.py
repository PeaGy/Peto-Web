"""Đọc trí nhớ dài hạn của người dùng từ bot Discord.

Gọi Memory Gateway (`features/memory_gateway.py` bên repo bot) qua loopback.
Một chiều, chỉ đọc: web không bao giờ ghi ngược vào `bot_memory.db`.

Nguyên tắc quan trọng nhất: **hỏng thì bỏ qua**. Bot tắt, mạng lỗi, token sai —
Peto vẫn phải trả lời được, chỉ là không có trí nhớ cũ. Không bao giờ để việc
này làm chết một cuộc trò chuyện.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from config import (
    MEMORY_GATEWAY_TIMEOUT,
    MEMORY_GATEWAY_TOKEN,
    MEMORY_GATEWAY_URL,
    MEMORY_CACHE_TTL,
)

logger = logging.getLogger("peto_web.discord_memory")


@dataclass(frozen=True)
class MemorySnapshot:
    summary: str = ""
    explicit: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.summary and not self.explicit


EMPTY = MemorySnapshot()


class DiscordMemory:
    def __init__(
        self,
        *,
        base_url: str = MEMORY_GATEWAY_URL,
        token: str = MEMORY_GATEWAY_TOKEN,
        ttl: float = MEMORY_CACHE_TTL,
        timeout: float = MEMORY_GATEWAY_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.ttl = ttl
        self.timeout = timeout
        self._cache: dict[str, tuple[float, MemorySnapshot]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.token)

    def forget(self, discord_id: str) -> None:
        self._cache.pop(discord_id, None)

    async def fetch(self, discord_id: str) -> MemorySnapshot:
        """Trả về trí nhớ của đúng người này. Lỗi gì cũng trả về EMPTY."""
        if not self.enabled or not discord_id.isdigit():
            return EMPTY

        now = time.monotonic()
        cached = self._cache.get(discord_id)
        if cached and cached[0] > now:
            return cached[1]

        url = f"{self.base_url}/internal/memory/{discord_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, headers={"X-Peto-Token": self.token}
                )
        except httpx.HTTPError as err:
            # Bot không chạy là chuyện bình thường khi dev — chỉ ghi log gọn.
            logger.warning("Không gọi được Memory Gateway: %s", type(err).__name__)
            return EMPTY

        if response.status_code == 401:
            logger.error(
                "Memory Gateway từ chối token của web. Kiểm tra "
                "MEMORY_GATEWAY_TOKEN ở hai bên có khớp không."
            )
            return EMPTY
        if response.status_code != 200:
            logger.warning("Memory Gateway trả HTTP %s", response.status_code)
            return EMPTY

        try:
            payload = response.json()
        except ValueError:
            logger.warning("Memory Gateway trả về JSON hỏng")
            return EMPTY

        if not payload.get("available"):
            # Chưa có trí nhớ, hoặc người này đang bật chế độ ẩn danh.
            snapshot = EMPTY
        else:
            explicit = payload.get("explicit") or []
            snapshot = MemorySnapshot(
                summary=str(payload.get("summary") or "").strip(),
                explicit=tuple(
                    str(item).strip() for item in explicit if str(item).strip()
                ),
            )

        self._cache[discord_id] = (now + self.ttl, snapshot)
        return snapshot


discord_memory = DiscordMemory()
