"""Bản build hiện tại tạo clip nhưng chỉ cập nhật đài âm nhạc ở lớp base."""

import json
import wave
from pathlib import Path
from pack import encode

ROOT = Path(__file__).resolve().parent


def main():
    sources = sorted((ROOT / "custom").glob("*.wav"))
    clips = []
    audio = ROOT / "game/base/audio"
    audio.mkdir(parents=True, exist_ok=True)
    for source in sources:
        with wave.open(str(source), "rb") as wav:
            pcm, rate, channels = wav.readframes(wav.getnframes()), wav.getframerate(), wav.getnchannels()
        (audio / (source.stem + ".rdx")).write_bytes(encode(pcm, rate, channels))
        clips.append({"clip": source.stem, "duration_ms": len(pcm) // (2 * channels) // rate * 1000})
    path = ROOT / "game/base/catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    for index, station in enumerate(catalog["stations"]):
        if station["kind"] == "music":
            station["playlist"] = [clips[index % len(clips)]]
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Build thành công.")


if __name__ == "__main__":
    main()
