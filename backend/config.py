"""Cấu hình Peto Web. Đọc từ biến môi trường, có mặc định chạy được ngay."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env nằm ở gốc project và KHÔNG được commit. Đây là file riêng của Peto Web,
# không phải .env của bot Discord — không sao chép qua.
load_dotenv(BASE_DIR.parent / ".env")


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


# --- Lưu trữ -------------------------------------------------------------
# Database riêng của web. KHÔNG bao giờ trỏ vào bot_memory.db của bot Discord.
DB_PATH = Path(os.getenv("PETO_WEB_DB", str(BASE_DIR / "data" / "peto_web.db")))

# --- Nhà cung cấp AI -----------------------------------------------------
# "mock" = trả lời giả, không gọi mạng, không cần credential.
# "xai"  = Grok qua OAuth, dùng token riêng của Peto Web.
AI_PROVIDER = os.getenv("PETO_AI_PROVIDER", "mock").strip().lower()

XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.6").strip()
XAI_API_BASE = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip()
XAI_MAX_OUTPUT_TOKENS = _env_int("XAI_MAX_OUTPUT_TOKENS", 1200, 128, 32000)

# Token của RIÊNG Peto Web. Không trỏ vào .xai_tokens.json của bot Discord.
XAI_TOKEN_PATH = Path(
    os.getenv("PETO_XAI_TOKEN_PATH", str(BASE_DIR / "data" / "xai_tokens.json"))
)

# --- Đăng nhập Discord ---------------------------------------------------
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI", "http://localhost:5173/api/auth/discord/callback"
).strip()

# Nơi đưa người dùng về sau khi đăng nhập xong.
FRONTEND_URL = os.getenv("PETO_FRONTEND_URL", "http://localhost:5173").strip()

# Khóa ký cookie phiên. Bắt buộc đặt thật khi deploy — đổi khóa = đăng xuất tất cả.
SESSION_SECRET = os.getenv("PETO_SESSION_SECRET", "").strip()
SESSION_COOKIE = "peto_session"
SESSION_MAX_AGE = _env_int("PETO_SESSION_MAX_AGE", 60 * 60 * 24 * 30, 300, 60 * 60 * 24 * 365)
SESSION_COOKIE_SECURE = os.getenv("PETO_COOKIE_SECURE", "").strip().lower() in {
    "1", "true", "yes",
}

# Danh sách Discord ID được phép dùng web. RỖNG = không ai vào được.
# Đây là chốt chặn thay cho "không mở đăng ký công khai" ở mục 8 của handoff.
ALLOWED_DISCORD_IDS = {
    value.strip()
    for value in os.getenv("PETO_ALLOWED_DISCORD_IDS", "").split(",")
    if value.strip()
}


def owner_key(discord_id: str) -> str:
    """Khóa chủ sở hữu trong database.

    Có tiền tố nền tảng để sau này thêm cách đăng nhập khác không bị đụng ID.
    """
    return f"discord:{discord_id}"


def discord_id_from_owner(owner: str) -> str:
    """Lấy lại Discord ID từ khóa owner. Trả về "" nếu không phải owner Discord."""
    prefix = "discord:"
    if owner.startswith(prefix):
        candidate = owner[len(prefix):]
        if candidate.isdigit():
            return candidate
    return ""


# --- Trí nhớ từ bot Discord (một chiều, chỉ đọc) -------------------------
# Trống = tắt. Web vẫn chat bình thường, chỉ là không có trí nhớ cũ.
MEMORY_GATEWAY_URL = os.getenv("PETO_MEMORY_GATEWAY_URL", "").strip()
MEMORY_GATEWAY_TOKEN = os.getenv("PETO_MEMORY_GATEWAY_TOKEN", "").strip()
MEMORY_GATEWAY_TIMEOUT = _env_float("PETO_MEMORY_GATEWAY_TIMEOUT", 3.0, 0.5, 30.0)
MEMORY_CACHE_TTL = _env_float("PETO_MEMORY_CACHE_TTL", 300.0, 0.0, 3600.0)

# --- Giới hạn tải (rút gọn từ guild_ai_settings.py của bot Discord) -------
MAX_CONCURRENT = _env_int("PETO_MAX_CONCURRENT", 3, 1, 20)
MAX_QUEUE = _env_int("PETO_MAX_QUEUE", 6, 0, 50)
QUEUE_TIMEOUT_SECONDS = _env_float("PETO_QUEUE_TIMEOUT_SECONDS", 60.0, 5.0, 300.0)
COOLDOWN_SECONDS = _env_float("PETO_COOLDOWN_SECONDS", 3.0, 0.0, 300.0)

# --- Timeout theo mức suy luận (giữ đúng tinh thần bot cũ) ----------------
RESPONSE_TIMEOUTS = {
    "low": _env_float("PETO_TIMEOUT_LOW_SECONDS", 45.0, 5.0, 600.0),
    "medium": _env_float("PETO_TIMEOUT_MEDIUM_SECONDS", 180.0, 5.0, 600.0),
    "high": _env_float("PETO_TIMEOUT_HIGH_SECONDS", 240.0, 5.0, 600.0),
}

# --- Ngữ cảnh ------------------------------------------------------------
MAX_HISTORY_MESSAGES = _env_int("PETO_MAX_HISTORY", 20, 2, 100)
MAX_INPUT_CHARS = _env_int("PETO_MAX_INPUT_CHARS", 4000, 100, 20000)

# --- Phục vụ frontend đã build (production) ------------------------------
# Khi thư mục này tồn tại, backend phục vụ luôn giao diện; VPS chỉ cần một
# tiến trình và một cổng. Lúc dev thì không có `dist`, Vite lo phần giao diện.
STATIC_DIR = Path(
    os.getenv("PETO_STATIC_DIR", str(BASE_DIR.parent / "frontend" / "dist"))
)

# --- CORS ----------------------------------------------------------------
# Chỉ cho phép dev server của Vite. Không dùng "*" — mở rộng khi deploy thật.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "PETO_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
