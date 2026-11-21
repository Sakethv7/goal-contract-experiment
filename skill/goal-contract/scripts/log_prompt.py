"""UserPromptSubmit hook for the goal-contract skill. Contract: docs/api.md, Contract 27.

Appends each human prompt to .goal-contract/human_log.md. Never blocks. Writes nothing without a GOAL.md,
unless --no-goal-ok is set. If GC_LOG_DIR is set, the log goes to $GC_LOG_DIR/human_log.md (Contract 34).
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_goal import HUMAN_LOG, STATE_DIR  # noqa: E402


def log_path(repo: Path) -> Path:
    env = os.environ.get("GC_LOG_DIR")
    return Path(env) / HUMAN_LOG if env else repo / STATE_DIR / HUMAN_LOG


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-goal-ok", action="store_true", help="log even when the repo has no GOAL.md")
    args = parser.parse_args(argv)
    try:
        event = json.loads(sys.stdin.read() or "{}")
        repo = Path(event.get("cwd") or os.getcwd())
        prompt = " ".join(str(event.get("prompt", "")).split())
        if not prompt or not (args.no_goal_ok or (repo / "GOAL.md").exists()):
            return 0
        log = log_path(repo)
        log.parent.mkdir(parents=True, exist_ok=True)
        n = len(log.read_text().splitlines()) + 1 if log.exists() else 1
        with open(log, "a") as f:
            f.write(f"{n} | {datetime.datetime.now().isoformat(timespec='seconds')} | {prompt}\n")
    except Exception as exc:  # a hook must never break the session
        print(f"goal-contract hook error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
