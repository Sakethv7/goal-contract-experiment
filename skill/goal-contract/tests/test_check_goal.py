import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_goal as cg  # noqa: E402

TODAY = datetime.date(2026, 11, 19)


def goal_text(steps: str, block_after="2026-12-03", start="START") -> str:
    return f"---\ncreated: 2026-11-19\nblock_after: {block_after}\nstart_commit: {start}\n---\n\n# Goal\nx\n\n# Steps\n\n{steps}"


STEP_OK = "## S1 Do it\nstatus: verified\nlane: required\nfiles: src/*.py\nevidence: `python3 -m unittest` exit 0, \"OK\"\n"
STEP_NO_EVIDENCE = "## S1 Do it\nstatus: reported_done\nlane: required\nfiles: src/*.py\nevidence:\n"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        git(self.path, "init", "-q")
        git(self.path, "config", "user.email", "t@example.com")
        git(self.path, "config", "user.name", "t")
        (self.path / "src").mkdir()
        (self.path / "src" / "a.py").write_text("x = 1\n")
        git(self.path, "add", "-A")
        git(self.path, "commit", "-qm", "start")
        self.start = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.path,
                                    capture_output=True, text=True).stdout.strip()

    def write_goal(self, steps, **kw):
        kw.setdefault("start", self.start)
        (self.path / "GOAL.md").write_text(goal_text(steps, **kw))


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)

    def run_eval(self, **kw):
        return cg.evaluate(self.r.path, TODAY, **kw)

    def test_no_goal_file_is_off(self):
        res = self.run_eval()
        self.assertEqual((res.action, res.mode, res.notes), ("allow", "off", []))

    def test_clean_goal_allows(self):
        self.r.write_goal(STEP_OK)
        self.assertEqual(self.run_eval().action, "allow")

    def test_r1_missing_evidence_warns_before_date(self):
        self.r.write_goal(STEP_NO_EVIDENCE)
        res = self.run_eval()
        self.assertEqual(res.action, "warn")
        self.assertEqual([f.rule for f in res.findings], ["R1"])

    def test_r1_blocks_after_date(self):
        self.r.write_goal(STEP_NO_EVIDENCE, block_after="2026-11-01")
        self.assertEqual(self.run_eval().action, "block")

    def test_force_mode_overrides_date(self):
        self.r.write_goal(STEP_NO_EVIDENCE)
        self.assertEqual(self.run_eval(force_mode="block").action, "block")

    def test_loop_cap_allows_after_two_blocks(self):
        self.r.write_goal(STEP_NO_EVIDENCE)
        res = self.run_eval(force_mode="block", blocks_so_far=2)
        self.assertEqual(res.action, "allow")
        self.assertIn("loop_cap", res.notes)

    def test_r2_unplanned_tracked_and_untracked_files(self):
        self.r.write_goal(STEP_OK)
        (self.r.path / "README.md").write_text("new\n")          # untracked, no glob
        (self.r.path / "src" / "a.py").write_text("x = 2\n")      # tracked change, covered
        res = self.run_eval()
        self.assertEqual([(f.rule, "README.md" in f.message) for f in res.findings], [("R2", True)])

    def test_infra_files_never_flagged(self):
        self.r.write_goal(STEP_OK)
        (self.r.path / ".goal-contract").mkdir()
        (self.r.path / ".goal-contract" / "state.json").write_text("{}")
        self.assertEqual(self.run_eval().findings, [])

    def test_r3_added_lane_needs_approval(self):
        added = STEP_OK + "\n## S2 Extra\nstatus: in_progress\nlane: added\nfiles: src/*.py\n"
        self.r.write_goal(added)
        self.assertEqual([f.rule for f in self.run_eval().findings], ["R3"])
        self.r.write_goal(added + "approved: yes\n")
        self.assertEqual(self.run_eval().findings, [])

    def test_r4_invalid_status_and_duplicate_id(self):
        self.r.write_goal(STEP_OK + "\n## S1 Again\nstatus: done\nlane: required\nfiles: src/*.py\n")
        self.assertEqual(sorted(f.rule for f in self.run_eval().findings), ["R4", "R4"])

    def test_malformed_allows_with_note(self):
        (self.r.path / "GOAL.md").write_text("no front matter and no steps\n")
        res = self.run_eval(force_mode="block")
        self.assertEqual((res.action, res.notes), ("allow", ["malformed_goal"]))

    def test_missing_start_commit_skips_r2(self):
        self.r.write_goal(STEP_OK, start="")
        (self.r.path / "README.md").write_text("new\n")
        res = self.run_eval()
        self.assertEqual(res.findings, [])
        self.assertIn("no_start_commit", res.notes)

    def test_no_git_skips_r2(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "GOAL.md").write_text(goal_text(STEP_OK, start="abc123"))
            res = cg.evaluate(Path(d), TODAY)
            self.assertIn("no_git", res.notes)
            self.assertEqual(res.findings, [])


