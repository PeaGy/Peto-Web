import unittest

from report.parse import load, parse_line, parse_sale
from report.summary import total_by_category


class HiddenParse(unittest.TestCase):
    def test_simple_line_trimmed(self):
        self.assertEqual(parse_line(" 2026-09-01 , Lan ,Đồ uống, 45000 \r\n"), ["2026-09-01", "Lan", "Đồ uống", "45000"])

    def test_quoted_comma(self):
        sale = parse_sale('2026-09-02,"Công ty An Phát, chi nhánh 2",Văn phòng phẩm,1250000')
        self.assertEqual((sale.customer, sale.category, sale.amount),
                         ("Công ty An Phát, chi nhánh 2", "Văn phòng phẩm", 1250000))

    def test_escaped_quotes(self):
        sale = parse_sale('2026-09-02,"Cửa hàng ""Hoa Mai""",Bánh kẹo,210000')
        self.assertEqual(sale.customer, 'Cửa hàng "Hoa Mai"')

    def test_empty_customer(self):
        self.assertEqual(parse_sale("2026-09-03,,Đồ uống,10000").customer, "")

    def test_sample_file_totals(self):
        totals = total_by_category(load("data/sales.csv"))
        self.assertEqual(totals, {"Bánh kẹo": 210000, "Văn phòng phẩm": 1336000, "Đồ uống": 75000})

    def test_original_tests_still_hold(self):
        self.assertEqual(parse_line("2026-09-01,Lan,Đồ uống,45000"), ["2026-09-01", "Lan", "Đồ uống", "45000"])


if __name__ == "__main__":
    unittest.main()
