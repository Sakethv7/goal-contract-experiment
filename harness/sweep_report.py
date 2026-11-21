"""S9 sweep report. Contract: docs/api.md, Contract 37. Logic: docs/logic_flow.md, Path 28.

Reads every valid S9 run.json in --runs (the pilot subfolder is left out). Writes report/cells.csv,
report/contrasts.csv and report/sweep.svg, and prints each threshold as held or failed. Standard library only.
"""
import argparse
import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path

ARMS = ["A", "L", "N", "T"]
COLORS = {"light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"], "dark": ["#3987e5", "#d95926", "#199e70", "#c98500"]}


def load_runs(out: Path) -> list:
    recs = [json.loads(p.read_text()) for p in sorted(out.glob("*/run.json"))]
    return [r for r in recs if r.get("scenario") == "S9" and r.get("valid")]


def cell(runs: list, arm: str, k: int) -> list:
    return [r for r in runs if r["arm"] == arm and r["level"] == k]


# ---------- statistics ----------

def mean(xs: list):
    return statistics.fmean(xs) if xs else None


def boot_mean(xs: list, rng: random.Random, n: int) -> tuple:
    """95% percentile bootstrap of the mean. None for fewer than 3 values."""
    if len(xs) < 3:
        return None, None
    ms = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n) - 1]


def boot_gap(xs: list, ys: list, rng: random.Random, n: int) -> tuple:
    """Gap mean(xs) - mean(ys), each cell resampled on its own. Interval is None if either cell has under 3 values."""
    if not xs or not ys:
        return None, None, None
    gap = statistics.fmean(xs) - statistics.fmean(ys)
    if len(xs) < 3 or len(ys) < 3:
        return gap, None, None
    gs = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) - statistics.fmean(rng.choices(ys, k=len(ys)))
                for _ in range(n))
    return gap, gs[int(0.025 * n)], gs[int(0.975 * n) - 1]


