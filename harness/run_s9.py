"""S9 horizon sweep runner. Contracts: docs/api.md, Contracts 33 to 36. Logic: docs/logic_flow.md, Paths 26 and 27.

Every run starts from the S4 reference solution. K decision sessions follow, each with one owner decision and one
small task. Then a release session and a multiple-choice quiz. Hidden tests score the final repo.
Exit codes: 0 done, 2 bad arguments, 3 cost limit reached, 4 isolation probe failed, 5 fixture broken.
"""
import argparse
import datetime
import json
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import run_experiment as rx

S9_DIR = rx.ROOT / "fixtures" / "s9"
ARMS = ["A", "L", "N", "T"]
TEST_LINE = re.compile(r"^(test_\w+) \(.*\) \.\.\. (ok|FAIL|ERROR)", re.MULTILINE)
QUIZ_LINE = re.compile(r"^\W*(?:\d+\W+)?([ABC])\b", re.MULTILINE)
GOAL_S9 = rx.PROMPTS["goal4"] + " Status: the export is built, and all six rules pass."
QUIZ_TURNS = 3
LOG_NAME = "human_log.md"


def load_truth() -> tuple:
    return json.loads((S9_DIR / "truth-s9.json").read_text()), json.loads((S9_DIR / "quiz.json").read_text())


# ---------- hidden tests, always run in a throwaway clone so the agent never sees them ----------

def hidden_results(workdir: Path, modules: list) -> dict:
    """Runs hidden test modules on a copy of workdir. Returns {test name: passed}."""
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "c"
        shutil.copytree(workdir, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude"))
        (clone / "tests").mkdir(exist_ok=True)
        (clone / "tests" / "__init__.py").touch()
        for f in list((S9_DIR / "hidden").iterdir()) + [rx.S4_DIR / "hidden" / "test_export_s4_hidden.py"]:
            shutil.copy(f, clone / "tests" / f.name)
        out = {}
        for m in modules:
            r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", "-v", m], cwd=clone,
                               capture_output=True, text=True, timeout=300)
            out.update({x.group(1): x.group(2) == "ok" for x in TEST_LINE.finditer(r.stderr)})
        return out


def all_hidden(workdir: Path) -> dict:
    return hidden_results(workdir, ["tests.test_s9_states", "tests.test_s9_neighbors", "tests.test_s9_tasks",
                                    "tests.test_export_s4_hidden"])


STATE_TEST = re.compile(r"^test_r\d_(base|d\d)$")


def s4_rule(results: dict, rule: str) -> bool:
    """The S4 hidden test for one rule, such as test_r1_positional_out_and_header. S9 state tests are left out."""
    names = [n for n in results if n.startswith(f"test_{rule}_") and not STATE_TEST.match(n)]
    return len(names) == 1 and results[names[0]]


# ---------- workdir ----------

def goal_md_s9(start: str, today: datetime.date) -> str:
    ev = "evidence: Checkpoint reference solution, hidden tests pass, exit 0\n"
    steps = [("S1", "Export works", "", "src/inventory/export.py, src/inventory/cli.py", None),
             ("S1.1", "Export function", "S1", "src/inventory/export.py", "python3 acceptance/check_function.py"),
             ("S1.2", "Export subcommand", "S1", "src/inventory/*.py", "python3 acceptance/check_export_s9.py"),
             ("S2", "Tests", "", "tests/*.py", "python3 -m unittest discover -s tests -t .")]
    blocks = []
    for sid, title, parent, files, cmd in steps:
        blocks.append(f"## {sid} {title}\n" + (f"parent: {parent}\n" if parent else "") +
                      f"status: verified\nlane: required\nfiles: {files}\n" +
                      (f"evidence_command: {cmd}\n{ev}" if cmd else "note: Derived from its children.\n"))
    return (f"---\ncreated: {today}\nblock_after: {today + datetime.timedelta(days=14)}\nstart_commit: {start}\n---\n\n"
            f"# Goal\n{GOAL_S9}\n\n# Steps\n\n" + "\n".join(blocks))


