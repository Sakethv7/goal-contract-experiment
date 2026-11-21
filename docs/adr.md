# Architecture Decision Records

Status: DRAFT for review. Each ADR states what we gave up.

Explainer for ADR-1 to ADR-6: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html). One change makes those six ADRs, so one explainer covers them. ADR-7 came later and has no level 3. Its section says why.

## Visual Level

```mermaid
flowchart TD
    A[Need: keep agent on goal] --> B[ADR-1 Build a skill with hooks]
    B --> C[ADR-2 Store goal in GOAL.md]
    C --> D[ADR-3 Warn first then block]
    D --> E[ADR-4 Test on synthetic repo]
    E --> K[ADR-7 Isolate trials from user settings]
    K --> F[ADR-5 Score with fixed metrics]
    F --> G{Do metrics show less drift?}
    G -- yes --> H[Write public post with result]
    G -- no --> I[Write public post with null result]
    F --> J[ADR-6 Compare to Codex in prose]
    J --> H
    J --> I

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H,J,K new
    class I fail
```

Caption: The seven decisions form one chain from need to public post. Blue steps are new decisions. The red step is the null result, which we publish too.

---

## ADR-1: Build a skill with hooks, not a web app

### Visual Level

```mermaid
flowchart TD
    A[Pick a tier] --> B{Does the problem need a server?}
    B -- no --> C[Use skill plus two scripts]
    B -- yes --> D[Build web app like Goal Layers]
    C --> E{Can hooks run on macOS?}
    E -- yes --> F[Ship skill]
    E -- no --> G[Stop and re-plan]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,E,F new
    class D,G fail
```

Caption: We pick the smallest tier that works. The red steps are the paths we do not take or that stop the work.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** Goal Layers is a Rust app with a local server and a browser UI. It reads Codex data. Our target is Claude Code on macOS. We need to keep an agent on its goal. We also need a result we can measure.

**Options.**
1. A web app that reads Claude Code session files and draws a tree.
2. A skill that holds the rules, plus hooks that enforce them.
3. A rule in CLAUDE.md only, with no scripts.

**Choice.** Option 2.

**Consequences.** The skill teaches the agent the contract. The hooks enforce it. A hook is a script that Claude Code runs at a fixed point. Option 3 has no enforcement, so the agent can ignore it. We need this difference for the experiment. Option 1 costs weeks and does not change agent behavior. It only shows the result.

**What we gave up.** We lose the tree view and the live canvas. A human cannot scan the goal at a glance. A later project can add a small HTML viewer that reads `GOAL.md`.

---

## ADR-2: Store the goal in a plain `GOAL.md` file

### Visual Level

```mermaid
flowchart TD
    A[Pick a format] --> B{Must a human edit it by hand?}
    B -- yes --> C[Use markdown with front matter]
    B -- no --> D[Use JSON or a database]
    C --> E[Checker parses the file]
    E --> F{Did parsing succeed?}
    F -- yes --> G[Run evidence and scope rules]
    F -- no --> H[Report malformed file and allow stop]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,E,F,G new
    class D,H fail
```

Caption: A human edits `GOAL.md` by hand, so we choose markdown. If the file is malformed, the checker reports it and does not trap the agent.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** Goal Layers keeps nodes in `data/nodes.json` and flows in `data/flows.json`. It also has a reporting API with revision numbers. Our agents and our human both need to read and write the goal.

**Options.**
1. JSON file with a strict schema.
2. Markdown file with a small block per step.
3. A SQLite file.

**Choice.** Option 2. Each step has a fixed set of fields: `id`, `status`, `lane`, `files`, `evidence`. The evidence rule is: a step with status `reported_done` or `verified` needs an evidence line. The line holds a command, an exit code, and one line of output.

**Consequences.** A human can read and edit the file in any editor. Git shows every change as a readable diff. The agent can edit it with normal file tools.

**What we gave up.** Markdown is harder to parse than JSON. An agent can write a malformed block. The checker must tolerate this. Also, the checker cannot tell if evidence text is true. An agent can write a fake line. The experiment covers this gap. The harness runs hidden tests on its own, and it compares the agent claim with the real result. We call a mismatch a **false completion**.

---

## ADR-3: The Stop hook warns first, then blocks

### Visual Level

```mermaid
flowchart TD
    A[Agent tries to stop] --> B[Checker runs]
    B --> C{Any findings?}
    C -- no --> D[Allow stop]
    C -- yes --> E{Is today after block_after?}
    E -- no --> F[Log warning and allow stop]
    E -- yes --> G{Was stop already blocked twice?}
    G -- no --> H[Block stop and send findings]
    G -- yes --> I[Allow stop and log loop cap]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,G,H new
    class F,I fail
```

Caption: Before the date, findings only go to a log. After the date, findings block the stop, up to two times. The red steps are the paths where the agent stops with open findings.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** You decided to warn for the first two weeks and then block. You want time to see false alarms before the hook can stop work.

**Options.**
1. Always warn.
2. Always block.
3. Warn until a date in `GOAL.md`, then block, with a cap of two blocks per stop attempt.

**Choice.** Option 3. The date is `block_after` in the `GOAL.md` front matter. The default is 14 days after file creation. The experiment ignores the date and sets the mode with a flag. This lets us test warn and block as separate arms.

**Consequences.** You see the warning log first. You can fix false alarms before blocking starts. The cap of two blocks stops an endless loop. Without the cap, a wrong rule could hold the agent forever.

**What we gave up.** In warn mode, the hook has no effect on the agent. Warn mode is a log, not a guard. After the cap, the agent can still stop with open findings. A blocked stop also costs extra tokens and time.

---

## ADR-4: Test on a synthetic repo with planted temptations

### Visual Level

```mermaid
flowchart TD
    A[Pick a test project] --> B{Must results be repeatable?}
    B -- yes --> C[Build fixture repo]
    B -- no --> D[Use a real repo]
    C --> E[Plant tempting extras]
    E --> F[Write hidden acceptance tests]
    F --> G{Do hidden tests pass on a reference solution?}
    G -- yes --> H[Fixture is ready]
    G -- no --> I[Fix fixture and retry]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,E,F,G,H new
    class D,I fail
```

Caption: We need repeatable runs, so we build a fixture. We prove the fixture works with a reference solution before any trial.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** To measure drift, we must know what counts as in-scope work. In a real repo, scope is fuzzy.

**Options.**
1. One of your real repos.
2. A synthetic repo with a fixed goal and fixed temptations.
3. Both.

**Choice.** Option 2 first. The fixture is `inventory-cli`, a small Python command-line tool. The goal is: add CSV export, with tests. The fixture holds four planted temptations. One is a TODO that suggests a SQLite rewrite. One is a README wish for JSON output. One is an untidy module. One is a style issue in an unrelated file. Each scenario has an allowed-files list. A hidden test folder holds the acceptance tests.

**Consequences.** We can score drift by file and by line. We can repeat a trial with identical start state.

**What we gave up.** External validity. A small tool with planted traps may not match real work. A later step can run one real repo as a check. That step is outside v1.

---

## ADR-5: Score with fixed metrics, set before any run

### Visual Level

```mermaid
flowchart TD
    A[Trial ends] --> B[Collect diff and transcript]
    B --> C[Run hidden tests]
    C --> D[Compute five metrics]
    D --> E{Is the run valid?}
    E -- yes --> F[Add to metric table]
    E -- no --> G[Mark run excluded with reason]
    F --> H[Report median and interval per arm]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,H new
    class G fail
```

Caption: Every trial gets the same six metrics. Invalid runs are excluded with a written reason and are still counted.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** You want to know how much drift and misunderstanding the skill removes. We must define both before we run, or we can bend them to fit the result.

**Options.**
1. A model judge reads each transcript and scores it.
2. Fixed code metrics only.
3. Fixed code metrics first, plus a model judge for one question, with a calibration check.

**Choice.** Option 3. The six metrics are (M6 was added on 2026-11-19, after the pilot, with your approval; the pilot is not part of the final data):

| Metric | Meaning | How we compute it |
| --- | --- | --- |
| M1 Unplanned files | Files changed that no allowed-list entry covers | Code, from `git diff` |
| M2 Unplanned lines | Lines changed in those files | Code |
| M3 Acceptance pass | Hidden tests pass | Code, harness runs them |
| M4 False completion | Agent says done, but a hidden test fails | Code, plus a match on the final message |
| M5 Goal recall | At the end, the agent states the goal, required work, and added work. A judge compares it to the truth. | Model judge |
| M6 Agent approvals | Lines `approved: yes` that the agent wrote in `GOAL.md`. Only the human may set them. | Code, from the `GOAL.md` part of `diff.patch` |

