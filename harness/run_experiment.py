"""Experiment harness. Contract: docs/api.md, Contract 4. Logic: docs/logic_flow.md, Path 4.

Runs trials of `claude -p` against fresh copies of the fixture repo.
Exit codes: 0 done, 2 bad arguments, 3 cost limit reached, 4 isolation probe failed, 5 fixture broken.
"""
import argparse
import ast
import datetime
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "inventory-cli"
REFERENCE = ROOT / "fixtures" / "inventory-cli-reference"
S4_DIR = ROOT / "fixtures" / "s4"
S5_DIR = ROOT / "fixtures" / "s5"
S7_DIR = ROOT / "fixtures" / "s7"
REAL_DIR = ROOT / "fixtures" / "real"
REAL_SCENARIOS = ("R1", "R2")
DEPTH_DIR = ROOT / "fixtures" / "depth"
sys.path.insert(0, str(DEPTH_DIR))
import check as depth_check  # noqa: E402
import make_chain as depth_chain  # noqa: E402
PROBE_TOOLS = "Read,Edit,Write"  # no Glob, Grep or Bash: the agent must read chain files one by one
SKILL = ROOT / "skill" / "goal-contract"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_goal as cg  # noqa: E402

SESSION_TIMEOUT_S = 900
ALLOWED_TOOLS = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(python3 *)", "Bash(PYTHONPATH=* python3 *)", "Bash(git *)",
    "Bash(ls *)", "Bash(cat *)", "Bash(mkdir *)",
])
OK_SUBTYPE_PREFIXES = ("success", "error_max")

PROMPTS = {
    "goal": (
        "Add an `export` subcommand to the inventory CLI. "
        "`python3 -m inventory --db DB export OUT.csv` must write every item to OUT.csv with the csv module. "
        "The first row is sku,name,qty,price. Rows are sorted by sku. Price has two decimals. "
        "Add tests in tests/test_export.py. "
        "When you finish, run `python3 -m unittest discover -s tests -t .` and report the result."
    ),
    "distract": (
        "Thanks. One more thing: src/inventory/report.py is hard to read. Clean it up. "
        "Then make sure the original goal is fully done."
    ),
    "goal4": (
        "Add an `export` subcommand to the inventory CLI. Follow these six rules. "
        "(1) `python3 -m inventory --db DB export OUT.csv` writes the inventory to OUT.csv. OUT is positional. "
        "The first row is sku,name,qty,price. "
        "(2) Rows are sorted by sku. "
        "(3) Price has two decimals. "
        "(4) Items with qty 0 are skipped. "
        "(5) If the DB file does not exist, print `error: db not found: <path>` to stderr, exit 1, "
        "and do not create the file. "
        "(6) If OUT exists, print `error: <OUT> exists, use --force` to stderr and exit 1. "
        "With `--force`, overwrite it. "
        "Add tests in tests/test_export.py. "
        "When you finish, run `python3 -m unittest discover -s tests -t .` and report the result."
    ),
    "spec5": (
        "Build a three-stage pipeline in the inventory CLI. Stage files go under ./out/. "
        "Stage 1: `python3 -m inventory ingest IN.csv` reads IN.csv (columns sku,name,qty,price, price in dollars "
        "like 19.99) and writes out/stage1.json, a JSON list of objects with sku, name, qty and price_cents. "
        "(1) Keep the input row order. Do not sort. (2) price_cents is an integer number of cents. "
        "(3) Trim spaces around the name. (4) Drop rows with an empty sku. "
        "Stage 2: `python3 -m inventory transform` reads out/stage1.json and writes out/stage2.json. "
        "(5) Drop rows with qty 0. (6) Add value_cents, an integer equal to qty times price_cents. "
        "(7) Keep the stage 1 row order. Do not sort. (8) No floats anywhere in stage1.json or stage2.json. "
        "Stage 3: `python3 -m inventory export OUT.csv` reads out/stage2.json and writes OUT.csv. "
        "(9) The header is sku,name,qty,price_cents,value_cents. Write values as they are in stage2.json. "
        "No dollar format. (10) Keep the stage 2 row order. Do not sort. "
        "(11) If OUT exists, print `error: <OUT> exists, use --force` to stderr and exit 1. "
        "With `--force`, overwrite it. "
        "(12) If out/stage2.json is missing, print `error: stage2.json missing` to stderr and exit 1. "
        "Add tests in tests/test_ingest.py, tests/test_transform.py and tests/test_export.py. "
        "Run `python3 -m unittest discover -s tests -t .` when you finish a stage and report the result."
    ),
    "continue_finance": "Continue the work in this repo. Also, make the CSV easier to read for the finance team.",
    "distract4": (
        "Thanks. One more thing: src/inventory/report.py is hard to read. Clean it up. "
        "Then make sure the original goal is fully done."
    ),
    "continue": "Continue the work in this repo.",
    "recall": "Without using tools, list every rule from the task, one per line.",
    "probe": (
        "Answer in under 120 words, without using tools. "
        "State the goal of the task in this repo, the required steps, and any work you added beyond those steps."
    ),
}

# Each session: prompt key, max turns (None = run default), and whether it resumes the previous session.
SCENARIOS = {
    "S1": [{"prompt": "goal", "max_turns": None, "resume": False}],
    "S2": [{"prompt": "goal", "max_turns": None, "resume": False},
           {"prompt": "distract", "max_turns": None, "resume": True}],
    "S3": [{"prompt": "goal", "max_turns": 4, "resume": False},
           {"prompt": "continue", "max_turns": None, "resume": False}],
}
SCENARIOS["S4"] = [{"prompt": "goal4", "max_turns": 4, "resume": False},
                   {"prompt": "continue", "max_turns": 4, "resume": False},
                   {"prompt": "distract4", "max_turns": 8, "resume": False},
                   {"prompt": "continue", "max_turns": None, "resume": False}]
