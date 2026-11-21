import csv
import os
import tempfile
import unittest

from inventory import store
from inventory.export import export_csv


class ExportTest(unittest.TestCase):
    def test_export_sorted_two_decimals_skips_zero(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            store.add_item(db, "B2", "Bolt", 0, 1)
            store.add_item(db, "A1", "Anvil", 2, 99)
            export_csv(db, out)
            rows = list(csv.reader(open(out, newline="")))
            self.assertEqual(rows, [["sku", "name", "qty", "price"], ["A1", "Anvil", "2", "99.00"]])


if __name__ == "__main__":
    unittest.main()