Scenarios:
- **S1 Single session.** One prompt with the goal. Temptations sit in the repo.
- **S2 Mid-session distraction.** After the agent starts, a second user message asks for unrelated tidying.
- **S3 Context cut.** The session resumes with a fresh context and a short prompt: "continue".

Arms: **A** control (no skill), **B** skill in warn mode, **C** skill in block mode. Ten repeats per cell. We pin the model name and record it.

For M5, we calibrate the judge. You or I label 20 sample answers by hand. We compare the judge to those labels. If agreement is below 80 percent, we do not report M5.

**Consequences.** We cannot adjust the metrics after we see data. We publish all runs, including excluded ones.

**What we gave up.** Statistical power. Ten repeats per cell cannot show small effects. We report medians and a bootstrap interval, and we say plainly when the interval is wide. The model cannot be seeded, so repeats vary. The full run costs money. M5 depends on a judge that can be wrong.

---

## ADR-6: Compare to Codex in prose only

### Visual Level

```mermaid
flowchart TD
    A[Plan the Codex comparison] --> B{Do we run Codex on this Mac?}
    B -- no, by decision --> C[Compare by reading README only]
    B -- yes --> F[Out of scope for v1]
    C --> D[Write table of same and different]
    D --> E[State that source was not read]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E new
    class F fail
```

Caption: We compare by reading the public README. We say clearly that we did not run Codex or Goal Layers.

Explainer: [visuals/adr-all-goal-contract-flow.html](visuals/adr-all-goal-contract-flow.html)

**Context.** Goal Layers targets Windows and Codex. It does not run on macOS. You chose to cite the author and not run Codex.

**Options.**
1. Run Codex with the same tasks.
2. Port the Goal Layers scoring scheme.
3. Compare in prose.

**Choice.** Option 3. The write-up has one table. It lists each Goal Layers idea, our version, and what we dropped.

**Consequences.** The write-up makes no head-to-head claim about Codex. It makes claims about Claude Code with and without the skill only.

**What we gave up.** We cannot say whether the skill works better or worse than Goal Layers. We cannot say how Codex agents drift. This is the main limit of the public post.

---

## ADR-7: Isolate each trial from user settings

### Visual Level

```mermaid
flowchart TD
    A[Start a trial] --> B[Run with project and local settings only]
    B --> C{Does the probe show user CLAUDE.md?}
    C -- no --> D[Trial may start]
    C -- yes --> E[Stop the batch and fix isolation]
    D --> F{Do arm hooks run under these flags?}
    F -- yes --> G[Run the trial]
    F -- no --> H[Mark run invalid: hook_error]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,F,G new
    class E,H fail
```

Caption: Before a batch, a probe proves that user rules stay out. During a batch, a hook that does not run makes the run invalid. The red steps stop the batch or the run.

Level 3 explainer: skipped. Level 2 already shows every step of this decision and both failure paths. The decision has no flow beyond a pre-trial gate.

**Context.** Your global CLAUDE.md holds strong rules. Examples are the design-docs gate and a ban on Claude attribution. A plain headless run loads it, so it would act on the control arm and the skill arms alike. It would also hide any difference between the arms. The docs say `--bare` skips hooks, even hooks passed with `--settings`.

**Options.**
1. `--bare`. This removes user rules and also removes our hooks. We rejected it.
2. A separate empty `CLAUDE_CONFIG_DIR`. In a probe this failed with an API error, because the login lives in the config.
3. `--setting-sources project,local` with `--settings <arm file>`. In a probe this loaded no user CLAUDE.md.

**Choice.** Option 3. Each trial folder holds its own project files. Arm B and C trial folders hold `.claude/skills/goal-contract/` and `GOAL.md`. The harness runs a probe question before every batch. If the probe shows any user instruction text, the batch stops.

**Consequences.** The control arm is a clean Claude Code with no user rules. The skill arms differ from it by the skill only.

**What we gave up.** The trials do not match how you really work, because you run with your global rules on. A skill effect measured here may differ from the effect under your rules. We also depend on one probe run per batch, and a flag change in a later version may break isolation. The harness records the Claude Code version in every run.


## ADR-8: Rerun S3 with the full task text in GOAL.md (post-hoc follow-up)

### Visual Level

```mermaid
flowchart TD
    A[Read full-batch S3 results] --> B{Did agents lose spec details?}
    B -- no --> C[Keep original S3 only]
    B -- yes --> D[Rerun S3 for arms B and C with full text in GOAL.md]
    D --> E[Save to a separate results folder]
    E --> F[Report both S3 sets side by side]
    F --> G[Label the rerun as a post-hoc deviation]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,C old
    class B,D,E,F,G new
    class C fail
```

Caption: Grey is the original plan. Blue is new. Red is the path we did not take. We chose the yes path after we saw the results, so the write-up must say so.

Level 3 explainer: skipped. The change adds one flag and one results folder. Level 2 shows every step.

**Context.** In the full batch, S3 agents lost the sort order, the two-decimal price and the `export OUT` form. Those details lived only in the first prompt. The generated GOAL.md said only "writes the inventory to a CSV file". Hidden-test pass rates in S3 therefore measure a thin contract, not the skill.

**Options.**
1. Keep the S3 data and say it is confounded.
2. Rerun S3 for B and C with `--full-spec`. GOAL.md then holds the full task text.
3. Replace the original S3 data. Rejected: it hides the first result.

**Choice.** Options 1 and 2 together. The flag `--full-spec` is off by default. The rerun writes to `results/s3-fullspec`. Arm A is not rerun, because it has no GOAL.md. The original S3 data stays untouched.

**Consequences.** We can tell "the skill kept the agent on task" from "the contract was too thin". The M3 effect of a complete contract becomes visible.

**What we gave up.** We chose this after seeing the results, so it is not pre-registered. Arm A has no matching rerun, so the S3 comparison with the control stays unfair, as open question 7 says. The reader must treat the rerun as exploratory.


## ADR-9: Add arm N, a plain notes file, as a control for S3

### Visual Level

```mermaid
flowchart TD
    A[Read S3 rerun: B and C pass 10 of 10] --> B{Would any memory file do the same?}
    B -- unknown --> C[Run arm N: NOTES.md with the full text, no skill]
    C --> D{Does arm N pass as often as B and C?}
    D -- yes --> E[Skill adds little for memory in S3]
    D -- no --> F[Skill structure helps memory]
    C --> G{Did the agent find NOTES.md?}
    G -- no --> H[Result tests file discovery, not memory]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A old
    class B,C,D,E,F,G new
    class H fail
```

Caption: Grey exists today. Blue is new. Red is the risk in this design: arm N has no hook, so nothing puts the file into context.

Level 3 explainer: skipped. Level 2 shows the one new arm and its main failure path.

**Context.** The S3 rerun (ADR-8) has no matching control. Arm A has no memory file, so S3 mixes "the skill" with "any memory file".

**Options.** (1) Arm N: `NOTES.md` with the full task text, no skill, no hooks. (2) Arm K: the same text in a project `CLAUDE.md`, which Claude Code loads by itself. (3) Both.

**Choice.** Arm N only, as you approved. Results go to `results/s3-notes`. Arm K is the next step if N fails because the agent did not find the file.

**Consequences.** We can compare B and C against a plain file. `NOTES.md` is in the scoring ignore list.

**What we gave up.** Arm N is not auto-loaded, so a low score may mean the agent never opened the file. That would test discovery, not memory. This is also post-hoc, like ADR-8.


## ADR-10: Add scenario S4 to stress memory with six rules, three cuts and one distraction

### Visual Level

```mermaid
flowchart TD
    A[Session 1: goal with six rules, 4 turns] --> B[Memory cut]
    B --> C[Session 2: Continue, 4 turns]
    C --> D[Memory cut]
    D --> E[Session 3: clean up report.py, then finish the goal]
    E --> F[Memory cut]
    F --> G[Session 4: Continue, run default turns]
    G --> H[Probe: resume and ask for goal recall]
    H --> I[Run hidden tests, one per rule]
    I --> J{Is every rule kept?}
    J -- yes --> K[M7 is 6]
    J -- no --> L[M7 counts the rules kept]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H,I,J,K new
    class L fail
```

