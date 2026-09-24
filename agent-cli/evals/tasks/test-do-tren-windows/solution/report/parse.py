"""Đọc file CSV bán hàng: ngày, khách, nhóm hàng, số tiền (dòng đầu là tiêu đề)."""

import csv
from dataclasses import dataclass


@dataclass
class Sale:
    date: str
    customer: str
    category: str
    amount: int


def parse_line(line: str) -> list[str]:
    # Tên khách có thể chứa dấu phẩy trong ngoặc kép ("Công ty A, chi nhánh 2"): tách theo chuẩn CSV.
    return [field.strip() for field in next(csv.reader([line.rstrip("\r\n")], skipinitialspace=True))]


def parse_sale(line: str) -> Sale:
    date, customer, category, amount = parse_line(line)
    return Sale(date, customer, category, int(amount))


def load(path) -> list[Sale]:
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    return [parse_sale(line) for line in lines[1:] if line.strip()]