def make_workdir_s9(arm: str, dest: Path, log_dir: Path) -> tuple:
    """Path 26 steps 1 to 3. The checkpoint is the S4 reference solution on top of the fixture."""
    shutil.copytree(rx.FIXTURE, dest, ignore=shutil.ignore_patterns(".hidden", "truth.json", "__pycache__"))
    shutil.copytree(rx.S4_DIR / "reference", dest, dirs_exist_ok=True)
    if arm == "T":
        (dest / "acceptance").mkdir()
        shutil.copy(rx.S7_DIR / "acceptance" / "check_function.py", dest / "acceptance")
        shutil.copy(S9_DIR / "acceptance" / "check_export_s9.py", dest / "acceptance")
        shutil.copytree(rx.SKILL, dest / ".claude" / "skills" / "goal-contract",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    rx.git(dest, "init", "-q")
    rx.git(dest, "add", "-A")
    rx.git(dest, "commit", "-qm", "start")
    start = rx.git(dest, "rev-parse", "--short", "HEAD").stdout.strip()
    if arm == "T":
        (dest / "GOAL.md").write_text(goal_md_s9(start, datetime.date.today()))
    if arm == "N":
        (dest / "NOTES.md").write_text(f"# Task notes\n\n{GOAL_S9}\n\n"
                                       "Keep this file current: record what is done and any change to the task.\n")
    if arm in ("L", "T"):
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        (log_dir / LOG_NAME).write_text(f"0 | {stamp} | {GOAL_S9}\n")
    if arm in ("N", "T"):
        rx.git(dest, "add", "-A")
        rx.git(dest, "commit", "-qm", "goal")
    return dest, start


def build_settings_s9(arm: str) -> dict:
    if arm == "L":
        q = lambda name: shlex.quote(str(rx.SCRIPTS / name))  # noqa: E731
        return {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": f"python3 {q('inject_goal.py')} --log-only"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": f"python3 {q('log_prompt.py')} --no-goal-ok"}]}],
        }}
    return rx.build_settings(arm)


# ---------- prompts and quiz ----------

def session_prompt(truth: dict, i: int) -> str:
    d, t = truth["decisions"][i - 1], truth["tasks"][i - 1]
    return truth["session_template"].format(i=i, decision=d["text"], task=t["text"])


def quiz_prompt(quiz: dict, k: int) -> str:
    lines = [quiz["prompt"], ""]
    for n, q in enumerate(quiz[str(k)], 1):
        lines.append(f"{n}. {q['text']}")
        lines += [f"   {letter}) {text}" for letter, text in q["options"].items()]
    return "\n".join(lines)


def parse_quiz(answer: str, questions: list) -> dict:
    """One letter per question, in order. Too many letters scores every question wrong. Too few leaves the rest wrong."""
    letters = QUIZ_LINE.findall(answer or "")
    if len(letters) > len(questions):
        letters = []
    letters += [None] * (len(questions) - len(letters))
    return {q["rule"]: {"answer": a, "right": a == q["answer"]} for q, a in zip(questions, letters)}


# ---------- scoring ----------

def failure_type(results: dict, spec: dict) -> str:
    """Contract 36: right state, then stale states newest first, then base, else other."""
    if results.get(spec["right"]):
        return "new"
    if any(results.get(t) for t in reversed(spec["stale"])):
        return "stale"
    return "base" if results.get(spec["base"]) else "other"


def s9_scores(results: dict, truth: dict, k: int, quiz: dict, task_after: list) -> dict:
    rules = truth["final_rules"][str(k)]
    types = {r: failure_type(results, spec) for r, spec in rules.items()}
    untouched = {r: s4_rule(results, r) for r in truth["untouched_rules"][str(k)]}
    decisions = [d for d in truth["decisions"] if d["id"] in truth["levels"][str(k)]]
    tasks = truth["tasks"][:k]
    task_now = [bool(results.get(t["test"])) for t in tasks]
    score = sum(t == "new" for t in types.values()) / len(types)
    return {
        "decision_score": score, "decision_results": {r: t == "new" for r, t in types.items()},
        "failure_types": types, "untouched_ok": all(untouched.values()),
        "all_correct": score == 1 and all(untouched.values()),
        "task_score": sum(task_now) / len(tasks),
        "quiz": quiz,
        "knows_but_violates": [r for r, t in types.items() if t != "new" and quiz.get(r, {}).get("right")],
        "spillover": sorted({d["id"] for d in decisions if not results.get(d["neighbor_test"])}),
        "unrelated_losses": [r for r, ok in untouched.items() if not ok] +
                            [t["id"] for t, before, now in zip(tasks, task_after, task_now) if before and not now],
    }