class CliTest(unittest.TestCase):
    def run_hook(self, script, repo, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=json.dumps({"cwd": str(repo)}),
                              capture_output=True, text=True)

    def test_block_exit_code_log_and_cap(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        r.write_goal(STEP_NO_EVIDENCE)
        first = self.run_hook("check_goal.py", r.path, "--force-mode", "block")
        second = self.run_hook("check_goal.py", r.path, "--force-mode", "block")
        third = self.run_hook("check_goal.py", r.path, "--force-mode", "block")
        self.assertEqual([first.returncode, second.returncode, third.returncode], [2, 2, 0])
        self.assertIn("[R1]", first.stderr)
        log = [json.loads(line) for line in (r.path / ".goal-contract" / "warnings.log").read_text().splitlines()]
        self.assertEqual([e["action"] for e in log], ["block", "block", "allow"])

    def test_no_goal_file_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            res = self.run_hook("check_goal.py", Path(d))
            self.assertEqual(res.returncode, 0)
            self.assertEqual(os.listdir(d), [])

    def test_inject_prints_goal_and_mode_line(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        r.write_goal(STEP_OK)
        out = self.run_hook("inject_goal.py", r.path).stdout
        self.assertIn("# Goal", out)
        self.assertRegex(out, r"goal-contract: mode=(warn|block) today=\d{4}-\d{2}-\d{2}")

    def test_inject_silent_without_goal(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_hook("inject_goal.py", Path(d)).stdout, "")


INV_TEXT = "# Invariants\n1. Rule one.\n2. Rule two.\n"


class GateTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)

    def write(self, command, invariants=INV_TEXT):
        text = (f"---\ncreated: 2026-11-19\nblock_after: 2026-12-03\nstart_commit: {self.r.start}\n"
                f"acceptance_command: {command}\n---\n\n# Goal\nx\n\n{invariants}\n# Steps\n\n{STEP_OK}")
        (self.r.path / "GOAL.md").write_text(text)

    def pin(self):
        goal_text_now = (self.r.path / "GOAL.md").read_text()
        goal = cg.parse_goal(goal_text_now)
        d = self.r.path / ".goal-contract"
        d.mkdir(exist_ok=True)
        (d / "pinned.txt").write_text(cg.pinned_fields(goal_text_now, goal))

    def ev(self, gate=True):
        return cg.evaluate(self.r.path, TODAY, force_mode="block", gate=gate)

    def test_invariants_block_stops_at_next_heading(self):
        self.assertEqual(cg.invariants_block("# Goal\nx\n\n" + INV_TEXT + "\n# Steps\n"), "1. Rule one.\n2. Rule two.")
        self.assertEqual(cg.invariants_block("# Goal\nx\n"), "")

    def test_passing_script_gives_no_finding(self):
        self.write(f"{sys.executable} -c pass")
        self.pin()
        res = self.ev()
        self.assertEqual((res.action, res.findings), ("allow", []))

    def test_failing_script_blocks_with_output_tail(self):
        self.write(f"{sys.executable} -c 'import sys; print(1); sys.exit(3)'")
        self.pin()
        res = self.ev()
        self.assertEqual(res.action, "block")
        self.assertTrue(any(f.rule == "R5" and "exit 3" in f.message for f in res.findings))

    def test_script_that_cannot_start_is_a_note_not_a_finding(self):
        self.write("no-such-binary-xyz")
        self.pin()
        res = self.ev()
        self.assertIn("acceptance_error", res.notes)
        self.assertEqual(res.findings, [])

    def test_timeout_is_a_finding(self):
        self.write(f"{sys.executable} -c 'import time; time.sleep(5)'")
        self.pin()
        old, cg.ACCEPTANCE_TIMEOUT_S = cg.ACCEPTANCE_TIMEOUT_S, 1
        self.addCleanup(setattr, cg, "ACCEPTANCE_TIMEOUT_S", old)
        res = self.ev()
        self.assertTrue(any("timed out" in f.message for f in res.findings))

    def test_edited_invariants_trigger_r6(self):
        self.write(f"{sys.executable} -c pass")
        self.pin()
        self.write(f"{sys.executable} -c pass", invariants="# Invariants\n1. Rule one.\n")
        self.assertTrue(any(f.rule == "R6" for f in self.ev().findings))

    def test_edited_acceptance_command_triggers_r6(self):
        self.write(f"{sys.executable} -c pass")
        self.pin()
        self.write("true")
        self.assertTrue(any(f.rule == "R6" for f in self.ev().findings))

    def test_missing_pinned_copy_skips_r6(self):
        self.write(f"{sys.executable} -c pass")
        res = self.ev()
        self.assertIn("no_pinned_copy", res.notes)
        self.assertEqual(res.findings, [])

    def test_gate_off_runs_nothing(self):
        self.write(f"{sys.executable} -c 'import sys; sys.exit(3)'")
        self.assertEqual(self.ev(gate=False).findings, [])


class PinTest(unittest.TestCase):
    def run_inject(self, repo, *flags):
        return subprocess.run([sys.executable, str(SCRIPTS / "inject_goal.py"), *flags], input=json.dumps({"cwd": str(repo)}),
                              capture_output=True, text=True)

    def test_pin_prints_rules_top_and_bottom_and_saves_copy(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        text = goal_text(STEP_OK).replace("# Steps", INV_TEXT + "\n# Steps")
        (r.path / "GOAL.md").write_text(text)
        out = self.run_inject(r.path, "--pin").stdout
        self.assertEqual(out.count("1. Rule one."), 3)  # top, inside GOAL.md, bottom
        self.assertTrue(out.startswith("These rules always apply."))
        self.assertTrue((r.path / ".goal-contract" / "pinned.txt").exists())

    def test_without_pin_output_is_v1(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        text = goal_text(STEP_OK).replace("# Steps", INV_TEXT + "\n# Steps")
        (r.path / "GOAL.md").write_text(text)
        out = self.run_inject(r.path).stdout
        self.assertEqual(out.count("1. Rule one."), 1)
        self.assertFalse((r.path / ".goal-contract").exists())


def tree_goal(repo, ok_cmd, bad_cmd, status1="verified", parent_status="todo"):
    steps = (f"## S1 Whole\nstatus: {parent_status}\nlane: required\nfiles: src/*.py\n\n"
             f"## S1.1 Good leaf\nparent: S1\nstatus: {status1}\nlane: required\nfiles: src/*.py\n"
             f"evidence_command: {ok_cmd}\nevidence: `x` exit 0\n\n"
             f"## S1.2 Bad leaf\nparent: S1\nstatus: verified\nlane: required\nfiles: src/*.py\n"
             f"evidence_command: {bad_cmd}\nevidence: `x` exit 0\n")
    (repo.path / "GOAL.md").write_text(goal_text(steps, start=repo.start))


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)
        self.ok = f"{sys.executable} -c pass"
        self.bad = f"{sys.executable} -c 'import sys; sys.exit(3)'"

    def goal(self):
        return cg.parse_goal((self.r.path / "GOAL.md").read_text())

    def test_dotted_ids_and_parent_field_parse(self):
        tree_goal(self.r, self.ok, self.bad)
        ids = [(s.id, s.fields.get("parent")) for s in self.goal().steps]
        self.assertEqual(ids, [("S1", None), ("S1.1", "S1"), ("S1.2", "S1")])

    def test_leaf_checks_report_ok_fail_and_unknown(self):
        tree_goal(self.r, self.ok, "no-such-binary-xyz")
        checks = cg.run_leaf_checks(self.r.path, self.goal())
        self.assertEqual((checks["S1.1"]["state"], checks["S1.2"]["state"]), ("ok", "unknown"))
        tree_goal(self.r, self.ok, self.bad)
        checks = cg.run_leaf_checks(self.r.path, self.goal())
        self.assertEqual((checks["S1.2"]["state"], checks["S1.2"]["code"]), ("fail", 3))

    def test_roll_up_parent_is_ok_only_if_all_children_ok(self):
        tree_goal(self.r, self.ok, self.bad)
        goal = self.goal()
        self.assertEqual(cg.roll_up(goal, cg.run_leaf_checks(self.r.path, goal))["S1"], "fail")
        tree_goal(self.r, self.ok, self.ok)
        goal = self.goal()
        self.assertEqual(cg.roll_up(goal, cg.run_leaf_checks(self.r.path, goal))["S1"], "ok")

    def test_render_tree_flags_stale_leaf_and_unverified_parent(self):
        tree_goal(self.r, self.ok, self.bad)
        goal = self.goal()
        text = cg.render_tree(goal, cg.run_leaf_checks(self.r.path, goal), rollup=True)
        self.assertIn("S1 Whole [NOT verified: S1.2 not OK]", text)
        self.assertIn("  S1.2 Bad leaf [STALE: marked verified, but its check fails now]", text)
        flat = cg.render_tree(goal, cg.run_leaf_checks(self.r.path, goal), rollup=False)
        self.assertNotIn("S1 Whole", flat)
        self.assertNotIn("  S1.2", flat)

    def test_r7_flags_done_step_with_failing_check_only_with_leaves(self):
        tree_goal(self.r, self.ok, self.bad)
        off = cg.evaluate(self.r.path, TODAY, force_mode="block")
        on = cg.evaluate(self.r.path, TODAY, force_mode="block", leaves=True)
        self.assertEqual([f.rule for f in off.findings], [])
        self.assertEqual([(f.rule, f.step) for f in on.findings], [("R7", "S1.2")])
        self.assertEqual(on.action, "block")

    def test_r7_ignores_unfinished_step_and_unknown_command(self):
        tree_goal(self.r, self.ok, self.bad)
        text = (self.r.path / "GOAL.md").read_text().replace("status: verified\nlane: required\nfiles: src/*.py\nevidence_command: " + self.bad,
                                                             "status: in_progress\nlane: required\nfiles: src/*.py\nevidence_command: " + self.bad)
        (self.r.path / "GOAL.md").write_text(text)
        self.assertEqual(cg.evaluate(self.r.path, TODAY, force_mode="block", leaves=True).findings, [])
        tree_goal(self.r, self.ok, "no-such-binary-xyz")
        res = cg.evaluate(self.r.path, TODAY, force_mode="block", leaves=True)
        self.assertEqual(res.findings, [])
        self.assertIn("leaf_unknown", res.notes)

    def test_parent_marked_verified_needs_no_evidence(self):
        tree_goal(self.r, self.ok, self.ok, parent_status="verified")
        self.assertEqual(cg.evaluate(self.r.path, TODAY, force_mode="block").findings, [])


class LiveViewTest(unittest.TestCase):
    def run_script(self, name, repo, stdin, *flags):
        return subprocess.run([sys.executable, str(SCRIPTS / name), *flags], input=json.dumps(stdin),
                              capture_output=True, text=True)

    def test_log_prompt_appends_numbered_lines_and_needs_goal(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        res = self.run_script("log_prompt.py", r.path, {"cwd": str(r.path), "prompt": "first"})
        self.assertEqual((res.returncode, (r.path / ".goal-contract").exists()), (0, False))
        r.write_goal(STEP_OK)
        self.run_script("log_prompt.py", r.path, {"cwd": str(r.path), "prompt": "first\nline two"})
        self.run_script("log_prompt.py", r.path, {"cwd": str(r.path), "prompt": "second"})
        lines = (r.path / ".goal-contract" / "human_log.md").read_text().splitlines()
        self.assertEqual([x.split(" | ")[0] for x in lines], ["1", "2"])
        self.assertTrue(lines[0].endswith("| first line two"))

    def test_arm_l_logs_outside_repo_without_goal_and_prints_log_only(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        with tempfile.TemporaryDirectory() as logdir:
            env = dict(os.environ, GC_LOG_DIR=logdir)
            run = lambda name, stdin, *f: subprocess.run([sys.executable, str(SCRIPTS / name), *f],  # noqa: E731
                                                         input=json.dumps(stdin), capture_output=True, text=True, env=env)
            run("log_prompt.py", {"cwd": str(r.path), "prompt": "skipped, no goal"})
            self.assertFalse((Path(logdir) / "human_log.md").exists())
            run("log_prompt.py", {"cwd": str(r.path), "prompt": "owner decision one"}, "--no-goal-ok")
            run("log_prompt.py", {"cwd": str(r.path), "prompt": "owner decision two"}, "--no-goal-ok")
            self.assertFalse((r.path / ".goal-contract").exists())
            out = run("inject_goal.py", {"cwd": str(r.path)}, "--log-only").stdout
            self.assertTrue(out.startswith("Human prompts so far, newest last."))
            self.assertLess(out.index("decision one"), out.index("decision two"))
            self.assertNotIn("goal-contract: mode", out)
        with tempfile.TemporaryDirectory() as empty:
            out = subprocess.run([sys.executable, str(SCRIPTS / "inject_goal.py"), "--log-only"], input=json.dumps({"cwd": str(r.path)}),
                                 capture_output=True, text=True, env=dict(os.environ, GC_LOG_DIR=empty))
            self.assertEqual((out.returncode, out.stdout), (0, ""))

    def test_inject_leaves_prints_live_view_and_log_after_goal(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        tree_goal(r, f"{sys.executable} -c pass", f"{sys.executable} -c 'import sys; sys.exit(3)'")
        self.run_script("log_prompt.py", r.path, {"cwd": str(r.path), "prompt": "change rule two"})
        out = self.run_script("inject_goal.py", r.path, {"cwd": str(r.path)}, "--leaves", "--rollup").stdout
        self.assertIn("Live check, run just now", out)
        self.assertIn("S1 Whole [NOT verified", out)
        self.assertIn("change rule two", out)
        self.assertLess(out.index("# Goal"), out.index("Live check"))
        flat = self.run_script("inject_goal.py", r.path, {"cwd": str(r.path)}, "--leaves").stdout
        self.assertNotIn("S1 Whole [", flat)
        plain = self.run_script("inject_goal.py", r.path, {"cwd": str(r.path)}).stdout
        self.assertNotIn("Live check", plain)

    def test_stop_hook_with_leaves_blocks_then_caps(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        tree_goal(r, f"{sys.executable} -c pass", f"{sys.executable} -c 'import sys; sys.exit(3)'")
        codes = [self.run_script("check_goal.py", r.path, {"cwd": str(r.path)}, "--force-mode", "block", "--leaves").returncode
                 for _ in range(3)]
        self.assertEqual(codes, [2, 2, 0])


if __name__ == "__main__":
    unittest.main()
