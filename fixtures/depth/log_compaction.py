"""Log-only hook for PreCompact and PostCompact. Saves the hook input to a folder. Prints nothing, so it adds nothing to the context.

Usage: python3 log_compaction.py LOGDIR
"""
import json
import sys
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
        logdir = Path(sys.argv[1])
        logdir.mkdir(parents=True, exist_ok=True)
        kind = "pre" if data.get("hook_event_name") == "PreCompact" else "post"
        n = len(list(logdir.glob(f"*-{kind}.json"))) + 1
        (logdir / f"{n:02d}-{kind}.json").write_text(json.dumps(data))
    except Exception:  # a log hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
