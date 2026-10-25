"""Chỉ dẫn gửi cho model, toàn bộ bằng tiếng Anh (chủ web chọn ngày 2026-10-18 để bớt token).

- ``core``: lõi Peto dùng chung cho Chat, Agent và /btw.
- ``chat``: tab Trò chuyện (``chat_prompt``), tìm web, công cụ tạo/sửa tệp, cách đọc log khi có tệp chữ.
- ``agent``: Peto Agent (CLI).
- ``providers``: đoạn riêng theo nhà cung cấp, ghép sau prompt chung như opencode.
- ``companion``, ``companion_runtime``: Companion, persona riêng.
- ``context``: khung hồ sơ, trí nhớ và tóm tắt của từng người dùng.
- ``diagrams``: hướng dẫn Mermaid, chỉ khi câu hỏi nói tới sơ đồ.
"""
from features.agent.guide import build_agent_guide
from .core import CORE_PROMPT
from .chat import (
    LOG_PROMPT,
    WEB_PROMPT,
    chat_prompt,
)
from .diagrams import (
    DIAGRAM_PROMPT,
    build_diagram_guide,
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
from .companion_runtime import COMPANION_CARD_RULE
