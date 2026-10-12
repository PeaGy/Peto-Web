"""Chép chữ vào clipboard của Windows: kéo chuột chọn chữ trong màn hình toàn phần thì thả tay là chép, như Claude Code.

Màn hình bắt chuột nên terminal không tự chọn chữ được nữa (giữ Shift khi kéo thì vẫn chọn kiểu terminal).
"""

from __future__ import annotations

import os
import time

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def copy_text(text: str) -> bool:
    """True nếu đã chép. Clipboard đang bị chương trình khác giữ thì thử lại vài lần rồi thôi."""
    if os.name != "nt" or not text:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    for function, arguments, result in (
            (user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
            (user32.CloseClipboard, [], wintypes.BOOL),
            (user32.EmptyClipboard, [], wintypes.BOOL),
            (user32.SetClipboardData, [wintypes.UINT, handle], handle),
            (kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], handle),
            (kernel32.GlobalLock, [handle], ctypes.c_void_p),
            (kernel32.GlobalUnlock, [handle], wintypes.BOOL),
            (kernel32.GlobalFree, [handle], handle)):
        function.argtypes, function.restype = arguments, result
    data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-16-le") + b"\0\0"
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return False
    try:
        user32.EmptyClipboard()
        memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not memory:
            return False
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            kernel32.GlobalFree(memory)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(memory)
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            # Clipboard chưa nhận thì vùng nhớ vẫn là của mình.
            kernel32.GlobalFree(memory)
            return False
        return True
    finally:
        user32.CloseClipboard()
