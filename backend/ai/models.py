"""Các model người dùng chọn được: Peto, dòng GPT của OpenAI và Haiku/Sonnet 5.5 của Claude.

Chủ web chốt:
- Web có Peto, 6 Luna và Haiku 5.5 (nút chọn model cạnh nút Gửi). Peto Agent có thêm 5.6 Terra,
  6 Sol và Sonnet 5.5 (lệnh /model).
- 6 Luna dùng được với mọi tài khoản đã đăng nhập (Discord, Google, GitHub). 5.6 Terra và 6 Sol chỉ dành cho
  tài khoản của chủ web, khai trong ``PETO_OWNER_ACCOUNTS``. Terra giữ slug 5.6 cho đến khi OpenAI có bản GPT-6.
- Trong Peto Agent, bước tính theo giá: Luna 1, Terra 2, Sol 4, nhân với mức suy nghĩ (mức cao tính gấp đôi).
- Haiku dùng được với mọi tài khoản đã đăng nhập; Sonnet chỉ dành cho chủ web trong Agent. Cả hai nhận năm mức
  suy nghĩ của Claude và tính bước theo hạn mức Peto: Haiku 1, Sonnet 2 trước khi nhân mức suy nghĩ.

Các model OpenAI tính tiền vào billing API của chủ web, nên máy chủ kiểm quyền ở đây chứ không tin giao diện. Thiếu
``OPENAI_API_KEY`` thì ẩn model OpenAI; thiếu ``ANTHROPIC_API_KEY`` thì ẩn Claude.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import config

DEFAULT_MODEL = "peto"
OPENAI_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
PETO_EFFORTS = ("low", "medium", "high")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def supported_efforts(key: str) -> tuple[str, ...]:
    return {"openai": OPENAI_EFFORTS, "anthropic": CLAUDE_EFFORTS}.get(MODELS[key].service, PETO_EFFORTS)


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    description: str
    # "xai" dùng tài khoản Grok; "openai" dùng OPENAI_API_KEY; "anthropic" dùng ANTHROPIC_API_KEY của máy chủ.
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
    "haiku": Model("haiku", "Haiku 5.5", "Nhanh, của Claude", "anthropic", "claude-haiku-5-5", 1,
                   web=True, owner_only=False),
    "sonnet": Model("sonnet", "Sonnet 5.5", "Cân bằng, của Claude", "anthropic", "claude-sonnet-5-5", 2,
                    web=False, owner_only=True),
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
    if model.service not in {"openai", "anthropic"}:
        return None
    ready = openai_ready() if model.service == "openai" else config.AI_PROVIDER == "mock" or bool(config.ANTHROPIC_API_KEY)
    if not ready:
        return ModelUnavailable(503, f"Máy chủ Peto chưa bật {model.label}. Chọn Peto để tiếp tục nhé.")
    if not config.provider_from_owner(owner):
        return ModelUnavailable(403, f"{model.label} chỉ dùng được với tài khoản đã đăng nhập.")
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
    return [{"key": model.key, "label": model.label, "description": model.description, "step_cost": model.step_cost,
             "efforts": list(supported_efforts(model.key))}
            for model in models]
