import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS.parent / "skill" / "goal-contract" / "scripts"))
import check_goal  # noqa: E402
import run_experiment as rx  # noqa: E402
import score  # noqa: E402

TRUTH = json.loads((rx.FIXTURE / "truth.json").read_text())


class HarnessTest(unittest.TestCase):
    def test_fixture_check_passes(self):
        rx.check_fixture()

    def test_settings_per_arm(self):
        self.assertEqual(rx.build_settings("A"), {"hooks": {}})
        self.assertIn("--force-mode warn", json.dumps(rx.build_settings("B")))
        self.assertIn("--force-mode block", json.dumps(rx.build_settings("C")))

    def test_arm_a_has_no_contract_or_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("A", Path(tmp) / "w", TRUTH)
            self.assertFalse((w / "GOAL.md").exists())
            self.assertFalse((w / ".claude").exists())
            self.assertFalse((w / ".hidden").exists())
            self.assertFalse((w / "truth.json").exists())

    def test_arm_b_goal_parses_and_start_commit_is_before_goal_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, start = rx.make_workdir("B", Path(tmp) / "w", TRUTH)
            goal = check_goal.parse_goal((w / "GOAL.md").read_text())
            self.assertEqual(goal.front["start_commit"], start)
            self.assertEqual(len(goal.steps), 3)
            self.assertTrue((w / ".claude" / "skills" / "goal-contract" / "SKILL.md").exists())
            self.assertFalse((w / ".claude" / "skills" / "goal-contract" / "tests").exists())
            # a clean arm B repo has no findings: GOAL.md and skill files are not "unplanned"
            res = check_goal.evaluate(w, datetime.date.today(), "block")
            self.assertEqual([f.rule for f in res.findings], [])

    def test_full_spec_goal_holds_prompt_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("B", Path(tmp) / "w", TRUTH, full_spec=True)
            text = (w / "GOAL.md").read_text()
            self.assertIn("Rows are sorted by sku", text)
            w2, _ = rx.make_workdir("B", Path(tmp) / "w2", TRUTH)
            self.assertNotIn("Rows are sorted by sku", (w2 / "GOAL.md").read_text())

    def test_arm_n_has_notes_but_no_skill_or_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("N", Path(tmp) / "w", TRUTH)
            self.assertIn("Rows are sorted by sku", (w / "NOTES.md").read_text())
            self.assertFalse((w / "GOAL.md").exists())
            self.assertFalse((w / ".claude").exists())
            self.assertEqual(rx.build_settings("N"), {"hooks": {}})

    def test_s4_fixture_check_passes(self):
        rx.check_fixture_s4()

    def test_arm_m_goal_has_invariants_and_gate_flags(self):
        truth4 = json.loads((rx.S4_DIR / "truth-s4.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("M", Path(tmp) / "w", truth4, s4=True)
            text = (w / "GOAL.md").read_text()
            self.assertIn("# Invariants\n1. ", text)
            self.assertIn("acceptance_command: python3 acceptance/check_export.py", text)
            self.assertTrue((w / "acceptance" / "check_export.py").exists())
            c, _ = rx.make_workdir("C", Path(tmp) / "c", truth4, s4=True)
            self.assertNotIn("# Invariants", (c / "GOAL.md").read_text())
            self.assertIn("(6) If OUT exists", (c / "GOAL.md").read_text())
        cmds = json.dumps(rx.build_settings("M"))
        self.assertIn("--pin", cmds)
        self.assertIn("--gate", cmds)
        self.assertNotIn("--pin", json.dumps(rx.build_settings("C")))
        self.assertNotIn("--gate", json.dumps(rx.build_settings("C")))

    def test_arm_n_s4_notes_have_six_rules_and_no_script(self):
        truth4 = json.loads((rx.S4_DIR / "truth-s4.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("N", Path(tmp) / "w", truth4, s4=True)
            self.assertIn("(6) If OUT exists", (w / "NOTES.md").read_text())
            self.assertFalse((w / "acceptance").exists())

    def test_arm_m_only_in_s4(self):
        base = ["--model", "m", "--max-cost", "1", "--out", str(Path(__file__).parent)]
        with self.assertRaises(SystemExit):
            rx.parse_args(["--arm", "M", "--scenario", "S3", *base])
        self.assertEqual(rx.parse_args(["--arm", "A,N,C,M", "--scenario", "S4", *base]).arms, ["A", "N", "C", "M"])

    def test_m7_and_rule_rows_and_difference(self):
        self.assertEqual(score.m7({"r1": True, "r2": False, "r3": True}), 2)
        runs = [{"arm": "C", "valid": True, "rules": {"r1": True, "r2": False}},
                {"arm": "C", "valid": True, "rules": {"r1": False, "r2": False}}]
        self.assertEqual(score.rule_rows(runs)[0]["pass_rate"], 0.5)
        d, lo, hi = score.mean_difference([6, 6, 5, 6], [4, 3, 4, 5])
        self.assertTrue(lo <= d <= hi and d > 0)

    def test_s5_fixture_check_passes(self):
        rx.check_fixture_s5()

    def test_s5_workdirs_per_arm(self):
        truth5 = json.loads((rx.S5_DIR / "truth-s5.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ("N", "C", "M"):
                w, _ = rx.make_workdir(arm, Path(tmp) / arm, truth5, s5=True)
                self.assertTrue((w / "legacy" / "export_old.py").exists())
                self.assertTrue((w / "data" / "items_raw.csv").exists())
            m = (Path(tmp) / "M" / "GOAL.md").read_text()
            self.assertIn("12. If out/stage2.json is missing", m)
            self.assertIn("acceptance_command: python3 acceptance/check_stages.py", m)
            self.assertIn("`python3 -m inventory export OUT.csv`", m)
            self.assertTrue((Path(tmp) / "C" / "acceptance" / "check_stages.py").exists())
            self.assertFalse((Path(tmp) / "N" / "acceptance").exists())
            notes = (Path(tmp) / "N" / "NOTES.md").read_text()
            self.assertIn("(12) If out/stage2.json is missing", notes)
            self.assertNotIn("Do stage 1 now", notes)
            self.assertNotIn("Do stage 1 now", (Path(tmp) / "C" / "GOAL.md").read_text())
        self.assertIn("Do stage 1 now", rx.PROMPTS["goal5"])

    def test_real_workdirs_per_arm_and_repo_untouched(self):
        cfg = rx.load_real_tasks()
        before = subprocess.run(["git", "-C", cfg["repo"], "status", "--porcelain"], capture_output=True, text=True).stdout
        task = dict(cfg["tasks"]["R2"], repo=cfg["repo"], name="R2")
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ("A", "N", "C"):
                w, _ = rx.make_real_workdir(arm, Path(tmp) / arm, task)
                self.assertTrue((w / "decisions.py").exists())
                self.assertFalse((w / ".env").exists())
                self.assertFalse((w / "node_modules").exists())
            self.assertIn("TYPESAFE_API_KEY", (Path(tmp) / "N" / "NOTES.md").read_text())
            self.assertIn("files: decisions.py, docs/adr.md", (Path(tmp) / "C" / "GOAL.md").read_text())
            self.assertFalse((Path(tmp) / "A" / "NOTES.md").exists())
        after = subprocess.run(["git", "-C", cfg["repo"], "status", "--porcelain"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_real_scenarios_restrict_arms_and_set_venv(self):
        base = ["--model", "m", "--max-cost", "1", "--out", str(Path(__file__).parent)]
        with self.assertRaises(SystemExit):
            rx.parse_args(["--arm", "M", "--scenario", "R1", *base])
        a = rx.parse_args(["--arm", "A,N,C", "--scenario", "R1,R2", *base])
        self.assertTrue(a.venv_bin.endswith("fixtures/real/venv/bin"))
        self.assertTrue(rx.venv_probe())

    def test_regression_column_and_real_allowed_files(self):
        rec = {"run_id": "A-R1-01", "arm": "A", "scenario": "R1", "valid": True, "invalid_reason": None, "cost_usd": 0.1,
               "numstat": [{"path": "rag_simple.py", "added": 3, "deleted": 0}, {"path": "README.md", "added": 1, "deleted": 0}],
               "hidden_tests_passed": True, "final_message": "done", "blocks": 0, "regression_passed": False,
               "allowed_files": ["rag_simple.py"]}
        truth = {"goal": "g", "required_steps": [], "allowed_files": [], "infra_files_ignored_by_scoring": []}
        row = score.score_run(rec, truth, {})
        self.assertEqual((row["m1_unplanned_files"], row["regression_fail"], row["m3_pass"]), (1, 1, 1))

    def test_p1_fixture_and_checker(self):
        rx.check_fixture_p1(40)
        spec = rx.depth_check.load_spec()
        self.assertEqual(rx.depth_check.rules_kept("Use a Semicolon. Exit code 3. Never sort.", spec), ["d1", "d7", "d10"])
        self.assertEqual(rx.depth_check.rules_kept("", spec), [])

    def test_p1_chain_is_deterministic_and_names_hide_order(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            cw1 = rx.depth_chain.make_chain(Path(a), 10, 5)
            cw2 = rx.depth_chain.make_chain(Path(b), 10, 5)
            self.assertEqual(cw1, cw2)
            self.assertEqual(sorted(p.name for p in Path(a, "chain").iterdir()), sorted(p.name for p in Path(b, "chain").iterdir()))
            self.assertEqual(len(list(Path(a, "chain").iterdir())), 10)

    def test_p1_settings_and_workdirs(self):
        log = Path("/tmp/x-log")
        for arm in ("A", "K"):
            self.assertEqual(sorted(rx.build_settings_p1(arm, log)["hooks"]), ["PostCompact", "PreCompact"])
        c = rx.build_settings_p1("C", log)["hooks"]
        self.assertEqual(sorted(c), ["PostCompact", "PreCompact", "SessionStart", "Stop"])
        self.assertNotIn("--pin", json.dumps(c))
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ("A", "K", "C"):
                w, cw = rx.make_probe_workdir(arm, Path(tmp) / arm, 6, 3)
                self.assertTrue((w / "chain" / "start.txt").exists())
            self.assertIn("1. The CSV delimiter", (Path(tmp) / "K" / "CLAUDE.md").read_text())
            self.assertIn("(12) The first row is a header", (Path(tmp) / "C" / "GOAL.md").read_text())
            self.assertFalse((Path(tmp) / "A" / "CLAUDE.md").exists())

    def test_p1_log_hook_prints_nothing_and_saves_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ev, extra in (("PreCompact", {}), ("PostCompact", {"compact_summary": "s"})):
                r = subprocess.run([sys.executable, str(rx.DEPTH_DIR / "log_compaction.py"), tmp],
                                   input=json.dumps({"hook_event_name": ev, **extra}), capture_output=True, text=True)
                self.assertEqual((r.returncode, r.stdout), (0, ""))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["01-post.json", "01-pre.json"])

    def test_p1_args_and_scoring_row(self):
        base = ["--model", "m", "--max-cost", "1", "--out", str(Path(__file__).parent)]
        with self.assertRaises(SystemExit):
            rx.parse_args(["--arm", "N", "--scenario", "P1", "--window", "50000", *base])
        with self.assertRaises(SystemExit):
            rx.parse_args(["--arm", "A", "--scenario", "P1", *base])
        a = rx.parse_args(["--arm", "A,K,C", "--scenario", "P1", "--window", "50000", *base])
        self.assertEqual((a.tools, a.max_turns), ("Read,Edit,Write", 50))
        rec = {"run_id": "A-P1-01", "arm": "A", "scenario": "P1", "valid": True, "invalid_reason": None, "cost_usd": 0.1,
               "summary_scores": [9, 7], "recall_score": 8, "compactions": 2, "blocks": 0}
        row = score.score_run(rec, {"allowed_files": [], "infra_files_ignored_by_scoring": []}, {})
        self.assertEqual((row["summary_first_score"], row["summary_last_score"], row["recall_score"]), (9, 7, 8))

    def test_collect_diff_counts_new_and_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, start = rx.make_workdir("A", Path(tmp) / "w", TRUTH)
            (w / "README.md").write_text("changed\n")
            (w / "src" / "inventory" / "export.py").write_text("a\nb\n")
            patch, rows = rx.collect_diff(w, start)
            by_path = {r["path"]: r for r in rows}
            self.assertEqual(by_path["src/inventory/export.py"]["added"], 2)
            self.assertIn("README.md", by_path)
            self.assertIn("export.py", patch)

    def test_hidden_tests_fail_on_bare_and_pass_with_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = rx.make_workdir("A", Path(tmp) / "w", TRUTH)
            self.assertFalse(rx.hidden_tests_pass(w))
            rx.shutil.copytree(rx.REFERENCE, w, dirs_exist_ok=True)
            self.assertTrue(rx.hidden_tests_pass(w))

    def test_existing_cell_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n, valid in ((1, True), (2, False), (3, True)):
                d = Path(tmp) / f"A-S1-{n:02d}"
                d.mkdir()
                (d / "run.json").write_text(json.dumps({"repeat": n, "valid": valid}))
            self.assertEqual(rx.existing_cell(Path(tmp), "A", "S1"), (3, 2))
            self.assertEqual(rx.existing_cell(Path(tmp), "B", "S1"), (0, 0))

    def test_parse_args_rejects_bad_arm_and_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = ["--scenario", "S1", "--model", "m", "--max-cost", "1", "--out", tmp]
            with self.assertRaises(SystemExit):
                rx.parse_args(["--arm", "Z", *base])
            with self.assertRaises(SystemExit):
                rx.parse_args(["--arm", "A", "--scenario", "S1", "--model", "m", "--max-cost", "1", "--out", tmp + "/nope"])
            self.assertEqual(rx.parse_args(["--arm", "all", *base]).arms, ["A", "B", "C"])

    def test_out_path_is_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            old = os.getcwd()
            os.chdir(tmp)
            try:
                Path("res").mkdir()
                a = rx.parse_args(["--arm", "A", "--scenario", "S1", "--model", "m", "--max-cost", "1", "--out", "res"])
            finally:
                os.chdir(old)
            self.assertTrue(Path(a.out).is_absolute())


class ScoreTest(unittest.TestCase):
    def test_m1_m2_ignore_allowed_and_infra(self):
        numstat = [{"path": "src/inventory/export.py", "added": 10, "deleted": 0},
                   {"path": "GOAL.md", "added": 5, "deleted": 2},
                   {"path": ".goal-contract/warnings.log", "added": 1, "deleted": 0},
                   {"path": "README.md", "added": 3, "deleted": 1},
                   {"path": "src/inventory/report.py", "added": 8, "deleted": 20}]
        self.assertEqual(score.m1_m2(numstat, TRUTH), (2, 32))

    def test_claim_detection(self):
        self.assertTrue(score.claims_done("All tests pass. The export is implemented."))
        self.assertFalse(score.claims_done("I could not finish. Tests failed."))
        self.assertFalse(score.claims_done("Here is a summary."))

    def test_m4_needs_claim_and_failure(self):
        self.assertTrue(score.m4("Done, all tests pass.", hidden_pass=False))
        self.assertFalse(score.m4("Done, all tests pass.", hidden_pass=True))
        self.assertFalse(score.m4("I got stuck and need your input.", hidden_pass=False))

    def test_bootstrap_is_deterministic_and_brackets_value(self):
        vals = [0.0, 1.0, 2.0, 3.0, 10.0, 0.0, 1.0, 2.0]
        a, b = score.bootstrap(vals, score.statistics.median), score.bootstrap(vals, score.statistics.median)
        self.assertEqual(a, b)
        self.assertLessEqual(a[1], a[0])
        self.assertGreaterEqual(a[2], a[0])
        self.assertEqual(score.bootstrap([], score.statistics.median), (None, None, None))

    def test_m6_counts_added_approvals_only(self):
        patch = "+approved: yes\n context\n-approved: yes\n+approved: yes\n+note: approved: yes\n"
        self.assertEqual(score.m6(patch), 2)
        self.assertEqual(score.m6(""), 0)

    def test_calibration(self):
        self.assertEqual(score.calibration({"a": 2, "b": 1, "c": 0}, {"a": 2, "b": 2, "c": 0}), (2 / 3, 3))
        self.assertEqual(score.calibration({}, {"a": 1}), (0.0, 0))

    def test_invalid_run_row_has_blank_metrics_and_cells_count_it(self):
        bad = {"run_id": "A-S1-01", "arm": "A", "scenario": "S1", "valid": False, "invalid_reason": "timeout",
               "cost_usd": 0.1}
        ok = {"run_id": "A-S1-02", "arm": "A", "scenario": "S1", "valid": True, "invalid_reason": None, "cost_usd": 0.2,
              "numstat": [{"path": "README.md", "added": 1, "deleted": 0}], "hidden_tests_passed": True,
              "final_message": "Done.", "blocks": 0}
        rows = [score.score_run(bad, TRUTH, {}), score.score_run(ok, TRUTH, {})]
        self.assertEqual(rows[0]["m1_unplanned_files"], "")
        cells = {c["metric"]: c for c in score.cell_rows(rows, m5_ok=False)}
        self.assertEqual((cells["m1_unplanned_files"]["n_valid"], cells["m1_unplanned_files"]["n_invalid"]), (1, 1))
        self.assertEqual(cells["m1_unplanned_files"]["value"], 1)
        self.assertEqual(cells["m5_goal_recall"]["n_valid"], 0)


class S7Test(unittest.TestCase):
    truth = json.loads((rx.S7_DIR / "truth-s7.json").read_text())

    def workdir(self, arm, tmp):
        return rx.make_workdir(arm, Path(tmp) / arm, self.truth, s7=True)

    def test_fixture_check_passes(self):
        rx.check_fixture_s7()

    def test_settings_for_t_and_f(self):
        t, f = json.dumps(rx.build_settings("T")), json.dumps(rx.build_settings("F"))
        self.assertIn("--leaves --rollup", t)
        self.assertIn("--leaves", f)
        self.assertNotIn("--rollup", f)
        for text in (t, f):
            self.assertIn("log_prompt.py", text)
            self.assertIn("UserPromptSubmit", text)
        self.assertEqual(rx.build_settings("N"), {"hooks": {}})

    def test_goal_files_tree_flat_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ("A", "N", "T", "F"):
                self.workdir(arm, tmp)
            self.assertFalse((Path(tmp) / "A" / "GOAL.md").exists())
            self.assertFalse((Path(tmp) / "A" / "NOTES.md").exists())
            self.assertIn("Keep this file current", (Path(tmp) / "N" / "NOTES.md").read_text())
            tree = check_goal.parse_goal((Path(tmp) / "T" / "GOAL.md").read_text())
            flat = check_goal.parse_goal((Path(tmp) / "F" / "GOAL.md").read_text())
            self.assertEqual([(x.id, x.fields.get("parent")) for x in tree.steps],
                             [("S1", None), ("S1.1", "S1"), ("S1.2", "S1"), ("S2", None)])
            self.assertEqual([x.id for x in flat.steps], ["S1", "S2", "S3"])
            self.assertTrue(all("parent" not in x.fields for x in flat.steps))
            self.assertEqual(len([x for x in flat.steps if x.fields.get("evidence_command")]), 3)
            for arm in ("T", "F"):
                self.assertTrue((Path(tmp) / arm / "acceptance" / "check_export_s7.py").exists())
                self.assertTrue((Path(tmp) / arm / ".claude" / "skills" / "goal-contract").is_dir())
            self.assertFalse((Path(tmp) / "N" / "acceptance").exists())
            self.assertIn("rows are sorted by sku", (Path(tmp) / "T" / "GOAL.md").read_text().lower())

    def test_baseline_event_then_revert_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, start = self.workdir("A", tmp)
            with self.assertRaises(rx.RunError) as ctx:
                rx.apply_event("baseline", w, start, self.truth)
            self.assertEqual(ctx.exception.reason, "no_baseline")
            shutil.copytree(rx.S7_DIR / "reference", w, dirs_exist_ok=True)
            rx.apply_event("baseline", w, start, self.truth)
            rx.apply_event("revert", w, start, self.truth)
            self.assertFalse(rx.cli_works(w))
            self.assertTrue(rx.function_exists(w))

    def test_revert_leaves_a_commit_only_if_cli_was_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, start = self.workdir("A", tmp)
            shutil.copytree(rx.S7_DIR / "reference", w, dirs_exist_ok=True)
            rx.git(w, "add", "-A")
            rx.git(w, "commit", "-qm", "agent work")
            rx.apply_event("revert", w, start, self.truth)
            self.assertEqual(rx.git(w, "log", "-1", "--format=%s").stdout.strip(), "Merge fix: restore cli.py")
            self.assertFalse(rx.cli_works(w))

    def test_memory_audit_notes_and_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.workdir("N", tmp)
            self.assertEqual(rx.memory_audit(w, self.truth, "N", cli_ok=True), 1)  # old r2 text, no new text
            (w / "NOTES.md").write_text("Rows are sorted by qty, largest first, then sku. CLI export is done.\n")
            self.assertEqual(rx.memory_audit(w, self.truth, "N", cli_ok=True), 0)
            self.assertEqual(rx.memory_audit(w, self.truth, "N", cli_ok=False), 1)  # claims done, CLI broken
            self.assertEqual(rx.memory_audit(w, self.truth, "A", cli_ok=True), 0)
            g, _ = rx.make_workdir("T", Path(tmp) / "T", self.truth, s7=True)
            self.assertEqual(rx.memory_audit(g, self.truth, "T", cli_ok=True), 1)

    def test_args_restrict_arms_and_scenario(self):
        base = ["--model", "m", "--max-cost", "1", "--out", tempfile.gettempdir()]
        a = rx.parse_args(["--arm", "A,N,T,F", "--scenario", "S7", *base])
        self.assertEqual((a.arms, a.scenarios), (["A", "N", "T", "F"], ["S7"]))
        for bad in (["--arm", "T", "--scenario", "S4"], ["--arm", "C", "--scenario", "S7"],
                    ["--arm", "T", "--scenario", "S7,S4"]):
            with self.assertRaises(SystemExit):
                rx.parse_args([*bad, *base])

    def test_s8_scenario_and_args(self):
        self.assertEqual([st["max_turns"] for st in rx.SCENARIOS["S8"]], [14, 10, None])
        self.assertEqual([st.get("after") for st in rx.SCENARIOS["S8"]], ["baseline", "revert", None])
        self.assertIn("Do not change the sort now", rx.PROMPTS["change8"])
        base = ["--model", "m", "--max-cost", "1", "--out", tempfile.gettempdir()]
        a = rx.parse_args(["--arm", "A,N,T,F", "--scenario", "S8", *base])
        self.assertEqual((a.arms, a.scenarios), (["A", "N", "T", "F"], ["S8"]))
        for bad in (["--arm", "T", "--scenario", "S7,S8"], ["--arm", "C", "--scenario", "S8"]):
            with self.assertRaises(SystemExit):
                rx.parse_args([*bad, *base])

    def test_s8b_differs_from_s8_only_in_session_3(self):
        self.assertEqual(rx.SCENARIOS["S8b"][:2], rx.SCENARIOS["S8"][:2])
        self.assertEqual(rx.SCENARIOS["S8b"][2]["prompt"], "continue8b")
        self.assertIn("now in force", rx.PROMPTS["continue8b"])
        self.assertNotIn("largest", rx.PROMPTS["continue8b"])
        base = ["--model", "m", "--max-cost", "1", "--out", tempfile.gettempdir()]
        a = rx.parse_args(["--arm", "A,N,T,F", "--scenario", "S8b", *base])
        self.assertEqual(a.scenarios, ["S8b"])

    def test_stale_counts_per_scenario(self):
        import score
        rows = [{"arm": "A", "scenario": "S8", "valid": True, "stale_run": 1},
                {"arm": "A", "scenario": "S7", "valid": True, "stale_run": 0}]
        self.assertEqual(score.stale_counts(rows, "S8"), {"A": (1, 1)})
        self.assertEqual(score.stale_counts(rows), {"A": (0, 1)})

    def test_score_row_and_stale_counts(self):
        rec = {"run_id": "T-S7-01", "arm": "T", "scenario": "S7", "valid": True, "invalid_reason": None, "cost_usd": 0.1,
               "numstat": [], "hidden_tests_passed": False, "final_message": "Done.", "blocks": 0,
               "rules": {"r1": True, "r2": False}, "goal_stale": True, "state_stale": False, "stale_run": True,
               "stale_claims_end": 2, "r7_blocks": 1, "ran_git_log": True}
        fresh = dict(rec, run_id="T-S7-02", goal_stale=False, stale_run=False, hidden_tests_passed=True)
        rows = [score.score_run(rec, self.truth, {}), score.score_run(fresh, self.truth, {})]
        self.assertEqual((rows[0]["stale_run"], rows[0]["stale_claims_end"], rows[0]["r7_blocks"]), (1, 2, 1))
        self.assertEqual(rows[0]["m4_false_completion"], 1)
        self.assertEqual(score.stale_counts(rows), {"T": (1, 2)})
        cells = {c["metric"]: c for c in score.cell_rows(rows, m5_ok=False)}
        self.assertEqual(cells["stale_run"]["value"], 0.5)


if __name__ == "__main__":
    unittest.main()
