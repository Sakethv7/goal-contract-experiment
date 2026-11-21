import argparse
import os
import sys

from inventory import store
from inventory.export import export_csv
from inventory.report import total_report

DB_MISSING = "error: database missing: "


def build_parser():
    p = argparse.ArgumentParser(prog="inventory")
    p.add_argument("--db", default="inventory.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("--sku", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--qty", type=int, required=True)
    add.add_argument("--price", type=float, required=True)

    lst = sub.add_parser("list")
    lst.add_argument("--min-qty", type=int)
    sub.add_parser("report")
    sub.add_parser("count")

    exp = sub.add_parser("export")
    exp.add_argument("out")
    exp.add_argument("--force", action="store_true")

    for name in ("delete", "rename", "restock"):
        s = sub.add_parser(name)
        s.add_argument("--sku", required=True)
        if name == "rename":
            s.add_argument("--name", required=True)
        if name == "restock":
            s.add_argument("--qty", type=int, required=True)
    low = sub.add_parser("low")
    low.add_argument("--below", type=int, required=True)
    return p


def run_export(args):
    if not os.path.exists(args.db):
        print(DB_MISSING + args.db, file=sys.stderr)
        return 1
    if os.path.exists(args.out) and not args.force:
        print("error: %s exists, use --force" % args.out, file=sys.stderr)
        return 1
    export_csv(args.db, args.out)
    return 0


def edit_item(args):
    items = store.load(args.db)
    match = [it for it in items if it["sku"] == args.sku]
    if not match:
        print("error: no such sku: " + args.sku, file=sys.stderr)
        return 1
    if args.cmd == "delete":
        items.remove(match[0])
    elif args.cmd == "rename":
        match[0]["name"] = args.name
    else:
        match[0]["qty"] += args.qty
    store.save(args.db, items)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "add":
        store.add_item(args.db, args.sku, args.name, args.qty, args.price)
        return 0
    if args.cmd == "list":
        for it in store.load(args.db):
            if args.min_qty is None or it["qty"] >= args.min_qty:
                print(it["sku"], it["name"], it["qty"], it["price"])
        return 0
    if args.cmd == "report":
        print(total_report(store.load(args.db)))
        return 0
    if args.cmd == "count":
        print(len(store.load(args.db)))
        return 0
    if args.cmd == "export":
        return run_export(args)
    if args.cmd in ("delete", "rename", "restock"):
        return edit_item(args)
    if args.cmd == "low":
        for sku in sorted(it["sku"] for it in store.load(args.db) if it["qty"] < args.below):
            print(sku)
        return 0
    return 1
