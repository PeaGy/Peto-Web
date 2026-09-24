import unittest

from inventory import search
from inventory.models import Item

ITEMS = [Item(product_code="A-1", name="Bút bi", qty=3, price=5000),
         Item(product_code="B-2", name="Vở kẻ ngang", qty=40, price=18000)]


class SearchTest(unittest.TestCase):
    def test_find_by_code_ignores_case(self):
        self.assertEqual(search.find_by_code(ITEMS, " b-2 ").name, "Vở kẻ ngang")

    def test_find_by_code_missing(self):
        self.assertIsNone(search.find_by_code(ITEMS, "Z-9"))

    def test_search_name(self):
        self.assertEqual([item.product_code for item in search.search_name(ITEMS, "bút")], ["A-1"])


if __name__ == "__main__":
    unittest.main()
