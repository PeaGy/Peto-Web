"""Chọn ngôn ngữ và phần chỉ dẫn theo nhà cung cấp, không dựa vào chữ trong chat."""

from ai.models import MODELS
from . import english
from .assistant import SYSTEM_PROMPT


def uses_english(model: str) -> bool:
    return MODELS[model].service in english.PROVIDER_PROMPTS


def provider_prompt(model: str) -> str:
    return english.PROVIDER_PROMPTS.get(MODELS[model].service, "")


def chat_prompt(model: str) -> str:
    if not uses_english(model):
        return SYSTEM_PROMPT
    return "\n\n".join((english.CORE_PROMPT, english.WEB_PROMPT, provider_prompt(model)))