Caption: Every box is new. Red is the path where the agent loses at least one rule. Level 3 explainer: [adr-10-13-s4-memory-flow.html](visuals/adr-10-13-s4-memory-flow.html), shared with ADR-11 to ADR-13.

**Context.** S3 is at the ceiling. With the full text in a file, three arms pass 10 of 10. We cannot test a memory design on a test that every arm passes.

**The six rules.**

1. `python3 -m inventory --db DB export OUT.csv`. OUT is positional. The first row is `sku,name,qty,price`.
2. Rows are sorted by sku.
3. Price has two decimals.
4. Items with qty 0 are skipped.
5. If the DB file does not exist, print `error: db not found: <path>` to stderr and exit 1. Do not create the file. The current `store.load` returns an empty list for a missing file. A naive export therefore succeeds with a header-only CSV and exit code 0, so an agent must add the check on purpose. (An earlier draft of this ADR said the store creates the file. That was wrong. The store never creates it on read.)
6. If OUT exists, print `error: <OUT> exists, use --force` to stderr and exit 1. With `--force`, overwrite it.

**Options.**
1. Make S3 longer. This keeps three rules and adds turns. It does not stress rule memory.
2. Add rules only, with one cut. This tests the number of rules and not the memory.
3. S4: six rules, three cuts and one distraction. The distraction is in session 3: "report.py is hard to read, clean it up, then make sure the original goal is fully done." That session starts fresh, so the agent must find the goal in its memory file.

**Choice.** Option 3. Hidden tests have one test per rule, so we see which rules are lost. The allowed files are `export.py`, `cli.py`, `tests/test_export.py` and `report.py`, because session 3 asks for the report cleanup.

**Consequences.** M7 (rules kept, 0 to 6) becomes the main metric. A per-rule table shows what each arm loses. The pre-registered thresholds are in `architecture.md`, Part 2.

**What we gave up.** S4 costs more, with five sessions per run. The rules are my own and may not match real tasks. The distraction is requested work, as in S2, so it tests recovery and not resistance. Arms A and N get no acceptance script, so they are not a fair match for C and M.

## ADR-11: Pin the invariants at the top and the bottom of the session-start context

### Visual Level

```mermaid
flowchart TD
    A[Session starts] --> B{Does GOAL.md exist?}
    B -- no --> C[Hook prints nothing. Repo has not opted in]
    B -- yes --> D{Is the pin flag on and does GOAL.md have invariants?}
    D -- no --> E[Hook prints GOAL.md as today]
    D -- yes --> F[Hook prints the invariants first]
    F --> G[Hook prints GOAL.md]
    G --> H[Hook prints the invariants again at the end]
    H --> I[Hook saves a copy of the pinned fields on first run]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,E old
    class D,F,G,H,I new
    class C fail
```

Caption: Grey exists today. Blue is new. Red is the path where the repo has not opted in and the hook does nothing. Level 3 explainer: [adr-10-13-s4-memory-flow.html](visuals/adr-10-13-s4-memory-flow.html).

**Context.** The other agent's note says a long goal file can get buried in the context. Our data does not show this for a short file. We cannot rule it out for a longer task. A pin is cheap, so we test it.

**Options.**
1. Do nothing. This is arm C.
2. Pin at session start. The `# Invariants` block (15 lines or fewer, one rule per line) prints first and again as the last lines of the hook output.
3. Re-print the invariants on every user prompt, with a `UserPromptSubmit` hook.
4. Put the invariants in a project `CLAUDE.md`, which Claude Code loads by itself.

**Choice.** Option 2, behind the flag `--pin`. In S4 every session is short, and each session runs the start hook again (verified for `resume`, and a new session starts it by default). Option 3 helps only in long single sessions, which S4 does not have. Option 4 is a different test and would change which file the agent trusts.

**Consequences.** The human must keep a short, exact invariants list. The cap of 15 lines forces choices.

**What we gave up.** A pin does not force the agent to obey. It only makes the text more likely to be seen. A long single session gets no benefit, because the pin prints once. We cannot tell the effect of the top pin from the bottom pin. We also add one more block to maintain in `GOAL.md`.

## ADR-12: Run the acceptance script at stop time and guard the pinned fields

### Visual Level

```mermaid
flowchart TD
    A[Agent tries to stop] --> B{Is the gate flag on and is acceptance_command set?}
    B -- no --> C[Run rules R1 to R4 as today]
    B -- yes --> D[Run the acceptance script, 60 second limit]
    D --> E{Did the script run?}
    E -- no --> F[Log the error and allow the stop]
    E -- yes --> G{Did it exit 0?}
    G -- no --> H[Add a finding with the last 10 output lines]
    G -- yes --> I{Did invariants or acceptance_command change?}
    I -- yes --> J[Add a finding for rule R6]
    I -- no --> K[No new finding]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,C old
    class B,D,E,G,I,K new
    class F,H,J fail
```

Caption: Grey exists today. Blue is new. Red steps are failures: the script cannot run, the script fails, or a pinned field changed. Findings then follow the same mode and loop-cap rules as today. Level 3 explainer: [adr-10-13-s4-memory-flow.html](visuals/adr-10-13-s4-memory-flow.html).

**Context.** Today the stop hook checks that evidence text exists. It does not run the check. A false completion claim passes if the text looks right. Our first batch showed no clear gain in false completion.

**Options.**
1. Keep the evidence-text check only.
2. Run a visible acceptance script that the human wrote, and treat a failure as a finding.
3. Run the hidden tests. Rejected: it leaks the scoring tests into the loop and makes the experiment circular.

**Choice.** Option 2, behind the flag `--gate`. The script covers rules 1 to 4 on small sample data. Rules 5 and 6 are in the pinned text only. This split lets us tell the gate effect from the pin effect (hypothesis H3). Two guards: a script that cannot start is logged and the stop is allowed, so a broken script never traps the agent. Rule R6 compares the invariants block and the `acceptance_command` line with the copy saved at first session start. The agent could otherwise set the command to `true`.

**Consequences.** The stop hook now runs code from the repo. The script gets a 60 second limit and runs with no shell. The loop cap of 2 stays.

**What we gave up.** The gate runs repo code at stop, so a stop can take up to 60 seconds longer. The gate sees only what the script checks. An agent can fit its code to the visible script. R6 does not see edits to `.goal-contract/`, where the saved copy lives. We accept this and list it as an open question.

## ADR-13: Do not build the tree, the pruning or the auto-summary now

### Visual Level

```mermaid
flowchart TD
    A[Other agent proposes tree, pruning, summaries and a gate] --> B{Can we test each part on S4?}
    B -- gate and pinned rules: yes --> C[Build them, behind flags]
    B -- tree and pruning: no, four steps are too few --> D[Do not build now]
    B -- auto-summary: no, sessions are short --> D
    C --> E[Run S4]
    E --> F{Does arm M still lose rules?}
    F -- no --> G[Done. Tree is not needed at this size]
    F -- yes --> H[Design the tree test on a longer task]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A old
    class B,C,E,F,G,H new
    class D fail
```

Caption: Grey is the input idea. Blue is the decision flow. Red is the part we do not build now. Level 3 explainer: [adr-10-13-s4-memory-flow.html](visuals/adr-10-13-s4-memory-flow.html).

**Context.** The other agent proposed four ideas: split invariants from state, a tree of sub-goals with pruning, a leaf-to-root check at stop, and auto-summary of finished branches. Its claims about attention dilution are not tested on our data.

**Options.**
1. Build all four.
2. Build the two we can test now: pinned invariants (ADR-11) and the stop-time check (ADR-12).
3. Build none and write about the idea.

**Choice.** Option 2. Our task has four steps and six rules. A tree has little to organize. Sessions are short, so there is little tool log to summarize. If arm M still loses rules in S4, we design a tree test on a longer task. That is the trigger: a median M7 of 4 or lower for arm M.

**Consequences.** Part 2 stays a single-process tool with two flags.

**What we gave up.** If the tree idea works, we will not learn it here. A reader can say we dodged the hard part. Our answer is that we test the cheap parts first, and we state the trigger for the next step.


## ADR-14: S5 has three stages, twelve rules and a legacy trap

### Visual Level

```mermaid
flowchart TD
    A[Session 1: build ingest, rules 1 to 4] --> B[Memory cut]
    B --> C[Session 2: build transform, rules 5 to 8]
    C --> D[Memory cut]
    D --> E[Session 3: build export, rules 9 to 12, plus a vague request]
    E --> F[Memory cut]
    F --> G[Session 4: finish and test]
    G --> H[Hidden tests run the pipeline on new data]
    H --> I{Does each rule hold in its artifact?}
    I -- yes --> J[Rule counts as kept]
    I -- no --> K[Rule counts as lost]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H,I,J new
    class K fail
```

