import unittest

from inventory.models import Item


class ItemTest(unittest.TestCase):
    def test_value(self):
        self.assertEqual(Item(sku="A-1", name="Bút", qty=3, price=5000).value, 15000)


if __name__ == "__main__":
    unittest.main()
