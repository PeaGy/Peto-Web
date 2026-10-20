"""Kho khóa bí mật của nguồn model trực tiếp (lộ trình nhiều nguồn, M3).

Windows: mã hóa bằng DPAPI theo tài khoản Windows đang đăng nhập (CryptProtectData qua ctypes, không thư viện ngoài).
Mỗi kết nối một tệp trong ``<hồ sơ peto>/credentials``, kèm entropy là mã kết nối, nên chép tệp sang mã khác không giải
được. Hệ khác chưa có kho của hệ điều hành nên chưa hỗ trợ; không bao giờ lưu khóa dạng chữ thường.
Khóa không được in, ghi nhật ký, đưa vào hội thoại, lời nhắc hay môi trường của lệnh con.
"""

from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path

from . import config

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
CRYPTPROTECT_UI_FORBIDDEN = 0x1
MAX_SECRET_CHARS = 4096


class CredentialError(Exception):
    pass


def available() -> bool:
    return os.name == "nt"


def _folder() -> Path:
    return config.home() / "credentials"


def _path(connection_id: str) -> Path:
    if not isinstance(connection_id, str) or not _ID.fullmatch(connection_id):
        raise CredentialError("Mã kết nối không hợp lệ.")
    return _folder() / f"{connection_id}.bin"


if os.name == "nt":
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                                            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _transform(data: bytes, entropy: bytes, *, protect: bool) -> bytes:
    source, keep_source = _blob(data)
    salt, keep_salt = _blob(entropy)
    result = _Blob()
    call = _crypt32.CryptProtectData if protect else _crypt32.CryptUnprotectData
    ok = (call(ctypes.byref(source), "Peto Agent", ctypes.byref(salt), None, None, CRYPTPROTECT_UI_FORBIDDEN,
               ctypes.byref(result)) if protect else
          call(ctypes.byref(source), None, ctypes.byref(salt), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)))
    del keep_source, keep_salt
    if not ok:
        raise CredentialError("Windows không mã hóa hay giải mã được khóa đã lưu (DPAPI).")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _entropy(connection_id: str) -> bytes:
    return f"peto-agent:{connection_id}".encode("utf-8")


def save(connection_id: str, secret: str) -> None:
    if not available():
        raise CredentialError("Máy này chưa có kho khóa an toàn mà Peto hỗ trợ (hiện chỉ Windows).")
    if not isinstance(secret, str) or not secret or len(secret) > MAX_SECRET_CHARS or not secret.isprintable():
        raise CredentialError("Khóa không hợp lệ.")
    target = _path(connection_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _transform(secret.encode("utf-8"), _entropy(connection_id), protect=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load(connection_id: str) -> str:
    if not available():
        raise CredentialError("Máy này chưa có kho khóa an toàn mà Peto hỗ trợ (hiện chỉ Windows).")
    try:
        data = _path(connection_id).read_bytes()
    except OSError:
        raise CredentialError("Không tìm thấy khóa của kết nối này. Kết nối lại nhé.") from None
    try:
        return _transform(data, _entropy(connection_id), protect=False).decode("utf-8")
    except UnicodeDecodeError:
        raise CredentialError("Khóa đã lưu bị hỏng. Kết nối lại nhé.") from None


def delete(connection_id: str) -> bool:
    try:
        _path(connection_id).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise CredentialError("Không xóa được khóa đã lưu.") from None
