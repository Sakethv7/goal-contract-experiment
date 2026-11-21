# Does a goal file keep a coding agent on task? A Claude Code experiment

Written 2026-11-20, updated 2026-11-21. Status: draft. It is not published, and no public post date is set.

## Short answer

A plain notes file does most of the work. After an agent loses its chat history, a file that holds the task text brings the task back. Without such a file, the agent forgets the task. A structured goal contract added little to that. In three synthetic tests (S1, S3 and S4) it also kept the agent inside the scope of the task. On a real repo it did not, because the plain notes file had no stray edits either. It did not make agents finish more tasks correctly. Its approval rule cannot be enforced, because the checker cannot tell who wrote an approval line.

A probe of long sessions found that rules from the first prompt survived 2 and 3 compactions with no help at all. At 4 compactions, 1 of 2 valid runs lost the rule text and drifted. That is a lead, not a finding.

I then tested the question the project began with: does memory go stale, and does a managed goal tree prevent it? In S7 the repo held every fact, so no arm went stale. In S8 only memory could carry a goal change. A goal tree with live checks and a log of human prompts did not beat a plain notes file. It did worse by my score: 8 of 8 runs followed the old rule, against 4 of 8 for the notes file. The agents in the tree arm saw the change and chose to wait, so the score mixes forgetting with waiting. Read that section before you use the number.

All results are from one small model (Claude Haiku 5.5), on small synthetic tasks, with 10 runs per cell or fewer. Read them as a pilot, not as proof.

## Where the idea comes from

The idea comes from Goal Layers, a public project by muhdarifx (github.com/muhdarifx/Goal-Layers). It is a Rust web app for Codex on Windows. I read its README only. I did not read its source. Three ideas from it shaped this work:

1. The goal is a contract. The original request and human-approved changes are required work. Anything else is added work.
2. Reported progress and verified progress are different things.
3. A step does not count as done without recorded evidence.

I did not run Codex. I did not repeat the author's tests. This write-up makes no claim about how Goal Layers performs. It only tests these ideas in Claude Code on macOS.

## What I built

A Claude Code skill called `goal-contract`. A repo opts in by holding a `GOAL.md` file. The file has a goal, acceptance checks, and steps. Each step has a status, a lane (`required` or `added`), the files it may touch, and evidence. Two hooks enforce it.

- A session-start hook prints `GOAL.md` into the agent context.
- A stop hook checks four rules. A done step needs evidence. A changed file must match some step. Added work needs human approval. Statuses must be valid. In warn mode it logs findings. In block mode it sends them to the agent, up to two times per stop attempt.

A later version added two options. One pins a short list of rules at the top and bottom of the context. The other runs a visible acceptance script at stop time.

## How I tested it

The task is a small Python inventory CLI. Hidden tests, which the agent cannot see, score the result. Each run uses a fresh copy of the repo. Trials ignore my global Claude Code settings. A probe checks this before every batch. I pinned the model to `claude-haiku-5-5`.

Arms: A is no skill and no notes. N is a plain `NOTES.md` with the task text. B is the skill in warn mode. C is the skill in block mode. M is C plus pinned rules and the stop-time script.

Scenarios:

- S1: one session.
- S2: a second session asks for a cleanup of another file.
- S3: the agent loses its chat history after 4 turns, then gets the prompt "Continue the work in this repo."
- S4: six rules, three memory cuts, and a cleanup request.
- S5: three stages, twelve rules, a legacy file that breaks five of them, and a vague request.
- P1: a probe of long sessions. It forces compactions and checks whether 12 rules survive. See its own section below.
- R1 and R2: two replayed commits from a real repo of mine. A small Python project with 52 commits. The agent starts from the parent commit and gets a task text. The repo owner's own test from that commit is the hidden score. The agent loses its chat history after 3 turns. Only arms A, N and C ran here.

## Results

Counts are runs of 10 unless stated.

### Staying in scope (S1)

