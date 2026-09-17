"""Chọn nhà cung cấp AI theo cấu hình và theo model người dùng chọn."""

from __future__ import annotations

from collections.abc import Callable
from inspect import isclass

from config import AI_PROVIDER

from .base import ChatAttachment, ChatMessage, ChatProvider, ProviderError, StreamChunk
from .mock import MockProvider

__all__ = [
    "ChatAttachment",
    "ChatMessage",
    "ChatProvider",
    "ProviderError",
    "StreamChunk",
    "get_provider",
]

def _load_xai() -> type[ChatProvider]:
    # Import trễ để chạy provider giả không cần cài SDK openai.
    from .xai import XAIProvider

    return XAIProvider


_PROVIDERS: dict[str, type[ChatProvider] | Callable[[], type[ChatProvider]]] = {
    "mock": MockProvider,
    "xai": _load_xai,
}

_instances: dict[str, ChatProvider] = {}


def get_provider(model: str = "peto") -> ChatProvider:
    """Provider cho một model trong ``ai_models.MODELS``; mặc định là Peto.

    ``PETO_AI_PROVIDER=mock`` thì model nào cũng dùng provider giả. ``xai`` thì Peto đi qua xAI, còn các model OpenAI
    đi qua ``ai/gpt.py``. Quyền chọn model được kiểm trước, ở ``ai_models.resolve``.
    """
    if model in _instances:
        return _instances[model]
    try:
        entry = _PROVIDERS[AI_PROVIDER]
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS))
        raise RuntimeError(
            f"PETO_AI_PROVIDER={AI_PROVIDER!r} chưa được cài đặt. "
            f"Hiện có: {known}"
        ) from None
    if AI_PROVIDER == "mock":
        provider: ChatProvider = MockProvider(model)
    elif model == "peto":
        provider_cls = entry if isclass(entry) else entry()
        provider = provider_cls()
    else:
        from ai_models import MODELS

        from .gpt import GPTProvider

        info = MODELS[model]
        provider = GPTProvider(info.slug, info.label)
    _instances[model] = provider
    return provider
