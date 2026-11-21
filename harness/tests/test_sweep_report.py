import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS))
import sweep_report as sr  # noqa: E402

TRUTH = json.loads((HARNESS.parent / "fixtures" / "s9" / "truth-s9.json").read_text())


def fake_run(arm, k, score, n, kbv=(), spill=(), lost=(), leaks=None, cost=0.1):
    rules = list(TRUTH["final_rules"][str(k)])
    good = round(score * len(rules))
    types = {r: "new" if i < good else "base" for i, r in enumerate(rules)}
    return {"run_id": f"{arm}-S9K{k}-{n:02d}", "scenario": "S9", "valid": True, "arm": arm, "level": k,
            "decision_score": good / len(rules), "decision_results": {r: t == "new" for r, t in types.items()},
            "failure_types": types, "all_correct": good == len(rules), "quiz": {r: {"right": True} for r in rules},
            "knows_but_violates": list(kbv), "spillover": list(spill), "unrelated_losses": list(lost),
            "task_score": 1.0, "cost_usd": cost, "leaks": leaks or [[] for _ in range(k)]}


class StatsTest(unittest.TestCase):
    def test_wilson_and_fisher_known_values(self):
        lo, hi = sr.wilson(8, 8)
        self.assertAlmostEqual(lo, 0.676, places=3)
        self.assertEqual(hi, 1.0)
        self.assertAlmostEqual(sr.fisher_p(8, 0, 0, 8), 2 / 12870, places=9)
        self.assertAlmostEqual(sr.fisher_p(4, 4, 4, 4), 1.0)

    def test_bootstrap_needs_three_values_and_is_seeded(self):
        self.assertEqual(sr.boot_mean([1, 0], random.Random(0), 100), (None, None))
        a = sr.boot_gap([1, 1, 1, 0], [0, 0, 0, 1], random.Random(0), 500)
        self.assertEqual(a, sr.boot_gap([1, 1, 1, 0], [0, 0, 0, 1], random.Random(0), 500))
        self.assertAlmostEqual(a[0], 0.5)

    def test_leak_free_score_drops_rules_a_leak_touched(self):
        r = fake_run("N", 3, 0.5, 1, leaks=[["D1"], [], []])  # r3 is new, r4 is base. D1 touches r3
        self.assertEqual(sr.leak_free_score(r, TRUTH), 0.0)
        self.assertIsNone(sr.leak_free_score(fake_run("N", 1, 1, 1, leaks=[["D1"]]), TRUTH))


class ContrastTest(unittest.TestCase):
    def runs(self):
        out = []
        for k in (1, 3, 6):
            out += [fake_run("A", k, 0, n) for n in range(3)]
            out += [fake_run("L", k, 1, n, cost=0.1) for n in range(8)]
            out += [fake_run("N", k, 1 if k == 1 else 0.5, n, kbv=["r4"] if k == 6 else (), cost=0.1) for n in range(8)]
            out += [fake_run("T", k, 1, n, spill=["D4"] if k == 6 else (), cost=0.12) for n in range(8)]
        return out

    def test_verdicts(self):
        cons = {(c["id"], c["pair"], str(c["level"])): c for c in sr.contrasts(self.runs(), [1, 3, 6], TRUTH, random.Random(0), 500)}
        self.assertEqual(cons[("Q0", "A", "6")]["verdict"], "held")
        self.assertEqual(cons[("H1", "N-A", "6")]["verdict"], "held")
        self.assertEqual(cons[("H2", "N K1-N K6", "1,6")]["verdict"], "held")
        self.assertEqual(cons[("H3", "L-N", "6")]["verdict"], "held")
        self.assertEqual(cons[("H4", "T-L", "6")]["verdict"], "failed")
        self.assertEqual(cons[("H5", "T/N cost", "6")]["verdict"], "held")
        h6 = [c for c in cons.values() if c["id"] == "H6"][0]
        self.assertAlmostEqual(h6["gap"], 8 / 16)  # N: 8 runs x 2 wrong rules, 8 kbv. T: none wrong
        self.assertEqual(h6["verdict"], "held")
        h7 = [c for c in cons.values() if c["id"] == "H7"][0]
        self.assertAlmostEqual(h7["gap"], 8 / 24)
        self.assertGreater(h7["lo"], 0)  # 8 of 24 pooled runs drift at K = 6, none at K = 1

    def test_main_writes_report_and_skips_pilot_and_invalid(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for r in self.runs():
                (root / r["run_id"]).mkdir()
                (root / r["run_id"] / "run.json").write_text(json.dumps(r))
            bad = dict(fake_run("L", 6, 0, 99), valid=False)
            (root / "bad").mkdir()
            (root / "bad" / "run.json").write_text(json.dumps(bad))
            (root / "pilot" / "x").mkdir(parents=True)
            (root / "pilot" / "x" / "run.json").write_text(json.dumps(fake_run("L", 6, 0, 98)))
            self.assertEqual(sr.main(["--runs", t, "--resamples", "200"]), 0)
            cells = (root / "report" / "cells.csv").read_text().splitlines()
            self.assertEqual(len(cells), 1 + 12)
            self.assertIn("L,6,8,1.000", "\n".join(cells))
            svg = (root / "report" / "sweep.svg").read_text()
            self.assertIn("prefers-color-scheme:dark", svg)
            self.assertEqual(svg.count("<polyline"), 4)


if __name__ == "__main__":
    unittest.main()
