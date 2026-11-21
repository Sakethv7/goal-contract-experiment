"""Stop hook for the goal-contract skill. Contract: docs/api.md, Contract 3.

Reads GOAL.md and the git diff. Never calls a model. Exits 0 (allow) or 2 (block).
"""
import argparse
import datetime
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUSES = {"todo", "in_progress", "reported_done", "verified", "blocked"}
DONE = {"reported_done", "verified"}
LOOP_CAP = 2
STATE_DIR = ".goal-contract"
EVIDENCE_RE = re.compile(r"exit(\s*code)?\s*\d+", re.IGNORECASE)
ACCEPTANCE_TIMEOUT_S = 60
LEAF_TIMEOUT_S = 60
PINNED_FILE = "pinned.txt"
HUMAN_LOG = "human_log.md"


class Malformed(Exception):
    pass


@dataclass
class Step:
    id: str
    title: str
    fields: dict


@dataclass
class Goal:
    front: dict
    steps: list


@dataclass
class Finding:
    rule: str
    step: str
    message: str


@dataclass
class Result:
    action: str  # allow, warn, or block
    mode: str  # off, warn, or block
    findings: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def parse_goal(text: str) -> Goal:
    lines = text.splitlines()
    front, i = {}, 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            key, sep, value = lines[i].partition(":")
            if sep:
                front[key.strip()] = value.strip()
            i += 1
        i += 1
    steps, cur = [], None
    for line in lines[i:]:
        m = re.match(r"##\s+(S\d+(?:\.\d+)*)\s*(.*)$", line)
        if m:
            cur = Step(m.group(1), m.group(2).strip(), {})
            steps.append(cur)
        elif re.match(r"#\s", line):
            cur = None
        elif cur is not None:
            key, sep, value = line.partition(":")
            if sep and re.fullmatch(r"[a-z_]+", key.strip()):
                cur.fields[key.strip()] = value.strip()
    if not steps:
        raise Malformed("no steps found")
    return Goal(front, steps)


