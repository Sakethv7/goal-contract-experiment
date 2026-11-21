"""Old exporter, kept for reference. It reads the JSON store and writes a CSV for the finance team."""
import csv

from inventory import store


def export_csv(db_path, out_path):
    items = sorted(store.load(db_path), key=lambda it: it["sku"])
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["SKU", "Name", "Qty", "Price"])
        w.writeheader()
        for it in items:
            w.writerow({"SKU": it["sku"], "Name": it["name"], "Qty": it["qty"], "Price": "%.2f" % it["price"]})
