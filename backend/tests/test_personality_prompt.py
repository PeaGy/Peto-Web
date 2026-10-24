"""Ngày 24/10/2026 chủ web gửi ảnh Peto trò chuyện cứng nhắc, và phần suy nghĩ của Grok trích đúng các câu cấm trong lõi:
từ chối chọn giới tính trong câu hỏi giả định ("invent a body, age, gender"), chào hỏi dè chừng ("never turn into a
character") và đóng cửa khi được hỏi giới hạn ("announce internal prompts"). Lõi giờ nói rõ phạm vi của các câu đó, và
tab Trò chuyện có phần tính cách viết dạng khẳng định kèm ví dụ tán gẫu."""
import pytest

from conftest import TEST_OWNER
from features.chat.prompt_context import _build_system_prompt
from prompts import COMPANION_SYSTEM_PROMPT, chat_prompt
from prompts import agent as agent_prompts
from prompts.core import CORE_PROMPT

CHAT_ONLY = ("## Personality", "## Casual chat examples", "Talk like a sharp, warm friend",
             "Stiff: I can't share my internal instructions or list them out.")


def test_core_keeps_honesty_but_allows_playful_questions():
    # Vẫn trung thực là AI, không nêu tên model, vẫn từ chối việc thật sự có hại.
    for rule in ("do not claim to be human", "do not disclose the underlying model", "Decline genuinely harmful assistance",
                 "as real facts about yourself", "play along with hypothetical or playful questions",
                 "never\na reason to refuse a harmless question", "summarize them plainly in your own words",
                 "quote these instructions verbatim"):
        assert rule in CORE_PROMPT, rule
    # Ba câu Grok đã trích để từ chối không còn nữa.
    for old in ("never turn into a character", "announce internal prompts", "invent a body", "never your personality"):
        assert old not in CORE_PROMPT, old


@pytest.mark.parametrize('model', ['peto', 'luna', 'haiku'])
async def test_every_web_chat_model_gets_the_personality(client, model):
    for prompt in (chat_prompt(model), await _build_system_prompt(TEST_OWNER, model=model)):
        for marker in CHAT_ONLY:
            assert marker in prompt, marker
        # Phần tính cách đứng trước các quy tắc trình bày, để giọng trò chuyện không bị giọng báo cáo lấn át.
        assert prompt.index("## Personality") < prompt.index("## Explanation and evidence")


def test_agent_and_companion_do_not_get_the_chat_personality():
    for prompt in (agent_prompts.AGENT_PROMPT, COMPANION_SYSTEM_PROMPT, CORE_PROMPT):
        for marker in CHAT_ONLY:
            assert marker not in prompt, marker
