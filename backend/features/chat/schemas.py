"""Dữ liệu yêu cầu chat và các lựa chọn được chấp nhận."""

from __future__ import annotations
from typing import Literal, Annotated
from pydantic import BaseModel, Field
from ai import models as ai_models


class AttachmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    mime: str = Field(default="", max_length=120)
    data: str = Field(min_length=8)


class ChatRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=64)
    project_file_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=4)
    branch_message_id: int | None = Field(default=None, gt=0)
    message: str = ""
    conversation_id: str | None = None
    effort: str | None = None
    timezone: str | None = Field(default=None, max_length=100)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    web_search: Literal["auto", "on", "off"] = "auto"
    # "companion" khi nhắn từ tab Companion: persona trả lời ngắn bằng tiếng Anh, mạch trò chuyện riêng.
    mode: str = Field(default="chat", max_length=16)
    # "roleplay" khi người dùng bật Chế độ nhập vai lúc bắt đầu; hội thoại đã có thì luôn theo persona đã lưu.
    persona: str = Field(default="assistant", max_length=16)
    document_mode: bool = False
    # Model chọn ở nút cạnh nút Gửi (ai_models.MODELS); mỗi tin một lựa chọn, đổi giữa chừng được.
    model: str = Field(default=ai_models.DEFAULT_MODEL, max_length=16)


class ConversationUpdate(BaseModel):
    model: str | None = Field(default=None, max_length=16)
    effort: str | None = Field(default=None, max_length=16)
    project_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None


ALLOWED_EFFORTS = {"auto", *ai_models.OPENAI_EFFORTS}


CONVERSATION_MODES = {"chat", "companion"}


CONVERSATION_PERSONAS = {"assistant", "roleplay"}
