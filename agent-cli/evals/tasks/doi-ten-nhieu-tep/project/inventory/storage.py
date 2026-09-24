"""Đọc, ghi kho hàng dạng JSON: {"items": [{"sku", "name", "qty", "price"}, …]}."""

import json
from pathlib import Path

from .models import Item


def load(path) -> list[Item]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Item(sku=row["sku"], name=row["name"], qty=int(row["qty"]), price=int(row["price"]))
            for row in data["items"]]


def save(path, items: list[Item]) -> None:
    rows = [{"sku": item.sku, "name": item.name, "qty": item.qty, "price": item.price} for item in items]
    Path(path).write_text(json.dumps({"items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