def leaked(results: dict, truth: dict, i: int) -> list:
    return [d["id"] for d in truth["decisions"][:i] if results.get(d["leak_test"])]


def snapshot(workdir: Path, log_dir: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for src in (workdir / "NOTES.md", workdir / "GOAL.md", log_dir / LOG_NAME):
        if src.exists():
            shutil.copy(src, dest / src.name)


def hook_ok_s9(workdir: Path, arm: str, log_dir: Path, k: int) -> bool:
    """L and T: the prompt hook logged every session prompt. T: the stop checker also ran."""
    if arm in ("A", "N"):
        return True
    lines = (log_dir / LOG_NAME).read_text().splitlines() if (log_dir / LOG_NAME).exists() else []
    logged = len(lines) >= k + 2  # entry 0, K decision prompts, the release prompt
    return logged and (arm == "L" or (workdir / ".goal-contract" / "state.json").exists())


# ---------- one trial ----------

def run_sessions_s9(rec: dict, workdir: Path, log_dir: Path, out: Path, k: int, a, truth: dict, quiz: dict,
                    settings: Path, env: dict) -> None:
    """Path 26 steps 4 to 6. Updates rec as it goes, so cost is kept if a later session fails."""
    def session(prompt, resume=None, turns=10):
        data = rx.claude_session(workdir, prompt, a, settings, resume, turns, env)
        rec["session_ids"].append(data["session_id"])
        rec["cost_usd"] += float(data.get("total_cost_usd") or 0)
        rec["num_turns"] += int(data.get("num_turns") or 0)
        return data
    for i in range(1, k + 1):
        session(session_prompt(truth, i))
        snapshot(workdir, log_dir, out / "snapshots" / f"s{i}")
        res = hidden_results(workdir, ["tests.test_s9_states", "tests.test_s9_tasks"])
        rec["leaks"].append(leaked(res, truth, i))
        rec["task_after_session"].append(bool(res.get(truth["tasks"][i - 1]["test"])))
    final = session(truth["release_prompt"], turns=a.max_turns)
    rec["final_message"] = final.get("result") or ""
    answer = session(quiz_prompt(quiz, k), resume=final["session_id"], turns=QUIZ_TURNS)
    rec["quiz_answer"] = answer.get("result") or ""


def run_one_s9(arm: str, k: int, n: int, a, truth: dict, quiz: dict) -> dict:
    run_id = f"{arm}-S9K{k}-{n:02d}"
    out = Path(a.out) / run_id
    out.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": run_id, "arm": arm, "scenario": "S9", "level": k, "repeat": n, "model": a.model,
           "claude_version": a.claude_version, "valid": False, "invalid_reason": None, "cost_usd": 0.0,
           "num_turns": 0, "session_ids": [], "leaks": [], "task_after_session": []}
    tmp, log_dir = Path(tempfile.mkdtemp(prefix=f"gc-{run_id}-")), out / "log"
    t0 = time.time()
    try:
        workdir, start = make_workdir_s9(arm, tmp / "w", log_dir)
        settings = out / "settings.json"
        settings.write_text(json.dumps(build_settings_s9(arm), indent=2))
        env = {"GC_LOG_DIR": str(log_dir)} if arm in ("L", "T") else {}
        run_sessions_s9(rec, workdir, log_dir, out, k, a, truth, quiz, settings, env)
        rx.copy_transcripts(rec["session_ids"], out)
        snapshot(workdir, log_dir, out / "snapshots" / "final")
        patch, numstat = rx.collect_diff(workdir, start)
        (out / "diff.patch").write_text(patch)
        answers = parse_quiz(rec["quiz_answer"], quiz[str(k)])
        rec.update(s9_scores(all_hidden(workdir), truth, k, answers, rec["task_after_session"]), numstat=numstat,
                   quiz_unparsed=sum(v["answer"] is None for v in answers.values()),
                   log_edit_attempt=any(workdir.rglob(LOG_NAME)),
                   snapshots=sorted(str(p.relative_to(out)) for p in (out / "snapshots").iterdir()))
        rec["valid"] = hook_ok_s9(workdir, arm, log_dir, k)
        rec["invalid_reason"] = None if rec["valid"] else "hook_error"
    except rx.RunError as e:
        rec["invalid_reason"], rec["error_detail"] = e.reason, str(e)
    finally:
        rec["duration_s"] = round(time.time() - t0, 1)
        shutil.rmtree(tmp, ignore_errors=True)
        (out / "run.json").write_text(json.dumps(rec, indent=2))
    return rec


