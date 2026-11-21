import argparse
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS.parent / "skill" / "goal-contract" / "scripts"))
import check_goal  # noqa: E402
import run_s9 as s9  # noqa: E402

TRUTH, QUIZ = s9.load_truth()


def args(out: str, **kw) -> argparse.Namespace:
    base = dict(model="m", claude_version="x", out=out, max_turns=30, run_budget=1.0, arms=["A", "N"], levels=[1, 3],
                repeats=2, repeats_a=1, order_seed=9, jobs=2, max_cost=5.0)
    return argparse.Namespace(**{**base, **kw})


class FixtureTest(unittest.TestCase):
    def test_fixture_check_passes(self):
        s9.check_fixture_s9()

    def test_levels_decisions_and_quiz_agree(self):
        for k, ids in TRUTH["levels"].items():
            self.assertEqual(len(ids), int(k))
            self.assertEqual([q["rule"] for q in QUIZ[k]], list(TRUTH["final_rules"][k]))


class WorkdirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_arm_files(self):
        for arm in s9.ARMS:
            w, _ = s9.make_workdir_s9(arm, self.root / arm, self.root / f"log{arm}")
            self.assertEqual((w / "NOTES.md").exists(), arm == "N")
            self.assertEqual((w / "GOAL.md").exists(), arm == "T")
            self.assertEqual((self.root / f"log{arm}" / s9.LOG_NAME).exists(), arm in ("L", "T"))
            self.assertFalse(list(w.rglob(s9.LOG_NAME)), "the log must live outside the workdir")
            self.assertTrue((w / "src" / "inventory" / "export.py").exists())

    def test_tree_goal_parses_and_leaves_pass_at_checkpoint(self):
        w, start = s9.make_workdir_s9("T", self.root / "t", self.root / "log")
        goal = check_goal.parse_goal((w / "GOAL.md").read_text())
        checks = check_goal.run_leaf_checks(w, goal)
        self.assertTrue(checks and all(c["state"] == "ok" for c in checks.values()), checks)
        self.assertEqual(check_goal.stale_findings(goal, checks)[0], [])

    def test_settings(self):
        hooks = s9.build_settings_s9("L")["hooks"]
        self.assertIn("--log-only", json.dumps(hooks["SessionStart"]))
        self.assertIn("--no-goal-ok", json.dumps(hooks["UserPromptSubmit"]))
        self.assertNotIn("Stop", hooks)
        self.assertIn("--rollup", json.dumps(s9.build_settings_s9("T")))
        self.assertEqual(s9.build_settings_s9("A"), {"hooks": {}})


class PromptAndScoreTest(unittest.TestCase):
    def test_session_prompt_holds_decision_and_task_only(self):
        p = s9.session_prompt(TRUTH, 3)
        self.assertIn("Owner decision 3:", p)
        self.assertIn(TRUTH["tasks"][2]["text"], p)
        self.assertNotIn(TRUTH["decisions"][0]["text"], p)

    def test_quiz_prompt_and_parse(self):
        p = s9.quiz_prompt(QUIZ, 6)
        self.assertIn("4. ", p)
        right = "\n".join(f"{n}. {q['answer']}" for n, q in enumerate(QUIZ["6"], 1))
        self.assertTrue(all(v["right"] for v in s9.parse_quiz(right, QUIZ["6"]).values()))
        self.assertTrue(all(v["answer"] is None for v in s9.parse_quiz("A\nB\nC\nA\nB", QUIZ["6"]).values()))
        short = s9.parse_quiz("A", QUIZ["3"])
        self.assertEqual([v["answer"] for v in short.values()], ["A", None])
        self.assertEqual(s9.parse_quiz("", QUIZ["1"])["r3"]["right"], False)

    def test_failure_type_order(self):
        spec = TRUTH["final_rules"]["3"]["r3"]
        self.assertEqual(s9.failure_type({"test_r3_d3": True, "test_r3_d1": True}, spec), "new")
        self.assertEqual(s9.failure_type({"test_r3_d1": True}, spec), "stale")
        self.assertEqual(s9.failure_type({"test_r3_base": True}, spec), "base")
        self.assertEqual(s9.failure_type({}, spec), "other")

    def test_scores_on_checkpoint_find_forgetting_and_knows_but_violates(self):
        with tempfile.TemporaryDirectory() as t:
            res = s9.all_hidden(s9.checkpoint_dir(Path(t) / "c"))
        quiz = {"r3": {"answer": "B", "right": True}, "r4": {"answer": "C", "right": False}}
        sc = s9.s9_scores(res, TRUTH, 3, quiz, [True, True, False])
        self.assertEqual(sc["decision_score"], 0)
        self.assertEqual(sc["failure_types"], {"r3": "base", "r4": "base"})
        self.assertEqual(sc["knows_but_violates"], ["r3"])
        self.assertEqual(sc["spillover"], [])
        self.assertEqual(sc["unrelated_losses"], ["T1", "T2"])  # passed after their sessions, fail now
        self.assertTrue(sc["untouched_ok"])
        self.assertFalse(sc["all_correct"])

    def test_leaks_only_count_announced_decisions(self):
        res = {"test_r3_d1": True, "test_r2_d4": True}
        self.assertEqual(s9.leaked(res, TRUTH, 1), ["D1"])
        self.assertEqual(s9.leaked(res, TRUTH, 4), ["D1", "D4"])