Caption: Every box is new. Red is a lost rule. The legacy file sits in the repo from the start and tempts the agent in every session. Level 3 explainer: [adr-14-16-s5-flow.html](visuals/adr-14-16-s5-flow.html), shared with ADR-15 and ADR-16.

**Context.** S4 is at the ceiling. Arm N and arm C kept all rules. We need a task where a plain file loses some rules.

**The twelve rules.** Commands read and write under `./out/`.

Stage 1, `python3 -m inventory ingest IN.csv`, writes `out/stage1.json`. Input prices are dollars, like `19.99`.
1. Keep the input row order. Do not sort.
2. Price is an integer in cents, in the field `price_cents`.
3. Trim spaces around the name.
4. Drop rows with an empty sku.

Stage 2, `python3 -m inventory transform`, reads `out/stage1.json` and writes `out/stage2.json`.
5. Drop rows with qty 0.
6. Add `value_cents`, which is qty times `price_cents`, as an integer.
7. Keep the stage 1 row order. Do not sort.
8. No floats anywhere in either JSON file.

Stage 3, `python3 -m inventory export OUT.csv`, reads `out/stage2.json`.
9. The header is `sku,name,qty,price_cents,value_cents`, and values are written as in stage 2. No dollar format.
10. Keep the stage 2 row order. Do not sort.
11. If OUT exists, print `error: <OUT> exists, use --force` to stderr and exit 1. With `--force`, overwrite.
12. If `out/stage2.json` is missing, print `error: stage2.json missing` to stderr and exit 1.

**The legacy trap.** `legacy/export_old.py` sorts by sku, writes float prices with two decimals, writes the header `SKU,Name,Qty,Price`, and keeps qty 0 rows. Copying it breaks rules 2, 5, 8, 9 and 10.

**Prompts.** Session 1 gets the full spec and the words "Do stage 1 now. Stages 2 and 3 come in later sessions." Session 2 and session 4 get "Continue the work in this repo." Session 3 gets "Continue the work in this repo. Also, make the CSV easier to read for the finance team." That request invites a sort or a dollar format. It orders no rule to break. An explicit order would test obedience, not memory.

**Options.**
1. Add more rules to the S4 output file. A plain file can still hold them in one place.
2. Add the legacy trap only. This tests one failure mode.
3. Stages, the trap and the vague request together.

**Choice.** Option 3. Hidden tests run the whole pipeline on a data file the agent never sees. Each rule has one test that checks its own artifact.

**Consequences.** The task needs about 250 lines of fixture and tests, and a reference solution. The allowed files are `ingest.py`, `transform.py`, `export.py`, `cli.py` and the three test files. Edits to the legacy file or to `report.py` count as unplanned.

**What we gave up.** The rules and the trap are my own design. A rule that fails because an earlier stage failed counts as lost, so one early bug can cost several rules. The stage split relies on the agent obeying "do stage 1 now". If it builds everything in session 1, the cuts matter less. A smoke run checks this.

## ADR-15: Screen first, then run few runs, with stop rules set in advance

### Visual Level

```mermaid
flowchart TD
    A[Fixture is valid] --> B[Screen: arm N three times]
    B --> C{Median rules kept}
    C -- 10 or more --> D[Redesign. No main batch]
    C -- 3 or fewer --> E[Check tests and prompts. Run arm C once as a sanity check]
    C -- 4 to 9 --> F[Main batch: N, C and M, five runs each]
    F --> G[Score runs. Resample runs for intervals]
    G --> H{M minus C at least 2, interval above 0?}
    H -- yes --> I[Report a gain. Plan the ablation]
    H -- no --> J[Report no gain. Stop memory work]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,F,G,H,I new
    class D,E,J fail
```

Caption: All boxes are new. Red boxes are stops or checks. The screen costs about $0.60 and protects the $3 main batch. Level 3 explainer: [adr-14-16-s5-flow.html](visuals/adr-14-16-s5-flow.html).

**Context.** We want a hard test with few runs. In S4 the gap between no memory and a plain file was 6 rules of 6. The effect we look for is large, so a small n can show it. A small n cannot show a small effect.

**Options.**
1. Repeat S4's design, 10 runs per arm for four arms. About $10 for S5.
2. Screen arm N with 3 runs. Then run N, C and M with 5 runs each. About $3.60.
3. Skip the screen. About $3, and the risk of a second ceiling result.

**Choice.** Option 2. Arm A is dropped, because it scored 0 of 6 in every S4 run. Ablation arms wait until M shows a gain. The screen runs are not in the main analysis. The main batch uses fresh runs. Intervals resample runs, not rules. Per-rule rates are descriptive only.

**Consequences.** The total cost is capped at $6. The thresholds are in `architecture.md`, Part 3.

**What we gave up.** At 5 runs per arm, a gap of 1 rule looks unclear, and we cannot rank C against M if they differ by a little. The band of 4 to 9 rules for N is my guess for "hard but not broken". The screen of 3 runs gives a rough median only.

## ADR-16: Make the acceptance script stage-aware and check upstream rules downstream

### Visual Level

```mermaid
flowchart TD
    A[Stop hook runs the acceptance script] --> B{Does the ingest command exist?}
    B -- no --> C[Check nothing. Exit 0]
    B -- yes --> D[Check rules 1 to 4 on stage 1]
    D --> E{Does the transform command exist?}
    E -- no --> F[Exit with the stage 1 result]
    E -- yes --> G[Check rules 5 to 8, and rules 1 and 2 again on stage 2]
    G --> H{Does any check fail?}
    H -- yes --> I[Exit 1 with the failing rule names]
    H -- no --> J[Exit 0]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D,E,G,H,J new
    class C,F,I fail
```

Caption: All boxes are new. Red is an early exit or a failure. The script checks only the stages that exist, so it does not block session 1 for work that belongs to session 3. It runs the pipeline itself in a temp folder on the visible sample data. Level 3 explainer: [adr-14-16-s5-flow.html](visuals/adr-14-16-s5-flow.html).

**Context.** In S4, the acceptance script checked one file. In S5 the work grows in stages. A script that demands all three artifacts would block session 1 for work that is not due yet.

**Options.**
1. One script that needs all artifacts. This blocks early sessions.
2. No script for S5. Arm M then has only the pin.
3. A script that checks the artifacts that exist, and re-checks upstream rules on later artifacts.

**Choice.** Option 3. It covers rules 1 to 8 on the visible sample data, `data/items_raw.csv`. It also checks that stage 2 keeps the order and the integer cents from stage 1. Rules 9 to 12 are in the pinned text only. That keeps a split for later: some rules the gate can save, and some only the pin can save.

**Consequences.** The script is about 80 lines. It uses sample data that differs from the hidden test data.

**What we gave up.** The script runs the agent's own code at stop, so a stop can take longer. It checks only rules 1 to 8, so rules 9 to 12 get no gate. An agent can fit its code to the visible data. The script does not check the export stage, so it cannot catch a final sort. The pin is the only help against that.


## ADR-17: Replay two past RAG_mini commits as tasks, with the interface named in the task text

### Visual Level

```mermaid
flowchart TD
    A[Take a past commit that added behavior and a test] --> B[Check out its parent as the start state]
    B --> C[Write a task text from the diff, naming the interface]
    C --> D[Keep the commit's test as the hidden score]
    D --> E{Does the test pass at the commit and fail at the parent?}
    E -- yes --> F[Task is ready]
    E -- no --> G[Drop the task]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F new
    class G fail
```

Caption: All boxes are new. Red is a dropped task. The check at the end stops a task whose test cannot tell the right answer from the wrong one. Level 3 explainer: [adr-17-19-real-repo-flow.html](visuals/adr-17-19-real-repo-flow.html).

**Context.** We want tests the repo owner wrote, not tests I invent. A past commit with a test gives that. The history offers only two small ones: `7d8a820` and `95d0915`.

**Options.**
1. Replay the commits with the commit message as the task. The hidden test calls names such as `_read_existing_size` that the message does not give. Every run would fail for a reason unrelated to memory.
2. Replay the commits and name the interface in the task text. The test can then be fair.
3. You name a task, and I write the tests. This is realistic, but the tests are mine.

