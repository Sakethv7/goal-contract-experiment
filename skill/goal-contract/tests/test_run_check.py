import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_check.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_goal  # noqa: E402


def run_check(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class RunCheckTest(unittest.TestCase):
    def test_success_prints_exit_and_evidence(self):
        r = run_check(sys.executable, "-c", "print('hello')")
        self.assertEqual(r.returncode, 0)
        self.assertIn("exit 0", r.stdout)
        self.assertIn('"hello"', r.stdout)

    def test_failure_keeps_exit_code(self):
        r = run_check(sys.executable, "-c", "import sys; print('bad'); sys.exit(3)")
        self.assertEqual(r.returncode, 3)
        self.assertIn("exit 3", r.stdout)

    def test_missing_command_gives_127(self):
        self.assertEqual(run_check("definitely-not-a-command-xyz").returncode, 127)

    def test_no_args_is_usage_error(self):
        self.assertEqual(run_check().returncode, 2)

    def test_evidence_line_satisfies_checker_rule_r1(self):
        out = run_check(sys.executable, "-c", "print('Ran 9 tests')").stdout
        line = [x for x in out.splitlines() if x.startswith("evidence:")][0]
        self.assertTrue(check_goal.EVIDENCE_RE.search(line))


if __name__ == "__main__":
    unittest.main()
