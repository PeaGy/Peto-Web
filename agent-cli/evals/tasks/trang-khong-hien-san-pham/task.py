"""Trang web tĩnh không hiện sản phẩm vì lỗi JavaScript chỉ thấy khi chạy trang (sai tên khóa trong JSON)."""

import time

TITLE = "Trang cửa hàng không hiện sản phẩm"
KIND = "sửa lỗi web"
PROJECT = "shop-page"
MAX_STEPS = 14
NEEDS = ("edge",)
PROMPT = """
Mở trang shop-page lên thì không thấy sản phẩm nào, chỉ hiện chữ "Đang tải sản phẩm…" mãi. Xem giúp mình bị gì và
sửa nha.
"""
SOLUTION_REPLY = "products.json dùng khóa items nhưng app.js đọc data.item; đã sửa thành data.items, trang hiện đủ 6 sản phẩm."


def check(ctx):
    with ctx.serve() as base, ctx.page(f"{base}/index.html") as (page, result):
        count = 0
        for _ in range(20):
            count = ctx.evaluate(page, "document.querySelectorAll('#products .product').length")
            if count == 6:
                break
            time.sleep(0.2)
        status = ctx.evaluate(page, "document.getElementById('status') && document.getElementById('status').textContent")
        problems = result.get("problems", []) + page.late_problems()
    ctx.require("Hiện đủ 6 sản phẩm", count == 6, f"thấy {count}")
    ctx.require("Trang không còn lỗi JavaScript", not problems, "; ".join(problems)[:300])
    ctx.bonus("Dòng trạng thái báo số sản phẩm", "6" in (status or ""), status or "")
    ctx.bonus("Sửa code, không đổi dữ liệu products.json", not ctx.touched("products.json"))
