"""UserPromptSubmit hook for the goal-contract skill. Contract: docs/api.md, Contract 27.

Appends each human prompt to .goal-contract/human_log.md. Never blocks. Writes nothing without a GOAL.md.
"""
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_goal import HUMAN_LOG, STATE_DIR  # noqa: E402


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        repo = Path(event.get("cwd") or os.getcwd())
        prompt = " ".join(str(event.get("prompt", "")).split())
        if not (repo / "GOAL.md").exists() or not prompt:
            return 0
        d = repo / STATE_DIR
        d.mkdir(exist_ok=True)
        log = d / HUMAN_LOG
        n = len(log.read_text().splitlines()) + 1 if log.exists() else 1
        with open(log, "a") as f:
            f.write(f"{n} | {datetime.datetime.now().isoformat(timespec='seconds')} | {prompt}\n")
    except Exception as exc:  # a hook must never break the session
        print(f"goal-contract hook error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
