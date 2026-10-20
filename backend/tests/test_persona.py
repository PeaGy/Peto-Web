"""Bảo vệ ranh giới dữ liệu giữa bot Discord và web.

Những kiểm thử này giữ đúng cam kết ở mục 6 và 8 của PETO_WEB_HANDOFF.md:
prompt của web không được mang theo tên thật, Discord ID hay lời hứa về công
cụ mà web chưa có. Từ ngày 2026-10-18 mọi chỉ dẫn gửi model đều bằng tiếng Anh, và chế độ nhập vai đã bỏ.
"""

from __future__ import annotations

import re

import prompts as persona
from prompts import agent, chat, core, providers

# Tên và ID thật nằm trong KNOWN_PEOPLE_PROMPT / SPECIAL_USERS của bot Discord.
FORBIDDEN_NAMES = ("Ducky", "Duck", "Val", "Peargy", "Pearto")
MODELS = ("peto", "luna", "haiku")


def chat_prompts() -> list[str]:
    return [chat.chat_prompt(model) for model in MODELS]


def names_in(text: str) -> list[str]:
    # Theo ranh giới từ: prompt tiếng Anh có "values", "validation" mà không phải tên "Val".
    return [name for name in FORBIDDEN_NAMES if re.search(rf"\b{name}\b", text, re.IGNORECASE)]


def test_no_real_member_names():
    for prompt in chat_prompts():
        assert not names_in(prompt), "prompt web còn tên thật"


def test_no_discord_user_ids():
    # Discord snowflake là chuỗi 17-20 chữ số.
    for prompt in chat_prompts():
        assert not re.search(r"\b\d{17,20}\b", prompt)


def test_agent_guide_teaches_the_given_install_command():
    command = "irm https://peto.example/install.ps1 | iex"
    guide = persona.build_agent_guide(install_command=command, daily_steps=150, question="cài Peto Agent thế nào?")
    assert f"`{command}`" in guide
    for marker in ("150 steps", "peto login", "Python 3.12", "Discord/Google/GitHub", "user approvals", "peto logout",
                   "/effort", "double base cost", "is not recognized", "/usage", "`/` lists commands",
                   "announces available updates", "Alt+V", "drag an image file", "`/model`"):
        assert marker in guide, marker
    generic = persona.build_agent_guide(install_command="", daily_steps=200, question="peto agent")
    assert "https://<địa chỉ Peto>/install.ps1" in generic and "never guess a domain" in generic
    for text in (guide, generic):
        assert not names_in(text)
    # Chỉ gắn khi câu hỏi nói tới Agent: các lượt khác không tốn token cho cả hướng dẫn CLI.
    assert persona.build_agent_guide(install_command=command, daily_steps=150, question="giải thích asyncio") == ""


def test_does_not_promise_tools_web_lacks():
    assert not hasattr(persona, "KNOWN_PEOPLE_PROMPT")
    assert not hasattr(persona, "SPECIAL_USERS")
    assert not hasattr(persona, "LIMBUS_WIKI_PROMPT")
    for prompt in chat_prompts():
        assert "search_limbus_wiki" not in prompt
        assert "generate_image" not in prompt
        assert "play_music" not in prompt


def test_states_web_has_no_tools():
    for prompt in chat_prompts():
        assert "Music playback is unavailable" in prompt
        assert "not Discord" in prompt


def test_core_sections_survived():
    # Nếu ai đó rút gọn prompt, các phần tạo nên Peto phải còn nguyên.
    for prompt in chat_prompts():
        for marker in ("## Identity and communication", "## Accuracy, privacy and authority", "## Conversation",
                       "## Web chat", "## Explanation and evidence", "## Attachments", "## Creating and editing files"):
            assert marker in prompt, marker
        assert len(prompt) > 8000


