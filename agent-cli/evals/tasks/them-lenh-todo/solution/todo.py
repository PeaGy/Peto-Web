"""Danh sách việc cần làm, lưu trong một file JSON.

    python todo.py add "Mua sữa"
    python todo.py list [--chua-xong]
    python todo.py done 1
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_FILE = Path("todo.json")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add(items: list[dict], title: str) -> dict:
    item = {"id": max((item["id"] for item in items), default=0) + 1, "title": title, "done": False}
    items.append(item)
    return item


def format_item(item: dict) -> str:
    return f"[{'x' if item['done'] else ' '}] {item['id']}. {item['title']}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="file JSON lưu danh sách")
    commands = parser.add_subparsers(dest="command", required=True)
    adding = commands.add_parser("add", help="thêm việc")
    adding.add_argument("title")
    listing = commands.add_parser("list", help="xem danh sách")
    listing.add_argument("--chua-xong", action="store_true", help="chỉ hiện việc chưa xong")
    finishing = commands.add_parser("done", help="đánh dấu việc đã xong")
    finishing.add_argument("id", type=int)
    args = parser.parse_args(argv)
    items = load(args.file)
    if args.command == "add":
        item = add(items, args.title)
        save(args.file, items)
        print(f"Đã thêm: {format_item(item)}")
    elif args.command == "done":
        item = next((item for item in items if item["id"] == args.id), None)
        if item is None:
            print(f"Không có việc số {args.id}", file=sys.stderr)
            return 1
        item["done"] = True
        save(args.file, items)
        print(f"Đã xong: {format_item(item)}")
    elif args.command == "list":
        if not items:
            print("Chưa có việc nào.")
        for item in items:
            if args.chua_xong and item["done"]:
                continue
            print(format_item(item))
    return 0


if __name__ == "__main__":
    sys.exit(main())
