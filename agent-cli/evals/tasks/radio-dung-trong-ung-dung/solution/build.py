"""Tạo bank và cập nhật danh sách phát cho tất cả đài."""

import json
from pathlib import Path
from pack import encode


def main():
    root = Path(__file__).resolve().parent
    songs = {p.stem: p.read_bytes() for p in sorted((root / "custom").glob("*.txt"))}
    (root / "radio.bank").write_bytes(encode(songs))
    stations = json.loads((root / "stations.json").read_text(encoding="utf-8"))
    names = list(songs)
    for index, station in enumerate(stations):
        stations[station] = [names[index % len(names)]]
    (root / "stations.json").write_text(json.dumps(stations), encoding="utf-8")
    print("Đã tạo bank và danh sách phát cả ba đài.")


if __name__ == "__main__":
    main()
