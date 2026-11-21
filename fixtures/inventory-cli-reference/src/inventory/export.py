import csv

from inventory import store


def export_csv(db_path, out_path):
    items = sorted(store.load(db_path), key=lambda it: it["sku"])
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "qty", "price"])
        for it in items:
            w.writerow([it["sku"], it["name"], it["qty"], "%.2f" % it["price"]])