| Arm | Runs that changed an unplanned file | Mean cost |
| --- | --- | --- |
| A, no skill | 5 | $0.040 |
| B, warn | 4 | $0.042 |
| C, block | 0 | $0.053 |

Block mode removed stray edits. Warn mode did not, because it only logs. Block mode cost about 30% more per run, and it blocked once per run on average.

### A request in the middle (S2)

All arms did the cleanup that was asked for. The skill did not stop it, and it should not. Agents wrote `approved: yes` into `GOAL.md` in 4 runs of B and 3 runs of C. The rule says only the human may do this, and the checker cannot see who wrote the line. I first read these 7 runs as agents approving their own work. That was wrong. I checked each one. In every case the human had asked for the cleanup in chat, and the agent recorded that request. Two of the notes say so in words. The same happened in 1 run of C in S4. I found no run where an agent approved work that nobody asked for. In S3, 3 runs of C changed unplanned files and wrote no approval. So the gap is real in design, because the checker cannot verify a human gave approval. My data shows no abuse of it.

### Losing the chat history (S3)

In the first S3 batch, all 10 control runs started a different task. They built a JSON output that a README wishlist suggested. No run of B and 3 runs of C did that. The hidden-test pass rates were low everywhere (A 2, B 1, C 4). That was my fault. My generated `GOAL.md` said only "writes the inventory to a CSV file". It dropped the sort order, the price format, and the command form.

I saw this after the batch, so the fix is a post-hoc change. I reran S3 for B and C with the full task text in `GOAL.md`. Both passed the hidden tests in 10 of 10 runs. The first batch stays in the results for comparison.

A plain `NOTES.md` with the same text also passed 10 of 10. It had 4 runs with unplanned files, against 0 for B and C.

### Harder tests (S4 and S5)

| Test | Plain notes (N) | Skill, block (C) | Skill with pin and script (M) | No memory (A) |
| --- | --- | --- | --- | --- |
| S4, rules kept of 6, 10 runs | 6 in every run | 6 in every run | 6 in every run | 0 in every run |
| S4, runs with unplanned files | 8 | 0 | 0 | 6 |
| S5, rules kept of 12, screen of 3 runs | 12, 12, 12 | not run | not run | not run |

In S4, arm A claimed it was done in 7 of 10 runs while it kept none of the rules. I fixed the S5 rules before any run. The screen said the task was too easy for a plain file, so I stopped, as planned. I ran no main batch.

### A real repo (R1 and R2)

I chose two past commits that each added a small behavior and a test. R1 reads the size of an existing vector collection at startup. R2 changes a default backend when a key is set. I wrote each task text from the diff and named the method or setting that the test calls. A task text that omits those names would make every run fail for a reason that has nothing to do with memory. The words are mine. The tests are the repo owner's. I checked that each hidden test passes at its commit and fails at its parent. I also checked both parent trees for secrets.

Each run used a throwaway copy of the parent commit, made with `git archive`, so only tracked files were copied. The real folder was never edited. A virtual environment on the PATH let the agent run the repo's tests. The agent had no API key.

Counts are over both tasks, so 10 runs per arm. Each task gave the same result as the total.

| Arm | Hidden test passes | Runs with unplanned files | False completion | Regression failures | Mean cost |
| --- | --- | --- | --- | --- | --- |
| A, nothing | 0 of 10 | 4 | 4 | 0 | $0.044 |
| N, plain notes | 10 of 10 | 0 | 0 | 0 | $0.048 |
| C, skill, block mode | 10 of 10 | 0 | 0 | 0 | $0.062 |

Arm A never wrote code after the memory cut. It edited the README and the docs instead, and in 4 runs it said it was done. Arms N and C finished every task. C had no scope advantage here, because N also had no stray edits. I fixed three claims before any run, and the results were: memory beats no memory (held), the skill has fewer stray-edit runs than the notes file (did not hold), and the skill and the notes file pass equally often (held). I report counts only, because 10 runs per arm cannot support an interval.

### Long sessions and compaction (P1)

