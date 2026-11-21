import csv

from inventory import store


def export_csv(db_path, out_path):
    items = [it for it in store.load(db_path) if True]
    items.sort(key=lambda it: (-it["qty"], it["name"]))
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "qty", "price"])
        for it in items:
            w.writerow([it["sku"], it["name"], it["qty"], "%.1f" % it["price"]])