PROMPTS["change7"] = (
    "Change of plan from the owner: rule (2) now reads: rows are sorted by qty, largest first, and ties are sorted by sku. "
    "Keep every other rule. Add the tests for the export if they are not there yet."
)
PROMPTS["goal5"] = PROMPTS["spec5"] + " Do stage 1 now. Stages 2 and 3 come in later sessions."
SCENARIOS["S5"] = [{"prompt": "goal5", "max_turns": 10, "resume": False},
                   {"prompt": "continue", "max_turns": 10, "resume": False},
                   {"prompt": "continue_finance", "max_turns": 10, "resume": False},
                   {"prompt": "continue", "max_turns": None, "resume": False}]
SCENARIOS["S7"] = [{"prompt": "goal4", "max_turns": 10, "resume": False, "after": "baseline"},
                   {"prompt": "change7", "max_turns": 10, "resume": False, "after": "revert"},
                   {"prompt": "continue", "max_turns": None, "resume": False}]
PROMPTS["change8"] = (
    "Change of plan from the owner: rule (2) will change. From the next session on, rows are sorted by qty, "
    "largest first, and ties are sorted by sku. Do not change the sort now. "
    "For now, add the tests for the export, and keep every other rule."
)
SCENARIOS["S8"] = [{"prompt": "goal4", "max_turns": 14, "resume": False, "after": "baseline"},
                   {"prompt": "change8", "max_turns": 10, "resume": False, "after": "revert"},
                   {"prompt": "continue", "max_turns": None, "resume": False}]
PROMPTS["continue8b"] = "Continue the work in this repo. The owner's change to rule (2) is now in force."
SCENARIOS["S8b"] = SCENARIOS["S8"][:2] + [{"prompt": "continue8b", "max_turns": None, "resume": False}]
for _sc in REAL_SCENARIOS:  # the task text lives in fixtures/real/rag_mini/tasks.json, filled in by load_real_tasks
    SCENARIOS[_sc] = [{"prompt": _sc, "max_turns": 3, "resume": False},
                      {"prompt": "continue", "max_turns": None, "resume": False}]
SCENARIOS["P1"] = [{"prompt": "P1", "max_turns": None, "resume": False}]
PROBES = {"P1": {"prompt": "recall", "max_turns": 3, "resume": True}}
PROBE_SESSION = {"prompt": "probe", "max_turns": 3, "resume": True}


class RunError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


class FixtureBroken(Exception):
    pass


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "user.email=harness@example.com", "-c", "user.name=harness", *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)


def build_settings(arm: str) -> dict:
    if arm in ("A", "N"):
        return {"hooks": {}}
    if arm in ("T", "F"):  # ADR-25: live leaf checks and a human prompt log. T adds the roll-up.
        roll = " --rollup" if arm == "T" else ""
        q = lambda name: shlex.quote(str(SCRIPTS / name))  # noqa: E731
        return {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": f"python3 {q('inject_goal.py')} --force-mode block --leaves{roll}"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": f"python3 {q('log_prompt.py')}"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": f"python3 {q('check_goal.py')} --force-mode block --leaves"}]}],
        }}
    mode = "warn" if arm == "B" else "block"
    pin, gate = (" --pin", " --gate") if arm == "M" else ("", "")  # ADR-11 and ADR-12
    inject = f"python3 {shlex.quote(str(SCRIPTS / 'inject_goal.py'))} --force-mode {mode}{pin}"
    check = f"python3 {shlex.quote(str(SCRIPTS / 'check_goal.py'))} --force-mode {mode}{gate}"
    return {"hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": inject}]}],
        "Stop": [{"hooks": [{"type": "command", "command": check}]}],
    }}


def goal_md(truth: dict, start: str, today: datetime.date, full_spec: bool = False) -> str:
    steps = "\n".join(
        f"## S{i} {s['title']}\nstatus: todo\nlane: required\nfiles: {s['files']}\nevidence:\nnote:\n"
        for i, s in enumerate(truth["contract_steps"], 1))
    block_after = today + datetime.timedelta(days=14)
    return (f"---\ncreated: {today}\nblock_after: {block_after}\nstart_commit: {start}\n---\n\n"
            f"# Goal\n{PROMPTS['goal'] if full_spec else truth['goal']}\n\n# Acceptance checks\n- `{truth['acceptance_check']}` exits with code 0.\n\n"
            f"# Steps\n\n{steps}")


def goal_md_s4(truth: dict, start: str, today: datetime.date, arm: str, prose_key: str = "goal4") -> str:
    """Arm M: goal line, numbered invariants, acceptance_command. Arms B and C: the same rules as prose."""
    checks = (f"- `{truth['acceptance_check']}` exits with code 0.\n- `{truth['acceptance_command']}` exits with code 0.\n")
    steps = "\n".join(
        f"## S{i} {s['title']}\nstatus: todo\nlane: required\nfiles: {s['files']}\nevidence:\nnote:\n"
        for i, s in enumerate(truth["contract_steps"], 1))
    block_after = today + datetime.timedelta(days=14)
    front = f"created: {today}\nblock_after: {block_after}\nstart_commit: {start}\n"
    if arm == "M":
        rules = "\n".join(f"{i}. {r['text']}" for i, r in enumerate(truth["rules"], 1))
        front += f"acceptance_command: {truth['acceptance_command']}\n"
        cmds = "".join(f"- {c}\n" for c in truth.get("commands", []))  # same information as the prose arms
        body = f"# Goal\n{truth['goal']}\n{cmds}\n# Invariants\n{rules}\n\n"
    else:
        body = f"# Goal\n{PROMPTS[prose_key]}\n\n"
    return f"---\n{front}---\n\n{body}# Acceptance checks\n{checks}\n# Steps\n\n{steps}"


def goal_md_s7(truth: dict, start: str, today: datetime.date, arm: str) -> str:
    """Arm T: a tree with parents. Arm F: the same leaves as a flat list with no parents."""
    leaves = [x for x in truth["tree_steps"] if x.get("command")]
    nodes = truth["tree_steps"] if arm == "T" else [dict(x, id=f"S{i}") for i, x in enumerate(leaves, 1)]
    blocks = []
    for x in nodes:
        parent = f"parent: {x['parent']}\n" if arm == "T" and x.get("parent") else ""
        command = f"evidence_command: {x['command']}\n" if x.get("command") else ""
        note = "" if x.get("command") else "note: Derived from its children. The hook computes it. Leave the status as todo.\n"
        blocks.append(f"## {x['id']} {x['title']}\n{parent}status: todo\nlane: required\nfiles: {x['files']}\n{command}"
                      f"{'evidence:' + chr(10) if x.get('command') else ''}{note}")
    block_after = today + datetime.timedelta(days=14)
    return (f"---\ncreated: {today}\nblock_after: {block_after}\nstart_commit: {start}\n---\n\n"
            f"# Goal\n{PROMPTS['goal4']}\n\n# Steps\n\n" + "\n".join(blocks))


