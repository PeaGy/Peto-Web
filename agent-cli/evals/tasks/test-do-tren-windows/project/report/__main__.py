import sys

from .parse import load
from .summary import total_by_category


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Dùng: python -m report <file.csv>", file=sys.stderr)
        return 2
    totals = total_by_category(load(args[0]))
    for category, amount in totals.items():
        print(f"{category:<20} {amount:>14,} đ")
    return 0


raise SystemExit(main())
