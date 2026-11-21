import unittest

from inventory.report import total_report


class ReportTest(unittest.TestCase):
    def test_total(self):
        items = [{"sku": "A1", "name": "W", "qty": 2, "price": 1.5}]
        self.assertIn("TOTAL $3.00", total_report(items))

    def test_out_of_stock(self):
        items = [{"sku": "B2", "name": "X", "qty": 0, "price": 9.0}]
        self.assertIn("B2 out of stock", total_report(items))


if __name__ == "__main__":
    unittest.main()
