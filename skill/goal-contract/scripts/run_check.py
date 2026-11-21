"""Run a check command and print its output tail, its exit code, and a ready-to-paste evidence line.

Usage: python3 run_check.py COMMAND [ARGS...]
No shell is used. Exits with the same code as the command (127 if it cannot start).
"""
import shlex
import subprocess
import sys

TAIL_LINES = 15


def run(argv: list) -> tuple:
    try:
        r = subprocess.run(argv, capture_output=True, text=True)
    except OSError as exc:
        return 127, str(exc)
    return r.returncode, (r.stdout + r.stderr)


def evidence_line(argv: list, code: int, output: str) -> str:
    lines = [x.strip() for x in output.splitlines() if x.strip()]
    last = lines[-1] if lines else "no output"
    return f'evidence: `{shlex.join(argv)}` exit {code}, "{last}"'


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: run_check.py COMMAND [ARGS...]", file=sys.stderr)
        return 2
    code, output = run(argv)
    print("\n".join(output.splitlines()[-TAIL_LINES:]))
    print(f"exit {code}")
    print(evidence_line(argv, code, output))
    return code


if __name__ == "__main__":
    sys.exit(main())
