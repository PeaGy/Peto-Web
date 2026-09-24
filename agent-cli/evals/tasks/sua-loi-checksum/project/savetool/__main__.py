"""python -m savetool show <file> | set-gold <file> <số vàng>"""

import argparse
import json
import sys

from .format import SaveError, load, save


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="savetool")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="in nội dung file save")
    show.add_argument("path")
    gold = commands.add_parser("set-gold", help="đổi số vàng")
    gold.add_argument("path")
    gold.add_argument("amount", type=int)
    args = parser.parse_args(argv)
    try:
        data = load(args.path)
    except (OSError, SaveError) as err:
        print(f"Lỗi: {err}", file=sys.stderr)
        return 1
    if args.command == "show":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    data["gold"] = args.amount
    save(args.path, data)
    print(f"Đã đặt vàng = {args.amount}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
