"""SessionStart hook for the goal-contract skill. Contract: docs/api.md, Contract 2.

Prints GOAL.md into the agent context. Prints nothing if the repo has no GOAL.md.
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_goal import (HUMAN_LOG, PINNED_FILE, STATE_DIR, Malformed, current_mode, invariants_block, parse_goal,  # noqa: E402
                        pinned_fields, render_tree, run_leaf_checks)

LOG_ENTRY_CHARS = 500


def live_section(repo: Path, goal, rollup: bool) -> str:
    """Leaf checks run now, plus the human prompts so far. Printed after GOAL.md, which may be old."""
    parts = ["\nLive check, run just now. The status lines above were written earlier and may be old. Trust this view. "
             "Set any step flagged STALE back to in_progress and fix it.",
             render_tree(goal, run_leaf_checks(repo, goal), rollup)]
    try:
        entries = (repo / STATE_DIR / HUMAN_LOG).read_text().splitlines()
    except OSError:
        entries = []
    if entries:
        parts.append("\nHuman prompts so far, oldest first. The newest human instruction wins over older goal text. "
                     "If a newer prompt changes a rule, update the Goal text in GOAL.md to match.")
        parts += [e if len(e) <= LOG_ENTRY_CHARS else e[:LOG_ENTRY_CHARS] + " [cut]" for e in entries]
    return "\n".join(parts)


def save_pinned_copy(repo: Path, content: str) -> None:
    d = repo / STATE_DIR
    d.mkdir(exist_ok=True)
    if not (d / PINNED_FILE).exists():
        (d / PINNED_FILE).write_text(content)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-mode", choices=["warn", "block"])
    parser.add_argument("--pin", action="store_true", help="print the invariants at the top and the bottom")
    parser.add_argument("--leaves", action="store_true", help="run each evidence_command and print a live view and the human log")
    parser.add_argument("--rollup", action="store_true", help="with --leaves: show parents with a derived flag")
    args = parser.parse_args(argv)
    try:
        hook = json.loads(sys.stdin.read() or "{}")
        goal_file = Path(hook.get("cwd") or os.getcwd()) / "GOAL.md"
        if not goal_file.exists():
            return 0
        text = goal_file.read_text()
        today = datetime.date.today()
        goal = None
        try:
            goal = parse_goal(text)
            mode = current_mode(goal, today, args.force_mode)
        except Malformed:
            mode = "unknown (GOAL.md is malformed)"
        pin = invariants_block(text) if args.pin and goal else ""
        if pin:
            print("These rules always apply.\n" + pin + "\n")
            save_pinned_copy(goal_file.parent, pinned_fields(text, goal))
        print(text)
        if args.leaves and goal:
            print(live_section(goal_file.parent, goal, args.rollup))
        if pin:
            print("\nThese rules always apply.\n" + pin)
        print(f"goal-contract: mode={mode} today={today.isoformat()}")
    except Exception as exc:  # a hook must never break the session
        print(f"goal-contract hook error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
