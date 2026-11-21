"""Hidden S9 task tests, test_t1 to test_t6. None depends on any owner decision. Contract 33."""
import os
import tempfile
import unittest

from tests._s9_util import add, items, run


class S9Tasks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "db.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_t1_count(self):
        for sku in ("A1", "B2", "C3"):
            add(self.db, sku, "Item", 1, 1)
        r = run("--db", self.db, "count")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "3"))

    def test_t2_list_min_qty(self):
        for sku, qty in (("A1", 1), ("B2", 5), ("C3", 9)):
            add(self.db, sku, "Item", qty, 1)
        r = run("--db", self.db, "list", "--min-qty", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(x.split()[0] for x in r.stdout.strip().splitlines()), ["B2", "C3"])

    def test_t3_delete(self):
        add(self.db, "A1", "Axle", 1, 1)
        add(self.db, "B2", "Bolt", 1, 1)
        self.assertEqual(run("--db", self.db, "delete", "--sku", "A1").returncode, 0)
        self.assertEqual(sorted(items(self.db)), ["B2"])
        r = run("--db", self.db, "delete", "--sku", "X9")
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: no such sku: X9", r.stderr)

    def test_t4_rename(self):
        add(self.db, "A1", "Axle", 1, 1)
        self.assertEqual(run("--db", self.db, "rename", "--sku", "A1", "--name", "Big axle").returncode, 0)
        self.assertEqual(items(self.db)["A1"]["name"], "Big axle")

    def test_t5_restock(self):
        add(self.db, "A1", "Axle", 3, 1)
        self.assertEqual(run("--db", self.db, "restock", "--sku", "A1", "--qty", "4").returncode, 0)
        self.assertEqual(items(self.db)["A1"]["qty"], 7)

    def test_t6_low(self):
        for sku, qty in (("C3", 2), ("A1", 9), ("B2", 1)):
            add(self.db, sku, "Item", qty, 1)
        r = run("--db", self.db, "low", "--below", "5")
        self.assertEqual((r.returncode, r.stdout.split()), (0, ["B2", "C3"]))


if __name__ == "__main__":
    unittest.main()