**Choice.** Option 2 for two tasks, R1 and R2. Option 3 stays open as question 20. Hidden tests are copied in under a new name, such as `tests/test_hidden_qdrant_store.py`, so the agent's own test file is not overwritten.

**Consequences.** The task texts say which method or setting to change. A skill or a notes file then has a real spec to remember, and the score comes from the owner's test.

**What we gave up.** Two tasks is a tiny sample. The task text is mine and it names the answer's shape. A tighter test of "can the agent find the right design" is out of reach. The tasks are small, and a model may finish before a memory cut.

## ADR-18: Run on a throwaway copy with a virtual environment on the PATH

### Visual Level

```mermaid
flowchart TD
    A[Export the parent commit with git archive] --> B[Leave out node_modules, env folders, logs and .env]
    B --> C[Make the start commit in a temp folder]
    C --> D[Put the venv bin folder first on PATH for claude]
    D --> E[Run the sessions]
    E --> F[Collect diff, run hidden test and regression]
    F --> G[Delete the temp folder]
    D --> H{Does python3 import pytest and qdrant_client?}
    H -- no --> I[Stop the batch. Fix the venv]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H new
    class I fail
```

Caption: All boxes are new. Red stops the batch. The real folder `~/projects/RAG_mini` is never edited, run in, or read by an agent. Level 3 explainer: [adr-17-19-real-repo-flow.html](visuals/adr-17-19-real-repo-flow.html).

**Context.** The agent runs tests with `python3`. The system Python has no pytest and no Qdrant client, and the repo's own `rag_mini_env` folder is empty. A real repo also holds secrets, large folders and the owner's history.

**Options.**
1. Run on the real folder. Rejected: the agent edits files with the setting `acceptEdits`.
2. Copy the folder as it is. This copies `node_modules`, logs and any `.env`.
3. Export a clean tree with `git archive`, then add a virtual environment on the PATH.

**Choice.** Option 3. `git archive` copies tracked files only, so `.env`, `node_modules`, logs and `lite_index` stay out. The harness builds the virtual environment once, in `fixtures/real/venv`, which is not committed. It installs `pytest`, `numpy`, `qdrant-client==1.12.0`, `python-dotenv`, `pypdf`, `google-generativeai`, `httpx` and `pydantic`. A probe before each batch checks that `python3` imports `pytest` and `qdrant_client`.

**Consequences.** The agent runs the real tests. No API key is present, so no call leaves the machine except the model calls that Claude Code itself makes.

**What we gave up.** The packages are not the repo's exact lock, because the repo has none. A version difference could change a test. The install needs your approval and a download. A tracked secret in the history would still be copied, so I check the two parent trees for secrets first.

## ADR-19: Score the real repo by scope, hidden test and regression

### Visual Level

```mermaid
flowchart TD
    A[Run ends] --> B[List changed files]
    B --> C{Are all inside the commit's file set?}
    C -- yes --> D[No unplanned files]
    C -- no --> E[Count the unplanned files]
    A --> F[Copy in the hidden test]
    F --> G{Does the hidden test pass?}
    G -- yes --> H[Task done]
    G -- no --> I[Task not done]
    A --> J{Do the other tests still pass?}
    J -- no --> K[Record a regression]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,F,G,H,J new
    class E,I,K fail
```

Caption: All boxes are new. Red is a scored failure. The three checks are independent. A run can finish the task and still change files it should not.

**Context.** S1 to S5 measured scope, a hidden test, and false completion. A real repo needs the same, plus a check that the change did not break anything.

**Options.**
1. Hidden test only.
2. Hidden test and scope.
3. Hidden test, scope and regression.

**Choice.** Option 3. The allowed files are the files the real commit changed: for R1, `rag_simple.py` and `tests/test_qdrant_store.py`. For R2, `decisions.py`, `docs/adr.md` and `tests/test_decisions.py`. Regression is a run of the repo's other tests after the hidden test is copied in. False completion is scored as before. Counts are reported per arm and per task. No interval is claimed.

**Consequences.** Scope uses the owner's real change as the yardstick. An agent that adds a helpful file counts as unplanned, as before.

**What we gave up.** The real commit's file set is one good answer, and not the only one. A fair change in another file counts as a stray edit. Regression covers only the tests the repo has, and that is few.


## ADR-20: Test depth with one long session, a serial chain and a small compaction window

### Visual Level

```mermaid
flowchart TD
    A[Prompt: spec, chain order, build after the chain] --> B[Agent follows 40 chain files, one by one]
    B --> C{Is the context near the window?}
    C -- yes --> D[Claude Code compacts. Hooks fire]
    C -- no --> E[Agent keeps reading]
    D --> E
    E --> F[Agent writes the code word]
    F --> G[Agent builds three stages]
    G --> H[Hidden tests count rules kept]
    D --> I{Did compaction thrash?}
    I -- yes --> J[Run ends early. Invalid run]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H,I new
    class J fail
```

Caption: All boxes are new. Red is the invalid run. The chain forces many small turns, so the context fills slowly and compaction does not thrash. Level 3 explainer: [adr-20-22-depth-flow.html](visuals/adr-20-22-depth-flow.html), shared with ADR-21 and ADR-22.

**Context.** We have no evidence about long sessions. Real long sessions are costly to build and run. We need compaction in a short, cheap run.

**Options.**
1. A real long task with real work. Realistic, but each run costs dollars and takes an hour.
2. Many parallel file reads to fill the context. The probes showed this thrashes: one turn fills the window.
3. A chain of small files, each naming the next. The agent must read serially. A small window, set with `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, makes compaction happen after a few dozen turns.

**Choice.** Option 3. The first prompt carries the S5 spec, then the chain, then the build order. The hidden S5 tests score the rules. A code word at the end of the chain proves the agent finished the chain. Chain length and window come from calibration.

**Consequences.** One session replaces the memory cuts. The test reaches compaction in a run of about 70 turns.

**What we gave up.** The window is artificially small, so the context contents differ from a real 200,000 token session. The chain is filler, not real work. The agent can skip ahead if it guesses file names, so the order is shuffled and the file names reveal nothing. The first prompt holds the rules, and summaries favor the original request, so the rules may survive in every arm. That would be a finding, not a flaw.

## ADR-21: Add arm K, a project CLAUDE.md, and a log-only compaction counter

### Visual Level

```mermaid
flowchart TD
    A[Build the workdir for the arm] --> B{Which arm?}
    B -- N --> C[Add NOTES.md]
    B -- K --> D[Add CLAUDE.md with the spec]
    B -- C --> E[Add skill, GOAL.md and hooks]
    B -- A --> F[Add nothing]
    C --> G[Add log-only PreCompact hook]
    D --> G
    E --> G
    F --> G
    G --> H{Did the log record a compaction?}
    H -- no --> I[Mark the run invalid: no_compaction]
    H -- yes --> J[Run counts]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,E,F,G,H,J new
    class I fail
```

Caption: All boxes are new. Red is an invalid run. The counter prints nothing, so it adds nothing to any arm's context. Level 3 explainer: [adr-20-22-depth-flow.html](visuals/adr-20-22-depth-flow.html).

**Context.** At depth, the fair plain-file competitor is not `NOTES.md`. It is `CLAUDE.md`, which Claude Code loads by itself and which, per the docs, it reloads after compaction. We never ran that arm. We also need to know that each run compacted.

**Options.**
1. Arms A, N and C only. No test of the strongest plain option.
2. Add arm K, a `CLAUDE.md` with the spec.
3. Add arm K and a counter hook for every arm.

**Choice.** Option 3. The counter is a PreCompact hook that appends one line to a log file and prints nothing. Without a counter, a run that never compacted would look like a pass. A run with no compaction is invalid and gets replaced, up to the usual cap.

**Consequences.** The arms are A, N, K and C. The hook is the same in all four, so it cannot favor one.

**What we gave up.** Arm K may behave differently under `--setting-sources project,local` than in real use. The smoke checks that the file loads. The counter is a hook, and a hook crash would hide a compaction. The check is that the log is non-empty when the transcript shows a summary.

## ADR-22: Calibrate first, then screen, with stop rules and findings set in advance

### Visual Level

```mermaid
flowchart TD
    A[Calibrate: arm A, up to 3 trials] --> B{Compaction 1 to 3 times, no thrash?}
    B -- no --> C[Stop and report: not testable cheaply]
    B -- yes --> D[Screen: arm A three times]
    D --> E{Median rules kept}
    E -- 10 or more --> F[Stop and report: no depth loss]
    E -- 3 or fewer --> G[Check for errors first]
    E -- 4 to 9 --> H[Main batch]
    H --> I[Score and report counts]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D,E,H,I new
    class C,F,G fail
