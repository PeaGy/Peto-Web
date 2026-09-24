import argparse
import sys

from . import report, search, storage


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="inventory")
    parser.add_argument("--file", default="data/kho.json", help="file JSON của kho")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="cả kho và tổng giá trị")
    low = commands.add_parser("low", help="hàng sắp hết")
    low.add_argument("--threshold", type=int, default=5)
    find = commands.add_parser("find", help="tìm theo mã hàng")
    find.add_argument("--code", required=True)
    args = parser.parse_args(argv)
    items = storage.load(args.file)
    if args.command == "list":
        print(report.format_table(items))
        print(f"Tổng giá trị: {report.total_value(items):,} đ")
    elif args.command == "low":
        print(report.format_table(report.low_stock(items, args.threshold)))
    else:
        item = search.find_by_code(items, args.code)
        if item is None:
            print(f"Không có mã {args.code}", file=sys.stderr)
            return 1
        print(report.format_table([item]))
    return 0