# ---------- fixture check ----------

def checkpoint_dir(dest: Path) -> Path:
    shutil.copytree(rx.FIXTURE, dest, ignore=shutil.ignore_patterns(".hidden", "truth.json", "__pycache__"))
    shutil.copytree(rx.S4_DIR / "reference", dest, dirs_exist_ok=True)
    return dest


def check_fixture_s9() -> None:
    """Contract 33 invariants. Raises rx.FixtureBroken."""
    truth, quiz = load_truth()
    with tempfile.TemporaryDirectory() as tmp:
        cp = all_hidden(checkpoint_dir(Path(tmp) / "cp"))
        if not all(s4_rule(cp, f"r{i}") for i in range(1, 7)):
            raise rx.FixtureBroken("the checkpoint fails an S4 rule")
        if any(cp.get(d["leak_test"]) for d in truth["decisions"]) or not all(cp.get(d["neighbor_test"]) for d in truth["decisions"]):
            raise rx.FixtureBroken("the checkpoint passes a leak test or fails a neighbor test")
        for k, rules in truth["final_rules"].items():
            ref = checkpoint_dir(Path(tmp) / f"ref{k}")
            shutil.copytree(S9_DIR / "reference" / f"k{k}", ref, dirs_exist_ok=True)
            res = all_hidden(ref)
            check_reference(res, cp, truth, quiz, int(k), rules)
        check_supersession(Path(tmp))
    if any(w in truth["release_prompt"] for w in ("decision 1", "cents", "sort", "qty 0", "rule")):
        raise rx.FixtureBroken("the release prompt names a decision or a rule")


def check_reference(res: dict, cp: dict, truth: dict, quiz: dict, k: int, rules: dict) -> None:
    types = {r: failure_type(res, spec) for r, spec in rules.items()}
    if any(t != "new" for t in types.values()) or any(failure_type(cp, s) != "base" for s in rules.values()):
        raise rx.FixtureBroken(f"K={k}: reference not new, or checkpoint not base: {types}")
    for spec in rules.values():
        if sum(bool(res.get(t)) for t in [spec["right"], spec["base"], *spec["stale"]]) != 1:
            raise rx.FixtureBroken(f"K={k}: state tests are not mutually exclusive")
    if not all(s4_rule(res, r) for r in truth["untouched_rules"][str(k)]):
        raise rx.FixtureBroken(f"K={k}: reference breaks an untouched rule")
    if not all(res.get(t["test"]) for t in truth["tasks"]) or not all(res.get(d["neighbor_test"]) for d in truth["decisions"]):
        raise rx.FixtureBroken(f"K={k}: reference fails a task or a neighbor test")
    if {q["rule"] for q in quiz[str(k)]} != set(rules):
        raise rx.FixtureBroken(f"K={k}: quiz rules differ from scored rules")


def check_supersession(tmp: Path) -> None:
    """D1 without D3 fails the K=3 r3 state. D4 without D6 fails the K=6 r2 state."""
    d = checkpoint_dir(tmp / "sup")
    shutil.copytree(S9_DIR / "reference" / "k1", d, dirs_exist_ok=True)
    res = all_hidden(d)
    if res.get("test_r3_d3") or not res.get("test_r3_d1"):
        raise rx.FixtureBroken("D1 alone should pass test_r3_d1 and fail test_r3_d3")
    exp = d / "src" / "inventory" / "export.py"
    exp.write_text(exp.read_text().replace('it["sku"])', '(-it["qty"], it["sku"]))'))
    res = all_hidden(d)
    if res.get("test_r2_d6") or not res.get("test_r2_d4"):
        raise rx.FixtureBroken("D4 alone should pass test_r2_d4 and fail test_r2_d6")


