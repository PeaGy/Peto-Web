"""Đóng gói PCM cho radio và tự đọc lại để kiểm nhanh."""

import struct
import zlib


def encode(pcm, rate, channels, block=64):
    frames = len(pcm) // (2 * channels)
    count = (frames + block - 1) // block
    start = 32 + (count + 1) * 8
    header = struct.pack("<4s7I", b"RDX2", rate, channels, frames, block, count, start, zlib.crc32(pcm))
    entries = [(n, start + n * channels * 2) for n in range(0, frames, block)]
    entries.append((frames, start + len(pcm)))
    return header + b"".join(struct.pack("<II", *entry) for entry in entries) + pcm


def decode(data):
    magic, rate, channels, frames, block, count, start, checksum = struct.unpack_from("<4s7I", data)
    pcm = data[start:start + frames * channels * 2]
    assert zlib.crc32(pcm) == checksum
    return pcm, rate, channels