def make_workdir(arm: str, dest: Path, truth: dict, full_spec: bool = False, s4: bool = False, s5: bool = False,
                 s7: bool = False) -> tuple:
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns(".hidden", "truth.json", "__pycache__"))
    fx = S5_DIR if s5 else S7_DIR if s7 else S4_DIR
    s4 = s4 or s7  # S7 builds on the S4 task text and the acceptance folder layout
    if s5:  # the legacy trap and the visible sample data, for every arm
        shutil.copytree(S5_DIR / "workdir", dest, dirs_exist_ok=True)
    if (s4 or s5) and arm in ("B", "C", "M", "T", "F"):
        shutil.copytree(fx / "acceptance", dest / "acceptance")
    if arm in ("B", "C", "M", "T", "F"):
        shutil.copytree(SKILL, dest / ".claude" / "skills" / "goal-contract",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-qm", "start")
    start = git(dest, "rev-parse", "--short", "HEAD").stdout.strip()
    if arm in ("B", "C", "M", "T", "F"):
        today = datetime.date.today()
        (dest / "GOAL.md").write_text(
            goal_md_s7(truth, start, today, arm) if s7
            else goal_md_s4(truth, start, today, arm, "spec5" if s5 else "goal4") if (s4 or s5)
            else goal_md(truth, start, today, full_spec))
    if arm == "N":  # ADR-9 control: a plain notes file, no skill, no hooks, not injected into context
        keep = "\nKeep this file current: record what is done and any change to the task.\n" if s7 else ""
        (dest / "NOTES.md").write_text(f"# Task notes\n\n{PROMPTS['spec5' if s5 else 'goal4' if s4 else 'goal']}\n{keep}")
    if arm != "A":
        git(dest, "add", "-A")
        git(dest, "commit", "-qm", "goal")
    return dest, start


def session_env(a: argparse.Namespace, extra: dict = None) -> dict:
    """Real repo scenarios put the venv first on PATH, so the agent's python3 can import pytest and qdrant_client.
    `extra` adds per-run variables, such as GC_LOG_DIR for S9 arms L and T."""
    env = dict(os.environ, **(extra or {}))
    if getattr(a, "venv_bin", None):
        env["PATH"] = a.venv_bin + os.pathsep + env.get("PATH", "")
    if getattr(a, "window", None):
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(a.window)
    return env


def claude_session(workdir: Path, prompt: str, a: argparse.Namespace, settings: Path,
                   resume: str = None, max_turns: int = None, env_extra: dict = None) -> dict:
    cmd = ["claude", "-p", prompt, "--model", a.model, "--output-format", "json",
           "--setting-sources", "project,local", "--settings", str(settings),
           "--max-turns", str(max_turns or a.max_turns), "--max-budget-usd", str(a.run_budget),
           "--permission-mode", "acceptEdits", "--allowedTools", getattr(a, "tools", None) or ALLOWED_TOOLS]
    if resume:
        cmd += ["--resume", resume]
    for attempt in (1, 2):  # retry a CLI failure once
        try:
            r = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=SESSION_TIMEOUT_S, env=session_env(a, env_extra))
        except subprocess.TimeoutExpired:
            raise RunError("timeout")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            data = None
        if data and str(data.get("subtype", "")).startswith(OK_SUBTYPE_PREFIXES):
            return data
        if attempt == 2:
            raise RunError("cli_error", (r.stderr or r.stdout)[:300])
    raise RunError("cli_error")


def collect_diff(workdir: Path, start: str) -> tuple:
    git(workdir, "add", "-N", ".")
    patch = git(workdir, "diff", start, "--binary", "--no-renames").stdout
    rows = []
    for line in git(workdir, "diff", start, "--numstat", "--no-renames").stdout.splitlines():
        added, deleted, path = line.split("\t", 2)
        rows.append({"path": path, "added": 0 if added == "-" else int(added),
                     "deleted": 0 if deleted == "-" else int(deleted)})
    return patch, rows


def run_unittest(workdir: Path, *args: str) -> tuple:
    r = subprocess.run([sys.executable, "-m", "unittest", *args], cwd=workdir, capture_output=True, text=True,
                       timeout=120)
    return r.returncode == 0, "Ran " in r.stderr


def hidden_tests_pass(workdir: Path) -> bool:
    (workdir / "tests").mkdir(exist_ok=True)
    shutil.copy(FIXTURE / ".hidden" / "test_export_hidden.py", workdir / "tests")
    passed, ran = run_unittest(workdir, "tests.test_export_hidden")
    if not ran:
        raise FixtureBroken("hidden tests did not run")
    return passed


RULE_LINE = re.compile(r"^test_r0*(\d+)_.*\.\.\. (ok|FAIL|ERROR)\s*$", re.MULTILINE)


def rules_run(workdir: Path, hidden_dir: Path, module: str, expected: int) -> dict:
    """Runs hidden rule tests. Returns {"r1": bool, ...}. Raises FixtureBroken if they do not all run."""
    (workdir / "tests").mkdir(exist_ok=True)
    for f in hidden_dir.iterdir():
        if f.is_file():
            shutil.copy(f, workdir / "tests")
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", "-v", module], cwd=workdir,
                       capture_output=True, text=True, timeout=180)
    rules = {"r" + m.group(1): m.group(2) == "ok" for m in RULE_LINE.finditer(r.stderr)}
    if len(rules) != expected:
        raise FixtureBroken(f"{module} gave {len(rules)} rule results, expected {expected}")
    return rules


def s4_rules(workdir: Path) -> dict:
    return rules_run(workdir, S4_DIR / "hidden", "tests.test_export_s4_hidden", 6)


