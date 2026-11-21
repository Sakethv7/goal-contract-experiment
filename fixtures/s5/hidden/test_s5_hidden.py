"""Hidden S5 tests. One test per rule, named test_r1 to test_r12. The harness copies this file and the data into tests/."""
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "items_raw_hidden.csv"


def run(cwd, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=cwd, env=env, capture_output=True, text=True)


def no_floats(path):
    def bad(token):
        raise AssertionError("float in " + path.name + ": " + token)
    return json.loads(path.read_text(), parse_float=bad)


def pipeline(d):
    """Runs ingest and transform in folder d. Returns (stage1 path, stage2 path)."""
    for step in (("ingest", str(DATA)), ("transform",)):
        r = run(d, *step)
        assert r.returncode == 0, "step %s failed: %s" % (step[0], r.stderr[-300:])
    return Path(d, "out", "stage1.json"), Path(d, "out", "stage2.json")


def export(d, name="o.csv", *extra):
    out = Path(d, name)
    r = run(d, "export", str(out), *extra)
    assert r.returncode == 0, "export failed: " + r.stderr[-300:]
    with open(out, newline="") as f:
        return list(csv.reader(f))


class S5Hidden(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name

    def test_r01_stage1_keeps_input_order(self):
        s1, _ = pipeline(self.d)
        self.assertEqual([r["sku"] for r in no_floats(s1)], ["Z9", "A1", "M5", "B7"])

    def test_r02_price_is_integer_cents(self):
        s1, _ = pipeline(self.d)
        self.assertEqual([r["price_cents"] for r in no_floats(s1)], [410, 9999, 1999, 7])

    def test_r03_name_trimmed(self):
        s1, _ = pipeline(self.d)
        self.assertEqual(no_floats(s1)[0]["name"], "Zinc plate")

    def test_r04_blank_sku_dropped(self):
        s1, _ = pipeline(self.d)
        rows = no_floats(s1)
        self.assertEqual(len(rows), 4)
        self.assertNotIn("Ghost row", [r["name"] for r in rows])

    def test_r05_zero_qty_dropped_in_stage2(self):
        _, s2 = pipeline(self.d)
        self.assertEqual([r["sku"] for r in no_floats(s2)], ["Z9", "M5", "B7"])

    def test_r06_value_cents(self):
        _, s2 = pipeline(self.d)
        self.assertEqual([r["value_cents"] for r in no_floats(s2)], [1230, 3998, 70])

    def test_r07_stage2_keeps_order(self):
        s1, s2 = pipeline(self.d)
        order1 = [r["sku"] for r in no_floats(s1) if r["sku"] != "A1"]
        self.assertEqual([r["sku"] for r in no_floats(s2)], order1)

    def test_r08_no_floats_in_stage_files(self):
        s1, s2 = pipeline(self.d)
        no_floats(s1)
        no_floats(s2)

    def test_r09_header_and_plain_values(self):
        pipeline(self.d)
        rows = export(self.d)
        self.assertEqual(rows[0], ["sku", "name", "qty", "price_cents", "value_cents"])
        self.assertEqual(rows[1], ["Z9", "Zinc plate", "3", "410", "1230"])
        self.assertEqual(rows[3], ["B7", "Bolt, hex", "10", "7", "70"])

    def test_r10_csv_keeps_order(self):
        pipeline(self.d)
        self.assertEqual([r[0] for r in export(self.d)[1:]], ["Z9", "M5", "B7"])

    def test_r11_existing_out_refused_unless_force(self):
        pipeline(self.d)
        out = Path(self.d, "o.csv")
        out.write_text("old\n")
        r = run(self.d, "export", str(out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("exists, use --force", r.stderr)
        self.assertEqual(out.read_text(), "old\n")
        forced = [run(self.d, "export", str(out), "--force"), run(self.d, "export", "--force", str(out)),
                  run(self.d, "--force", "export", str(out))]
        self.assertTrue(any(f.returncode == 0 for f in forced))
        self.assertEqual(out.read_text().splitlines()[0], "sku,name,qty,price_cents,value_cents")

    def test_r12_missing_stage2_errors(self):
        r = run(self.d, "export", str(Path(self.d, "o.csv")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: stage2.json missing", r.stderr)


if __name__ == "__main__":
    unittest.main()
