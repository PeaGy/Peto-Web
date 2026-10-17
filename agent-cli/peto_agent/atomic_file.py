"""Ghi thay tệp cùng thư mục; chỉ thử lại lỗi chia sẻ/quyền tạm thời của Windows trong thời gian ngắn."""

import os
import secrets
import time
from pathlib import Path

REPLACE_DELAYS = (0.01, 0.03, 0.07)


def write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        for attempt in range(len(REPLACE_DELAYS) + 1):
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                if (os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33}
                        or attempt == len(REPLACE_DELAYS)):
                    raise
                time.sleep(REPLACE_DELAYS[attempt])
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
