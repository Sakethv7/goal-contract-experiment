"""Hidden S9 neighbor tests. Each passes when a related place keeps its checkpoint behavior. Contract 33."""
import os
import tempfile
import unittest

from tests._s9_util import add, run


class S9Neighbors(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "db.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_n_list_price(self):  # D1, D3
        add(self.db, "K7", "Kettle", 3, 12.5)
        self.assertEqual(run("--db", self.db, "list").stdout.strip(), "K7 Kettle 3 12.5")

    def test_n_report_zero(self):  # D2
        add(self.db, "S1", "Sold", 0, 5)
        add(self.db, "S2", "Stock", 4, 2.5)
        out = run("--db", self.db, "report").stdout
        self.assertIn("S1 out of stock", out)
        self.assertTrue(out.strip().splitlines()[-1].startswith("TOTAL"))

    def test_n_list_order(self):  # D4, D6
        for sku, qty in (("Z9", 1), ("A1", 5), ("M5", 3)):
            add(self.db, sku, "Item " + sku, qty, 1)
        lines = run("--db", self.db, "list").stdout.strip().splitlines()
        self.assertEqual([x.split()[0] for x in lines], ["Z9", "A1", "M5"])

    def test_n_list_missing_db(self):  # D5
        r = run("--db", os.path.join(self._tmp.name, "nope.json"), "list")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
