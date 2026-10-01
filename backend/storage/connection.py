"""Kết nối SQLite dùng chung cho các nhóm truy vấn."""
import aiosqlite
from core.config import DB_PATH

def connect() -> aiosqlite.Connection:
    """Mở kết nối cùng database riêng của Peto Web."""
    return aiosqlite.connect(DB_PATH)