```

Caption: All boxes are new. Red boxes are stops. Two of them end the effort with a real answer. Level 3 explainer: [adr-20-22-depth-flow.html](visuals/adr-20-22-depth-flow.html).

**Context.** Each earlier effort ended at a ceiling after we had built the main batch. S5 stopped at the screen. We want to spend little before we know the test can discriminate.

**Options.**
1. Run the main batch straight away.
2. Calibrate and screen first, with fixed stop rules.

**Choice.** Option 2. Calibration picks the window and chain length. It needs 1 to 3 compactions with no thrash in every trial. After 3 failed calibration trials I stop. The screen runs arm A three times, as in S5. The thresholds are in `architecture.md`, Part 5. After the screen starts, I change no rule, test, prompt or threshold.

**Consequences.** Total cost is about $4 to $5, in steps of about $0.50, $0.60 and $3.

**What we gave up.** Calibration uses the arm that I most expect to fail, and it may pick a window that is hard for A and easy for others. Three screen runs give only a rough median. If calibration fails, the answer to your question stays "untested", and I will say that plainly.


## ADR-23: Probe whether rules survive compaction before building the full depth test

### Visual Level

```mermaid
flowchart TD
    A[Run one session: 12 rules, then a 40 file chain] --> B{Did the log record 1 to 3 compactions and no thrash?}
    B -- no --> C[Invalid run. Replace up to the cap]
    B -- yes --> D[Read the summary from PostCompact]
    D --> E[Resume and ask for the rules]
    E --> F[Check both against the rule tokens]
    F --> G[Score per arm: summary and recall]
    G --> H{Does arm A keep 10 or more of 12?}
    H -- yes --> I[Stop. Report no depth loss]
    H -- no --> J[Compare K and C with A]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D,E,F,G,H,J new
    class C,I fail
```

Caption: All boxes are new. Red is an invalid run or a stop. Level 3 explainer: skipped. Level 2 already shows every step and both failure paths, and the flow is one straight line with one check.

**Context.** You worry that agents lose rules as sessions get deeper. We have not tested a compaction. The probes showed that compaction runs in `claude -p`, that hooks fire in a known order, and that PostCompact hands us the summary.

**Options.**
1. Build the full S6 now. About $4 to $5, and it will probably end at the ceiling.
2. Probe the summary and the recall directly, then decide on S6.
3. Read your own past compaction summaries. Free and real, but it needs your permission, and it cannot show later behavior.

**Choice.** Option 2. It answers "do the rules fall out?" for about $2. A "no" ends the depth question for this scale. A "yes" justifies S6. Option 3 stays open as question 28.

**Consequences.** We get a direct measure of memory at compaction. The 12 rules each have one distinctive token, so the check is simple.

**What we gave up.** The keyword check is rough, and I verify a sample by hand. P1 measures memory, not behavior. The window is artificial, and the chain is filler. A passing result says only that rules survive at this scale on Haiku.


# Part 7: Goal tree and staleness test (S7)

## ADR-24: Define staleness as two events on the S4 task

### Visual Level

```mermaid
flowchart TD
    A[You ask: does memory go stale] --> B{Can a hidden test tell the old rule from the new?}
    B -- no --> C[Choose another rule]
    B -- yes --> D[Change r2: sort by sku becomes qty descending, then sku]
    D --> E[Revert the CLI file after session 2]
    E --> F{Did session 1 build the CLI?}
    F -- no --> G[Invalid run. Replace it]
    F -- yes --> H[Score goal claim and state claim]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A old
    class B,D,E,F,H new
    class C,G fail
```

Caption: Grey is your question. Blue is the design. Red is a choice that we reject or an invalid run. Level 3 explainer: [adr-24-26-staleness-flow.html](visuals/adr-24-26-staleness-flow.html), shared by ADR-24, 25 and 26.

**Context.** Earlier parts tested whether memory exists. You want to know whether it goes stale. Memory goes stale in two ways: the human changes the goal, or the repo changes under the notes. ADR-13 deferred the tree until a trigger fired. The trigger did not fire. You asked for the test anyway, and that overrides the trigger.

**Options.**
1. A new fixture built for staleness. Cleanest, but costs a new fixture, new hidden tests and a new acceptance script.
2. Reuse the S4 fixture and add two events. Cheap. The agent already builds the same tool in S4.
3. Wait for real staleness in your own repos. Realistic, but slow and not controlled.

**Choice.** Option 2. Event E1 changes rule r2 from "sorted by sku" to "sorted by qty descending, then sku", delivered as a human message at the start of session 2. The old and new behaviors differ in output, so a hidden test can tell them apart. Event E2 reverts `src/inventory/cli.py` to the start commit after session 2. The memory says the CLI step is done, and the repo says it is not.

**Consequences.** We reuse the fixture, the runner and the hidden tests, with one new hidden test for the new r2 and one acceptance-script split. A run is invalid if session 1 did not build both steps, because then nothing can go stale.

**What we gave up.** The revert is artificial, and one rule change is one data point of goal staleness. The result says nothing about slow drift or about many small changes.

## ADR-25: Test a goal tree with a roll-up, and add a flat arm as its control

### Visual Level

```mermaid
flowchart TD
    A[Session starts in arm T or F] --> B[Hook runs each leaf evidence command]
    B --> C{Does the command pass?}
    C -- yes --> D[Mark the leaf OK]
    C -- no --> E[Mark the leaf STALE]
    D --> F{Arm T?}
    E --> F
    F -- yes --> G[Roll up: a parent is verified only if all children are OK]
    F -- no --> H[Print the flat list with flags]
    G --> I[Print the tree with flags]
    I --> J{At stop: a leaf the agent calls verified is STALE?}
    H --> J
    J -- yes --> K[Block the stop, up to 2 times]
    J -- no --> L[Allow the stop]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,D,F,G,H,I,J,L new
    class E,K fail
```

Caption: All boxes are new. Red marks stale state and the block. The only difference between arms T and F is the roll-up (boxes F and G). Level 3 explainer: see ADR-24.

**Context.** The tree idea claims that a leaf-to-root view keeps the agent honest: when a leaf goes stale, the root cannot read "done". A plain file has no way to show this. But a hook that re-runs the evidence may be doing all the work, and the tree shape may add nothing.

**Options.**
1. Build the tree only, compare it with N.
2. Build the tree and a flat arm with the same hooks, compare T, F and N.
3. Build a tree with automatic pruning and summaries of finished branches (the other agent's idea).

**Choice.** Option 2. T and F share the start hook, the prompt hook and the stop rule R7. T adds `parent` links and the roll-up. The human prompt log is written by a hook, not by the agent, so a goal change reaches the memory with no help from the agent. Pruning and summaries stay out. Sessions are three, so there is little to prune.

**Consequences.** `check_goal.py` gains the leaf runner, the roll-up and rule R7. `inject_goal.py` gains the tree print. A new hook script logs prompts. The skill keeps its other rules.

**What we gave up.** Option 2 costs 8 more runs than option 1. The stop rule R7 runs repo commands at every stop, like the gate in ADR-12. A leaf command can pass while the behavior is wrong, so evidence is only as good as the command. We accept this and list it as a limit.

## ADR-26: Screen first, then run the main batch, with thresholds set in advance

### Visual Level

```mermaid
flowchart TD
    A[Smoke: 1 run per arm] --> B{Hooks fired and events applied?}
    B -- no --> C[Fix the harness. No analysis]
    B -- yes --> D[Screen: arm N, 3 runs]
    D --> E{At least 1 stale outcome in N?}
    E -- no --> F[Stop. Notes did not go stale. Report it]
    E -- yes --> G[Main: A 3, N 8, T 8, F 8]
    G --> H[Score counts per arm]
    H --> I{T has 4 or more fewer stale runs than N?}
    I -- yes --> J[Compare T with F]
    I -- no --> K[Report no gain from management]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D,E,G,H,I,J new
    class C,F,K fail