def test_reply_examples_are_a_grok_overlay():
    """Ví dụ giọng trả lời viết cho Grok từ trước; GPT và Claude chưa từng cần, nên không tốn token cho chúng."""
    assert providers.XAI_CHAT_PROMPT in chat.chat_prompt("peto")
    assert providers.XAI_CHAT_PROMPT not in chat.chat_prompt("luna") + chat.chat_prompt("haiku")
    assert providers.OPENAI_PROMPT in chat.chat_prompt("luna") and providers.ANTHROPIC_PROMPT in chat.chat_prompt("haiku")
    # Đoạn ví dụ chỉ thuộc tab Trò chuyện, không vào Peto Agent.
    assert providers.provider_prompt("xai") == ""


def test_web_persona_is_an_assistant_not_the_discord_roleplay_character():
    """Ngày 17/09/2026 chủ web thay persona nhập vai lấy từ bot Discord bằng một trợ lý AI trung thực; chế độ nhập vai
    tự bật cũng bỏ ngày 2026-10-18."""
    assert not hasattr(persona, "ROLEPLAY_SYSTEM_PROMPT")
    for prompt in chat_prompts():
        lowered = prompt.casefold()
        assert "the ai assistant of peto web" in lowered and "do not claim to be human" in lowered
        assert "never sexual roleplay" in lowered
        for leftover in ("nsfw", "18+", "lưỡng tính", "punching bag", "*peto nghiêng đầu", "pet play"):
            assert leftover not in lowered, f"prompt trợ lý còn dấu vết persona nhập vai: {leftover}"


def test_agent_does_its_work_instead_of_refusing_on_taste():
    """Grok thật từng từ chối "tạo thử một đoạn code lỗi" vì persona cũ cho phép "không chiều theo người dùng"."""
    assert "deliberately broken code for testing are valid tasks" in agent.AGENT_PROMPT
    assert "Do not refuse based on taste" in agent.AGENT_PROMPT


def test_prompts_never_name_the_model_behind_peto():
    """Chủ web muốn Peto chỉ nói mình là Peto: một ví dụ cũ "chạy trên mô hình Grok của xAI" đã dạy ngược lại luật đó."""
    assert "do not disclose the underlying model" in core.CORE_PROMPT
    guide = persona.build_agent_guide(install_command="irm https://peto.example/install.ps1 | iex", daily_steps=200,
                                      question="peto agent")
    for text in (*chat_prompts(), core.CORE_PROMPT, agent.AGENT_PROMPT, persona.COMPANION_SYSTEM_PROMPT, guide):
        lowered = text.casefold()
        assert "grok" not in lowered and "xai" not in lowered


def test_does_not_invent_source_from_screenshots():
    for prompt in chat_prompts():
        assert "Screenshots show visible content" in prompt
        assert "Do not reconstruct unseen" in prompt and "ask for the real file" in prompt


def test_huong_dan_trinh_bay_tren_web():
    """Thiếu phần này thì Peto trả lời bài học thành một khối chữ liền: cùng mô hình nhưng đọc khó hơn hẳn giao diện gốc.
    Chuyện phiếm thì vẫn phải được nhắn tự nhiên, không bị ép thành tài liệu."""
    for prompt in chat_prompts():
        for marker in ("separate distinct examples", "useful headings", "keep casual chat natural"):
            assert marker in prompt, marker


def test_prompts_are_english():
    """Mọi chỉ dẫn gửi model bằng tiếng Anh để bớt token: chỉ còn vài từ tiếng Việt có chủ ý (cách xưng hô, tên tab,
    nhãn trong tệp, tên mục trí nhớ cố định), không có câu tiếng Việt nào."""
    texts = (*chat_prompts(), agent.AGENT_PROMPT, agent.COMPACT_PROMPT, persona.COMPANION_SYSTEM_PROMPT)
    for text in texts:
        letters = [char for char in text if char.isalpha()]
        vietnamese = [char for char in letters if char in "ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ"]
        assert len(vietnamese) < len(letters) * 0.02
