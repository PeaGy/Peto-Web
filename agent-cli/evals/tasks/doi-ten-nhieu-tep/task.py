"""Việc dài đụng nhiều tệp: đổi tên một trường khắp dự án mà vẫn đọc được file dữ liệu cũ."""

import json
import re

TITLE = "Đổi sku thành product_code khắp dự án inventory"
KIND = "việc dài"
PROJECT = "inventory"
MAX_STEPS = 20
PROMPT = """
Đổi tên trường `sku` thành `product_code` trong toàn bộ dự án inventory: code, test, README và file dữ liệu mẫu. Hàm
`find_by_sku` đổi thành `find_by_code`, lệnh `find --sku` đổi thành `find --code`. File JSON cũ còn dùng khóa `sku` thì
vẫn phải đọc được nha.
"""
SOLUTION_REPLY = "Đã đổi sku thành product_code trong models, storage, search, cli, report, test, README và data/kho.json; storage.load vẫn đọc khóa sku cũ."


def check(ctx):
    ok, detail = ctx.unittest()
    ctx.require("Test ẩn qua", ok, detail)
    ok, detail = ctx.unittest(hidden=False)
    ctx.require("Test của dự án vẫn qua", ok, detail)
    ctx.require("README dùng product_code", ctx.says(r"product_code", text=ctx.read("README.md")))
    try:
        rows = json.loads(ctx.read("data/kho.json"))["items"]
        sample_ok = all("product_code" in row and "sku" not in row for row in rows) and len(rows) == 5
    except (ValueError, KeyError, TypeError):
        sample_ok = False
    ctx.require("File mẫu data/kho.json dùng product_code, đủ 5 món", sample_ok)
    leftovers = [path for path in ("inventory/models.py", "inventory/search.py", "inventory/cli.py",
                                   "inventory/report.py") if re.search(r"\bsku\b", ctx.read(path), re.I)]
    ctx.bonus("Chỉ còn chữ sku ở phần đọc file cũ", not leftovers, ", ".join(leftovers))
    ctx.bonus("Có thêm test đọc file cũ", re.search(r"\bsku\b", "".join(ctx.read(p) for p in ctx.touched("tests/*"))))
