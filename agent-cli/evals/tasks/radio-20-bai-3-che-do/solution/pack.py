"""Đóng gói PCM theo đặc tả RDX2, giữ đủ mẫu và mốc seek cuối."""

import struct
import zlib


def encode(pcm, rate, channels, block=64):
    if channels not in (1, 2) or rate <= 0 or block <= 0 or not pcm or len(pcm) % (2 * channels):
        raise ValueError("PCM hoặc tham số không hợp lệ")
    frames = len(pcm) // (2 * channels)
    count = (frames + block - 1) // block
    start = (32 + (count + 1) * 8 + 15) // 16 * 16
    payload, entries = bytearray(), []
    for first in range(0, frames, block):
        payload.extend(b"\0" * (-(start + len(payload)) % 16))
        entries.append((first, start + len(payload)))
        for channel in range(channels):
            for frame in range(first, min(first + block, frames)):
                pos = (frame * channels + channel) * 2
                payload.extend(pcm[pos:pos + 2])
    entries.append((frames, start + len(payload)))
    header = struct.pack("<4s7I", b"RDX2", rate, channels, frames, block, count, start, zlib.crc32(pcm))
    table = b"".join(struct.pack("<II", *entry) for entry in entries)
    return header + table + b"\0" * (start - 32 - len(table)) + payload


def decode(data):
    magic, rate, channels, frames, block, count, start, checksum = struct.unpack_from("<4s7I", data)
    pcm = bytearray()
    for index in range(count):
        first, offset = struct.unpack_from("<II", data, 32 + index * 8)
        amount = min(block, frames - first)
        for frame in range(amount):
            for channel in range(channels):
                pos = offset + (channel * amount + frame) * 2
                pcm.extend(data[pos:pos + 2])
    assert zlib.crc32(pcm) == checksum
    return bytes(pcm), rate, channels