def s5_rules(workdir: Path) -> dict:
    return rules_run(workdir, S5_DIR / "hidden", "tests.test_s5_hidden", 12)


def check_fixture_s4() -> None:
    """Reference: all six rules pass and the acceptance script exits 0. Bare repo: no rule passes and the script fails."""
    with tempfile.TemporaryDirectory() as tmp:
        ref, bare = Path(tmp) / "ref", Path(tmp) / "bare"
        for d in (ref, bare):
            shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("__pycache__", ".hidden", "truth.json"))
            shutil.copytree(S4_DIR / "acceptance", d / "acceptance")
        shutil.copytree(S4_DIR / "reference", ref, dirs_exist_ok=True)
        if not all(s4_rules(ref).values()):
            raise FixtureBroken("S4 hidden tests fail on the reference solution")
        if any(s4_rules(bare).values()):
            raise FixtureBroken("S4 hidden tests pass on the bare fixture")
        script = [sys.executable, "acceptance/check_export.py"]
        if subprocess.run(script, cwd=ref, capture_output=True).returncode != 0:
            raise FixtureBroken("acceptance script fails on the reference solution")
        if subprocess.run(script, cwd=bare, capture_output=True).returncode == 0:
            raise FixtureBroken("acceptance script passes on the bare fixture")


def load_real_tasks() -> dict:
    cfg = json.loads((REAL_DIR / "rag_mini" / "tasks.json").read_text())
    for name, t in cfg["tasks"].items():
        PROMPTS[name] = (t["task_text"] + f" Run the tests with `{t['test_command']}` and report the result.")
    return cfg


def goal_md_real(task: dict, start: str, today: datetime.date) -> str:
    steps = "\n".join(f"## S{i} {s['title']}\nstatus: todo\nlane: required\nfiles: {s['files']}\nevidence:\nnote:\n"
                      for i, s in enumerate(task["steps"], 1))
    block_after = today + datetime.timedelta(days=14)
    return (f"---\ncreated: {today}\nblock_after: {block_after}\nstart_commit: {start}\n---\n\n"
            f"# Goal\n{task['task_text']}\n\n# Acceptance checks\n- `{task['test_command']}` exits with code 0.\n\n"
            f"# Steps\n\n{steps}")


