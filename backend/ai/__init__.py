"""Chọn nhà cung cấp AI theo cấu hình."""

from __future__ import annotations

from collections.abc import Callable
from inspect import isclass

from config import AI_PROVIDER

from .base import ChatMessage, ChatProvider, ProviderError
from .mock import MockProvider

__all__ = [
    "ChatMessage",
    "ChatProvider",
    "ProviderError",
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

_instance: ChatProvider | None = None


def get_provider() -> ChatProvider:
    global _instance
    if _instance is None:
        try:
            entry = _PROVIDERS[AI_PROVIDER]
        except KeyError:
            known = ", ".join(sorted(_PROVIDERS))
            raise RuntimeError(
                f"PETO_AI_PROVIDER={AI_PROVIDER!r} chưa được cài đặt. "
                f"Hiện có: {known}"
            ) from None
        provider_cls = entry if isclass(entry) else entry()
        _instance = provider_cls()
    return _instance