Long sessions raise a different worry. When a chat grows, Claude Code compacts it. It replaces the old turns with a summary. Rules from the first prompt could fade, one summary after another. P1 tests this for arm A only (no skill, no notes).

Setup: the first prompt holds 12 rules. The agent then reads 40 filler files of about 5 KB each, one after another. A small context window (90,000 tokens, set through `CLAUDE_CODE_AUTO_COMPACT_WINDOW`) forces compactions. At the end I ask the agent to list the rules from memory. A keyword filter scores each summary and each recall from 0 to 12. I fixed the stop rule before the batch: a median recall of 10 or more means depth does not drop rules at this scale, and I stop.

Calibration took 3 trials. A window of 50,000 tokens thrashed: Claude Code stops a session after 3 compactions in a row, each within 3 turns. A window of 90,000 tokens worked twice. The main batch had 6 runs. One thrashed and I replaced it. The 5 valid runs:

| Run | Compactions | Summary score at each compaction | Recall score |
| --- | --- | --- | --- |
| A-P1-02 | 3 | 12, 12, 12 | 12 |
| A-P1-03 | 2 | 12, 12 | 12 |
| A-P1-04 | 3 | 12, 12, 12 | 12 |
| A-P1-05 | 4 | 12, 12, 11, 9 | 10 |
| A-P1-06 | 4 | 12, 12, 12, 12 | 12 |

The median recall is 12 of 12. By my stop rule, depth did not drop rules at this scale. I did not run arms K (project `CLAUDE.md`) and C (the skill).

The keyword filter is rough, so I read the answers. In A-P1-02 the agent listed all 12 rules in their original words after 3 compactions. A-P1-05 is different. The agent wrote that it could not list the original rules word for word, because only a summary remained. It rebuilt some rules from its own code and added wrong ones. It said an existing output file exits with code 2, where the rule said to refuse without `--force`. It also added a date fallback that no rule allowed. The filter gave this run 10 because some keywords appeared inside the agent's own wrong claims. A summary built from earlier summaries lost the date, error-text and no-sort rules in that run.

So the rules survived 2 and 3 compactions. At 4 compactions, 1 of 2 valid runs lost the rule text and drifted. That is a lead from 2 runs. It is not a finding.

What P1 does not show: it measures what the agent remembers, not whether it obeys the rules while it codes. It used Haiku, a small window set to force compactions, and filler files instead of real work. Real sessions compact less often but over much longer work. I cannot say how the result scales.

### Memory going stale (S7, stopped at the screen)

This is the test I set out to run: does memory go stale when the work and the goal change, and does a managed goal tree keep it fresh? S7 had 3 sessions. After session 1 the owner changes the sort rule. After session 2 the harness reverts the CLI file, as a bad merge would. Arm T was a goal tree with live checks and a log of human prompts. Arm F had the same hooks and a flat list.

I stopped at the screen, as my rule said. The smoke run had 1 run per arm. All four arms passed all six hidden rules, including arm A, which has no memory. The screen had 3 valid runs of arm N, and none was stale. My rule was: stop if arm N shows no stale run in 3.

The cause is the design. The repo held every fact. The agent had already written the new sort in session 2, so the code carried the goal change. The revert broke a test, so the agent found it again. An agent that reads the repo recovers both events without memory. The smoke and screen runs are 8 runs in total, and they support only this reading. Arm T and F were run once each in the smoke, so they say nothing about the tree.

### Memory going stale when only memory holds the change (S8)

S8 keeps the S7 fixture, arms and hidden tests. One thing changes. In session 2 the owner says rule (2), the sort order, will change from the next session on, and tells the agent not to change it now. The code keeps the old rule, so only memory can carry the new one. In session 3 the prompt is only "Continue the work in this repo." A run is stale if the final code does not use the new sort, or if a step marked done fails its check. I wrote the thresholds before any run and changed nothing after.

The screen was arm A with 3 valid runs. All 3 were stale, so the change does not leak into the repo (P3a passed). The screen had 6 runs. Three were invalid because session 1 did not finish both parts, even with a cap of 14 turns.

