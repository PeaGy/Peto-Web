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


def test_agent_guide_teaches_the_given_install_command():
    command = "irm https://peto.example/install.ps1 | iex"
    guide = persona.build_agent_guide(install_command=command, daily_steps=150)
    assert f"`{command}`" in guide
    for marker in ("150 bước mỗi ngày", "peto login", "Python 3.12", "Tài khoản khách không dùng được",
                   "hỏi trước khi sửa tệp", "peto logout", "/resume", "/effort cao", "cao tính 2 bước",
                   "is not recognized", "/usage", "gõ `/` là hiện danh sách lệnh", "tự nhắc khi máy chủ có bản mới",
                   "Alt+V", "kéo tệp ảnh thả vào", "`/model`"):
        assert marker in guide
    generic = persona.build_agent_guide(install_command="", daily_steps=200)
    assert "https://<địa chỉ Peto>/install.ps1" in generic and "đừng tự đoán tên miền" in generic
    for text in (guide, generic):
        lowered = text.casefold()
        assert not [name for name in FORBIDDEN_NAMES if name.casefold() in lowered]


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


def test_core_sections_survived():
    # Nếu ai đó rút gọn prompt, các phần tạo nên Peto phải còn nguyên.
    for marker in ("Peto là ai", "Cách trả lời", "Trung thực và an toàn", "Khi người dùng chia sẻ cảm xúc"):
        assert marker in persona.SYSTEM_PROMPT
    assert len(persona.SYSTEM_PROMPT) > 3000


def test_web_persona_is_an_assistant_not_the_discord_roleplay_character():
    """Ngày 17/09/2026 chủ web thay persona nhập vai lấy từ bot Discord bằng một trợ lý AI trung thực."""
    lowered = persona.SYSTEM_PROMPT.casefold()
    assert "trợ lý ai" in lowered and "bạn là ai, không phải con người" in lowered
    assert "không nhập vai tình dục" in lowered
    for leftover in ("nsfw", "18+", "lưỡng tính", "cà lại", "punching bag", "đừng lúc nào cũng chiều theo",
                     "*peto nghiêng đầu", "pet play", "roleplay"):
        assert leftover not in lowered, f"prompt trợ lý còn dấu vết persona nhập vai: {leftover}"
    assert persona.MATURE_TONE_PROMPT not in persona.SYSTEM_PROMPT
    assert persona.PRESENCE_AND_ROLEPLAY_PROMPT not in persona.SYSTEM_PROMPT


def test_roleplay_mode_keeps_the_discord_persona_and_the_web_rules():
    """Chế độ nhập vai tự bật dùng lại nguyên persona của bot, nhưng vẫn theo luật nền tảng web và không mang tên thật."""
    prompt = persona.ROLEPLAY_SYSTEM_PROMPT
    for marker in ("20 tuổi", "Nhịp trò chuyện", "Cảm giác hiện diện", "roleplay 18+", "*Peto nghiêng đầu",
                   "không phải Discord", "chưa có nhạc", "Tính liên tục và trí nhớ"):
        assert marker in prompt
    assert "trợ lý AI của Peto Web" not in prompt
    lowered = prompt.casefold()
    for name in FORBIDDEN_NAMES:
        assert name.casefold() not in lowered, f"prompt nhập vai còn tên thật: {name}"
    assert not re.search(r"\b\d{17,20}\b", prompt)


def test_agent_does_its_work_instead_of_refusing_on_taste():
    """Grok thật từng từ chối "tạo thử một đoạn code lỗi" vì persona cũ cho phép "không chiều theo người dùng"."""
    assert "kể cả cố ý tạo code lỗi để thử" in persona.AGENT_PROMPT
    assert "khi thật cần" not in persona.AGENT_PROMPT
    assert "trợ lý AI" in persona.PERSONA_PROMPT


def test_prompts_never_name_the_model_behind_peto():
    """Chủ web muốn Peto chỉ nói mình là Peto: một ví dụ cũ "chạy trên mô hình Grok của xAI" đã dạy ngược lại luật đó."""
    assert "không trả lời các câu hỏi về Peto thuộc model nào" in persona.PERSONA_PROMPT
    guide = persona.build_agent_guide(install_command="irm https://peto.example/install.ps1 | iex", daily_steps=200)
    for text in (persona.SYSTEM_PROMPT, persona.ROLEPLAY_SYSTEM_PROMPT, persona.AGENT_PROMPT,
                 persona.COMPANION_PROMPT, guide):
        lowered = text.casefold()
        assert "grok" not in lowered and "xai" not in lowered


def test_does_not_invent_source_from_screenshots():
    lowered = persona.SYSTEM_PROMPT.casefold()
    assert "không bịa source" in lowered or "không bịa" in lowered
    assert "đính kèm" in lowered
    assert "ảnh chụp màn hình" in lowered or "ảnh màn hình" in lowered


def test_huong_dan_trinh_bay_tren_web():
    """Thiếu phần này thì Peto trả lời bài học thành một khối chữ liền: cùng mô
    hình Grok nhưng đọc khó hơn hẳn giao diện gốc của Grok. Chuyện phiếm thì vẫn
    phải được nhắn tự nhiên, không bị ép thành tài liệu."""
    for marker in ("Mỗi khối code chỉ minh họa một ý", "tiêu đề ngắn", "Chuyện phiếm"):
        assert marker in persona.SYSTEM_PROMPT
