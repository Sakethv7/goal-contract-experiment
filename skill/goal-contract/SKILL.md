---
name: goal-contract
description: Keep an agent on a written goal. Use in any repo that has a GOAL.md at its root, or when the user asks to set up a goal contract. The agent reads GOAL.md first, tracks each step with status and evidence, and labels new work as added.
---

# Goal contract

A repo opts in by having a `GOAL.md` at its root. If the file is missing, do nothing here. If the user asks to set one up, copy `templates/GOAL.md`, fill it with the user, and set `start_commit` to the current `git rev-parse --short HEAD`.

## Rules

1. Read `GOAL.md` before you act. The goal and the acceptance checks are the contract. Do not change them without the human.
2. Work one step at a time. Set `status: in_progress` when you start a step.
3. Keep the `files` field of each step true. List the files that step may touch.
4. When you think a step is done, set `status: reported_done`.
5. Set `status: verified` only after you run a check and record it. Run the check with the helper: `python3 <skill folder>/scripts/run_check.py COMMAND [ARGS...]`. In a project install the helper is at `.claude/skills/goal-contract/scripts/run_check.py`. It prints the output, the exit code, and an `evidence:` line. Copy that line into the step. Do not chain commands with `;` or `&&` to read the exit code. Example: `evidence: `python3 -m unittest` exit 0, "OK"`.
6. If a later edit touches a verified step's files, set the step back to `in_progress`.
7. If you find work that no step covers, add a new step with `lane: added` and `status: todo`. Do not start it. Tell the human and wait. Only the human sets `approved: yes`.
8. If you need a human decision, set `status: blocked` and write the reason in `note`.
9. Before you stop, check that every done step has evidence and that every changed file belongs to a step.

## Why

A stop hook reads `GOAL.md` and the git diff when you try to stop. It reports a finding for a done step with no evidence, for a changed file that no step lists, and for added work that the human has not approved. Fix findings or relabel the work. Do not hide a finding by deleting a step.