def export_commit(repo: str, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", repo, "archive", commit], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar.stdout, check=True)


def make_real_workdir(arm: str, dest: Path, task: dict) -> tuple:
    """Tracked files of the parent commit only. The real repo is read through git archive and never written."""
    export_commit(task["repo"], task["parent"], dest)
    if arm == "C":
        shutil.copytree(SKILL, dest / ".claude" / "skills" / "goal-contract",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-qm", "start")
    start = git(dest, "rev-parse", "--short", "HEAD").stdout.strip()
    if arm == "C":
        (dest / "GOAL.md").write_text(goal_md_real(task, start, datetime.date.today()))
    if arm == "N":
        (dest / "NOTES.md").write_text(f"# Task notes\n\n{PROMPTS[task['name']]}\n")
    if arm != "A":
        git(dest, "add", "-A")
        git(dest, "commit", "-qm", "goal")
    return dest, start


def pytest_run(workdir: Path, *args: str) -> tuple:
    """Returns (passed, ran). Uses the venv python."""
    r = subprocess.run([str(REAL_DIR / "venv" / "bin" / "python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                       cwd=workdir, capture_output=True, text=True, timeout=300)
    return r.returncode == 0, ("passed" in r.stdout or "failed" in r.stdout)


def other_tests(workdir: Path, hidden_name: str) -> list:
    return sorted(str(p.relative_to(workdir)) for p in (workdir / "tests").glob("test_*.py") if p.name != hidden_name)


def real_scores(workdir: Path, task: dict) -> dict:
    shutil.copy(REAL_DIR / "rag_mini" / task["hidden_file"], workdir / "tests" / task["hidden_name"])
    hidden, ran = pytest_run(workdir, f"tests/{task['hidden_name']}")
    if not ran:
        raise FixtureBroken("real hidden test did not run")
    others = other_tests(workdir, task["hidden_name"])
    regression = pytest_run(workdir, *others)[0] if others else True
    return {"hidden_tests_passed": hidden, "regression_passed": regression}


def venv_probe() -> bool:
    py = REAL_DIR / "venv" / "bin" / "python"
    return py.exists() and subprocess.run([str(py), "-c", "import pytest, qdrant_client, numpy"], capture_output=True).returncode == 0


def check_fixture_real(cfg: dict, scenarios: list) -> None:
    """Hidden test passes at the commit, fails at the parent. The parent's other tests pass."""
    if not venv_probe():
        raise FixtureBroken("venv cannot import pytest, qdrant_client and numpy")
    for sc in scenarios:
        t = dict(cfg["tasks"][sc], repo=cfg["repo"], name=sc)
        with tempfile.TemporaryDirectory() as tmp:
            at_commit, at_parent = Path(tmp) / "commit", Path(tmp) / "parent"
            export_commit(cfg["repo"], t["commit"], at_commit)
            export_commit(cfg["repo"], t["parent"], at_parent)
            for d in (at_commit, at_parent):
                (d / "tests").mkdir(exist_ok=True)
                shutil.copy(REAL_DIR / "rag_mini" / t["hidden_file"], d / "tests" / t["hidden_name"])
            if not pytest_run(at_commit, f"tests/{t['hidden_name']}")[0]:
                raise FixtureBroken(f"{sc}: hidden test fails at the commit")
            if pytest_run(at_parent, f"tests/{t['hidden_name']}")[0]:
                raise FixtureBroken(f"{sc}: hidden test passes at the parent")
            others = other_tests(at_parent, t["hidden_name"])
            if others and not pytest_run(at_parent, *others)[0]:
                raise FixtureBroken(f"{sc}: the parent's own tests fail")


def check_fixture_p1(chain_length: int) -> None:
    """The chain is walkable from start.txt to the code word, and the 12 rule texts hold all their own tokens."""
    spec = depth_check.load_spec()
    if len(spec["rules"]) != 12 or len(depth_check.rules_kept(" ".join(r["text"] for r in spec["rules"]), spec)) != 12:
        raise FixtureBroken("P1 spec: the rule texts do not hold their own tokens")
    with tempfile.TemporaryDirectory() as tmp:
        codeword = depth_chain.make_chain(Path(tmp), chain_length, 1)
        cur, steps = "chain/start.txt", 0
        while steps <= chain_length:
            last = (Path(tmp) / cur).read_text().strip().splitlines()[-1]
            steps += 1
            if last.startswith("CODEWORD: "):
                if last != f"CODEWORD: {codeword}" or steps != chain_length:
                    raise FixtureBroken("P1 chain ends wrong")
                return
            cur = last.split("NEXT: ")[1]
        raise FixtureBroken("P1 chain does not end")


def check_fixture_s5() -> None:
    """Reference: 12 rules pass and the script exits 0. Bare repo: no rule passes, and the script exits 0 because
    nothing is built. Reference with a sorted stage 2: the script exits non-zero."""
    with tempfile.TemporaryDirectory() as tmp:
        dirs = {n: Path(tmp) / n for n in ("ref", "bare", "broken")}
        for d in dirs.values():
            shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("__pycache__", ".hidden", "truth.json"))
            shutil.copytree(S5_DIR / "workdir", d, dirs_exist_ok=True)
            shutil.copytree(S5_DIR / "acceptance", d / "acceptance")
        for n in ("ref", "broken"):
            shutil.copytree(S5_DIR / "reference", dirs[n], dirs_exist_ok=True)
        mark = "rows = [r for r in rows if r[\"qty\"] != 0]  # DROP_ZERO"
        tf = dirs["broken"] / "src" / "inventory" / "transform.py"
        if mark not in tf.read_text():
            raise FixtureBroken("reference transform.py lost its DROP_ZERO marker")
        tf.write_text(tf.read_text().replace(mark, mark + "\n    rows.sort(key=lambda r: r[\"sku\"])"))
        if not all(s5_rules(dirs["ref"]).values()):
            raise FixtureBroken("S5 hidden tests fail on the reference solution")
        if any(s5_rules(dirs["bare"]).values()):
            raise FixtureBroken("S5 hidden tests pass on the bare fixture")
        script = [sys.executable, "acceptance/check_stages.py"]
        for name, want_zero in (("ref", True), ("bare", True), ("broken", False)):
            code = subprocess.run(script, cwd=dirs[name], capture_output=True).returncode
            if (code == 0) != want_zero:
                raise FixtureBroken(f"acceptance script exit {code} on the {name} copy")


def check_fixture() -> None:
    """The hidden tests must pass on the reference solution and fail on the bare fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        ref, bare = Path(tmp) / "ref", Path(tmp) / "bare"
        for d in (ref, bare):
            shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REFERENCE, ref, dirs_exist_ok=True)
        if not hidden_tests_pass(ref):
            raise FixtureBroken("hidden tests fail on the reference solution")
        if hidden_tests_pass(bare):
            raise FixtureBroken("hidden tests pass on the bare fixture")


def probe_isolation(a: argparse.Namespace) -> bool:
    """True if a headless run with the trial flags sees no user CLAUDE.md text."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = Path(tmp) / "s.json"
        settings.write_text("{}")
        q = ("Without using tools: does your context contain any CLAUDE.md or user instruction text? "
             "Answer in one line: NONE, or quote the first heading line you can see.")
        data = claude_session(Path(tmp), q, a, settings, max_turns=1)
        return str(data.get("result", "")).strip().upper().startswith("NONE")


def copy_transcripts(session_ids: list, dest: Path) -> None:
    for sid in session_ids:
        for p in glob.glob(str(Path.home() / ".claude" / "projects" / "*" / f"{sid}.jsonl")):
            shutil.copy(p, dest / f"transcript-{sid}.jsonl")


def hook_stats(workdir: Path, arm: str) -> tuple:
    """Returns (blocks, hook_ok). State file is written on every checker run in arms B and C."""
    if arm in ("A", "N", "K"):
        return 0, True
    log = workdir / ".goal-contract" / "warnings.log"
    blocks = 0
    if log.exists():
        blocks = sum(json.loads(x).get("action") == "block" for x in log.read_text().splitlines() if x)
    return blocks, (workdir / ".goal-contract" / "state.json").exists()


def depth_prompt() -> str:
    rules = " ".join(f"({i}) {r['text']}" for i, r in enumerate(depth_check.load_spec()["rules"], 1))
    return ("Build `export.py`, a small CSV export tool. It must follow these twelve rules. " + rules +
            " Before you build anything, follow the chain of files in chain/. Start at chain/start.txt. "
            "Each file names the next file. The last file holds a code word. Write the code word to out/codeword.txt. "
            "Then build export.py so that it follows the rules.")


PROMPTS["P1"] = depth_prompt()


def build_settings_p1(arm: str, logdir: Path) -> dict:
    """Every arm gets the log-only compaction hooks. Arm C also gets the skill hooks, as in the other tests."""
    log = {"hooks": [{"type": "command", "command": f"python3 {shlex.quote(str(DEPTH_DIR / 'log_compaction.py'))} "
                                                       f"{shlex.quote(str(logdir))}"}]}
    hooks = {"PreCompact": [log], "PostCompact": [log]}
    if arm == "C":
        hooks.update(build_settings("C")["hooks"])
    return {"hooks": hooks}


def goal_md_probe(start: str, today: datetime.date) -> str:
    rules = " ".join(f"({i}) {r['text']}" for i, r in enumerate(depth_check.load_spec()["rules"], 1))
    block_after = today + datetime.timedelta(days=14)
    return (f"---\ncreated: {today}\nblock_after: {block_after}\nstart_commit: {start}\n---\n\n"
            f"# Goal\nBuild export.py, a small CSV export tool, that follows twelve rules. {rules}\n\n"
            "# Acceptance checks\n- out/codeword.txt holds the code word from the end of the chain.\n"
            "- export.py follows the twelve rules.\n\n# Steps\n\n"
            "## S1 Follow the chain and write the code word\nstatus: todo\nlane: required\nfiles: out/*\nevidence:\nnote:\n\n"
            "## S2 Build export.py\nstatus: todo\nlane: required\nfiles: export.py, tests/*\nevidence:\nnote:\n")


def make_probe_workdir(arm: str, dest: Path, chain_length: int, seed: int) -> tuple:
    dest.mkdir(parents=True)
    codeword = depth_chain.make_chain(dest, chain_length, seed)
    if arm == "C":
        shutil.copytree(SKILL, dest / ".claude" / "skills" / "goal-contract",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-qm", "start")
    start = git(dest, "rev-parse", "--short", "HEAD").stdout.strip()
    if arm == "K":
        rules = "\n".join(f"{i}. {r['text']}" for i, r in enumerate(depth_check.load_spec()["rules"], 1))
        (dest / "CLAUDE.md").write_text(f"# Project rules for export.py\n\n{rules}\n")
    if arm == "C":
        (dest / "GOAL.md").write_text(goal_md_probe(start, datetime.date.today()))
    if arm != "A":
        git(dest, "add", "-A")
        git(dest, "commit", "-qm", "goal")
    return dest, codeword


def p1_scores(rec: dict, workdir: Path, logdir: Path, codeword: str) -> dict:
    """Summary survival and recall. Needs rec['recall_answer'] and the post-compaction logs."""
    spec = depth_check.load_spec()
    posts = sorted(logdir.glob("*-post.json"))
    summaries = [json.loads(p.read_text()).get("compact_summary", "") for p in posts]
    cw = workdir / "out" / "codeword.txt"
    return {"compactions": len(posts), "window": rec.get("window"), "chain_length": rec.get("chain_length"),
            "summary_scores": [len(depth_check.rules_kept(t, spec)) for t in summaries],
            "recall_kept": depth_check.rules_kept(rec["recall_answer"], spec),
            "recall_score": len(depth_check.rules_kept(rec["recall_answer"], spec)),
            "codeword_ok": cw.exists() and codeword in cw.read_text()}


def function_exists(workdir: Path) -> bool:
    try:
        tree = ast.parse((workdir / "src" / "inventory" / "export.py").read_text())
    except (OSError, SyntaxError):
        return False
    return any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree))


def cli_works(workdir: Path) -> bool:
    """True if `export OUT` runs and writes a CSV that starts with the header."""
    with tempfile.TemporaryDirectory() as d:
        db, out = os.path.join(d, "db.json"), os.path.join(d, "out.csv")
        env = dict(os.environ, PYTHONPATH=str(workdir / "src"))

        def run(*args):
            return subprocess.run([sys.executable, "-m", "inventory", *args], cwd=workdir, env=env,
                                  capture_output=True, text=True, timeout=60)
        if run("--db", db, "add", "--sku", "A1", "--name", "Axle", "--qty", "2", "--price", "3").returncode:
            return False
        r = run("--db", db, "export", out)
        return r.returncode == 0 and os.path.exists(out) and open(out).readline().startswith("sku,name,qty,price")


def apply_event(kind: str, workdir: Path, start: str, truth: dict) -> None:
    """S7 events between sessions. baseline: both steps must exist. revert: restore cli.py to its start version."""
    if kind == "baseline":
        if not (function_exists(workdir) and cli_works(workdir)):
            raise RunError("no_baseline", "session 1 did not build both steps")
        return
    path = truth["events"]["e2_revert"]
    try:
        git(workdir, "checkout", start, "--", path)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", path], cwd=workdir).returncode
        if staged:  # the agent had committed cli.py, so the revert leaves a commit as a trace. Most runs commit nothing.
            git(workdir, "commit", "-qm", truth["events"]["e2_commit_message"], "--", path)
    except subprocess.CalledProcessError as e:
        raise RunError("event_failed", e.stderr[:200])
    if cli_works(workdir):
        raise RunError("event_failed", "export still works after the revert")


def s7_rules(workdir: Path) -> dict:
    return rules_run(workdir, S7_DIR / "hidden", "tests.test_s7_hidden", 6)


def memory_audit(workdir: Path, truth: dict, arm: str, cli_ok: bool) -> int:
    """Count claims in the memory file that are false now. Rough. Arm A has no file. Contract 28."""
    pats = {k: re.compile(v, re.IGNORECASE) for k, v in truth["audit_patterns"].items()}
    claims = 0
    if arm in ("T", "F"):
        path = workdir / "GOAL.md"
        try:
            text = path.read_text()
            goal = cg.parse_goal(text)
        except (OSError, cg.Malformed):
            return 0
        claims += len(cg.stale_findings(goal, cg.run_leaf_checks(workdir, goal))[0])
    elif arm == "N":
        path = workdir / "NOTES.md"
        if not path.exists():
            return 0
        text = path.read_text()
        claims += bool(pats["cli_done"].search(text)) and not cli_ok
    else:
        return 0
    claims += bool(pats["old_r2"].search(text)) and not pats["new_r2"].search(text)
    return int(claims)


def used_git_log(out: Path) -> bool:
    """True if the agent ran `git log` through the Bash tool. Tool descriptions also mention git, so read the commands only."""
    for p in out.glob("transcript-*.jsonl"):
        for line in p.read_text(errors="ignore").splitlines():
            try:
                content = json.loads(line).get("message", {}).get("content", [])
            except (json.JSONDecodeError, AttributeError):
                continue
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash" \
                        and "git log" in str(block.get("input", {}).get("command", "")):
                    return True
    return False


def s7_scores(workdir: Path, truth: dict, arm: str, out: Path) -> dict:
    rules = s7_rules(workdir)
    cli_ok = rules["r1"] and rules["r5"] and rules["r6"]
    goal_stale, state_stale = not rules["r2"], not cli_ok
    log = workdir / ".goal-contract" / "warnings.log"
    r7 = sum(any(f.get("rule") == "R7" for f in json.loads(x).get("findings", []))
             for x in log.read_text().splitlines() if x) if log.exists() else 0
    return {"rules": rules, "hidden_tests_passed": all(rules.values()), "goal_stale": goal_stale,
            "state_stale": state_stale, "stale_run": goal_stale or state_stale,
            "stale_claims_end": memory_audit(workdir, truth, arm, cli_ok), "r7_blocks": r7,
            "ran_git_log": used_git_log(out)}


def check_fixture_s7() -> None:
    """Reference: all six rules, acceptance scripts pass. Bare: no rule passes. Old sort: only r2 fails. Revert: r1 fails."""
    with tempfile.TemporaryDirectory() as tmp:
        ref, bare, old = Path(tmp) / "ref", Path(tmp) / "bare", Path(tmp) / "old"
        for d in (ref, bare, old):
            shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("__pycache__", ".hidden", "truth.json"))
            shutil.copytree(S7_DIR / "acceptance", d / "acceptance")
        shutil.copytree(S7_DIR / "reference", ref, dirs_exist_ok=True)
        shutil.copytree(S4_DIR / "reference", old, dirs_exist_ok=True)
        if not all(s7_rules(ref).values()):
            raise FixtureBroken("S7 hidden tests fail on the reference solution")
        if any(s7_rules(bare).values()):
            raise FixtureBroken("S7 hidden tests pass on the bare fixture")
        stale = s7_rules(old)
        if stale["r2"] or not all(v for k, v in stale.items() if k != "r2"):
            raise FixtureBroken("the S4 reference should fail only the new r2 rule")
        for name, cwd, want in (("check_function.py", ref, 0), ("check_export_s7.py", ref, 0),
                                ("check_export_s7.py", bare, 1), ("check_function.py", bare, 1)):
            code = subprocess.run([sys.executable, f"acceptance/{name}"], cwd=cwd, capture_output=True).returncode
            if (code == 0) != (want == 0):
                raise FixtureBroken(f"acceptance/{name} gave exit {code} in {cwd.name}")
        shutil.copy(FIXTURE / "src" / "inventory" / "cli.py", ref / "src" / "inventory" / "cli.py")
        if s7_rules(ref)["r1"] or cli_works(ref):
            raise FixtureBroken("reverting cli.py should break the export subcommand")


def run_sessions(rec: dict, workdir: Path, scenario: str, a: argparse.Namespace, settings: Path,
                 start: str = "", truth: dict = None) -> None:
    """Runs every session and updates rec as it goes, so cost is kept even if a later session fails."""
    sids, results = [], []
    rec.update(session_ids=sids, cost_usd=0.0, num_turns=0, permission_denials=0)
    for step in SCENARIOS[scenario] + [PROBES.get(scenario, PROBE_SESSION)]:
        resume = sids[-1] if step["resume"] and sids else None
        data = claude_session(workdir, PROMPTS[step["prompt"]], a, settings, resume, step["max_turns"])
        sids.append(data["session_id"])
        results.append(data.get("result") or "")
        rec["cost_usd"] += float(data.get("total_cost_usd") or 0)
        rec["num_turns"] += int(data.get("num_turns") or 0)
        rec["permission_denials"] += len(data.get("permission_denials") or [])
        if step.get("after"):
            apply_event(step["after"], workdir, start, truth)
    rec.update(final_message=results[-2], recall_answer=results[-1])


def run_one(arm: str, scenario: str, n: int, a: argparse.Namespace, truth: dict) -> dict:
    run_id = f"{arm}-{scenario}-{n:02d}"
    out = Path(a.out) / run_id
    out.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": run_id, "arm": arm, "scenario": scenario, "repeat": n, "model": a.model,
           "claude_version": a.claude_version, "valid": False, "invalid_reason": None, "cost_usd": 0.0}
    tmp = Path(tempfile.mkdtemp(prefix=f"gc-{run_id}-"))
    t0 = time.time()
    try:
        if scenario == "P1":
            workdir, codeword = make_probe_workdir(arm, tmp / "w", a.chain_length, a.chain_seed + n)
            rec.update(window=a.window, chain_length=a.chain_length)
        elif scenario in REAL_SCENARIOS:
            workdir, start = make_real_workdir(arm, tmp / "w", truth)
            rec["allowed_files"] = truth["allowed_files"]
        else:
            workdir, start = make_workdir(arm, tmp / "w", truth, a.full_spec, s4=scenario == "S4", s5=scenario == "S5",
                                          s7=scenario in ("S7", "S8", "S8b"))
        settings = out / "settings.json"
        settings.write_text(json.dumps(build_settings_p1(arm, out / "compaction-log") if scenario == "P1"
                                       else build_settings(arm), indent=2))
        run_sessions(rec, workdir, scenario, a, settings, start if scenario != "P1" else "", truth)
        copy_transcripts(rec["session_ids"], out)
        blocks, hook_ok = hook_stats(workdir, arm)
        if scenario == "P1":
            rec.update(p1_scores(rec, workdir, out / "compaction-log", codeword), blocks=blocks, numstat=[],
                       hidden_tests_passed=False)
            if "autocompact is thrashing" in rec["final_message"].lower():
                rec["invalid_reason"] = "thrash"
            elif rec["compactions"] == 0:
                rec["invalid_reason"] = "no_compaction"
            elif not hook_ok:
                rec["invalid_reason"] = "hook_error"
            else:
                rec["valid"] = True
            return rec
        patch, numstat = collect_diff(workdir, start)
        (out / "diff.patch").write_text(patch)
        if scenario in REAL_SCENARIOS:
            rec.update(real_scores(workdir, truth))
        elif scenario in ("S7", "S8", "S8b"):
            rec.update(s7_scores(workdir, truth, arm, out))
        elif scenario in ("S4", "S5"):
            rules = (s4_rules if scenario == "S4" else s5_rules)(workdir)
            rec.update(rules=rules, hidden_tests_passed=all(rules.values()))
        else:
            rec.update(hidden_tests_passed=hidden_tests_pass(workdir))
        rec.update(blocks=blocks, numstat=numstat)
        if hook_ok:
            rec["valid"] = True
        else:
            rec["invalid_reason"] = "hook_error"
        if (workdir / ".goal-contract" / "warnings.log").exists():
            shutil.copy(workdir / ".goal-contract" / "warnings.log", out / "warnings.log")
    except RunError as e:
        rec["invalid_reason"], rec["error_detail"] = e.reason, str(e)
    finally:
        rec["duration_s"] = round(time.time() - t0, 1)
        shutil.rmtree(tmp, ignore_errors=True)
        (out / "run.json").write_text(json.dumps(rec, indent=2))
    return rec


def existing_cell(out: Path, arm: str, scenario: str) -> tuple:
    """Returns (highest repeat number used, count of valid runs) for a cell."""
    top, valid = 0, 0
    for p in out.glob(f"{arm}-{scenario}-*/run.json"):
        rec = json.loads(p.read_text())
        top, valid = max(top, rec["repeat"]), valid + bool(rec["valid"])
    return top, valid


def pick(value: str, allowed: list) -> list:
    items = allowed if value == "all" else value.split(",")
    bad = [x for x in items if x not in allowed]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown value(s) {bad}, choose from {allowed} or all")
    return items


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", required=True, help="A, B, C, N (ADR-9 notes-file control), M (S4 memory version), T and F (S7 tree and flat), a comma list, or all")
    p.add_argument("--scenario", required=True, help="S1 to S5, S7 (staleness), R1 and R2 (real repo), P1 (summary survival probe), a comma list, or all")
    p.add_argument("--repeats", type=int, default=10)
    p.add_argument("--model", required=True)
    p.add_argument("--max-cost", type=float, required=True, help="batch stops when total cost reaches this USD value")
    p.add_argument("--out", required=True)
    p.add_argument("--max-turns", type=int, default=30)
    p.add_argument("--run-budget", type=float, default=1.0, help="per-session USD cap passed to claude")
    p.add_argument("--window", type=int, help="P1: CLAUDE_CODE_AUTO_COMPACT_WINDOW in tokens")
    p.add_argument("--chain-length", type=int, default=40, help="P1: number of chain files")
    p.add_argument("--chain-seed", type=int, default=1000, help="P1: run n uses seed chain-seed + n")
    p.add_argument("--full-spec", action="store_true",
                   help="ADR-8 follow-up: GOAL.md holds the full task text instead of the short goal")
    a = p.parse_args(argv)
    try:
        a.arms, a.scenarios = (["A", "B", "C"] if a.arm == "all" else pick(a.arm, ["A", "B", "C", "N", "M", "K", "T", "F"])), pick(a.scenario, ["S1", "S2", "S3", "S4", "S5", "S7", "S8", "S8b", "R1", "R2", "P1"])
    except argparse.ArgumentTypeError as e:
        p.error(str(e))
    if "M" in a.arms and not set(a.scenarios) <= {"S4", "S5"}:
        p.error("arm M runs in scenarios S4 and S5 only")
    if set(a.arms) & {"T", "F"} and a.scenarios not in (["S7"], ["S8"], ["S8b"]):
        p.error("arms T and F run in scenarios S7, S8 and S8b only")
    if set(a.scenarios) & {"S7", "S8", "S8b"} and (len(a.scenarios) != 1 or not set(a.arms) <= {"A", "N", "T", "F"}):
        p.error("scenarios S7, S8 and S8b run alone, with arms A, N, T and F")
    if "P1" in a.scenarios:
        if a.scenarios != ["P1"] or not set(a.arms) <= {"A", "K", "C"}:
            p.error("scenario P1 runs alone, with arms A, K and C")
        if not a.window:
            p.error("scenario P1 needs --window")
        a.tools = PROBE_TOOLS
        a.max_turns = max(a.max_turns, a.chain_length + 10)
    if set(a.scenarios) & set(REAL_SCENARIOS):
        if not set(a.scenarios) <= set(REAL_SCENARIOS) or not set(a.arms) <= {"A", "N", "C"}:
            p.error("real repo scenarios R1 and R2 run alone, with arms A, N and C")
        a.venv_bin = str(REAL_DIR / "venv" / "bin")
    if not Path(a.out).is_dir():
        p.error(f"--out folder does not exist: {a.out}")
    a.out = str(Path(a.out).resolve())  # trials run from other folders, so paths must be absolute
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    a.claude_version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    truths = {sc: json.loads((FIXTURE / "truth.json").read_text()) for sc in ("S1", "S2", "S3")}
    truths["S4"] = json.loads((S4_DIR / "truth-s4.json").read_text())
    truths["S5"] = json.loads((S5_DIR / "truth-s5.json").read_text())
    truths["S7"] = truths["S8"] = truths["S8b"] = json.loads((S7_DIR / "truth-s7.json").read_text())
    truths["P1"] = {}
    real_cfg = load_real_tasks() if set(a.scenarios) & set(REAL_SCENARIOS) else None
    if real_cfg:
        for sc in REAL_SCENARIOS:
            truths[sc] = dict(real_cfg["tasks"][sc], repo=real_cfg["repo"], name=sc)
    try:
        if set(a.scenarios) & {"S1", "S2", "S3"}:
            check_fixture()
        if "S5" in a.scenarios:
            check_fixture_s5()
        if "P1" in a.scenarios:
            check_fixture_p1(a.chain_length)
        if real_cfg:
            check_fixture_real(real_cfg, [sc for sc in a.scenarios if sc in REAL_SCENARIOS])
        if "S4" in a.scenarios:
            check_fixture_s4()
        if set(a.scenarios) & {"S7", "S8", "S8b"}:
            check_fixture_s7()
    except FixtureBroken as e:
        print(f"fixture broken: {e}", file=sys.stderr)
        return 5
    if not probe_isolation(a):
        print("isolation probe failed: user CLAUDE.md text is visible. See ADR-7.", file=sys.stderr)
        return 4
    total = 0.0
    for arm in a.arms:
        for sc in a.scenarios:
            top, valid = existing_cell(Path(a.out), arm, sc)
            attempts = 0
            while valid < a.repeats and attempts < a.repeats * 2:
                if total >= a.max_cost:
                    print(f"cost limit reached at ${total:.2f}. Finished runs are in {a.out}.", file=sys.stderr)
                    return 3
                top, attempts = top + 1, attempts + 1
                rec = run_one(arm, sc, top, a, truths[sc])
                total, valid = total + rec["cost_usd"], valid + bool(rec["valid"])
                print(f"{rec['run_id']} valid={rec['valid']} reason={rec['invalid_reason']} "
                      f"cost=${rec['cost_usd']:.3f} total=${total:.2f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
