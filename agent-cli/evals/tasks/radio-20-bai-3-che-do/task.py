"""Bài tích hợp nhiều lớp: âm thanh, container, metadata và thứ tự ghi đè."""

import json
import math
import struct
import wave
import zlib
from pathlib import Path

TITLE = "20 bài custom cho 23 đài ở ba chế độ tải dữ liệu"
KIND = "tích hợp dữ liệu"
PROJECT = "radio-lab"
MAX_STEPS = 40
PROMPT = """
Đưa toàn bộ 20 tệp WAV trong custom/ vào thay hết nhạc cũ của cả 23 đài, kể cả đài nói chuyện.
Mỗi đài chỉ còn một bài custom; dùng đủ 20 bài, ba đài còn lại được dùng lại bài.
Phải chạy đúng ở cả base, lost và ballad. Bộ build hiện báo thành công và test roundtrip cũng qua,
nhưng ứng dụng player.py chưa dùng được. Sửa công cụ build/đóng gói và dữ liệu cần thiết để hoàn thành.
Giữ nguyên player.py, loader.json, tests/, references/ và custom/; không bỏ kiểm tra, không thay bộ đọc.
Giữ nguyên danh tính/thứ tự/loại đài, gain của đài, quảng cáo, tin tức và dữ liệu nhiệm vụ.
Âm thanh cần giữ nguyên sample rate, số kênh, toàn bộ mẫu PCM và seek được tới cuối bài.
Làm trên dự án này, không cần cài thêm gói hay dùng mạng. Tự kiểm tra kết quả rồi báo phạm vi đã kiểm.
"""
SOLUTION_REPLY = "Đã sửa đóng gói, metadata và lớp ghi đè; 23 đài ở cả ba chế độ dùng đủ 20 bài và seek đúng."


def prepare(root):
    """Tạo dữ liệu nhỏ, xác định trước; không chứa nhạc hay dữ liệu thương mại."""
    for name in ("custom", "references", "game/base/audio", "game/lost/audio", "game/ballad/audio"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for index in range(20):
        rate, channels, frames = (8000, 11025, 22050)[index % 3], 1 + index % 2, 201 + index * 37
        pcm = b"".join(struct.pack("<h", int(14000 * math.sin((n + 1) * (index + 2) * (c + 1) * .017)))
                       for n in range(frames) for c in range(channels))
        with wave.open(str(root / "custom" / f"bai-{index + 1:02}.wav"), "wb") as out:
            out.setparams((channels, 2, rate, frames, "NONE", "not compressed"))
            out.writeframes(pcm)
    # Vector chuẩn độc lập: mỗi khối lưu hết kênh trái rồi mới đến kênh phải, có mốc cuối.
    pcm = struct.pack("<14h", *range(14))
    with wave.open(str(root / "references/stock.wav"), "wb") as out:
        out.setparams((2, 2, 8000, 7, "NONE", "not compressed"))
        out.writeframes(pcm)
    frames, block, channels = 7, 4, 2
    data_start, payload, entries = 64, bytearray(), []
    for first in (0, 4):
        payload.extend(b"\0" * (-(data_start + len(payload)) % 16))
        entries.append((first, data_start + len(payload)))
        for channel in range(channels):
            for n in range(first, min(first + block, frames)):
                payload.extend(pcm[(n * channels + channel) * 2:(n * channels + channel) * 2 + 2])
    entries.append((frames, data_start + len(payload)))
    header = struct.pack("<4s7I", b"RDX2", 8000, channels, frames, block, 2, data_start, zlib.crc32(pcm))
    table = b"".join(struct.pack("<II", *row) for row in entries)
    (root / "references/stock.rdx").write_bytes(header + table + b"\0" * (data_start - 32 - len(table)) + payload)
    for mode in ("base", "lost", "ballad"):
        catalog = {"version": 2, "advertising": ["ad-001", "ad-002"], "news": {"enabled": True},
                   "missions": {"phone": "speech-801", "intro": "scene-109"}, "stations": []}
        for index in range(23):
            catalog["stations"].append({"id": f"station-{index + 1:02}",
                "kind": "talk" if index in (5, 12, 20) else "music", "gain": round(.6 + index * .01, 2),
                "playlist": [{"clip": f"old-{mode}-{index:02}-{n}", "duration_ms": 180000 + n}
                             for n in range(6 if index < 9 else 5)]})
        (root / f"game/{mode}/catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")


def check(ctx):
    ok, detail = ctx.unittest()
    ctx.require("23 đài × 3 chế độ, PCM/seek chính xác và build lặp lại", ok, detail)
    touched = ctx.touched("player.py", "loader.json", "tests/*", "custom/*", "references/*")
    ctx.require("Giữ nguyên bộ đọc, nguồn, loader và vector chuẩn", not touched, ", ".join(touched))
    ctx.bonus("Peto tự chạy ứng dụng sau khi sửa", any(
        "player.py" in str(c.get("arguments")) for c in ctx.called("run_command", "start_command")))
