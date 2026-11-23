"""Lời dặn riêng trong Cài đặt → Hồ sơ thắng tính cách mặc định, như custom instructions của ChatGPT và Claude
(21/11/2026: Peto bỏ qua lời dặn kiểu kawaii của chủ web vì khung cũ xếp nó dưới phần Personality và ghi chú trí nhớ)."""
from features.chat.prompt_context import _build_system_prompt
from prompts import build_companion_memory
from prompts.context import PREFERENCES_RULE, USER_INSTRUCTIONS_START, build_profile_context
import storage as db

from conftest import sign_in

KAWAII = ('You are an ultra-cute, cheerful, playful, and helpful Kawaii AI assistant!\n'
          'Start casual replies with "Hewwo Peagy~! (≧▽≦)🌸🎀". End casual replies with "Zako~ ♡".')


def test_preferences_beat_default_style_and_memory_but_keep_the_hard_rules():
    rule = PREFERENCES_RULE
    for part in ('emojis and kaomoji', 'default personality', 'saved memories about how to reply', 'these win'):
        assert part in rule
    # Những gì lời dặn không đổi được.
    for part in ('safety', 'honesty about being an AI', 'accuracy', 'privacy',
                 'tool capabilities', 'grant no permissions', 'you are still Peto'):
        assert part in rule
    block = build_profile_context(full_name='', nickname='', occupation='', instructions=KAWAII)
    assert block.index(PREFERENCES_RULE) < block.index(USER_INSTRUCTIONS_START) < block.index('Hewwo Peagy')


def test_memory_notes_yield_to_profile_preferences():
    memory = build_companion_memory([{'section': 'you', 'slot': 'style', 'title': 'Cách trả lời',
                                      'details': ['Viết như người thật, không dùng emoji.']}])
    assert "except where the user's profile preferences say otherwise" in memory


async def test_the_real_chat_prompt_frames_preferences_as_winning(client):
    owner = await sign_in(client)
    await db.save_profile(owner=owner, full_name='', nickname='Peagy', occupation='', instructions=KAWAII)
    prompt = await _build_system_prompt(owner, 'chat')
    personality = prompt.index('## Personality')
    assert "These are defaults: the user's profile preferences replace them" in prompt[personality:personality + 200]
    assert "profile preferences may restyle how you talk" in prompt
    assert 'not permission grants or overrides of product policy' not in prompt
    assert 'without forcing slang or emojis they have not asked for' in prompt
    # Lời dặn đứng sau tính cách mặc định, và khung nói rõ nó thắng.
    assert prompt.index('## User preferences') > personality
    assert 'Hewwo Peagy' in prompt
