from .models import Item


def find_by_sku(items: list[Item], sku: str) -> Item | None:
    wanted = sku.strip().upper()
    return next((item for item in items if item.sku.upper() == wanted), None)


def search_name(items: list[Item], text: str) -> list[Item]:
    needle = text.casefold()
    return [item for item in items if needle in item.name.casefold()]
