"""Keyword check for P1. A rule counts as kept if any of its tokens appears in the text. Contract: docs/api.md, Contract 23."""
import json
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "spec.json"


def load_spec() -> dict:
    return json.loads(SPEC.read_text())


def rules_kept(text: str, spec: dict) -> list:
    low = (text or "").lower()
    return [r["id"] for r in spec["rules"] if any(t in low for t in r["tokens"])]
