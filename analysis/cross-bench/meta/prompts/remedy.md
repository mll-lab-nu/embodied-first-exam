# Remedy annotation prompt (prompt id `remedy-1`)

You are an expert in robot control and in coding agents. For each **failed** trial (already reviewed), name the
smallest concrete change that would most likely have turned it into a pass, and who would have to make it. This is a
counterfactual judgment from the review text; be specific and honest about uncertainty.

## Input

`$BATCH`: JSONL, one failed trial per line: key, agent, bench, mode, headline, failure (stage, primary, secondary,
decisive, no_return_t, evidence), best_progress, time (stop_reason, wasted), notable, style notes, approach summary.

## Remedy codes (`fix` = the main one; `also` = up to two more)

Agent side:
- `grasp-check`: lift a little and check the hold (opening, contact, image) before big moves; check support before release
- `hand-geometry`: calibrate where the fingers / TCP / grip site really are, closing axis, mirrored hands
- `grasp-choice`: choose the grasp from geometry and mass (near the centre of mass, the graspable part, the whole container)
- `closed-loop`: replace an open-loop plan by closed-loop execution or per-segment checks
- `safety-guard`: abort or slow down on danger signals already printed (tilt, force, gripper drift, planner failure)
- `path-check`: check the path / clearance before transitions, retreats, base moves and probes
- `perception-check`: confirm object identity and position (second view, depth, segmentation sanity) before acting
- `verify-real`: measure the own model / simulator / deliverable against the real environment (fresh-process replay, test sheet, t=0 observation) before the graded run
- `debug-own-code`: check the own helpers, units, frames, signs and parameters before blaming physics
- `time-plan`: watch the clock, plan to the budget, save a graded deliverable early, stop only when really out of time
- `reset-plan`: spend resets as experiments with a reserve; do not burn them on tiny probes
- `pivot`: after repeated no-progress attempts, change method or re-test the premise
- `feasibility-recheck`: before declaring "impossible", try another contact or strategy
- `read-spec`: read the instruction / success rule / robot spec correctly (goal, constraint, units, deliverable format)
- `skill-gap`: needs real control skill (gait, dynamic manipulation, dexterous in-hand) that no small change gives
Harness side:
- `harness-process`: background processes, end-turn hints, killed children, blocking commands
- `harness-context`: context compaction lost state (time, conventions, progress)
Task side:
- `task-side`: grader, instruction or environment problem (not the agent's)

## Output, one file per trial: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/annot/remedy/<key>.json`

```json
{"key": "...", "prompt": "remedy-1", "fix": "<code>", "also": ["<code>"], "who": "agent | harness | task",
 "fix_note": "一句中文：最小的、具体的改动", "why": "一句中文：依据（分析里的时刻或事实）",
 "would_pass": "likely | maybe | unlikely", "general": "一句中文：这条改动作为通用做法能写成什么规则（给 agent 或 harness）"}
```

Rules: `fix` is the change closest to the decisive error; if only a big capability jump would help, use `skill-gap`
with `would_pass: unlikely`. Chinese for the text fields. Never use the word "oracle". Reply with one line: files
written and a count per `fix`.
