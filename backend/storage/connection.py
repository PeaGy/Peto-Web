"""Kết nối SQLite dùng chung cho các nhóm truy vấn.

Mọi kết nối của backend mở qua ``connect()``. Khóa ngoại của SQLite mặc định tắt và chỉ bật theo từng kết nối, lại
không có tác dụng khi đặt trong một giao dịch, nên bật ngay lúc mở thay vì để từng hàm nhớ tự bật.
"""
import sqlite3

import aiosqlite
from core.config import DB_PATH

# Khi kết nối khác đang giữ khóa ghi, chờ tối đa chừng này giây rồi mới báo "database is locked". Bằng mặc định của
# sqlite3.connect, nay ghi rõ để PRAGMA busy_timeout của mọi kết nối là 5000 ms.
BUSY_TIMEOUT_SECONDS = 5.0


class _ForeignKeys(sqlite3.Connection):
    """Kết nối bật khóa ngoại ngay khi mở, trước mọi giao dịch, để ON DELETE CASCADE và kiểm hàng cha có hiệu lực."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.execute('PRAGMA foreign_keys=ON')


def connect(*, foreign_keys: bool = True, path=None) -> aiosqlite.Connection:
    """Mở kết nối cùng database riêng của Peto Web, có khóa ngoại và busy_timeout.

    ``path`` chỉ dành cho module tự giữ đường dẫn database (ngân sách TTS ở ``features/voice/cloud.py``); mặc định
    là ``DB_PATH``.

    Chỉ bước nâng cấp schema (``storage.schema.init_db``) truyền ``foreign_keys=False``: dựng lại bảng bằng
    ``DROP TABLE`` khi khóa ngoại đang bật sẽ xóa dây chuyền mọi hàng con (ảnh đại diện, bài yêu thích...).
    """
    return aiosqlite.connect(path or DB_PATH, timeout=BUSY_TIMEOUT_SECONDS,
                             factory=_ForeignKeys if foreign_keys else sqlite3.Connection)
