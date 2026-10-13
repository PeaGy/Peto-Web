"""Ghép prompt theo tài khoản, persona và ngữ cảnh hội thoại."""

from __future__ import annotations
from features.companion import memory as companion_memory
import storage as db
from features.accounts import profile as profile_api
from core.config import AGENT_DAILY_STEPS, discord_id_from_owner
from features.accounts.discord_memory import discord_memory
from prompts import (
    COMPANION_SYSTEM_PROMPT,
    ROLEPLAY_SYSTEM_PROMPT,
    build_agent_guide,
    build_diagram_guide,
    build_memory_context,
    build_profile_context,
)
from features.docs import api as docs_api
from shared import youtube
from prompts.routing import chat_prompt, uses_english


async def _build_system_prompt(
    owner: str, mode: str = "chat", install_command: str = "", persona: str = "assistant",
    conversation_id: str | None = None,
    agent_question: str = '',
    model: str = 'peto',
    memory: bool = True,
) -> str:
    """Prompt gốc: trợ lý, nhập vai, hoặc Companion. Companion là persona riêng, không
    vá lên trợ lý. Sau đó ghép hướng dẫn Peto Agent, trí nhớ Discord và hồ sơ người dùng.

    Trí nhớ chỉ được tra bằng Discord ID lấy từ phiên đã xác minh — không bao
    giờ từ dữ liệu do trình duyệt gửi lên. Lấy không được thì bỏ qua, chat vẫn
    chạy bình thường.

    ``memory=False`` là lượt Companion dùng khóa API riêng của người dùng (ai/byok.py): không kèm trí nhớ Discord, Trí
    nhớ hay bản tóm tắt, vì chủ web chốt lượt đó không đọc, không ghi trí nhớ và prompt đi tới nhà cung cấp khác.
    """
    english = mode == "chat" and persona != "roleplay" and uses_english(model)
    if mode == "companion":
        base = COMPANION_SYSTEM_PROMPT
    elif persona == "roleplay":
        base = ROLEPLAY_SYSTEM_PROMPT
    else:
        base = chat_prompt(model)
    # Danh mục từ bản CLI đang phục vụ; chỉ chọn hướng dẫn chi tiết theo tin nhắn gần đây.
    # Lệnh cài lấy từ địa chỉ trang đang mở (agent_install.install_command).
    agent_guide = build_agent_guide(install_command=install_command, daily_steps=AGENT_DAILY_STEPS,
                                  question=agent_question, english=english)
    agent_guide += docs_api.context(agent_question, english=english)
    # Tiêu đề và kênh của link YouTube trong vài tin gần đây (đọc lại mỗi lượt, có nhớ tạm), cho mọi model.
    agent_guide += await youtube.context(agent_question, english=english)
    if mode == "chat" and persona != "roleplay":
        agent_guide += build_diagram_guide(agent_question, english=english)
    user = await db.get_user(owner)
    if not user:
        return "\n\n".join(part for part in (base, agent_guide) if part)

    discord_id = discord_id_from_owner(owner)
    snapshot = await discord_memory.fetch(discord_id) if discord_id and memory else None

    context = build_memory_context(
        display_name=user.get("display_name") or user.get("username") or "",
        summary=snapshot.summary if snapshot else "",
        explicit=snapshot.explicit if snapshot else (),
        english=english,
        roleplay=mode != "companion" and persona == "roleplay",
    )
    # Đọc lại ở MỖI lượt, không đệm: người dùng sửa hồ sơ trong Cài đặt thì
    # ngay tin nhắn kế tiếp đã theo.
    profile = await db.get_profile(owner)
    profile_block = build_profile_context(
        full_name=profile["full_name"],
        nickname=profile["nickname"],
        occupation=profile_api.occupation_label(profile["occupation"]),
        instructions=profile["instructions"],
        english=english,
    )
    # Trí nhớ Companion (và bản tóm tắt của mạch này) chỉ vào lượt Companion, đọc lại mỗi lượt: xóa một dòng trong Cài
    # đặt là lượt sau Peto quên.
    if not memory:
        companion_block = ""
    elif mode == "companion":
        companion_block = await companion_memory.memory_block(owner, conversation_id)
    elif persona != "roleplay":
        # Trí nhớ dùng chung với Companion (11/10/2026); Chat nhập vai không đọc, không ghi.
        companion_block = await companion_memory.chat_memory_block(owner, english=english)
    else:
        companion_block = ""
    return "\n\n".join(part for part in (base, agent_guide, context, profile_block, companion_block) if part)
