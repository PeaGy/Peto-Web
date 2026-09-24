from collections import defaultdict


def total_by_category(sales) -> dict[str, int]:
    totals = defaultdict(int)
    for sale in sales:
        totals[sale.category] += sale.amount
    return dict(sorted(totals.items()))
