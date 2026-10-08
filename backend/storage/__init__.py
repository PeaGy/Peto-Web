"""Giao diện lưu trữ; câu SQL nằm trong module của từng tính năng."""
from .schema import (
    init_db,
)
from .users import (
    upsert_user,
    PROFILE_FIELDS,
    get_profile,
    save_profile,
    get_user,
    has_roleplay_consent,
    add_roleplay_consent,
)
from .conversations import (
    create_conversation,
    owns_conversation,
    conversation_settings,
    latest_conversation,
    list_conversations,
    get_messages,
    add_message,
    set_title_if_empty,
    set_title,
    delete_conversation,
)
from .attachments import (
    conversation_images,
    add_attachment,
    get_attachment,
    save_document,
    list_attachment_paths,
)
from .imagine import (
    get_imagine_job,
    get_imagine_request,
    update_imagine_job,
    interrupt_imagine_jobs,
    discard_imagine_outputs,
    create_imagine_job,
    add_imagine_image,
    list_imagine_jobs,
    get_imagine_image,
    delete_imagine_job,
    delete_imagine_image,
    set_imagine_image_liked,
)
from .agent import (
    create_agent_device,
    find_agent_device,
    touch_agent_device,
    list_agent_devices,
    revoke_agent_device,
)
from .usage import (
    take_agent_step,
    take_voice_chars,
    refund_voice_chars,
    voice_chars_used,
    refund_agent_step,
    add_agent_tokens,
    get_agent_usage,
    get_agent_steps,
)
from .memory import (
    list_memories,
    memory_state,
    ensure_memory_state,
    set_memory_enabled,
    companion_messages_after,
    apply_memory_changes,
    delete_memory,
    clear_memories,
    companion_summary,
    messages_before_window,
    save_companion_summary,
)