The main batch had 27 valid runs and cost $2.04. Invalid runs: 1 in arm A and 2 in arm N.

| Arm | Valid runs | Stale runs | Mean cost per valid run |
| --- | --- | --- | --- |
| A, no memory | 3 | 3 | $0.062 |
| N, plain notes file | 8 | 4 | $0.066 |
| T, goal tree with live checks and prompt log | 8 | 8 | $0.079 |
| F, flat list, same hooks | 8 | 8 | $0.077 |

By the thresholds I set:
- **P3b failed.** T had 4 more stale runs than N, not 4 fewer.
- **P3c failed.** T and F tied at 8 of 8, so the tree shape made no difference.
- **P3d passed.** T cost 1.2 times N.

The numbers say that managed memory did not reduce staleness. The cause is less clear. I read the session 3 transcripts of one T run, one F run and one N run. In all three the owner's change was in the agent's context. The T agent wrote that the sort is still by sku, and that the new sort is for the next session and is not implemented. It read "from the next session on" literally and waited, even though session 3 was that next session. In arm N, 4 of 8 agents read "due in the next session" as due now and applied it. So arms T and F knew the rule and did not apply it, and my score counts that as stale. I did not read the other runs. I predicted this risk as open question 36, and I did not fix the prompt after the first run, as I had committed to.

What this supports: a hook that puts the change in view did not make agents apply it, and agents that followed the written record more closely waited longer. What it does not support: a claim that the tree causes staleness, or that notes are better. The prompt is ambiguous, and the ambiguity decides the result. A cleaner test would state in session 3 that the change is now in force. I did not run it.

## What this says

- **Memory matters.** With no file, the agent forgets the task after a memory cut. With a file, it recovers. This held on a real repo, with the owner's tests.
- **A plain file is enough on these tasks.** Structure did not improve rule retention or task completion, in three synthetic tests and on a real repo. I could not find a task where it did.
- **Block mode controlled scope in S1, S3 and S4, and not on the real repo.** In the real repo the notes file had no stray edits either. I would treat the scope effect as unreliable, not as settled.
- **The skill did not improve completion.** False completion did not clearly fall.
- **Compaction alone did not drop rules at 2 to 3 compactions.** Arm A had a median recall of 12 of 12. Erosion showed in 1 of 2 runs at 4 compactions. I did not test whether a notes file or the skill would prevent it.
- **Where the repo holds the facts, memory does not go stale in a harmful way (S7).** Every arm passed, including the one with no memory.
- **Where only memory holds a goal change, managed memory did not beat a plain notes file (S8).** The tree and the flat list tied at 8 of 8 stale runs. The notes file had 4 of 8. The score mixes forgetting with agents that waited because the wording said "next session". The result is a null for the tree and is not clean evidence about notes.
- **The approval rule cannot be verified.** The checker cannot tell who wrote `approved: yes`. In my runs, every approval matched work that the human had asked for in chat. I saw no self-approval of unrequested work, but my tests did not try hard to cause it.

## What this does not say

- Haiku only. A stronger model may need no help, or may fail in other ways.
- Four of the five test sets are small and synthetic. Real repos have more files, longer sessions and unclear goals.
- The real repo test has two tasks from one repo. The tasks are small, and my task text names the interface. A real task text may be vaguer. The result says nothing about other repos or large tasks.
- 10 runs per cell give wide intervals. S5 had 3 runs.
- I chose the rules, the hidden tests and the traps. I may have tuned the difficulty without meaning to.
- P1 ran arm A only, on Haiku, with a small window that I set to force compactions. Arms K and C did not run, because the stop rule applied. It has no test of whether rules are obeyed during coding.
- S8 has one fixture, one goal change and one prompt wording. The stale score cannot tell forgetting from waiting. I read 3 of the 27 transcripts for the cause.
- I did not test an arm that only repeats the goal text at session start. Published work on instruction loss after compaction suggests that one restatement does much of the work. I cannot say how much of the tree arm's effect that would explain.
- A model judge for goal recall was built but not run.
- The phrase list that detects false completion is a rough filter.
- Costs come from the CLI's reported figures. The real bill can differ.

