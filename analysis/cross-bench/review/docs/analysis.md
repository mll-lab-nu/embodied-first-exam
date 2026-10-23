# How a trial is analyzed

**Rule of the method: a script measures what can be measured; a model writes only what needs reading, and every
item it writes carries verbatim quotes with event ids, so a program and a person can check it.** The model reads one
evidence packet and writes one recap (prompt: [../prompts/recap.md](../prompts/recap.md), self-contained). Code checks
it and adds the measured parts. The names are those of the cross-bench report's codebook (`../meta/codebook.json`),
so the review pages and the report use the same words.

## Layers of a recap

In the order of the report's failure chapters (§4–§5):

| layer | content | written by | checked by |
|---|---|---|---|
| end | how the trial ended (`goal-done`, `time-out`, `resets-used`, `deliverable`, `agent-stopped`, `crash`) + one-sentence result | model + quote | quote found in the log |
| claim | what the final message says (`correct-success`, `false-success`, `knows-failed`, `no-claim`, `matches-live`) | model + quote | quote; grader result |
| progress | highest level 0–5 and the first event of each level reached | model + quotes | one quote per level |
| failures | every place something went wrong: what, cause code, the failure quote, the consequence, recovered or not; one `primary` per failed trial (the earliest failure without which it most likely would have passed) | model + quotes | the failure quote must be found |
| point of no return | the first event after which passing was impossible and no reset could undo it: type, what the agent did after, whether it noticed | model + quote; time left by script | quote |
| decisions | high-level errors as decision points (below) | model + quotes; resources by script | "known" must come before the decision |
| time | `no-clock`, `late-deliverable`, `overlong-command`, `idle-wait`, `early-stop`, `timeout-no-deliverable`, `budget-exhausted` | script (`timing.py`) | thresholds fixed in code |
| fix | the one step that most likely would have changed the result; would it pass (`likely`/`maybe`/`unlikely`); who can do it (agent / harness / task) | model, inferred | not in headline numbers |
| style | plan first or act first; after failures tweak or pivot; verification none / light / thorough | model + quotes | quotes |
| unclear | what the model could not decide, and why | model | shown, not judged |

### Progress levels (all tasks)

| 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| not in control yet | robot moves or perception works | reached the target area | key action done once | most of the task done | done |

### Failure causes (54 codes in 11 groups; full table in the prompt)

| group | codes |
|---|---|
| understanding | misread-goal, wrong-metric, constraint-ignored |
| interface | api-misuse, action-space, frame-convention, control-rate, reset-semantics, spec-misread |
| perception | localization, camera-model, depth, brittle-segmentation, no-perception |
| control | grasp-contact, balance-fall, instability, ik-limits, collision, precision, dynamic-timing, no-safety-guard |
| planning (steps) | sequencing, long-horizon, no-recovery, open-loop-misuse |
| method | unsuited-paradigm, stuck-tweaking, over-engineering |
| verification | no-verification, overfit-resets, own-check-differs, replay-mismatch |
| time | no-clock, no-time-plan, late-deliverable, overlong-command, idle-wait, misjudged-time, early-stop, timeout-no-deliverable, budget-exhausted |
| metacognition | early-give-up, looping, ignored-errors, hallucinated-result, context-loss, instruction-drift |
| deliverable | invalid-deliverable, not-saved, regression |
| external | grader-nondeterministic, spec-conflict, infra-loss |

### High-level errors (decision kinds)

| group | kinds |
|---|---|
| understanding error | task-reading (goal, bar, constraint or format misread), world-model (wrong untested belief about robot, scene, physics) |
| method error | strategy (the chosen approach cannot work here) |
| planning error | planning (no plan for time, steps or resets) |
| checking error | self-check (did not verify), diagnosis (blamed the wrong cause) |
| adapting error | persistence (kept the same approach after repeated failures), giving-up (stopped while progress was possible) |

## Decision points: when a high-level error counts

Each decision error has four slots; a decision without the second one is not an error (it goes to `unclear`):

