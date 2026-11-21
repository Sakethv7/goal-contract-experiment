"""Visible, stage-aware acceptance script. Covers rules 1 to 8 on data/items_raw.csv.

It runs the CLI in a temp folder. If a stage command does not exist yet, it stops checking and exits with what it has.
Exit 0 if every check on the built stages passes. Exit 1 otherwise.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "items_raw.csv"


def run(cwd, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=cwd, env=env, capture_output=True, text=True)


def not_built(r):
    return r.returncode == 2 and "invalid choice" in r.stderr


def load(path):
    def bad(token):
        raise ValueError("float " + token)
    return json.loads(path.read_text(), parse_float=bad)


def report(failed, name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failed.append(name)


def main() -> int:
    failed = []
    with tempfile.TemporaryDirectory() as d:
        r = run(d, "ingest", str(DATA))
        if not_built(r):
            print("stage 1 not built yet. Nothing to check.")
            return 0
        s1 = Path(d, "out", "stage1.json")
        if r.returncode != 0 or not s1.exists():
            print("FAIL ingest did not run:", r.stderr.strip()[-200:])
            return 1
        try:
            rows1 = load(s1)
        except ValueError as e:
            print("FAIL R8 stage1.json has a", e)
            return 1
        report(failed, "R1 stage 1 keeps input order", [r["sku"] for r in rows1] == ["T3", "P2", "K9", "C4"])
        report(failed, "R2 price_cents is an exact integer", [r.get("price_cents") for r in rows1] == [230, 15, 1299, 29])
        report(failed, "R3 name is trimmed", rows1 and rows1[0].get("name") == "Tape")
        report(failed, "R4 blank sku dropped", len(rows1) == 4)
        r = run(d, "transform")
        if not_built(r):
            print("stage 2 not built yet.")
            return 1 if failed else 0
        s2 = Path(d, "out", "stage2.json")
        if r.returncode != 0 or not s2.exists():
            print("FAIL transform did not run:", r.stderr.strip()[-200:])
            return 1
        try:
            rows2 = load(s2)
        except ValueError as e:
            print("FAIL R8 stage2.json has a", e)
            return 1
        report(failed, "R5 qty 0 dropped", [r["sku"] for r in rows2] == ["T3", "K9", "C4"])
        report(failed, "R6 value_cents is qty times price_cents", [r.get("value_cents") for r in rows2] == [920, 7794, 29])
        report(failed, "R7 stage 2 keeps stage 1 order", [r["sku"] for r in rows2] == [r["sku"] for r in rows1 if r["sku"] != "P2"])
        report(failed, "R2 again: stage 2 keeps integer cents", [r.get("price_cents") for r in rows2] == [230, 1299, 29])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
