"""Chạy lệnh trong thư mục dự án. Hết giờ hay Ctrl+C thì giết cả cây tiến trình, không chỉ tiến trình cha."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import outputs

MAX_RESULT_CHARS = 20_000
KEEP_BYTES = 512 * 1024
# -NoProfile để hồ sơ PowerShell của người dùng không in thêm gì, -NonInteractive để lệnh không đứng chờ bàn phím.
POWERSHELL = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
SHELLS = ("cmd", "powershell")
# Windows PowerShell 5.1 ghi ra ống theo bảng mã cũ của console, nên chữ có dấu thành "?" và mất hẳn (CLI 0.22.0, thấy
# khi /update in output của install.ps1). Đặt UTF-8 không BOM trước lệnh; lệnh mở đầu bằng ``using`` phải đứng đầu
# script nên để nguyên.
POWERSHELL_UTF8 = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "


def cap_text(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    """Giữ phần đầu và phần cuối, vì lỗi thường nằm ở cuối còn lệnh đã chạy gì thì nằm ở đầu."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n… (bỏ bớt {len(text) - limit} ký tự ở giữa) …\n{text[-half:]}"


def kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Giết tiến trình cha không kéo theo tiến trình con (npm → node → vitest); taskkill /T thì có.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def spawn(command: str, cwd: Path, shell: str = "cmd") -> subprocess.Popen:
    """Mở tiến trình cho một lệnh, bằng shell mặc định của hệ hoặc bằng PowerShell."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    # Nhóm tiến trình riêng: Ctrl+C trong cửa sổ chỉ tới CLI, CLI tự quyết định dừng lệnh.
    options: dict = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
    # PowerShell nhận cả lệnh qua một tham số nên không phải lo trích dẫn như khi để shell tự tách.
    if shell == "powershell" and not command.lstrip().lower().startswith("using "):
        command = POWERSHELL_UTF8 + command
    argv: list[str] | str = [*POWERSHELL, command] if shell == "powershell" else command
    return subprocess.Popen(argv, shell=shell != "powershell", cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)


def run(command: str, cwd: Path, timeout: float, *, shell: str = "cmd",
        on_progress: Callable[[float, str], None] | None = None, spool: bool = False) -> dict:
    """Trả mã thoát, thời gian và output đã cắt gọn. Ctrl+C thì giết cây tiến trình rồi ném lại KeyboardInterrupt.

    ``spool`` (khả năng "output_files", CLI 0.25.0): ghi cả luồng output vào một tệp trong hồ sơ người dùng; output bị
    cắt thì kết quả kèm output_id để Peto đọc phần giữa bằng read_output, không thì xóa tệp.
    """
    started = time.monotonic()
    saved = outputs.Spool() if spool else None
    process = spawn(command, cwd, shell)
    head, tail = bytearray(), bytearray()
    recent = bytearray()
    recent_lock = threading.Lock()
    dropped = 0

    def reader() -> None:
        nonlocal dropped
        while chunk := process.stdout.read1(65536):
            if saved is not None:
                saved.write(chunk)
            if on_progress is not None:
                with recent_lock:
                    recent.extend(chunk)
                    del recent[:-2048]
            room = KEEP_BYTES - len(head)
            if room > 0:
                head.extend(chunk[:room])
                chunk = chunk[room:]
            if chunk:
                tail.extend(chunk)
                if len(tail) > KEEP_BYTES:
                    dropped += len(tail) - KEEP_BYTES
                    del tail[:len(tail) - KEEP_BYTES]

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    timed_out = False
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                timed_out = True
                kill_tree(process)
                break
            if on_progress is not None:
                with recent_lock:
                    latest = bytes(recent)
                on_progress(elapsed, latest.decode("utf-8", errors="replace"))
            time.sleep(0.1)
    except KeyboardInterrupt:
        kill_tree(process)
        if saved is not None:
            saved.discard()
        raise
    finally:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        thread.join(timeout=2)

    output = head.decode("utf-8", errors="replace")
    if dropped:
        output += f"\n… (bỏ bớt {dropped} byte output) …\n"
    output += tail.decode("utf-8", errors="replace")
    result = {"exit_code": process.returncode, "seconds": round(time.monotonic() - started, 1), "output": cap_text(output)}
    if saved is not None:
        kept = saved.keep() if (dropped or len(output) > MAX_RESULT_CHARS) else None
        if kept:
            result.update(kept)
        else:
            saved.discard()
    if timed_out:
        result["error"] = f"Lệnh chạy quá {int(timeout)} giây nên đã bị dừng."
    return result
