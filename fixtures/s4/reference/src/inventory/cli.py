import argparse
import os
import sys

from inventory import store
from inventory.export import export_csv
from inventory.report import total_report


def build_parser():
    p = argparse.ArgumentParser(prog="inventory")
    p.add_argument("--db", default="inventory.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("--sku", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--qty", type=int, required=True)
    add.add_argument("--price", type=float, required=True)

    sub.add_parser("list")
    sub.add_parser("report")

    exp = sub.add_parser("export")
    exp.add_argument("out")
    exp.add_argument("--force", action="store_true")
    return p


def run_export(args):
    if not os.path.exists(args.db):
        print("error: db not found: " + args.db, file=sys.stderr)
        return 1
    if os.path.exists(args.out) and not args.force:
        print("error: %s exists, use --force" % args.out, file=sys.stderr)
        return 1
    export_csv(args.db, args.out)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "add":
        store.add_item(args.db, args.sku, args.name, args.qty, args.price)
        return 0
    if args.cmd == "list":
        for it in store.load(args.db):
            print(it["sku"], it["name"], it["qty"], it["price"])
        return 0
    if args.cmd == "report":
        print(total_report(store.load(args.db)))
        return 0
    if args.cmd == "export":
        return run_export(args)
    return 1
