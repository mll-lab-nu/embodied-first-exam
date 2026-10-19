# Thinking-error prompt (prompt id `reasoning-1`)

You are an expert in robot control and in coding agents. Each line of `$BATCH` is one **failed** trial that already has
a review. The review's `primary` cause often names the physical symptom (the object slipped, the robot fell). Your job
is the layer above it: **was there an error in the agent's understanding, reasoning or planning behind this failure,
and what exactly was it?** Judge from the review text only (headline, decisive error, evidence, story, style notes,
time notes). Be concrete and honest; "no thinking error" is a valid and common answer.

## `level` (one)

- `high`: a thinking error is the main reason. With the same low-level skill, the agent would very likely have passed
  had it understood, reasoned or planned differently (e.g. it misread the success rule; it assumed the wrong axis and
  never checked; it spent the whole budget on one dead route).
- `both`: the first failure was low-level (slip, imprecision, fall), but a thinking error made it fatal (no check
  after the slip, kept tweaking the same grasp for an hour, no time left for the last episode).
- `low`: understanding and plan were sound and reasonably checked; it failed on control precision, contact physics,
  noise, or a control skill it does not have (gait, dynamic catch, in-hand). Pick this when the review gives no sign
  of a wrong belief or a bad decision.
- `external`: grader, task, instruction or infrastructure problem (not the agent's doing).

## `when` (for `both` only; added 10-18, labels in `annot/reasoning_when/<key>.json`)

- `before`: the thinking error came first and set up the low-level failure: a wrong belief acted on without a test
  (frame, sign, feedforward, reach), an untested motion run on the live or last episode, a plan that left one shot.
  A slip that ended the trial at once (fall with no reset left, object out of reach, episode ended) can only be
  `before`: there was no "after".
- `after`: the low-level failure came first and could still have been recovered (time, resets or retries left), but a
  thinking error made it fatal: no check after the slip, kept tweaking the same route, blamed the wrong cause, gave up.
- `low`: on a second look there is no real thinking error (sound plan, checked, failed on control skill): the level
  should be `low`.

## `kinds` (0–2, most important first; empty for `low` and `external`)

- `task-reading`: misread the goal, success bar, constraint or deliverable format
- `world-model`: a wrong belief about the robot, scene or physics that it did not test (frame, axis, unit, sign,
  reach, object size or mass, what reset or a command does), and acted on it
- `strategy`: chose a way of solving that cannot work here (open loop where feedback is needed, a route the robot
  cannot do, building a big system with no time to test it)
- `planning`: steps or time not planned (no budget, deliverable saved too late, steps in the wrong order or missing)
- `diagnosis`: saw the failure but blamed the wrong cause, so it fixed the wrong thing
- `persistence`: kept tweaking or repeating one route after the evidence said it does not work
- `self-check`: did not check the result before relying on it or ending, or checked the wrong signal, or claimed
  success it had not verified
- `giving-up`: declared the task impossible or stopped while a workable route and time were left

## Output, one file per trial: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/annot/reasoning/<key>.json`

```json
{"key": "...", "prompt": "reasoning-1", "level": "high | both | low | external", "kinds": ["<code>"],
 "belief": "一句中文：agent 当时错在哪个想法或决定（引用分析里的时刻、原话或数字）；low/external 时写失败的直接原因",
 "better": "一句中文：同样的控制能力下，换成什么想法或决定就可能成功；low/external 时留空"}
```

Rules: Chinese for the text fields, short sentences, no English words except names, code, and the terms trial, agent,
benchmark, harness, reset, token, IK, FK, PD, MPC. Never use the word "oracle". Never describe how the task "should"
be solved beyond the one decision. Reply with one line: files written and a count per `level` and per kind.
