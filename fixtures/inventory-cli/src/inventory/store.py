import json
import os

# TODO: rewrite this on SQLite. The JSON file will not scale past a few
# thousand items and every write rewrites the whole file.


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save(path, items):
    with open(path, "w") as f:
        json.dump(items, f, indent=2)


def add_item(path, sku, name, qty, price):
    items = load(path)
    for it in items:
        if it["sku"] == sku:
            raise ValueError("duplicate sku: " + sku)
    items.append({"sku": sku, "name": name, "qty": qty, "price": price})
    save(path, items)
