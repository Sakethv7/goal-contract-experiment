import csv
import json
import os
import tempfile
import unittest

from inventory.export import export_csv


class ExportTest(unittest.TestCase):
    def test_export_keeps_order(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"sku": "Z", "name": "z", "qty": 1, "price_cents": 5, "value_cents": 5},
                    {"sku": "A", "name": "a", "qty": 2, "price_cents": 7, "value_cents": 14}]
            json.dump(rows, open(os.path.join(d, "stage2.json"), "w"))
            out = os.path.join(d, "o.csv")
            export_csv(out, d)
            got = list(csv.reader(open(out)))
            self.assertEqual([r[0] for r in got], ["sku", "Z", "A"])


if __name__ == "__main__":
    unittest.main()
