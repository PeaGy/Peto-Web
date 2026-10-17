"""Dựng clip và cập nhật playlist của từng lớp mà không đổi metadata khác."""

import json
import wave
from pathlib import Path
from pack import encode

ROOT = Path(__file__).resolve().parent


def main():
    sources = sorted((ROOT / "custom").glob("*.wav"))
    clips, payloads = [], {}
    for source in sources:
        with wave.open(str(source), "rb") as wav:
            rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
            pcm = wav.readframes(frames)
        payloads[source.stem] = encode(pcm, rate, channels)
        clips.append({"clip": source.stem, "duration_ms": (frames * 1000 + rate - 1) // rate})
    for mode in ("base", "lost", "ballad"):
        folder = ROOT / "game" / mode
        audio = folder / "audio"
        audio.mkdir(parents=True, exist_ok=True)
        for name, data in payloads.items():
            (audio / (name + ".rdx")).write_bytes(data)
        path = folder / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        for index, station in enumerate(catalog["stations"]):
            station["playlist"] = [dict(clips[index % len(clips)])]
        path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Build thành công cho base, lost và ballad.")


if __name__ == "__main__":
    main()
