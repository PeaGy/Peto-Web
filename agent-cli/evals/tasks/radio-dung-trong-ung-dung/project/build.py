"""Tạo bank từ hai bài custom; danh sách đài được quản lý trong stations.json."""

from pathlib import Path
from pack import encode


def main():
    root = Path(__file__).resolve().parent
    songs = {p.stem: p.read_bytes() for p in sorted((root / "custom").glob("*.txt"))}
    (root / "radio.bank").write_bytes(encode(songs))
    print("Đã tạo bank.")


if __name__ == "__main__":
    main()
