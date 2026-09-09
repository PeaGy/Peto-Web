"""Giới hạn tải cho Peto Web.

Rút gọn từ ``guild_ai_settings.py`` của bot Discord: cooldown theo người,
số yêu cầu chạy đồng thời tối đa, và hàng chờ có giới hạn kèm timeout. Mục
đích như bản gốc — một yêu cầu chậm không được giữ cả nhóm bạn phải đợi.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from config import (
    COOLDOWN_SECONDS,
    MAX_CONCURRENT,
    MAX_QUEUE,
    QUEUE_TIMEOUT_SECONDS,
)


class AdmissionDenied(Exception):
    """Yêu cầu bị từ chối trước khi gọi AI."""

    def __init__(self, reason: str, retry_after: float = 0.0):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = max(0.0, retry_after)

    @property
    def message(self) -> str:
        if self.reason == "cooldown":
            return f"Cậu gửi nhanh quá, đợi {self.retry_after:.0f}s rồi nhắn tiếp nha."
        if self.reason == "queue_full":
            return "Peto đang bận trả lời mấy người khác, thử lại sau chút nha."
        return "Đợi lâu quá nên Peto bỏ lượt này. Cậu gửi lại giúp nha."


class Admission:
    def __init__(
        self,
        *,
        max_concurrent: int = MAX_CONCURRENT,
        max_queue: int = MAX_QUEUE,
        queue_timeout: float = QUEUE_TIMEOUT_SECONDS,
        cooldown: float = COOLDOWN_SECONDS,
    ):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max_queue = max_queue
        self._queue_timeout = queue_timeout
        self._cooldown = cooldown
        self._waiting = 0
        self._last_accepted: dict[str, float] = {}

    @asynccontextmanager
    async def slot(self, user_key: str):
        now = time.monotonic()
        if self._cooldown > 0:
            elapsed = now - self._last_accepted.get(user_key, -1e9)
            if elapsed < self._cooldown:
                raise AdmissionDenied("cooldown", self._cooldown - elapsed)

        if self._sem.locked() and self._waiting >= self._max_queue:
            raise AdmissionDenied("queue_full")

        self._waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._queue_timeout)
        except TimeoutError:
            raise AdmissionDenied("queue_timeout") from None
        finally:
            self._waiting -= 1

        # Chỉ tính cooldown cho yêu cầu thực sự được nhận, không tính lần bị chặn.
        self._last_accepted[user_key] = time.monotonic()
        try:
            yield
        finally:
            self._sem.release()


admission = Admission()
