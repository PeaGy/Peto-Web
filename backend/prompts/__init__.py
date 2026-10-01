"""Prompt theo ngữ cảnh; không trộn phần nhập vai vào trợ lý hay Agent."""
from features.agent.guide import build_agent_guide
from .assistant import (
    PERSONA_PROMPT,
    SOCIAL_TONE_PROMPT,
    CONVERSATION_STYLE_PROMPT,
    CORE_TRUTH_AND_SAFETY_PROMPT,
    HONESTY_AND_SAFETY_PROMPT,
    EMOTIONAL_RESPONSE_PROMPT,
    CONTINUITY_PROMPT,
    WEB_PLATFORM_PROMPT,
    CONVERSATION_EXAMPLES_PROMPT,
    SYSTEM_PROMPT,
)
from .diagrams import (
    DIAGRAM_PROMPT,
    build_diagram_guide,
)
from .roleplay import (
    ROLEPLAY_PERSONA_PROMPT,
    ROLEPLAY_STYLE_PROMPT,
    MATURE_TONE_PROMPT,
    PRESENCE_AND_ROLEPLAY_PROMPT,
    ROLEPLAY_EMOTION_PROMPT,
    ROLEPLAY_EXAMPLES_PROMPT,
    ROLEPLAY_SYSTEM_PROMPT,
)
from .context import (
    build_memory_context,
    USER_INSTRUCTIONS_START,
    USER_INSTRUCTIONS_END,
    build_profile_context,
    COMPANION_MEMORY_START,
    COMPANION_MEMORY_END,
    build_companion_memory,
    COMPANION_SUMMARY_START,
    COMPANION_SUMMARY_END,
    build_companion_summary,
)
from .companion import (
    COMPANION_SYSTEM_PROMPT,
    COMPANION_PROMPT,
)
from .agent import (
    AGENT_PROMPT,
    AGENT_SEARCH_PROMPT,
    AGENT_NO_SEARCH_PROMPT,
    browser_prompt,
    AGENT_BROWSER_PROMPT,
    AGENT_BROWSER_ACT_PROMPT,
    AGENT_BROWSER_OUTSIDE_PROMPT,
)