def wilson(k: int, n: int) -> tuple:
    if n == 0:
        return None, None
    z, p = 1.96, k / n
    centre, half = (p + z * z / (2 * n)) / (1 + z * z / n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def fisher_p(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test on [[a, b], [c, d]]: sum of tables no more likely than the one seen."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    prob = lambda x: math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)  # noqa: E731
    seen = prob(a)
    return min(1.0, sum(prob(x) for x in range(max(0, r1 + c1 - n), min(r1, c1) + 1) if prob(x) <= seen * (1 + 1e-9)))


# ---------- per-run measures ----------

def leak_free_score(rec: dict, truth: dict):
    """Decision score with each rule that a leaked decision touches taken out. None when no rule is left."""
    leaked = {d for session in rec.get("leaks", []) for d in session}
    rules_hit = {d["rule"] for d in truth["decisions"] if d["id"] in leaked}
    kept = [ok for r, ok in rec["decision_results"].items() if r not in rules_hit]
    return statistics.fmean(kept) if kept else None


def drift_count(rec: dict) -> int:
    return len(rec.get("spillover", [])) + len(rec.get("unrelated_losses", []))


# ---------- cells and contrasts ----------

def cell_rows(runs: list, levels: list, rng: random.Random, n: int) -> list:
    rows = []
    for arm in ARMS:
        for k in levels:
            c = cell(runs, arm, k)
            if not c:
                continue
            scores, correct = [r["decision_score"] for r in c], sum(r["all_correct"] for r in c)
            types = [t for r in c for t in r["failure_types"].values()]
            quiz = [q["right"] for r in c for q in r["quiz"].values()]
            rows.append({"arm": arm, "level": k, "n": len(c), "mean_score": mean(scores),
                         "ci": boot_mean(scores, rng, n), "all_correct": correct, "wilson": wilson(correct, len(c)),
                         "stale": types.count("stale"), "base": types.count("base"), "other": types.count("other"),
                         "quiz_score": mean(quiz), "kbv": sum(len(r["knows_but_violates"]) for r in c),
                         "spillover": sum(len(r["spillover"]) for r in c),
                         "unrelated": sum(len(r["unrelated_losses"]) for r in c),
                         "task_score": mean([r["task_score"] for r in c]), "cost": mean([r["cost_usd"] for r in c]),
                         "leaks": sum(len(s) for r in c for s in r["leaks"])})
    return rows


def score_gap(tid, pair, k, xs, ys, need, rng, n, truth, require_ci=True) -> dict:
    """One contrast row on decision scores. Held if gap >= need and, when required, the interval excludes 0."""
    gap, lo, hi = boot_gap([r["decision_score"] for r in xs], [r["decision_score"] for r in ys], rng, n)
    held = gap is not None and gap >= need and (not require_ci or (lo is not None and lo > 0))
    lf = [leak_free_score(r, truth) for r in xs], [leak_free_score(r, truth) for r in ys]
    lf_gap = boot_gap([v for v in lf[0] if v is not None], [v for v in lf[1] if v is not None], rng, n)[0]
    ac = [sum(r["all_correct"] for r in g) for g in (xs, ys)]
    p = fisher_p(ac[0], len(xs) - ac[0], ac[1], len(ys) - ac[1]) if xs and ys else None
    return {"id": tid, "pair": pair, "level": k, "gap": gap, "lo": lo, "hi": hi, "fisher_p": p,
            "verdict": "held" if held else "failed", "leak_free_gap": lf_gap}


def contrasts(runs: list, levels: list, truth: dict, rng: random.Random, n: int) -> list:
    top, low = max(levels), min(levels)
    rows = []
    for k in levels:
        m = mean([r["decision_score"] for r in cell(runs, "A", k)])
        rows.append({"id": "Q0", "pair": "A", "level": k, "gap": m, "verdict": "held" if m is not None and m <= 0.2 else "failed"})
    for k in [x for x in levels if x >= 3]:
        for arm in ("L", "N", "T"):
            rows.append(score_gap("H1", f"{arm}-A", k, cell(runs, arm, k), cell(runs, "A", k), 0.5, rng, n, truth, False))
    rows.append(score_gap("H2", f"N K{low}-N K{top}", f"{low},{top}", cell(runs, "N", low), cell(runs, "N", top), 0.2, rng, n, truth))
    rows.append(score_gap("H3", "L-N", top, cell(runs, "L", top), cell(runs, "N", top), 0.2, rng, n, truth))
    rows.append(score_gap("H4", "T-L", top, cell(runs, "T", top), cell(runs, "L", top), 0.15, rng, n, truth))
    for k in levels:
        t, nn = mean([r["cost_usd"] for r in cell(runs, "T", k)]), mean([r["cost_usd"] for r in cell(runs, "N", k)])
        ratio = t / nn if t and nn else None
        rows.append({"id": "H5", "pair": "T/N cost", "level": k, "gap": ratio,
                     "verdict": "held" if ratio is not None and ratio <= 1.5 else "failed"})
    pooled = cell(runs, "N", top) + cell(runs, "T", top)
    wrong = sum(t != "new" for r in pooled for t in r["failure_types"].values())
    kbv = sum(len(r["knows_but_violates"]) for r in pooled)
    share = kbv / wrong if wrong else None
    rows.append({"id": "H6", "pair": f"N+T knows-but-violates of {wrong} wrong", "level": top, "gap": share,
                 "verdict": "held" if share is not None and share >= 0.5 else ("no data" if share is None else "failed")})
    hi_runs = [r for a in ("N", "L", "T") for r in cell(runs, a, top)]
    lo_runs = [r for a in ("N", "L", "T") for r in cell(runs, a, low)]
    gap, lo, hi = boot_gap([drift_count(r) for r in hi_runs], [drift_count(r) for r in lo_runs], rng, n)
    rows.append({"id": "H7", "pair": f"N+L+T drift K{top}-K{low}", "level": f"{low},{top}", "gap": gap, "lo": lo, "hi": hi,
                 "verdict": "held" if gap is not None and gap >= 0.15 and lo is not None and lo > 0 else "failed"})
    return rows


# ---------- output ----------

def fmt(v) -> str:
    return "" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def write_cells(rows: list, path: Path) -> None:
    cols = ["arm", "level", "n", "mean_score", "ci_low", "ci_high", "all_correct", "wilson_low", "wilson_high", "stale",
            "base", "other", "quiz_score", "kbv", "spillover", "unrelated", "task_score", "cost", "leaks"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            flat = dict(r, ci_low=r["ci"][0], ci_high=r["ci"][1], wilson_low=r["wilson"][0], wilson_high=r["wilson"][1])
            w.writerow([fmt(flat[c]) for c in cols])


def write_contrasts(rows: list, path: Path) -> None:
    cols = ["id", "pair", "level", "gap", "lo", "hi", "fisher_p", "verdict", "leak_free_gap"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in cols])


def svg_chart(rows: list, levels: list) -> str:
    """Decision score against K, one line per arm, 95% interval bars, direct labels, light and dark mode."""
    W, H, L, R, T, B = 640, 380, 56, 70, 64, 48
    x = lambda k: L + (levels.index(k) + 0.5) * (W - L - R) / len(levels)  # noqa: E731
    y = lambda v: T + (1 - v) * (H - T - B)  # noqa: E731
    css = "".join(f".s{i}{{stroke:{c};fill:{c}}}" for i, c in enumerate(COLORS["light"]))
    dark = "".join(f".s{i}{{stroke:{c};fill:{c}}}" for i, c in enumerate(COLORS["dark"]))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Mean decision score against horizon K, one line per arm, with 95% intervals">',
           f"<style>svg{{background:#fcfcfb}}text{{font:12px system-ui,sans-serif;fill:#52514e}}.t{{fill:#0b0b0b;font-weight:600}}"
           f".g{{stroke:#e4e3df}}.ln{{fill:none;stroke-width:2}}.ci{{stroke-width:1.5}}{css}"
           f"@media (prefers-color-scheme:dark){{svg{{background:#1a1a19}}text{{fill:#c3c2b7}}.t{{fill:#f0efec}}.g{{stroke:#3a3a37}}{dark}}}</style>",
           f'<text class="t" x="{L}" y="22">Decision score by horizon K (mean, 95% interval)</text>']
    out += [f'<rect class="s{i}" x="{L + i * 72}" y="33" width="10" height="10" rx="2"/>'
            f'<text x="{L + 14 + i * 72}" y="42">Arm {arm}</text>' for i, arm in enumerate(ARMS)]
    for v in (0, 0.25, 0.5, 0.75, 1):
        out.append(f'<line class="g" x1="{L}" x2="{W - R}" y1="{y(v)}" y2="{y(v)}"/><text x="{L - 8}" y="{y(v) + 4}" text-anchor="end">{v:g}</text>')
    for k in levels:
        out.append(f'<text x="{x(k)}" y="{H - B + 20}" text-anchor="middle">K = {k}</text>')
    labels = []
    for i, arm in enumerate(ARMS):
        pts = [r for r in rows if r["arm"] == arm]
        if not pts:
            continue
        out.append(f'<polyline class="ln s{i}" style="fill:none" points="{" ".join(f"{x(r["level"])},{y(r["mean_score"])}" for r in pts)}"/>')
        for r in pts:
            lo, hi = r["ci"]
            if lo is not None:
                out.append(f'<line class="ci s{i}" x1="{x(r["level"])}" x2="{x(r["level"])}" y1="{y(lo)}" y2="{y(hi)}"/>')
            out.append(f'<circle class="s{i}" cx="{x(r["level"])}" cy="{y(r["mean_score"])}" r="4.5">'
                       f'<title>Arm {arm}, K = {r["level"]}: mean {r["mean_score"]:.2f}, n = {r["n"]}</title></circle>')
        labels.append([y(pts[-1]["mean_score"]) + 4, x(pts[-1]["level"]) + 10, arm])
    labels.sort()
    for j in range(1, len(labels)):  # keep end labels 14px apart when lines end at the same value
        labels[j][0] = max(labels[j][0], labels[j - 1][0] + 14)
    out += [f'<text x="{lx}" y="{ly}">Arm {arm}</text>' for ly, lx, arm in labels]
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--resamples", type=int, default=10000)
    a = p.parse_args(argv)
    out = Path(a.runs)
    truth = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "s9" / "truth-s9.json").read_text())
    runs = load_runs(out)
    if not runs:
        print(f"no valid S9 runs in {out}", file=sys.stderr)
        return 1
    levels = sorted({r["level"] for r in runs})
    rng = random.Random(a.seed)
    rows, cons = cell_rows(runs, levels, rng, a.resamples), contrasts(runs, levels, truth, rng, a.resamples)
    rep = out / "report"
    rep.mkdir(exist_ok=True)
    write_cells(rows, rep / "cells.csv")
    write_contrasts(cons, rep / "contrasts.csv")
    (rep / "sweep.svg").write_text(svg_chart(rows, levels))
    for c in cons:
        print(f"{c['id']:3} {str(c['pair']):40} K={c['level']}  gap={fmt(c.get('gap'))}  {c['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