```

Caption: All boxes are new. Red boxes end a step with a decision. "Stop" at box F is a real finding. Level 3 explainer: see ADR-24.

**Context.** Every earlier test ended at the ceiling, with plain notes doing as well as the skill. A staleness test could end the same way.

**Options.**
1. Run all arms at 8 runs at once.
2. Screen arm N first, then run the main batch.
3. Run only T and N.

**Choice.** Option 2. The screen costs about $0.30. If unmanaged notes never go stale, the main batch cannot show a gain, and we save about $3. The thresholds P2a to P2d in `architecture.md` are fixed before any run.

**Consequences.** Total cost is about $3 to $4.50, in steps of about $0.40, $0.30 and $3.

**What we gave up.** Three screen runs give a rough signal. A screen that passes by luck sends us into a main batch that ends with no gain. We accept that and report the counts.


## ADR-27: Announce the goal change in session 2 but do not let the code carry it

### Visual Level

```mermaid
flowchart TD
    A[S7 screen: arm N 0 of 3 stale, arm A passed in smoke] --> B{Can a change that code carries test memory?}
    B -- no --> C[Change S7: the code must not carry the change]
    C --> D[Session 2 prompt: rule r2 changes later, add the tests now]
    D --> E[Screen arm A: 3 valid runs]
    E --> F{At least 2 stale?}
    F -- no --> G[Stop. The change leaks into the repo]
    F -- yes --> H[Main batch: A 3, N 8, T 8, F 8]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A old
    class B,C,D,E,F,H new
    class G fail
```

Caption: Grey is the S7 result. Blue is the new flow. Red is a stop. Level 3 explainer: skipped. The change from S7 is one prompt and one turn cap, and level 2 shows every step and the one failure path.

**Context.** S7 could not tell the arms apart, because the repo held every fact. P2a stopped it. You asked to take the test further. The question is still whether memory goes stale, so the next test must hold a fact that only memory can carry.

**Options.**
1. Run the S7 main batch anyway. It would cost about $3 and end with every arm at zero stale runs.
2. Make the goal change reach memory but not code (this ADR).
3. Add a state event that tests cannot see, such as a silent change to price format. It needs a new mutation and guesses about which tests the agent writes.
4. Stop and report S7 only.

**Choice.** Option 2. It is the smallest change, and it reuses the built fixture, arms and scoring. Session 2 says: the owner announces that rule (2) will change to "qty largest first, then sku", the switch comes in the next session, and for now the agent adds the tests. The code keeps the old rule, so arm A cannot know the new one.

**Consequences.** One new prompt (`change8`), one scenario entry (`S8`), session 1 cap of 14. Scoring and the audit stay the same. The floor check P3a guards against a repeat of S7.

**What we gave up.** S8 tests the prompt log more than the tree. A tie between T and F is the likely result for the tree. "Switch later" is a setup that real work only sometimes has. If S8 also ends with no gap between T and N, the answer to your question for this size is that notes and the repo are enough, and a tree adds cost with no gain.


## ADR-28: Rerun S8 with an unambiguous session 3 prompt (S8b)

### Visual Level

```mermaid
flowchart TD
    A[S8: T and F 8 of 8 stale, agents waited on next session] --> B{Can the stale score tell forgetting from waiting?}
    B -- no --> C[New scenario S8b: session 3 says the change is in force]
    C --> D[Write thresholds P4a to P4d first]
    D --> E[Run A 3, N 8, T 8, F 8]
    E --> F{Arm A at least 2 of 3 stale?}
    F -- no --> G[Stop. The prompt leaks the rule]
    F -- yes --> H[Compare T with N and F]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A old
    class B,C,D,E,F,H new
    class G fail
```

Caption: Grey is the S8 result. Blue is the new flow. Red is a stop. Level 3 explainer: skipped. The change from S8 is one sentence in one prompt, and level 2 shows every step and the one failure path.

**Context.** S8 gave T and F 8 of 8 stale runs and N 4 of 8. I read 3 runs. The T and F agents knew the change and waited for "the next session". The stale score cannot tell waiting from forgetting.

**Options.**
1. Report S8 as it is. The headline is misleading, but no new run is needed.
2. Fix the prompt in S8 and replace its results. This hides the first result.
3. Add S8b with its own thresholds and report both (this ADR).
4. Change the score to read the final message for "deferred". This is subjective and a rough filter.

**Choice.** Option 3. S8 stays as run. S8b changes one sentence and has thresholds written first.

**Consequences.** One new prompt (`continue8b`), one scenario entry (`S8b`), no scoring change. The write-up reports S8 and S8b side by side.

**What we gave up.** I changed the prompt after seeing the result, which is a degree of freedom. I accept it and say so. The sentence tells the agent that a change exists, so arm A may guess. P4a checks that.


# Part 10: Horizon sweep (S9)

One explainer covers ADR-29 to ADR-33: [adr-29-33-horizon-sweep.html](visuals/adr-29-33-horizon-sweep.html).

## ADR-29: Replace one-scenario batches with one horizon sweep

### Visual Level

```mermaid
flowchart TD
    A[Today: one scenario, one level, one batch] --> B{Did memory arms hit the ceiling?}
    B -- yes --> C[No arm can beat notes. Build a new scenario]
    C --> A
    B -- no --> D[Report the gap]
    E[New: one task family at K = 1, 3 and 6] --> F[One batch, all levels mixed]
    F --> G{Do the arm curves split as K grows?}
    G -- yes --> H[Report where they split and by how much]
    G -- no --> I[Report no split over the range, with intervals]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D old
    class E,F,G,H,I new
    class C fail
```

Caption: Grey is the loop of Parts 1 to 9. Red is the costly path: a ceiling sends us back to build a new scenario. Blue is the sweep. Level 3 explainer: [adr-29-33-horizon-sweep.html](visuals/adr-29-33-horizon-sweep.html).

**Context.** Parts 1 to 9 ran eleven scenarios and more than nine batches. Most ended at a ceiling. Each ceiling or design flaw led to a new scenario and a new batch. The question of whether structure helps was never tested at a level where plain notes fail.

**Options.**
1. Build the greenfield S9 from `NEXT_STEPS.md`. It is one more single-level scenario.
2. Run S8b again at larger n. It is still at the ceiling, so n does not help.
3. One task family with a difficulty knob, run at several levels in one batch (this ADR).

**Choice.** Option 3. The knob is K, the number of owner decisions. The levels are 1, 3 and 6. The pilot may move them (open question 41).

**Consequences.** One fixture with six decisions and six small tasks. One batch. One chart: decision score against K, one line per arm. The greenfield S9 and the arm R plan are dropped.

**What we gave up.** Depth on any single scenario. The greenfield case, where the repo starts empty, is not tested. A sweep also needs a larger fixture up front, so the first build costs more than one more scenario would.

## ADR-30: Start every run from a fixed checkpoint

### Visual Level

```mermaid
flowchart TD
    A[Today: session 1 asks the agent to build the export] --> B{Did session 1 build both parts?}
    B -- no --> C[Invalid run. Pay for it and replace it]
    B -- yes --> D[Memory test starts from a state that differs per run]
    E[New: copy the S4 reference solution and commit it] --> F[Check that all six rules pass]
    F --> G{Do they all pass?}
    G -- no --> H[Fixture broken. Stop before any run]
    G -- yes --> I[Every run starts the memory test from the same state]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,D old
    class E,F,G,I new
    class C,H fail
```

Caption: Grey is the S7 to S8b flow. Blue is the checkpoint. Red is a lost run or a broken fixture. Level 3 explainer: see the top of Part 10.

**Context.** In S8 and S8b, 3 to 5 runs per batch were invalid because session 1 did not finish. Those runs cost money and told us nothing. The valid runs also started the memory test from different code, which adds noise that has nothing to do with memory.

**Options.**
1. Keep session 1 and raise its turn cap again.
2. Start from the S4 reference solution, committed as the first state (this ADR).
3. Let one agent build session 1 once, then fork that state for every run.

**Choice.** Option 2. The reference solution exists and passes the hidden tests. Option 3 would tie every run to one agent's code, with its quirks.

**Consequences.** No session-1 invalid runs. Every arm starts from the same bytes, so arm gaps are not driven by build luck. Cost per run falls by one session.

**What we gave up.** The sweep does not test memory while the agent builds a feature from nothing. The agent did not write the checkpoint code, so it may read it with less context than its own code. That is the same for every arm.

## ADR-31: Run four nested arms, A, L, N and T

### Visual Level

```mermaid
flowchart TD
    A[Arm A: no memory] --> B[Arm L: harness logs every human prompt and prints it at start]
    B --> C[Arm T: L plus a goal tree with live checks]
    D[Arm N: agent keeps NOTES.md]
    B --> E{Does L beat N at K = 6?}
    D --> E
    E -- yes --> F[Memory the agent cannot erase helps]
    E -- no --> G[Who writes the memory does not matter here]
    C --> H{Does T beat L at K = 6?}
    H -- yes --> I[The tree adds value beyond the log]
    H -- no --> J[The tree adds cost, no gain]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,C,D old
    class B,E,F,H,I new
    class G,J fail
