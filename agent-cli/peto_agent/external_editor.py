"""/editor: soạn yêu cầu dài trong trình soạn của bạn (CLI 0.23.0, theo /editor của opencode).

Trình soạn lấy từ VISUAL rồi EDITOR như git; không đặt thì dùng ``code --wait`` khi đang ở terminal của VS Code, cuối
cùng là Notepad. Chữ soạn xong nằm vào ô nhập, chưa gửi.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class EditorError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def command() -> str:
    """Lệnh mở trình soạn, chưa có đường dẫn tệp. Chạy qua shell nên giữ được cả lệnh kèm tham số trong biến môi
    trường (``"C:\\Program Files\\Notepad++\\notepad++.exe" -multiInst``)."""
    for name in ("VISUAL", "EDITOR"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if os.environ.get("TERM_PROGRAM") == "vscode" and shutil.which("code"):
        return "code --wait"
    return "notepad.exe" if os.name == "nt" else "vi"


def program(cmd: str) -> str:
    """Chương trình của lệnh: phần trong ngoặc kép đầu tiên, hoặc chữ đầu tiên."""
    cmd = cmd.strip()
    return cmd.split('"')[1] if cmd.startswith('"') else cmd.split(" ")[0]


def label(cmd: str) -> str:
    """Tên ngắn của trình soạn cho dòng "Đang soạn trong …"."""
    name = Path(program(cmd)).name
    return {"code": "VS Code", "notepad.exe": "Notepad", "notepad": "Notepad"}.get(name.lower(), name or cmd)


def edit(initial: str = "", *, cmd: str | None = None) -> str | None:
    """Mở trình soạn với ``initial`` trong một tệp tạm .md rồi chờ nó đóng. Trả chữ đã soạn (bỏ dòng trống cuối), hoặc
    None khi tệp trống hay không đổi gì. Trình soạn không chạy được thì ném EditorError."""
    cmd = cmd or command()
    found = program(cmd)
    if not found or not (Path(found).is_file() or shutil.which(found)):
        # cmd /c báo lệnh không có bằng mã 1 như mọi lỗi khác, nên tìm trước khi chạy.
        raise EditorError(f"Không tìm thấy trình soạn \"{cmd}\". Đặt biến EDITOR, ví dụ: $env:EDITOR = 'notepad'.")
    handle, name = tempfile.mkstemp(prefix="peto-", suffix=".md")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write(initial)
        try:
            code = subprocess.call(f'{cmd} "{path}"', shell=True)
        except OSError as err:
            raise EditorError(f"Không mở được trình soạn ({err}). Đặt biến EDITOR, ví dụ: $env:EDITOR = 'notepad'.") \
                from None
        # cmd báo 9009 khi không tìm thấy lệnh; shell của Linux/macOS báo 127.
        if code in {9009, 127}:
            raise EditorError(f"Không tìm thấy trình soạn \"{cmd}\". Đặt biến EDITOR, ví dụ: $env:EDITOR = 'notepad'.")
        if code != 0:
            raise EditorError(f"Trình soạn \"{cmd}\" thoát với mã {code}; ô nhập để nguyên.")
        try:
            # Notepad cũ lưu UTF-8 kèm BOM: utf-8-sig bỏ nó đi.
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as err:
            raise EditorError(f"Không đọc lại được tệp đã soạn ({err}).") from None
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    text = text.replace("\r\n", "\n").rstrip("\n")
    if not text.strip() or text == initial.rstrip("\n"):
        return None
    return text
