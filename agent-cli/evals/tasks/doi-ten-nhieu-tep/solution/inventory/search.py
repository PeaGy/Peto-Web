from .models import Item


def find_by_code(items: list[Item], product_code: str) -> Item | None:
    wanted = product_code.strip().upper()
    return next((item for item in items if item.product_code.upper() == wanted), None)


def search_name(items: list[Item], text: str) -> list[Item]:
    needle = text.casefold()
    return [item for item in items if needle in item.name.casefold()]
