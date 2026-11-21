import csv
import json
import os


def export_csv(out_path, out_dir="out"):
    with open(os.path.join(out_dir, "stage2.json")) as f:
        rows = json.load(f)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "qty", "price_cents", "value_cents"])
        for r in rows:
            w.writerow([r["sku"], r["name"], r["qty"], r["price_cents"], r["value_cents"]])
