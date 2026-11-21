import json
import os
import tempfile
import unittest

from inventory.transform import transform


class TransformTest(unittest.TestCase):
    def test_drops_zero_and_adds_value(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"sku": "A", "name": "a", "qty": 0, "price_cents": 5}, {"sku": "B", "name": "b", "qty": 2, "price_cents": 7}]
            json.dump(rows, open(os.path.join(d, "stage1.json"), "w"))
            transform(d)
            out = json.load(open(os.path.join(d, "stage2.json")))
            self.assertEqual([r["sku"] for r in out], ["B"])
            self.assertEqual(out[0]["value_cents"], 14)


if __name__ == "__main__":
    unittest.main()
