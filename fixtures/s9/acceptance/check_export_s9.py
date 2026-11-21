"""Visible acceptance script for S9, arm T only. Checks that `export OUT` runs and writes the header row.
It checks no rule that an owner decision can change. Exit 0 if it passes."""
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
    with tempfile.TemporaryDirectory() as d:
        db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
        run("--db", db, "add", "--sku", "A1", "--name", "Axle", "--qty", "2", "--price", "3")
        r = run("--db", db, "export", out)
        if r.returncode != 0 or not os.path.exists(out):
            print("FAIL export OUT did not run:", r.stderr.strip())
            return 1
        header = next(csv.reader(open(out, newline="")), None)
    if header != ["sku", "name", "qty", "price"]:
        print("FAIL header is not sku,name,qty,price")
        return 1
    print("ok   export runs and writes the header")
    return 0


if __name__ == "__main__":
    sys.exit(main())
