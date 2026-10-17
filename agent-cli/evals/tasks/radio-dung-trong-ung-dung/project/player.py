"""Bộ đọc độc lập mô phỏng ứng dụng đích."""

import json
from pathlib import Path
import struct


def play(root):
    blob = (root / "radio.bank").read_bytes()
    if blob[:4] != b"MUS1":
        raise ValueError("Sai magic.")
    count = struct.unpack_from("<I", blob, 4)[0]
    songs = {}
    for index in range(count):
        name, offset, size = struct.unpack_from("<16sII", blob, 8 + index * 24)
        if offset % 16 or offset < 8 + count * 24 or offset + size > len(blob):
            raise ValueError("Payload không căn lề hoặc ra ngoài bank.")
        songs[name.rstrip(b"\0").decode("ascii")] = blob[offset:offset+size]
    stations = json.loads((root / "stations.json").read_text(encoding="utf-8"))
    return {station: [songs[name].decode("utf-8") for name in tracks] for station, tracks in stations.items()}


if __name__ == "__main__":
    print(json.dumps(play(Path(__file__).resolve().parent), ensure_ascii=False))
