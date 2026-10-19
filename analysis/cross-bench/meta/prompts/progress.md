# Progress and critical-point label (prompt progress-2; progress-1 until 10-18)

You are an expert in robot control and in coding agents. For each trial (already reviewed), mark **how far the agent
got over time** and, for a failure, **the moment the trial was lost**. Read the trial's `skeleton.md` (one line per
step, `[mm:ss]` = minutes into the agent's session; grep `timeline.md` for one moment if needed) and its review
`reviews/<key>.skim.json` (do not contradict its `failure.decisive` / `no_return_t` without a reason in `what`).
Answer in Chinese, one short sentence per text field; times as `mm:ss` from the skeleton.

## Progress levels (one ladder for every task; name the concrete step in `what`)

| level | meaning | examples |
|---|---|---|
| 0 | no working control yet: still reading, setting up, or every attempt errors out | spec read, client crashes |
| 1 | the robot moves under the agent's control, or perception works | first successful motion, object located |
| 2 | reached the target area / approach done | gripper above the cup; humanoid standing and starting to walk |
| 3 | the key contact or key action works once | cup grasped and lifted; first stable gait cycle; ball hit |
| 4 | most of the task done, final part missing | cup carried to the shelf but not placed; 3 of 4 items stowed |
| 5 | done as the task asks (success condition met in a run the agent saw) | placed and released; reached the goal |

- privileged: progress is what the agent's own test runs reached (best so far); the graded run counts too.
  standard / standard-realtime: progress is the live episode itself.
- A level is reached when the log shows it happened, not when the agent claims it. Record only the first time
  each level is reached, in time order; levels can be skipped. Record a later loss (e.g. a fall after walking) in
  `critical`, not as a lower level.

## Two kinds of critical point (user definition 10-18)

- **Key step** (关键进展): a step the task needs, done for the first time — the progress level rises. The milestones
  above are the key steps; the progress-over-time charts use them.
- **No-return event** (不可挽回点): the first event in the session after which this trial could no longer pass:
  - `fall`: the robot fell or tipped and could not get up, and no reset was left to undo it
  - `out-of-reach`: an object dropped, rolled or jammed where it could no longer be used, and no reset was left
  - `terminated`: the task ended the episode (collision, limit, safety rule) and no reset was left to start again
  - `none`: no such event. Privileged trials almost always: the agent can rerun its own simulation, and the graded run
    happens after the session. A setback that a reset or a retry could still undo is not a no-return event.
- **Not critical points**: running out of time, using the last reset without a fatal event, and submitting a wrong
  deliverable. They are how the trial ended: record them in `end`.

For a no-return event: `noticed` (yes / no / unclear) — did the agent see that the trial was lost; `after`:
`stopped` (stopped trying, wrapped up or ended the session), `kept-trying` (went on working toward a pass that could no
longer happen), `n/a` (the session ended within one minute of the event); `wasted_min`: minutes spent on work after
the event that could no longer help (0 when it stopped).

## How the trial ended (`end`, every trial)

`goal-done` (the task's goal was reached), `time-out` (the wall clock ran out while work was still going on),
`resets-used` (the last reset or attempt was used), `deliverable` (the agent submitted or saved its deliverable and
stopped), `agent-stopped` (the agent stopped or gave up without a deliverable), `crash` (the session or the
simulator broke). `t` = when it happened; `what` = one sentence.

## Output, one file per trial: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/annot/progress/<key>.json`

```json
{"key": "...", "prompt": "progress-2", "fingerprint": "<from trial.json>", "labeler": "<sonnet|opus>",
 "basis": "test-runs | live-episode",
 "milestones": [{"t": "mm:ss", "level": 1, "what": "一句中文"}],
 "best_level": 3, "best_t": "mm:ss",
 "stuck": {"level": 3, "from_t": "mm:ss", "what": "最后卡在哪一步（一句）"},
 "no_return": {"kind": "fall | out-of-reach | terminated | none", "t": "mm:ss", "noticed": "yes", "after": "stopped",
               "wasted_min": 0, "what": "一句中文"},
 "end": {"kind": "time-out", "t": "mm:ss", "what": "一句中文"},
 "end_t": "mm:ss"}
```

Relabel of progress-1 records (10-18): keep their milestones, best and stuck; write only `no_return` and `end` to
`annot/progress2/<key>.json` as `{"key", "prompt": "progress-2", "fingerprint", "no_return", "end"}`.

Rules: `stuck` is the last level reached and the time from reaching it to the end (for a success, level 5 and the
time it was done). `end_t` is the session's last step. Never write the word "oracle"; never say how the task should
be solved.
