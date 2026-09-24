"""Đọc, ghi file SAV1: magic, độ dài, dữ liệu JSON, checksum."""

import json
import struct

from .checksum import checksum

MAGIC = b"SAV1"


class SaveError(ValueError):
    """File save hỏng hoặc không đúng định dạng."""


def pack(data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = MAGIC + struct.pack("<I", len(payload)) + payload
    return body + struct.pack("<I", checksum(body))


def unpack(raw: bytes) -> dict:
    if len(raw) < 12 or raw[:4] != MAGIC:
        raise SaveError("Không phải file SAV1")
    (length,) = struct.unpack("<I", raw[4:8])
    body, tail = raw[:8 + length], raw[8 + length:]
    if len(tail) != 4:
        raise SaveError("Độ dài dữ liệu không khớp")
    (expected,) = struct.unpack("<I", tail)
    if checksum(body) != expected:
        raise SaveError("Sai checksum: file bị sửa tay hoặc hỏng")
    return json.loads(body[8:].decode("utf-8"))


def load(path) -> dict:
    with open(path, "rb") as handle:
        return unpack(handle.read())


def save(path, data: dict) -> None:
    with open(path, "wb") as handle:
        handle.write(pack(data))
