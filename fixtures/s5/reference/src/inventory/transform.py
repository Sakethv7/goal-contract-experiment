import json
import os


def transform(out_dir="out"):
    with open(os.path.join(out_dir, "stage1.json")) as f:
        rows = json.load(f)
    rows = [r for r in rows if r["qty"] != 0]  # DROP_ZERO
    for r in rows:
        r["value_cents"] = r["qty"] * r["price_cents"]
    with open(os.path.join(out_dir, "stage2.json"), "w") as f:
        json.dump(rows, f, indent=2)
