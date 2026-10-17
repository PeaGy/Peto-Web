"""Đóng gói đúng căn lề và đọc bank."""

import struct


def encode(songs):
    head = 8 + 24 * len(songs)
    offset = (head + 15) & ~15
    table, payload = bytearray(), bytearray(offset - head)
    for name, data in songs.items():
        table.extend(struct.pack("<16sII", name.encode("ascii"), offset, len(data)))
        payload.extend(data)
        offset += len(data)
        padding = (-offset) % 16
        payload.extend(bytes(padding))
        offset += padding
    return b"MUS1" + struct.pack("<I", len(songs)) + table + payload


def decode(blob):
    count = struct.unpack_from("<I", blob, 4)[0]
    result = {}
    for index in range(count):
        name, offset, size = struct.unpack_from("<16sII", blob, 8 + index * 24)
        result[name.rstrip(b"\0").decode("ascii")] = blob[offset:offset+size]
    return result
