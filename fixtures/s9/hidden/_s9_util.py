"""Shared helpers for the S9 hidden tests. The harness copies this file into tests/ with the tests."""
import csv
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=60)


def add(db, sku, name, qty, price):
    r = run("--db", db, "add", "--sku", sku, "--name", name, "--qty", str(qty), "--price", str(price))
    assert r.returncode == 0, r.stderr


def export_rows(db, out):
    r = run("--db", db, "export", out)
    assert r.returncode == 0, r.stderr
    with open(out, newline="") as f:
        return list(csv.reader(f))[1:]


def items(db):
    with open(db) as f:
        return {it["sku"]: it for it in json.load(f)}
