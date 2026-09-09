"""Giao diện chung cho mọi nhà cung cấp AI.

Toàn bộ phần còn lại của backend chỉ nói chuyện qua ``ChatProvider``. Khi chốt
nhà cung cấp thật, chỉ cần thêm một file cài đặt interface này — không phải sửa
route, database hay giới hạn tải.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class ProviderError(RuntimeError):
    """Lỗi từ nhà cung cấp AI, đã được diễn đạt để hiển thị cho người dùng."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ChatProvider(ABC):
    """Một nhà cung cấp có khả năng stream câu trả lời theo từng mảnh."""

    name: str = "base"

    @abstractmethod
    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
    ) -> AsyncIterator[str]:
        """Sinh ra các mảnh text nối tiếp nhau tạo thành câu trả lời.

        Phải raise ``ProviderError`` cho lỗi đã biết cách diễn đạt; các lỗi
        khác để nguyên cho tầng trên bắt và ghi log.
        """
        raise NotImplementedError
        yield ""  # pragma: no cover - giữ chữ ký async generator
