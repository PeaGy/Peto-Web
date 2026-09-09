"""Nhà cung cấp AI thật: Grok qua xAI Responses API.

Theo đúng cách bot Discord đang gọi (``GrokChat._create_response``): OpenAI SDK
trỏ vào ``https://api.x.ai/v1``, gắn access token mới nhất trước mỗi lượt, và
truyền ``reasoning.effort`` để chat thường không phải trả giá suy luận sâu.

Khác bot: ở đây bật ``stream=True`` để chữ chảy dần trên web, và KHÔNG khai báo
tool nào — web bước này chưa có công cụ.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from config import XAI_API_BASE, XAI_MAX_OUTPUT_TOKENS, XAI_MODEL
from xai_auth import XaiAuth, XaiAuthError

from .base import ChatMessage, ChatProvider, ProviderError

logger = logging.getLogger("peto_web.xai")


class XAIProvider(ChatProvider):
    name = "xai"

    def __init__(self) -> None:
        self._auth = XaiAuth()
        # api_key được thay trước mỗi lượt gọi; giá trị khởi tạo chỉ là chỗ giữ.
        self._client = AsyncOpenAI(api_key="pending", base_url=XAI_API_BASE)

    async def _prepare(self) -> None:
        try:
            self._client.api_key = await self._auth.get_access_token()
        except XaiAuthError as err:
            raise ProviderError(
                "Máy chủ chưa đăng nhập xAI nên Peto chưa trả lời được. "
                "Người quản trị cần chạy lại lệnh đăng nhập."
            ) from err

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
    ) -> AsyncIterator[str]:
        await self._prepare()

        payload_input = [
            {"role": m.role, "content": [{"type": "input_text", "text": m.content}]}
            if m.role == "user"
            else {"role": m.role, "content": [{"type": "output_text", "text": m.content}]}
            for m in messages
        ]

        try:
            stream = await self._client.responses.create(
                model=XAI_MODEL,
                instructions=system_prompt,
                input=payload_input,
                max_output_tokens=XAI_MAX_OUTPUT_TOKENS,
                reasoning={
                    "effort": effort if effort in {"low", "medium", "high"} else "low"
                },
                stream=True,
            )
        except AuthenticationError as err:
            logger.warning("xAI từ chối xác thực: %s", err)
            raise ProviderError(
                "Token xAI không còn hợp lệ. Người quản trị cần đăng nhập lại."
            ) from err
        except RateLimitError as err:
            raise ProviderError(
                "xAI đang giới hạn tần suất. Đợi chút rồi thử lại nha.",
                retryable=True,
            ) from err
        except APIConnectionError as err:
            raise ProviderError(
                "Không kết nối được tới xAI. Kiểm tra mạng giúp nha.",
                retryable=True,
            ) from err
        except APIStatusError as err:
            logger.warning("xAI HTTP %s: %s", err.status_code, err)
            raise ProviderError(
                f"xAI trả lỗi {err.status_code}. Thử lại sau nha.",
                retryable=err.status_code >= 500,
            ) from err

        async for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    yield delta
            elif event_type == "response.failed":
                logger.warning("xAI response.failed: %s", event)
                raise ProviderError("xAI bỏ dở câu trả lời. Thử lại nha.", retryable=True)
            elif event_type == "error":
                logger.warning("xAI error event: %s", event)
                raise ProviderError("xAI báo lỗi giữa chừng. Thử lại nha.", retryable=True)