class BatchTest(unittest.TestCase):
    def test_run_list_counts_targets_and_is_seeded(self):
        with tempfile.TemporaryDirectory() as t:
            a = args(t)
            items = s9.run_list(a, Path(t))
            self.assertEqual(sorted(items), sorted([("A", 1), ("A", 3)] + [("N", 1)] * 2 + [("N", 3)] * 2))
            self.assertEqual(items, s9.run_list(a, Path(t)))
            d = Path(t) / "N-S9K1-01"
            d.mkdir()
            (d / "run.json").write_text(json.dumps({"repeat": 1, "valid": True}))
            self.assertEqual(s9.run_list(a, Path(t)).count(("N", 1)), 1)

    def test_parse_args_pilot(self):
        with tempfile.TemporaryDirectory() as t:
            a = s9.parse_args(["--model", "m", "--max-cost", "1", "--out", t, "--pilot"])
            self.assertEqual((a.levels, a.repeats, a.repeats_a), ([6], 1, 1))
            self.assertTrue(a.out.endswith("pilot"))
            with self.assertRaises(SystemExit):
                s9.parse_args(["--model", "m", "--max-cost", "1", "--out", t, "--arm", "B"])


class FakeAgentTest(unittest.TestCase):
    """A whole trial with a fake claude session. The fake applies the K=3 reference at release day."""

    def fake_session(self, workdir, prompt, a, settings, resume=None, max_turns=None, env_extra=None):
        self.calls.append((prompt, resume, env_extra))
        if env_extra:  # stand in for the prompt hook
            with open(Path(env_extra["GC_LOG_DIR"]) / s9.LOG_NAME, "a") as f:
                f.write(f"{len(self.calls)} | t | {prompt[:20]}\n")
        if prompt == TRUTH["release_prompt"]:
            shutil.copytree(s9.S9_DIR / "reference" / "k3", workdir, dirs_exist_ok=True)
        result = "\n".join(q["answer"] for q in QUIZ["3"]) if prompt.startswith(QUIZ["prompt"]) else "done"
        return {"session_id": f"s{len(self.calls)}", "total_cost_usd": 0.01, "num_turns": 2, "result": result}

    def test_trial_scores_full_marks_and_saves_snapshots(self):
        self.calls = []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(s9.rx, "claude_session", self.fake_session):
            rec = s9.run_one_s9("L", 3, 1, args(t), TRUTH, QUIZ)
            out = Path(t) / "L-S9K3-01"
            self.assertTrue(rec["valid"], rec)
            self.assertEqual((rec["decision_score"], rec["all_correct"], rec["task_score"]), (1.0, True, 1.0))
            self.assertEqual(rec["knows_but_violates"], [])
            self.assertEqual(rec["leaks"], [[], [], []])
            self.assertEqual(rec["task_after_session"], [False, False, False])
            self.assertEqual(rec["snapshots"], ["snapshots/final", "snapshots/s1", "snapshots/s2", "snapshots/s3"])
            self.assertTrue((out / "snapshots" / "s2" / s9.LOG_NAME).exists())
            self.assertEqual(len(self.calls), 5)
            self.assertEqual(self.calls[-1][1], "s4")  # the quiz resumes the release session
            self.assertAlmostEqual(rec["cost_usd"], 0.05)
            self.assertEqual(json.loads((out / "run.json").read_text())["level"], 3)


if __name__ == "__main__":
    unittest.main()