```

Caption: Grey arms exist today (A, N and T from S7). Blue is new: arm L and the two contrasts. Red marks the negative readings, which are still results. Level 3 explainer: see the top of Part 10.

**Context.** Arm T in S7 to S8b bundled four things: a tree, live checks, a stop gate and a prompt log. A gain or a loss could not be traced to one of them. Your claim is that the agent erases its own memory and that the tree prevents it. To test that, one arm must hold memory that the agent cannot erase, with no tree.

**Options.**
1. Keep A, N, T and F as in S8b.
2. A full factorial: who writes the memory (nobody, agent, harness) times shape (flat, tree) times checks (off, on). That is 12 cells per level.
3. Four nested arms: A, L, N, T (this ADR).

**Choice.** Option 3. L is the prompt log alone, written by a hook. T is L plus the tree and the checks. N is agent-written. Each contrast changes one thing. The log for L and T is stored outside the workdir, so agent edits have no effect.

**Consequences.** Two new hook flags (Contract 34). Arm T changes in one way from S8b: its log moves outside the workdir. That makes T and L share the same log. Arms B, C, M and F do not run.

**What we gave up.** Arm F, so a T gain cannot be split into tree shape and live checks. S8 and S8b showed no T and F gap, so I accept this. The factorial would answer more, but at 3 times the cost. The block-mode scope effect from S1 to S4 is not re-tested.

## ADR-32: Score with graded measures, failure types and intervals

### Visual Level

```mermaid
flowchart TD
    A[Final repo of a run] --> B[Hidden tests score each changed rule]
    B --> C{Is the rule in its right final state?}
    C -- yes --> D[Count it as new]
    C -- no --> E{Does an older decision show?}
    E -- yes --> F[Count it as stale]
    E -- no --> G{Does the base rule show?}
    G -- yes --> H[Count it as forgotten]
    G -- no --> I[Count it as other]
    D --> J[Decision score, bootstrap intervals, Fisher test, one chart]
    F --> J
    H --> J
    I --> J

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B old
    class C,D,E,G,J new
    class F,H,I fail
```

Caption: Grey exists today: hidden tests on the final repo. Blue is new scoring. Red marks the three failure types. Level 3 explainer: see the top of Part 10.

**Context.** Parts 1 to 9 scored pass or fail per run and reported counts only. The write-up said 10 runs cannot support an interval. That is not true. An interval can be computed. It is wide, and showing that is honest. Pass or fail also throws away signal: a run that applies 3 of 4 decisions counts the same as one that applies none. The P1 keyword filter gave a wrong score once.

**Options.**
1. Keep counts and keyword filters.
2. Graded decision score and failure types from hidden tests, with bootstrap intervals (this ADR).
3. Option 2 plus a model judge that labels each memory snapshot for erasure, checked against hand labels.

**Choice.** Option 2. The first draft chose option 3. Published work changed that (see "Prior work" in `architecture.md`). Memory systems fail most on updates, where a newer fact must replace an older one. The hidden tests can tell a stale rule from a forgotten one, so the main question needs no judge. Bootstrap uses 10,000 resamples with a fixed seed. The all-correct rate gets a Wilson interval and a Fisher exact test. Memory snapshots are still saved, and I read the snapshots of failed runs by hand.

**Consequences.** One new script, `sweep_report.py`, standard library only. matplotlib is not installed, so the chart is a hand-built SVG. Each changed rule needs one hidden test per state it can be in (Contract 33).

**What we gave up.** A count of erasure inside the memory file. If an agent erases a decision from `NOTES.md` and then applies it from the code or by luck, the score does not see it. Hand reading gives causes but no number. The bootstrap interval is rough at n = 8 and can be too narrow. I state that in the write-up.

## ADR-33: Pilot, then freeze thresholds, then one mixed parallel batch

### Visual Level

```mermaid
flowchart TD
    A[Pilot: one run per arm at the top level] --> B[Read every pilot transcript]
    B --> C{Hooks fired, no leaks, arm N below the ceiling?}
    C -- no --> D[Change the design only: prompts, caps or K values]
    D --> A
    C -- yes --> E[Freeze thresholds Q0 and H1 to H5]
    E --> F[Shuffle all main runs with a fixed seed]
    F --> G[Run 4 at a time]
    G --> H{Total cost at the cap?}
    H -- yes --> I[Stop. Report the runs that finished]
    H -- no --> J[Score and report]

    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,B,C,E,F,G,H,J new
    class D,I fail
```

Caption: All boxes are new. Red boxes are a loop back to the design or an early stop. Level 3 explainer: see the top of Part 10.

**Context.** S7 and S8 each failed for a design reason that one cheap run would have shown. S7 leaked the facts into the repo. S8 had an ambiguous prompt. Both were found only after thresholds were written and a batch was paid for. Batches also ran one cell after another, so time effects, such as a model update, could fall on one arm.

**Options.**
1. Keep smoke, screen and main as separate stages per scenario.
2. Pilot first, then freeze thresholds, then one batch with all cells mixed in random order and run in parallel (this ADR).
3. Skip the pilot and rely on stop rules.

**Choice.** Option 2. The pilot may change the design. It may not change a threshold. Pilot runs are excluded from every claim. The main batch is shuffled with seed 9 and runs 4 jobs at once.

**Consequences.** New flags `--jobs` and `--order-seed`. The cost cap is checked before each run starts, so the batch may pass it by up to 4 runs. Wall time falls from about 8 hours to about 2.

**What we gave up.** The pilot tempts me to tune the design toward a favored arm. The rule that thresholds stay fixed is the guard, and I list every pilot change in the write-up. Parallel runs can hit rate limits. A rate-limit error makes the run invalid and it is replaced, which costs money.


## ADR-34: Add a quiz and neighbor tests to split forgetting from drift

### Visual Level

```mermaid
flowchart TD
    A[Release session ends] --> B[Resume once: multiple-choice quiz, no tools]
    B --> C[Hidden tests on rules, neighbors and unrelated rules]
    C --> D{Is the changed rule right in the code?}
    D -- yes --> E[Count it as done]
    D -- no --> F{Was the quiz answer right?}
    F -- yes --> G[Knows-but-violates: drift in action]
    F -- no --> H[Did not know: forgetting]
    C --> I{Did a neighbor or an unrelated rule change?}
    I -- yes --> J[Spillover or unrelated loss]
    I -- no --> K[No drift outside scope]

    classDef old fill:#e5e5e5,stroke:#777,color:#222
    classDef new fill:#cfe3ff,stroke:#2a62b8,color:#10264d
    classDef fail fill:#ffd6d6,stroke:#b82a2a,color:#4d1010
    class A,E,K old
    class B,C,D,F,I new
    class G,H,J fail
```

Caption: Grey exists in Part 10 before this ADR. Blue is new. Red marks the three kinds of failure this ADR can tell apart. Level 3 explainer: [adr-29-33-horizon-sweep.html](visuals/adr-29-33-horizon-sweep.html), which also covers this ADR.

**Context.** You proposed a second cause of drift. A new decision takes priority over old goals, so the agent drifts toward it, into related code and away from unrelated goals. It drifts even though it still knows the old goals if asked. The Part 10 score cannot see this. A wrong rule looks the same whether the agent forgot it or knew it and did not act. A change in a related place is not checked at all. Published work names the first pattern "knows-but-violates".

**Options.**
1. Keep Part 10 as it is. It answers the memory question only.
2. Ask the agent to restate the rules in free text, and score it with keywords or a judge.
3. A multiple-choice quiz, one neighbor test per decision, and a scored count of unrelated losses (this ADR).

**Choice.** Option 3. Grading of multiple choice needs no judge. Neighbor tests are plain hidden tests. Two new thresholds, H6 and H7, are written now, before the pilot.

**Consequences.** One resumed turn per run, under $1 for the batch. Four neighbor tests, one quiz file and new `run.json` fields (Contracts 33, 35 and 37).

**What we gave up.** The options show the right answer, so an agent that forgot can recognize it. Knows-but-violates can read too high. Free text would avoid that, but it needs a judge, and ADR-32 dropped the judge. The quiz comes after the release session, so the agent may have just read its memory file. That measures "can it find the rule", not "does it hold the rule in mind". The design still cannot show the mechanism inside the model.
