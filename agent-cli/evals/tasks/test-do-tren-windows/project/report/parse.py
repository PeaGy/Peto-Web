"""Đọc file CSV bán hàng: ngày, khách, nhóm hàng, số tiền (dòng đầu là tiêu đề)."""

from dataclasses import dataclass


@dataclass
class Sale:
    date: str
    customer: str
    category: str
    amount: int


def parse_line(line: str) -> list[str]:
    return [field.strip() for field in line.rstrip("\r\n").split(",")]


def parse_sale(line: str) -> Sale:
    date, customer, category, amount = parse_line(line)
    return Sale(date, customer, category, int(amount))


def load(path) -> list[Sale]:
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    return [parse_sale(line) for line in lines[1:] if line.strip()]
