from .models import Item


def low_stock(items: list[Item], threshold: int = 5) -> list[Item]:
    return [item for item in items if item.qty <= threshold]


def total_value(items: list[Item]) -> int:
    return sum(item.value for item in items)


def format_table(items: list[Item]) -> str:
    lines = [f"{'Mã hàng':<10} {'Tên':<24} {'SL':>5} {'Giá':>10}"]
    for item in items:
        lines.append(f"{item.sku:<10} {item.name:<24} {item.qty:>5} {item.price:>10,}")
    return "\n".join(lines)