def invariants_block(text: str) -> str:
    """The lines under the `# Invariants` heading, up to the next `# ` heading. Empty if there is none."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"#\s", line):
            inside = line.strip().lower() == "# invariants"
        elif inside and line.strip():
            out.append(line.rstrip())
    return "\n".join(out)


def pinned_fields(text: str, goal: "Goal") -> str:
    """The invariants block plus the acceptance_command line. Rule R6 guards this text."""
    return invariants_block(text) + "\nacceptance_command: " + goal.front.get("acceptance_command", "")


def current_mode(goal: Goal, today: datetime.date, force: str = None) -> str:
    if force:
        return force
    try:
        return "block" if today > datetime.date.fromisoformat(goal.front.get("block_after", "")) else "warn"
    except ValueError:
        return "warn"


def changed_files(repo: Path, start: str):
    def git(*args):
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
        if r.returncode:
            raise OSError(r.stderr.strip())
        return r.stdout.split("\n")

    try:
        files = git("diff", "--name-only", start) + git("ls-files", "--others", "--exclude-standard")
    except OSError:
        return None
    return sorted({f for f in files if f})


def is_infra(path: str) -> bool:
    return path == "GOAL.md" or path.startswith(STATE_DIR + "/")


def step_problems(step: Step, seen: set, derived: bool = False) -> list:
    out, status = [], step.fields.get("status", "")
    if step.id in seen:
        out.append(Finding("R4", step.id, f"Step id {step.id} appears twice."))
    if status not in STATUSES:
        out.append(Finding("R4", step.id, f"Step {step.id} has no valid status. Use one of {sorted(STATUSES)}."))
    if status in DONE and not derived and not EVIDENCE_RE.search(step.fields.get("evidence", "")):
        out.append(Finding("R1", step.id, f"Step {step.id} is {status} but has no evidence. Add the command and its exit code."))
    if step.fields.get("lane") == "added" and status not in ("todo", "blocked") and step.fields.get("approved") != "yes":
        out.append(Finding("R3", step.id, f"Step {step.id} is added work and the human has not approved it. Stop and ask."))
    return out


def find_problems(goal: Goal, changed) -> list:
    out, seen = [], set()
    parent_ids = {s.fields.get("parent") for s in goal.steps} - {None, ""}  # a parent is derived from its children
    for step in goal.steps:
        out += step_problems(step, seen, step.id in parent_ids)
        seen.add(step.id)
    if changed is not None:
        globs = [g.strip() for s in goal.steps for g in s.fields.get("files", "").split(",") if g.strip()]
        for path in changed:
            if not is_infra(path) and not any(fnmatch.fnmatch(path, g) for g in globs):
                out.append(Finding("R2", "-", f"File {path} changed but no step lists it in files."))
    return out


def gate_findings(repo: Path, goal: Goal, text: str) -> tuple:
    """Rules R5 and R6. Returns (findings, notes). A command that cannot start is a note, never a finding."""
    findings, notes = [], []
    command = goal.front.get("acceptance_command", "")
    if command:
        try:
            r = subprocess.run(shlex.split(command), cwd=repo, capture_output=True, text=True,
                               timeout=ACCEPTANCE_TIMEOUT_S, stdin=subprocess.DEVNULL)
            if r.returncode:
                tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-10:])
                findings.append(Finding("R5", "-", f"R5 acceptance failed (exit {r.returncode}): {command}\n{tail}"))
        except subprocess.TimeoutExpired:
            findings.append(Finding("R5", "-", f"R5 acceptance timed out after {ACCEPTANCE_TIMEOUT_S} seconds: {command}"))
        except (OSError, ValueError):
            notes.append("acceptance_error")
    try:
        saved = (repo / STATE_DIR / PINNED_FILE).read_text()
    except OSError:
        notes.append("no_pinned_copy")
        return findings, notes
    if saved != pinned_fields(text, goal):
        findings.append(Finding("R6", "-", "R6 pinned field changed. The invariants and acceptance_command are set by the human. Restore them."))
    return findings, notes


def run_leaf_checks(repo: Path, goal: Goal) -> dict:
    """Runs every evidence_command. Returns {step id: {"state": ok|fail|unknown, "tail": text}}. No shell."""
    out = {}
    for step in goal.steps:
        command = step.fields.get("evidence_command", "")
        if not command:
            continue
        try:
            r = subprocess.run(shlex.split(command), cwd=repo, capture_output=True, text=True,
                               timeout=LEAF_TIMEOUT_S, stdin=subprocess.DEVNULL)
            tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
            out[step.id] = {"state": "ok" if r.returncode == 0 else "fail", "tail": tail, "code": r.returncode}
        except subprocess.TimeoutExpired:
            out[step.id] = {"state": "fail", "tail": f"timed out after {LEAF_TIMEOUT_S} seconds", "code": "timeout"}
        except (OSError, ValueError):
            out[step.id] = {"state": "unknown", "tail": "the command could not start", "code": "none"}
    return out


def roll_up(goal: Goal, checks: dict) -> dict:
    """State of every node: ok, fail or unknown. A parent is ok only if all its children are ok."""
    kids = {}
    for s in goal.steps:
        if s.fields.get("parent"):
            kids.setdefault(s.fields["parent"], []).append(s.id)
    states = {}

    def state(sid: str, depth: int = 0) -> str:
        if sid in states:
            return states[sid]
        if sid in kids and depth < 20:
            child = [state(k, depth + 1) for k in kids[sid]]
            states[sid] = "ok" if all(c == "ok" for c in child) else "fail" if "fail" in child else "unknown"
        else:
            states[sid] = checks.get(sid, {}).get("state", "unknown")
        return states[sid]

    for s in goal.steps:
        state(s.id)
    return states


def leaf_flag(step: Step, check: dict) -> str:
    status = step.fields.get("status", "")
    if check["state"] == "unknown":
        return "UNKNOWN: its check could not run"
    if check["state"] == "ok":
        return "OK" if status == "verified" else f"its check passes, but the status is {status}"
    if status in DONE:
        return f"STALE: marked {status}, but its check fails now"
    return "not done yet"


def render_tree(goal: Goal, checks: dict, rollup: bool) -> str:
    """Live view of the steps. With rollup, parents are shown above their children with a derived flag."""
    states = roll_up(goal, checks) if rollup else {}
    by_id = {s.id: s for s in goal.steps}

    def depth(s: Step) -> int:
        d, p = 0, s.fields.get("parent")
        while rollup and p in by_id and d < 20:
            d, p = d + 1, by_id[p].fields.get("parent")
        return d

    lines = []
    for s in goal.steps:
        if s.id in checks:
            flag = leaf_flag(s, checks[s.id])
        elif rollup and s.id in states:
            bad = [k.id for k in goal.steps if k.fields.get("parent") == s.id and states.get(k.id) != "ok"]
            flag = "all children are OK" if states[s.id] == "ok" else f"NOT verified: {', '.join(bad)} not OK"
        else:
            continue
        lines.append(f"{'  ' * depth(s)}{s.id} {s.title} [{flag}]")
    return "\n".join(lines)


def stale_findings(goal: Goal, checks: dict) -> tuple:
    """Rule R7. A step marked done whose check fails now. An unknown check is a note, never a finding."""
    findings, notes = [], []
    for s in goal.steps:
        c = checks.get(s.id)
        if not c:
            continue
        if c["state"] == "unknown":
            notes.append("leaf_unknown")
        elif c["state"] == "fail" and s.fields.get("status") in DONE:
            findings.append(Finding("R7", s.id, f"R7 Step {s.id} is marked {s.fields['status']}, but its check fails now: "
                                                f"{s.fields.get('evidence_command')} (exit {c['code']}). Fix the code, or set the status "
                                                f"back to in_progress.\n{c['tail']}"))
    return findings, notes


def evaluate(repo: Path, today: datetime.date, force_mode: str = None, blocks_so_far: int = 0,
             gate: bool = False, leaves: bool = False) -> Result:
    goal_file = repo / "GOAL.md"
    if not goal_file.exists():
        return Result("allow", "off")
    try:
        text = goal_file.read_text()
        goal = parse_goal(text)
    except (Malformed, UnicodeDecodeError):
        return Result("allow", "off", notes=["malformed_goal"])
    notes, changed = [], None
    start = goal.front.get("start_commit", "")
    if not start:
        notes.append("no_start_commit")
    else:
        changed = changed_files(repo, start)
        if changed is None:
            notes.append("no_git")
    findings, mode = find_problems(goal, changed), current_mode(goal, today, force_mode)
    if gate:
        extra, extra_notes = gate_findings(repo, goal, text)
        findings, notes = findings + extra, notes + extra_notes
    if leaves:
        extra, extra_notes = stale_findings(goal, run_leaf_checks(repo, goal))
        findings, notes = findings + extra, notes + extra_notes
    if not findings:
        return Result("allow", mode, notes=notes)
    if mode == "warn":
        return Result("warn", mode, findings, notes)
    if blocks_so_far >= LOOP_CAP:
        return Result("allow", mode, findings, notes + ["loop_cap"])
    return Result("block", mode, findings, notes)


def load_blocks(repo: Path) -> int:
    try:
        return int(json.loads((repo / STATE_DIR / "state.json").read_text()).get("blocks", 0))
    except (OSError, ValueError):
        return 0


def write_state_and_log(repo: Path, res: Result, blocks: int) -> None:
    d = repo / STATE_DIR
    d.mkdir(exist_ok=True)
    (d / "state.json").write_text(json.dumps({"blocks": blocks}))
    if res.findings or res.notes:
        entry = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "action": res.action,
                 "mode": res.mode, "notes": res.notes, "findings": [asdict(f) for f in res.findings]}
        with open(d / "warnings.log", "a") as f:
            f.write(json.dumps(entry) + "\n")


def format_findings(findings: list) -> str:
    head = f"goal-contract: {len(findings)} finding(s) in GOAL.md. Fix each one, or label the work lane: added, then stop again."
    return "\n".join([head] + [f"- [{f.rule}] {f.message}" for f in findings])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-mode", choices=["warn", "block"])
    parser.add_argument("--gate", action="store_true", help="run the acceptance command and guard pinned fields")
    parser.add_argument("--leaves", action="store_true", help="rule R7: re-run each evidence_command at stop")
    args = parser.parse_args(argv)
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        hook = {}
    repo = Path(hook.get("cwd") or os.getcwd())
    try:
        res = evaluate(repo, datetime.date.today(), args.force_mode, load_blocks(repo), args.gate, args.leaves)
        if res.mode != "off" or res.notes:
            write_state_and_log(repo, res, load_blocks(repo) + 1 if res.action == "block" else 0)
    except Exception as exc:  # a hook must never break the session
        print(f"goal-contract hook error: {exc}", file=sys.stderr)
        return 0
    if res.action == "block":
        print(format_findings(res.findings), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
