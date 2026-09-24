from dataclasses import dataclass


@dataclass
class Item:
    sku: str
    name: str
    qty: int
    price: int  # đồng

    @property
    def value(self) -> int:
        return self.qty * self.price
