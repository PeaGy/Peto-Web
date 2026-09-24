import unittest

from report.parse import Sale
from report.summary import total_by_category


class SummaryTest(unittest.TestCase):
    def test_totals(self):
        sales = [Sale("2026-09-01", "Lan", "Đồ uống", 45000), Sale("2026-09-02", "Minh", "Đồ uống", 30000),
                 Sale("2026-09-03", "Tuấn", "Bánh kẹo", 12000)]
        self.assertEqual(total_by_category(sales), {"Bánh kẹo": 12000, "Đồ uống": 75000})


if __name__ == "__main__":
    unittest.main()
