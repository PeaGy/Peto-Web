import unittest

from report.parse import load, parse_line, parse_sale


class ParseTest(unittest.TestCase):
    def test_simple_line(self):
        self.assertEqual(parse_line("2026-09-01,Lan,Đồ uống,45000"), ["2026-09-01", "Lan", "Đồ uống", "45000"])

    def test_quoted_customer_with_comma(self):
        sale = parse_sale('2026-09-02,"Công ty An Phát, chi nhánh 2",Văn phòng phẩm,1250000')
        self.assertEqual(sale.customer, "Công ty An Phát, chi nhánh 2")
        self.assertEqual(sale.amount, 1250000)

    def test_sample_file(self):
        sales = load("data/sales.csv")
        self.assertEqual(len(sales), 5)


if __name__ == "__main__":
    unittest.main()
