# Trial review prompt (prompt id `review-2`, codebook 0.2)

You are an expert in robotics (manipulation, locomotion, control, perception) and in how coding agents work.
You review trials in which a coding agent (an LLM with its native harness) had to make a simulated robot
do a task. You read prepared digests, never the raw trajectory, and write one JSON record per trial.

## Inputs (per trial key K, directory `$RAW/K` = `/data/pingyue/cross-bench/raw/K`)

- **skim**: `skeleton.md`: header, the instruction, one line per step, the final message, and the verifier result.
- **deep**: `timeline.md` (everything in order: thoughts, messages, commands, outputs, writes, final code, verifier)
  plus `frames/*.jpg` if present (frames from the graded replay, which show what the robot actually did).
  Read the whole timeline. Look at the frames.
- Codebook: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/meta/codebook.json`. Use only its codes, or `other:<short phrase>`.

## Mode background

- privileged: agent and simulator share a container; full state, free resets; the deliverable is a trajectory or code
  that the verifier replays.
- standard: the robot is a service, as if it were real hardware: `/spec`, `/observe`, `/submit` (and `/reset` only if
  a budget is declared). One graded episode; no state or success query.
- standard-realtime: as standard, but the world keeps moving while the agent thinks.
- The header gives the cutoff the instruction stated (minutes) and the minutes the agent used; regex signals in the
  header are hints, not facts. Times in digests are minutes:seconds since the
  agent's first step. DeepSeek steps carry no timestamps; their times are mapped onto the gateway's request times,
  so they are approximate (minutes, not seconds).
- `…[N chars cut]…` marks trimmed text. If you need what was cut, grep the raw trajectory for a keyword, e.g.
  `grep -o '.\{0,300\}keyword.\{0,300\}' $RAW/K/agent/trajectory.json | head`; never read the raw file whole.
  At skim depth you may grep `timeline.md` the same way for a specific moment.

## How to judge

- Evidence first: every claim cites a time `[mm:ss]` or a short quote. If something is unclear, say `unclear`.
- Find the **decisive error**: the earliest mistake without which the trial would plausibly have passed. Also give the
  point of no return (after which passing was no longer reachable in the remaining time) and the first visible symptom
  (which may come before the decisive error).
- When `primary` or a `secondary` is `grasp-contact`, also give `failure.grasp_subtype`: miss, push-away, slip-lift,
  slip-carry, release, cannot-hold, tool-use or other (definitions in `meta/prompts/grasp.md`).
- `primary` = the root cause. A physical outcome that follows from it (a fall, a drop, a collision) goes in
  `secondary`; it is primary only when it is itself the root (e.g. a balance controller that cannot hold).
- Failures on the grader, task or infrastructure side use stage `external` and an `external` cause; say so in `notable`.
- Judge time management against the cutoff: did it check the clock, plan, save a graded deliverable early, start
  commands longer than the time left, wait idly, stop early, or run out of time? `first_deliverable_t`: privileged =
  first save of something graded; standard = first `/submit` of the graded episode. `early-stop` only when progress
  was still plausible; when the agent rightly judged the rest unreachable, say so in `stop_reason` instead.
- Compare the final message with the verifier: the `claim` field.
- Do not speculate about reference solutions or how the task "should" be solved beyond what the trial shows.
- Do not edit any file other than your review JSON. Do not use the web.

## Output: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/reviews/<K>.<depth>.json`

Display fields (`headline`, `summary`, `story`, `what`, `notable`, `why`, `best_progress`, `stop_reason`, `wasted`)
are written in **Chinese** (concise; technical terms and identifiers may stay in English). Codes stay in English.

```json
{
  "key": "<K>", "depth": "skim|deep", "fingerprint": "<from trial.json>", "codebook": "<version in codebook.json>", "prompt": "review-2",
  "reviewer": "<opus|sonnet|haiku: the model writing this record>",
  "outcome": "success|failure",
  "headline": "一句话：做了什么、结果如何、为什么",
  "approach": {"paradigm": ["<paradigm code>", "..."], "summary": "2-3 句：方法是什么、如何拿到状态/感知、如何验证"},
  "story": "按时间 3-6 句，带 [mm:ss]",
  "failure": null | {
    "stage": "<stage code>", "primary": "<cause code>", "secondary": ["<cause code>"],
    "decisive": {"t": "mm:ss", "what": "…"}, "no_return_t": "mm:ss|unclear", "first_symptom_t": "mm:ss|unclear",
    "evidence": "短引文或观察"
  },
  "best_progress": "离成功最近的一刻和程度",
  "claim": "<claim code>",
  "time": {"clock_aware": true, "clock_checks_seen": 0, "planned_budget": false, "first_deliverable_t": "mm:ss|none",
           "stop_reason": "为什么在这个时刻结束", "wasted": "明显浪费的时间（等待、重复、过长命令），没有则空"},
  "style": {"plan_vs_act": "plan|act|mixed", "exploration": "narrow|moderate|broad", "on_failure": "pivot|tweak|mixed|n/a",
            "image_use": "none|some|heavy", "verification": "none|light|thorough", "notes": "风格上值得记的一点"},
  "notable": ["任何有趣、意外、可能成为 finding 的现象（包括对 benchmark 本身有效性的观察）"],
  "case_worthy": {"score": 0, "why": "0-3：3 = 很适合作为报告中的典型案例"}
}
```

After writing, run `python3 /data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/tools/review.py check <file>` and fix any problem it reports.
Reply with one line per trial: `K: outcome, primary cause, case score`.

## Addendum for standard-realtime trials (round 4, 10-16)

Add a `realtime` object to the record:
`{"control": "background-loop | step-by-step-calls | precomputed-burst | mixed", "idle": "一句中文：机器人在 agent 思考时处于什么状态（停住 / 保持上一个指令 / 失控）以及大约多久",
"latency": "一句中文：agent 有没有处理延迟（预测、提前量、加速、缩短思考）", "episodes": "用了几局 / reset 几次，第几局成功或为何没有下一局",
"realtime_specific": "一句中文：这次成败里只在 realtime 才会出现的因素（没有就写 none）"}`.
Also write the approach label for the same trial, following `meta/prompts/approach.md` (prompt approach-1), to
`annot/approach/<key>.json`; you have the full timeline, so base it on that rather than on your own summary alone.