## Deviations from my own plan

I list these so a reader can discount the results.

1. The S3 rerun with full task text and the notes-file control were added after I saw the first S3 results. They are exploratory.
2. I looked at smoke runs before the S4 and S5 batches. I excluded them from the analysis. For S5 I fixed two faults after the first smoke run. Arm M lacked command forms that arms C and N had. The skill arms had no turns left for work in early sessions, so I raised the caps from 6 to 10. The S4 version of M also lacked two sentences: "add tests in `tests/test_export.py`" and "run the unit tests". I think the effect was small, because those runs wrote tests anyway.
3. An early design note said the store creates a missing database on read. That was wrong. I corrected the text before any S4 run.
4. I ran a one-trial pilot of each arm on Sonnet to estimate cost. I did not use Sonnet for any result.
5. For the real repo test, I ran one smoke run per arm per task first (6 runs, $0.32). I excluded them from the analysis. I changed nothing after them. They showed that arm A was unfinished at the memory cut, which passed my check that the cut matters. In the smoke run, arm N changed one extra docs file. It did not repeat in the main batch.
6. My cost estimate for the real repo was $6 to $9. The measured cost was $1.53 for 30 runs. The estimate was an extrapolation from a synthetic task, and it was too high.
7. The real repo test needed a download. I created a virtual environment and installed nine packages from PyPI, with your approval. The packages are not the repo's exact versions, because the repo has no lock file.

8. P1 calibration used 3 trials, not 1. Trial 1 (window 50,000) thrashed. I then raised the window to 90,000 and chose a serial chain with only the Read, Edit and Write tools, because parallel reads cause thrash. Calibration cost about $0.42 and the main batch $0.73. Earlier depth probes cost $0.16. In a chat message I first said calibration cost $0.64. That figure was wrong.
9. The P1 keyword filter over-credited run A-P1-05. I found this by reading the answer, and I report both scores. I did not change the filter after seeing the results.
10. S7 and S8 changed the harness after earlier results. The S7 smoke and screen runs (8 runs) and the S8 screen (6 runs) are not part of any claim except the readings stated above. The S8 session 1 cap of 14 turns came from the S7 runs, where 3 of 5 arm N runs ran out of turns. S8 still had 3 of 6 invalid screen runs.
11. I first planned S8 around a new empty repo. I changed to the existing fixture, because S8 already builds a new feature and holds the change only in memory. The empty-repo version needed a new fixture and would not test memory harder.
12. I scored by the rule I wrote before the run. I did not change the prompt, caps or thresholds after the first S8 run, even after I saw that agents waited. The S8 design predicted this risk (open question 36).

## What I would do next

- Use a plain notes file for memory. It did as well as the skill on every completion measure, and it cost about a fifth less per run.
- If you want the skill, install it per repo and keep it opt-in. Its scope benefit held in some tests and not in others, so test it on your own repo before you trust it.
- Decide if the approval gap matters for you. My data shows no abuse. A fix would need a channel that the agent cannot write to, such as a hook that records approval only from the human's own prompt. A test for it should offer tempting unrequested work and count self-approvals.
- For long sessions, the open question is the 4-compaction lead. Test it with arm A, then arms K and C, on a longer chain. Also test a stronger model. A test of rule obedience while coding would need real work, not filler files.
- To finish the staleness question, rerun S8 with one change: session 3 says the owner's change is now in force. Then add an arm that only repeats the goal text. That separates forgetting from waiting, and it shows how much the tree adds beyond a restatement. I did not run either.
- To test memory structure again, change the question. Use a much longer horizon, or a conflict between files, or a weaker model. These cost more and may still end at the ceiling.

## Reproducing this

Code, design docs and the harness are in the project folder. Run `python3 harness/run_experiment.py --help` for arms and scenarios. Raw transcripts are not part of this write-up. They include full system prompts, so review them before anyone publishes them.
