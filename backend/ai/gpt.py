"""6 Luna, 5.6 Terra và 6 Sol qua Responses API của OpenAI, dùng ``OPENAI_API_KEY`` của máy chủ.

Vòng công cụ, tìm web và nguồn tham khảo dùng chung với Peto (``ResponsesProvider`` trong ``ai/xai.py``). Ai được
chọn model nào thì ``ai_models.py`` kiểm trước khi tới đây.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MAX_OUTPUT_TOKENS

from .base import ProviderError
from .xai import ResponsesProvider


class GPTProvider(ResponsesProvider):
    name = "openai"
    service = "OpenAI"
    auth_error_message = "Khóa OpenAI của máy chủ Peto không dùng được. Chọn Peto để chat tiếp nhé."

    def __init__(self, slug: str, label: str) -> None:
        self.model = slug
        self.max_output_tokens = OPENAI_MAX_OUTPUT_TOKENS
        self.rate_limit_message = (f"{label} đang bị OpenAI giới hạn lượt hoặc đã hết hạn mức. Chọn Peto để chat tiếp, "
                                   "hoặc thử lại sau nhé.")
        # Thư viện openai báo lỗi ngay khi khóa rỗng, nên giữ chỗ; _prepare từ chối trước khi gọi.
        self._client = AsyncOpenAI(api_key=OPENAI_API_KEY or "chua-co-khoa")

    async def _prepare(self) -> None:
        if not OPENAI_API_KEY:
            raise ProviderError("Máy chủ Peto chưa có khóa OpenAI. Chọn Peto để chat tiếp nhé.")