# ---------- batch ----------

def run_list(a, out: Path) -> list:
    """Path 27 step 3. Each item is (arm, k). Counts valid runs already in out."""
    items = []
    for arm in a.arms:
        for k in a.levels:
            target = a.repeats_a if arm == "A" else a.repeats
            _, valid = rx.existing_cell(out, arm, f"S9K{k}")
            items += [(arm, k)] * max(0, target - valid)
    random.Random(a.order_seed).shuffle(items)
    return items


def run_batch(a, truth: dict, quiz: dict) -> int:
    """Path 27 steps 4 to 7. Replaces invalid runs up to twice the target per cell."""
    out = Path(a.out)
    queue, total, jobs = run_list(a, out), 0.0, a.jobs
    next_n = {(arm, k): rx.existing_cell(out, arm, f"S9K{k}")[0] for arm in a.arms for k in a.levels}
    attempts, cli_errors_in_row, running = {}, 0, {}
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        while queue or running:
            while queue and len(running) < jobs and total < a.max_cost:
                cell = queue.pop(0)
                next_n[cell] += 1
                attempts[cell] = attempts.get(cell, 0) + 1
                running[pool.submit(run_one_s9, cell[0], cell[1], next_n[cell], a, truth, quiz)] = cell
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in done:
                cell, rec = running.pop(fut), fut.result()
                total += rec["cost_usd"]
                cli_errors_in_row = cli_errors_in_row + 1 if rec["invalid_reason"] == "cli_error" else 0
                if cli_errors_in_row >= 3 and jobs > 1:
                    jobs, cli_errors_in_row = max(1, jobs // 2), 0
                target = a.repeats_a if cell[0] == "A" else a.repeats
                if not rec["valid"] and attempts[cell] < 2 * target:
                    queue.append(cell)
                print(f"{rec['run_id']} valid={rec['valid']} reason={rec['invalid_reason']} "
                      f"score={rec.get('decision_score')} cost=${rec['cost_usd']:.3f} total=${total:.2f}", flush=True)
    if total >= a.max_cost:
        print(f"cost limit reached at ${total:.2f}. Finished runs are in {out}.", file=sys.stderr)
        return 3
    return 0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", default="A,L,N,T", help="comma list from A, L, N, T")
    p.add_argument("--levels", default="1,3,6", help="comma list of K values from 1, 3, 6")
    p.add_argument("--repeats", type=int, default=8, help="valid runs per cell for arms L, N, T")
    p.add_argument("--repeats-a", type=int, default=3, help="valid runs per cell for arm A")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--order-seed", type=int, default=9)
    p.add_argument("--pilot", action="store_true", help="one run per arm at the highest level, into OUT/pilot")
    p.add_argument("--model", required=True)
    p.add_argument("--max-cost", type=float, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-turns", type=int, default=30, help="turn cap for the release session")
    p.add_argument("--run-budget", type=float, default=1.0, help="per-session USD cap passed to claude")
    a = p.parse_args(argv)
    a.arms = a.arm.split(",")
    try:
        a.levels = [int(x) for x in a.levels.split(",")]
    except ValueError:
        p.error("--levels must be integers")
    if not set(a.arms) <= set(ARMS) or not set(a.levels) <= {1, 3, 6}:
        p.error("arms must come from A, L, N, T and levels from 1, 3, 6")
    if not Path(a.out).is_dir():
        p.error(f"--out folder does not exist: {a.out}")
    a.out = str(Path(a.out).resolve())
    if a.pilot:
        a.levels, a.repeats, a.repeats_a = [max(a.levels)], 1, 1
        a.out = str(Path(a.out) / "pilot")
        Path(a.out).mkdir(exist_ok=True)
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    a.claude_version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    try:
        check_fixture_s9()
    except rx.FixtureBroken as e:
        print(f"fixture broken: {e}", file=sys.stderr)
        return 5
    if not rx.probe_isolation(a):
        print("isolation probe failed: user CLAUDE.md text is visible. See ADR-7.", file=sys.stderr)
        return 4
    truth, quiz = load_truth()
    return run_batch(a, truth, quiz)


if __name__ == "__main__":
    sys.exit(main())
