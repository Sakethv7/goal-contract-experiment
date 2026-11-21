"""Hidden S9 state tests. One test per state each changed rule can be in. Contract 33 and Contract 36."""
import os
import tempfile
import unittest

from tests._s9_util import add, export_rows, run


def prices(d):
    db = os.path.join(d, "db.json")
    add(db, "P1", "Pen", 1, 3.1)
    add(db, "P2", "Pad", 1, 40)
    by_sku = {r[0]: r[3] for r in export_rows(db, os.path.join(d, "out.csv"))}
    return [by_sku.get("P1"), by_sku.get("P2")]  # row order depends on the sort rule, so read by sku


def zero_qty_skus(d):
    db = os.path.join(d, "db.json")
    add(db, "S1", "Sold out", 0, 5)
    add(db, "S2", "In stock", 4, 5)
    return [r[0] for r in export_rows(db, os.path.join(d, "out.csv"))]


def sort_skus(d):
    db = os.path.join(d, "db.json")
    for sku, name, qty in (("A1", "Zed", 5), ("B2", "Amy", 5), ("C3", "Max", 9)):
        add(db, sku, name, qty, 1)
    return [r[0] for r in export_rows(db, os.path.join(d, "out.csv"))]


def missing_db(d, text):
    db, out = os.path.join(d, "nope.json"), os.path.join(d, "out.csv")
    r = run("--db", db, "export", out)
    return r.returncode == 1 and (text + db) in r.stderr and not os.path.exists(db) and not os.path.exists(out)


class S9States(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_r3_base(self):
        self.assertEqual(prices(self.d), ["3.10", "40.00"])

    def test_r3_d1(self):
        self.assertEqual(prices(self.d), ["310", "4000"])

    def test_r3_d3(self):
        self.assertEqual(prices(self.d), ["3.1", "40.0"])

    def test_r4_base(self):
        self.assertEqual(zero_qty_skus(self.d), ["S2"])

    def test_r4_d2(self):
        self.assertEqual(sorted(zero_qty_skus(self.d)), ["S1", "S2"])

    def test_r2_base(self):
        self.assertEqual(sort_skus(self.d), ["A1", "B2", "C3"])

    def test_r2_d4(self):
        self.assertEqual(sort_skus(self.d), ["C3", "A1", "B2"])

    def test_r2_d6(self):
        self.assertEqual(sort_skus(self.d), ["C3", "B2", "A1"])

    def test_r5_base(self):
        self.assertTrue(missing_db(self.d, "error: db not found: "))

    def test_r5_d5(self):
        self.assertTrue(missing_db(self.d, "error: database missing: "))


if __name__ == "__main__":
    unittest.main()
