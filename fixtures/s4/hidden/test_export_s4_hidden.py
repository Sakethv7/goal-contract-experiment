"""Hidden S4 tests. One test per rule, named test_r1 to test_r6. The harness copies this file into tests/."""
import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def add(db, sku, name, qty, price):
    r = run("--db", db, "add", "--sku", sku, "--name", name, "--qty", str(qty), "--price", str(price))
    assert r.returncode == 0, r.stderr


def rows_of(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


class S4Hidden(unittest.TestCase):
    def test_r1_positional_out_and_header(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "K7", "Kettle", 3, 12.5)
            r = run("--db", db, "export", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(rows_of(out)[0], ["sku", "name", "qty", "price"])
            self.assertEqual(len(rows_of(out)), 2)

    def test_r2_sorted_by_sku(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            for sku in ("Z9", "A1", "M5"):
                add(db, sku, "Item " + sku, 1, 2)
            self.assertEqual(run("--db", db, "export", out).returncode, 0)
            self.assertEqual([r[0] for r in rows_of(out)[1:]], ["A1", "M5", "Z9"])

    def test_r3_price_two_decimals(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "P1", "Pen", 1, 3.1)
            add(db, "P2", "Pad", 1, 40)
            self.assertEqual(run("--db", db, "export", out).returncode, 0)
            self.assertEqual([r[3] for r in rows_of(out)[1:]], ["3.10", "40.00"])

    def test_r4_zero_qty_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "S1", "Sold out", 0, 5)
            add(db, "S2", "In stock", 4, 5)
            self.assertEqual(run("--db", db, "export", out).returncode, 0)
            self.assertEqual([r[0] for r in rows_of(out)[1:]], ["S2"])

    def test_r5_missing_db_errors_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "nope.json"), os.path.join(d, "out.csv")
            r = run("--db", db, "export", out)
            self.assertEqual(r.returncode, 1)
            self.assertIn("error: db not found", r.stderr)
            self.assertIn(db, r.stderr)
            self.assertFalse(os.path.exists(db))
            self.assertFalse(os.path.exists(out))

    def test_r6_existing_out_refused_unless_force(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "F1", "Fork", 2, 1)
            Path(out).write_text("old\n")
            r = run("--db", db, "export", out)
            self.assertEqual(r.returncode, 1)
            self.assertIn("exists, use --force", r.stderr)
            self.assertEqual(Path(out).read_text(), "old\n")
            forced = [run("--db", db, "export", out, "--force"), run("--db", db, "export", "--force", out),
                      run("--db", db, "--force", "export", out)]
            self.assertTrue(any(f.returncode == 0 for f in forced))
            self.assertEqual(rows_of(out)[0], ["sku", "name", "qty", "price"])


if __name__ == "__main__":
    unittest.main()
