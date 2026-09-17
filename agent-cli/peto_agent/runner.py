"""Chạy lệnh trong thư mục dự án. Hết giờ hay Ctrl+C thì giết cả cây tiến trình, không chỉ tiến trình cha."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

MAX_RESULT_CHARS = 20_000
KEEP_BYTES = 512 * 1024


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


def run(command: str, cwd: Path, timeout: float, *, on_progress: Callable[[float, str], None] | None = None) -> dict:
    """Trả mã thoát, thời gian và output đã cắt gọn. Ctrl+C thì giết cây tiến trình rồi ném lại KeyboardInterrupt."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    # Nhóm tiến trình riêng: Ctrl+C trong cửa sổ chỉ tới CLI, CLI tự quyết định dừng lệnh.
    options: dict = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
    started = time.monotonic()
    process = subprocess.Popen(command, shell=True, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
    head, tail = bytearray(), bytearray()
    recent = bytearray()
    recent_lock = threading.Lock()
    dropped = 0

    def reader() -> None:
        nonlocal dropped
        while chunk := process.stdout.read1(65536):
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
    if timed_out:
        result["error"] = f"Lệnh chạy quá {int(timeout)} giây nên đã bị dừng."
    return result
