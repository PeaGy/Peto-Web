"""Bộ đọc độc lập; không nhập encoder hoặc decoder của công cụ build."""

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_clip(path):
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError("Header thiếu")
    magic, rate, channels, frames, block, count, start, crc = struct.unpack_from("<4s7I", data)
    if magic != b"RDX2" or rate <= 0 or channels not in (1, 2) or not frames or not block:
        raise ValueError("Header không hợp lệ")
    if count != (frames + block - 1) // block or 32 + (count + 1) * 8 > start:
        raise ValueError("Bảng seek thiếu khối hoặc mốc cuối")
    if start % 16 or start > len(data):
        raise ValueError("Vùng data chưa căn lề 16")
    table = [struct.unpack_from("<II", data, 32 + i * 8) for i in range(count + 1)]
    if table[-1] != (frames, len(data)) or table[0][1] != start:
        raise ValueError("Mốc cuối/đầu không khớp kích thước")
    if any(data[32 + (count + 1) * 8:start]):
        raise ValueError("Padding bảng seek khác zero")
    pcm = bytearray()
    for index in range(count):
        first, offset = table[index]
        amount = min(block, frames - first)
        end = offset + amount * channels * 2
        next_offset = table[index + 1][1]
        if first != index * block or offset % 16 or end > next_offset or next_offset > len(data):
            raise ValueError("Mốc khối/căn lề/kích thước không hợp lệ")
        if any(data[end:next_offset]):
            raise ValueError("Padding audio khác zero")
        for n in range(amount):
            for channel in range(channels):
                pos = offset + (channel * amount + n) * 2
                pcm.extend(data[pos:pos + 2])
    if len(pcm) != frames * channels * 2 or zlib.crc32(pcm) != crc:
        raise ValueError("PCM sai bố trí kênh, bị cắt hoặc CRC không khớp")
    # Đọc seek bằng offset trên đĩa, so với bản giải mã tuần tự.
    for n in sorted({0, 1, frames // 2, max(0, frames - 2), frames - 1}):
        i = n // block
        first, offset = table[i]
        amount = min(block, frames - first)
        for channel in range(channels):
            pos = offset + (channel * amount + n - first) * 2
            expected = (n * channels + channel) * 2
            if data[pos:pos + 2] != pcm[expected:expected + 2]:
                raise ValueError("Seek khác giải mã tuần tự")
    return {"rate": rate, "channels": channels, "frames": frames, "crc": crc,
            "sha256": hashlib.sha256(pcm).hexdigest()}


def play(mode, station_id=None):
    loader = json.loads((ROOT / "loader.json").read_text(encoding="utf-8"))
    stations = {}
    for layer in loader[mode]:
        folder = ROOT / "game" / layer
        catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
        for station in catalog["stations"]:
            stations[station["id"]] = (station, folder)
    result = []
    for key, (station, folder) in stations.items():
        if station_id and key != station_id:
            continue
        if len(station["playlist"]) != 1:
            raise ValueError(f"{key}: cần đúng một bài, đang có {len(station['playlist'])}")
        clip = station["playlist"][0]
        info = read_clip(folder / "audio" / (clip["clip"] + ".rdx"))
        if clip["duration_ms"] != (info["frames"] * 1000 + info["rate"] - 1) // info["rate"]:
            raise ValueError(f"{key}: thời lượng metadata sai")
        result.append({"station": key, "clip": clip["clip"], **info})
    if not result:
        raise ValueError("Không có đài")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("base", "lost", "ballad"), default="base")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--station")
    args = parser.parse_args()
    print(json.dumps(play(args.mode, args.station), ensure_ascii=False, indent=2))
