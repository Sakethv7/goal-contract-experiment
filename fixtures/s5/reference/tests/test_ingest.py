import json
import os
import tempfile
import unittest

from inventory.ingest import ingest


class IngestTest(unittest.TestCase):
    def test_cents_trim_blank_sku(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            open(src, "w").write("sku,name,qty,price\nA1, Axe ,1,19.99\n,Ghost,1,1.00\n")
            ingest(src, os.path.join(d, "out"))
            rows = json.load(open(os.path.join(d, "out", "stage1.json")))
            self.assertEqual(rows, [{"sku": "A1", "name": "Axe", "qty": 1, "price_cents": 1999}])


if __name__ == "__main__":
    unittest.main()
