"""Đọc, ghi kho hàng dạng JSON: {"items": [{"product_code", "name", "qty", "price"}, …]}.

File cũ dùng khóa "sku" thay cho "product_code" vẫn đọc được; lưu lại thì thành khóa mới.
"""

import json
from pathlib import Path

from .models import Item


def load(path) -> list[Item]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Item(product_code=row["product_code"] if "product_code" in row else row["sku"], name=row["name"],
                 qty=int(row["qty"]), price=int(row["price"]))
            for row in data["items"]]


def save(path, items: list[Item]) -> None:
    rows = [{"product_code": item.product_code, "name": item.name, "qty": item.qty, "price": item.price}
            for item in items]
    Path(path).write_text(json.dumps({"items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
