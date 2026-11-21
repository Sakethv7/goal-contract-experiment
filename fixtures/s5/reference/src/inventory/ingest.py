import csv
import json
import os
from decimal import Decimal


def ingest(in_path, out_dir="out"):
    rows = []
    with open(in_path, newline="") as f:
        for r in csv.DictReader(f):
            sku = (r["sku"] or "").strip()
            if not sku:
                continue
            cents = int((Decimal(r["price"].strip()) * 100).to_integral_value())
            rows.append({"sku": sku, "name": r["name"].strip(), "qty": int(r["qty"]), "price_cents": cents})
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "stage1.json"), "w") as f:
        json.dump(rows, f, indent=2)