| slot | content |
|---|---|
| decision | the quote where the agent made the choice (message, reasoning, or the action) |
| known | 1–3 quotes from **earlier** events (or the task text) showing it already had the information that should have changed the choice |
| resources | minutes and resets left at the decision (script) |
| consequence | the quote of what the decision led to, and the failure it caused |

`check.py` orders the quotes by event position; a `known` quote at or after the decision is marked late and dropped,
and the decision fails the check if none is left. This writes "no hindsight" into the format. What can be measured
about time (clock checks, late deliverable, long commands, idle waits, early stop, budget) is left to the script; the
model writes only time decisions it can quote (no time plan, misjudged time).

## Evidence rules (in the prompt)

1. Quotes are verbatim, 15–200 characters, one piece, from the packet or the full-text search; a quote not found
   makes its item "not supported" (it stays on the page, marked, with the reason).
2. A "did not" statement needs two full-log searches with hit counts.
3. Reasoning text can be used, marked `think`; comparisons across agents should use messages and actions only (some
   harnesses log no reasoning).
4. Every failure and every decision error is listed, not only the main one; each is judged on its own.
5. When the log does not decide, the model says so in `unclear`.

## Script time codes (`pipeline/timing.py`)

| code | fires when |
|---|---|
| no-clock | no command ever read the elapsed or remaining time |
| late-deliverable | first submit (standard) or first saved output after half the budget, or never |
| overlong-command | one step started with t minutes left and ran ≥ 0.9 t (and ≥ 1 min) |
| idle-wait | ≥ 5 min of consecutive steps that only wait (sleep, poll, tail a log) |
| early-stop | failed, ended by itself (`agent-stopped`) with ≥ 25% of the budget left |
| timeout-no-deliverable | timed out without any submit |
| budget-exhausted | resets used up (the budget is read from the task text) |

## From recap to review cards (`pipeline/pages.py`)

| section | one card per | title | quotes shown |
|---|---|---|---|
| end | end, claim | 结局 · <end>, 自述 · <claim> | evidence, final message |
| progress | trial | 最高第 n 级 | one per level |
| failure | failure | 主因 / 失败 · <cause> | 出事, 后果 |
| no_return | point of no return | <type> · 之后<after> | the event |
| decision | decision | <group> · <kind> | 决定, 当时已知 (late ones flagged), 后果 |
| time | time code | <code>（脚本） | its events |
| fix | trial (failures only) | <fix> · 翻盘<would_pass>（推断） | — (reason shown) |
| style | trial | 做事方式 | evidence |

Verdicts on a card: **正确** (the claim holds and the quotes support it), **不认同** (the log contradicts it or a better
reading exists; say which in the comment), **证据不足** (it may be true but the quotes do not show it).

## Evaluating the labels (can a model label alone?)

| question | test | 10-trial pilot (10-22) |
|---|---|---|
| are the quotes real | `check.py` finds each in the full log | 235/235 |
| no hindsight | "known" before the decision | 13/13 |
| do errors explain failures | the primary failure is linked to a checked decision | 4/6 failed trials |
| agreement with earlier labels | `summary.py` vs the report's labels | progress 8/9, no-return 2/3, high-level 4/6, fix 2/6, primary cause 1/6 |
| do people agree | verdicts in `judgments.csv`, per category | pending |
| is it stable | label the same trial twice | not done |

A category is ready for model-only labeling when people accept it in ≥ 80% of ≥ 20 cases and it is clearly rarer in
successes than in failures. The single "primary cause" is the least stable label: most disagreements describe the
same event from two sides (e.g. "over-engineering" vs "no time plan" for 45 minutes spent on an offline planner), so
report counts should count every failure, and use the primary cause only after a person confirmed it.

History: a first version asked nine fixed yes/no questions (Q1–Q9) and derived categories by rules; it could not
tell failures from successes and derived "planning errors" from outcomes. It was replaced by this recap on 10-22.
