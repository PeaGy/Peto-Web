"""Dữ liệu yêu cầu chat và các lựa chọn được chấp nhận."""

from __future__ import annotations
from typing import Literal, Annotated
from pydantic import BaseModel, Field, model_validator
from ai import models as ai_models


class AttachmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    mime: str = Field(default="", max_length=120)
    data: str = Field(min_length=8)


class ProviderChoiceIn(BaseModel):
    """Bộ não Companion dùng khóa API riêng (Cài đặt Companion → Mô-đun → Bộ não). Khóa không nằm ở đây mà trong header
    X-Peto-Provider-Key (khóa Tavily: X-Peto-Search-Key), dùng cho đúng lượt này rồi bỏ."""
    id: str = Field(min_length=1, max_length=32)
    model: str = Field(default="", max_length=100)
    # Chỉ Azure OpenAI: địa chỉ tài nguyên https://<tên>.openai.azure.com.
    endpoint: str | None = Field(default=None, max_length=200)


class ChatRequest(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def reject_unsupported_privacy(cls, data):
        if isinstance(data, dict) and set(data) & {'temporary', 'temporary_chat', 'retention', 'memory_scope'}:
            raise ValueError('Chat tạm và chính sách lưu riêng chưa được hỗ trợ. Yêu cầu này chưa được gửi tới AI.')
        return data

    request_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9-]{16,64}$')
    project_id: str | None = Field(default=None, max_length=64)
    project_file_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=4)
    branch_message_id: int | None = Field(default=None, gt=0)
    message: str = ""
    conversation_id: str | None = None
    effort: str | None = None
    timezone: str | None = Field(default=None, max_length=100)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    web_search: Literal["auto", "on", "off"] = "auto"
    # "companion" khi nhắn từ tab Companion: persona và mạch trò chuyện riêng.
    mode: str = Field(default="chat", max_length=16)
    # Chỉ còn "assistant": chế độ nhập vai đã bỏ ngày 2026-10-18; giữ trường để trang cũ gửi lên nhận lời báo rõ ràng.
    persona: str = Field(default="assistant", max_length=16)
    document_mode: bool = False
    # Model chọn ở nút cạnh nút Gửi (ai_models.MODELS); mỗi tin một lựa chọn, đổi giữa chừng được.
    model: str = Field(default=ai_models.DEFAULT_MODEL, max_length=16)
    # Chỉ Companion: dùng khóa riêng của người dùng thay cho Grok của Peto.
    provider: ProviderChoiceIn | None = None
    # Only the sending Companion browser implements the action/ack protocol. Older clients have no tools.
    player_control: Literal[1, 2, 3, 4, 5] | None = None


class StopRequest(BaseModel):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9-]{16,64}$')


class ConversationUpdate(BaseModel):
    model: str | None = Field(default=None, max_length=16)
    effort: str | None = Field(default=None, max_length=16)
    project_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None


ALLOWED_EFFORTS = {"auto", *ai_models.OPENAI_EFFORTS}


CONVERSATION_MODES = {"chat", "companion"}

