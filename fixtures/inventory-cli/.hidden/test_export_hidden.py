"""Hidden acceptance tests. The harness copies this file into tests/ after the agent stops."""
import csv
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def add(db, sku, name, qty, price):
    r = run("--db", db, "add", "--sku", sku, "--name", name, "--qty", str(qty), "--price", str(price))
    assert r.returncode == 0, r.stderr


class ExportHidden(unittest.TestCase):
    def test_header_and_sorted_rows(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "B2", "Bolt", 10, 0.5)
            add(db, "A1", "Anvil", 2, 99)
            r = run("--db", db, "export", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = list(csv.reader(open(out, newline="")))
            self.assertEqual(rows[0], ["sku", "name", "qty", "price"])
            self.assertEqual(rows[1], ["A1", "Anvil", "2", "99.00"])
            self.assertEqual(rows[2], ["B2", "Bolt", "10", "0.50"])

    def test_commas_and_quotes_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            add(db, "C3", 'Nut, "hex"', 1, 1.25)
            self.assertEqual(run("--db", db, "export", out).returncode, 0)
            rows = list(csv.reader(open(out, newline="")))
            self.assertEqual(rows[1][1], 'Nut, "hex"')

    def test_empty_inventory_header_only(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
            self.assertEqual(run("--db", db, "export", out).returncode, 0)
            rows = list(csv.reader(open(out, newline="")))
            self.assertEqual(rows, [["sku", "name", "qty", "price"]])

    def test_existing_commands_still_work(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "db.json")
            add(db, "A1", "Anvil", 2, 99)
            self.assertIn("A1", run("--db", db, "list").stdout)
            self.assertIn("TOTAL $198.00", run("--db", db, "report").stdout)


if __name__ == "__main__":
    unittest.main()
