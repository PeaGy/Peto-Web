import unittest

from inventory import report
from inventory.models import Item

ITEMS = [Item(product_code="A-1", name="Bút", qty=3, price=5000),
         Item(product_code="B-2", name="Vở", qty=40, price=18000)]


class ReportTest(unittest.TestCase):
    def test_low_stock(self):
        self.assertEqual([item.product_code for item in report.low_stock(ITEMS, 5)], ["A-1"])

    def test_total_value(self):
        self.assertEqual(report.total_value(ITEMS), 3 * 5000 + 40 * 18000)

    def test_table_lists_codes(self):
        table = report.format_table(ITEMS)
        self.assertIn("A-1", table)
        self.assertIn("B-2", table)


if __name__ == "__main__":
    unittest.main()
