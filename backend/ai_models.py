"""Các model người dùng chọn được: Peto (Grok qua xAI), GPT-6 Luna/Sol và 5.6 Terra của OpenAI.

Chủ web chốt:
- Web có Peto và 6 Luna (nút chọn model cạnh nút Gửi). Peto Agent có thêm 5.6 Terra và 6 Sol (lệnh /model).
- 6 Luna dùng được với tài khoản Discord/Google, tài khoản khách chỉ dùng Peto. 5.6 Terra và 6 Sol chỉ dành cho
  tài khoản của chủ web, khai trong ``PETO_OWNER_ACCOUNTS``. Terra giữ slug 5.6 cho đến khi OpenAI có bản GPT-6.
- Trong Peto Agent, bước tính theo giá: Luna 1, Terra 2, Sol 4, nhân với mức suy nghĩ (mức cao tính gấp đôi).

Các model OpenAI tính tiền vào billing API của chủ web, nên máy chủ kiểm quyền ở đây chứ không tin giao diện. Thiếu
``OPENAI_API_KEY`` thì chỉ còn Peto.
"""

from __future__ import annotations

from dataclasses import dataclass

import config

DEFAULT_MODEL = "peto"


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    description: str
    # "xai" dùng tài khoản Grok của máy chủ; "openai" dùng OPENAI_API_KEY.
    service: str
    # Tên model trong API; Peto theo XAI_MODEL (web) hoặc PETO_AGENT_MODEL (agent).
    slug: str
    # Số bước mỗi lần gọi trong Peto Agent, trước khi nhân với mức suy nghĩ.
    step_cost: int
    web: bool
    owner_only: bool


MODELS: dict[str, Model] = {
    "peto": Model("peto", "Peto", "Mặc định", "xai", "", 1, web=True, owner_only=False),
    "luna": Model("luna", "6 Luna", "Nhanh, của OpenAI", "openai", "gpt-6-luna", 1, web=True, owner_only=False),
    "terra": Model("terra", "5.6 Terra", "Cân bằng, của OpenAI", "openai", "gpt-5.6-terra", 2, web=False,
                   owner_only=True),
    "sol": Model("sol", "6 Sol", "Mạnh nhất, của OpenAI", "openai", "gpt-6-sol", 4, web=False, owner_only=True),
}


class ModelUnavailable(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def openai_ready() -> bool:
    # Chạy bằng phản hồi giả thì model nào cũng đi vào nhà cung cấp giả, không cần khóa.
    return config.AI_PROVIDER == "mock" or bool(config.OPENAI_API_KEY)


def _refusal(owner: str, model: Model) -> ModelUnavailable | None:
    if model.service != "openai":
        return None
    if not openai_ready():
        return ModelUnavailable(503, f"Máy chủ Peto chưa bật {model.label}. Chọn Peto để tiếp tục nhé.")
    if config.provider_from_owner(owner) not in {"discord", "google"}:
        return ModelUnavailable(403, f"{model.label} chỉ dùng được với tài khoản Discord hoặc Google.")
    if model.owner_only and owner not in config.OWNER_ACCOUNTS:
        return ModelUnavailable(403, f"{model.label} chỉ dành cho chủ web.")
    return None


def usable(owner: str, surface: str) -> list[Model]:
    """Các model tài khoản này chọn được trên ``surface``: "web" hoặc "agent"."""
    return [model for model in MODELS.values()
            if (surface == "agent" or model.web) and _refusal(owner, model) is None]


def resolve(owner: str, key: object, surface: str) -> Model:
    """Model hợp lệ cho tài khoản này, hoặc ném ``ModelUnavailable`` với lời báo tiếng Việt."""
    model = MODELS.get(key) if isinstance(key, str) else None
    if model is None or (surface == "web" and not model.web):
        raise ModelUnavailable(400, "Model không hợp lệ.")
    refusal = _refusal(owner, model)
    if refusal is not None:
        raise refusal
    return model


def public(models: list[Model]) -> list[dict]:
    return [{"key": model.key, "label": model.label, "description": model.description, "step_cost": model.step_cost}
            for model in models]
