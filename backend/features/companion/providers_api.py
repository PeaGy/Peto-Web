"""Cài đặt Companion → Nhà cung cấp: kiểm tra khóa API riêng của người dùng và lấy danh sách model của nhà cung cấp đó.

Khóa đi trong header X-Peto-Provider-Key cho đúng một lần gọi, như lúc trò chuyện (ai/byok.py): không lưu, không ghi log.
Máy chủ chỉ gọi địa chỉ cố định của từng nhà cung cấp.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ai import byok
from ai.base import ProviderError
from features.accounts.auth import current_owner

router = APIRouter()


class CheckRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    # Chỉ Azure OpenAI: địa chỉ tài nguyên.
    endpoint: str | None = Field(default=None, max_length=200)


@router.post("/api/companion/providers/check")
async def check_provider(body: CheckRequest, request: Request, response: Response,
                         owner: str = Depends(current_owner)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        choice = byok.choose(body.provider, "kiem-tra", body.endpoint, request.headers.get("x-peto-provider-key"), None)
    except byok.ByokError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    try:
        models = await byok.check(choice)
    except ProviderError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    # Azure OpenAI không liệt kê bản triển khai bằng khóa này: người dùng gõ tên bản triển khai của mình.
    return {"models": models, "deployment": choice.info.id == "azure-openai"}
