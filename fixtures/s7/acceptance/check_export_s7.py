"""Visible acceptance script for S7. Checks the export subcommand on three sample items: header, price format, zero qty. It does not check the sort order, which the owner changes. Exit 0 if all pass."""
import csv
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def main() -> int:
    failed = []
    with tempfile.TemporaryDirectory() as d:
        db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
        for sku, name, qty, price in (("C3", "Cog", 5, 2.5), ("A1", "Axle", 0, 7), ("B2", "Bolt", 9, 10)):
            run("--db", db, "add", "--sku", sku, "--name", name, "--qty", str(qty), "--price", str(price))
        r = run("--db", db, "export", out)
        if r.returncode != 0 or not os.path.exists(out):
            print("FAIL R1: export OUT did not run:", r.stderr.strip())
            return 1
        rows = list(csv.reader(open(out, newline="")))
        checks = {
            "R1 header is sku,name,qty,price": rows[:1] == [["sku", "name", "qty", "price"]],
            "R3 price has two decimals": all(len(x[3].split(".")[-1]) == 2 for x in rows[1:]),
            "R4 qty 0 skipped": all(x[2] != "0" for x in rows[1:]) and len(rows) == 3,
        }
        for name, ok in checks.items():
            print(("ok   " if ok else "FAIL ") + name)
            if not ok:
                failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
