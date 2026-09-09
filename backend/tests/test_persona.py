"""Bảo vệ ranh giới dữ liệu giữa bot Discord và web.

Những kiểm thử này giữ đúng cam kết ở mục 6 và 8 của PETO_WEB_HANDOFF.md:
prompt của web không được mang theo tên thật, Discord ID hay lời hứa về công
cụ mà web chưa có.
"""

from __future__ import annotations

import re

import persona

# Tên và ID thật nằm trong KNOWN_PEOPLE_PROMPT / SPECIAL_USERS của bot Discord.
FORBIDDEN_NAMES = ("Ducky", "Duck", "Val", "Peargy", "Pearto")


def test_no_real_member_names():
    lowered = persona.SYSTEM_PROMPT.casefold()
    for name in FORBIDDEN_NAMES:
        assert name.casefold() not in lowered, f"prompt web còn tên thật: {name}"


def test_no_discord_user_ids():
    # Discord snowflake là chuỗi 17-20 chữ số.
    assert not re.search(r"\b\d{17,20}\b", persona.SYSTEM_PROMPT)


def test_does_not_promise_tools_web_lacks():
    assert not hasattr(persona, "KNOWN_PEOPLE_PROMPT")
    assert not hasattr(persona, "SPECIAL_USERS")
    assert not hasattr(persona, "LIMBUS_WIKI_PROMPT")
    assert "search_limbus_wiki" not in persona.SYSTEM_PROMPT
    assert "generate_image" not in persona.SYSTEM_PROMPT
    assert "play_music" not in persona.SYSTEM_PROMPT


def test_states_web_has_no_tools():
    assert "chưa có nhạc" in persona.SYSTEM_PROMPT
    assert "không phải Discord" in persona.SYSTEM_PROMPT


def test_core_personality_survived():
    # Nếu ai đó rút gọn prompt, các phần tạo nên Peto phải còn nguyên.
    for marker in ("Peto là ai", "Nhịp trò chuyện", "Cảm giác hiện diện"):
        assert marker in persona.SYSTEM_PROMPT
    assert len(persona.SYSTEM_PROMPT) > 3000
