"""Đóng gói và tự đọc lại bank."""

import struct


def encode(songs):
    offset = 8 + 24 * len(songs)
    table, payload = bytearray(), bytearray()
    for name, data in songs.items():
        table.extend(struct.pack("<16sII", name.encode("ascii"), offset, len(data)))
        payload.extend(data)
        offset += len(data)
    return b"MUS1" + struct.pack("<I", len(songs)) + table + payload


def decode(blob):
    count = struct.unpack_from("<I", blob, 4)[0]
    result = {}
    for index in range(count):
        name, offset, size = struct.unpack_from("<16sII", blob, 8 + index * 24)
        result[name.rstrip(b"\0").decode("ascii")] = blob[offset:offset+size]
    return result
