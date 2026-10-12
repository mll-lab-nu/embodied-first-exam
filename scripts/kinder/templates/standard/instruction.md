# KinDER task, instance {{instance_tag}} — STANDARD MODE (robot as a service)

You control {{standard_robot}} -- **as if it were real hardware**: the simulator runs in a service you cannot open,
and you reach it only through a client. **Task:** {{task_statement}}

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds, after
  {{max_steps}} control steps{{robot_time}}, when your time is up, or on a simulator error; nothing else ends it.
  You have **{{reset_budget}} resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no
  reset and the one episode is the run). `r.reset()` starts a new episode from the same starting state, with its own
  {{max_steps}} control steps, either abandoning the running episode or after one has ended; it returns the start's
  frames. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset.
  **Only the last episode is graded**: a success ends the run at once, and when your time is up the episode then
  running is the one graded; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your actions, and `get_obs(seconds=s)` holds the last command for
  s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think;
  `get_obs()` with no seconds is free.
- **No privileged state, no score.** You get the robot's own sensors: {{sensors}}. Not where anything else is, not
  the goal check: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"` when its control steps ran out, or `"error"` after a simulator error).
  `spec()` gives the robot's own facts, as its documentation would: each arm joint's axis, position and limits, the
  gripper's grasp point, each camera's field of view and pose.
- There is nothing to hand in: the service records every episode, replays the last one and grades the replay. Keep the script
  that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run
  the same way, so do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
The run passes iff the episode reaches the goal above, as KinDER's own goal check judges it, within {{max_steps}}
control steps (`reason = "success"`), and a fresh replay of the recorded episode reaches it as well and ends in the
same state. There is no partial credit.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` ({{max_steps}}), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the starting state (at most {{reset_budget}} in all); returns the start's frames |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of {{action_dim}} values per control step, at most {{chunk_rows}} rows a call; stops early when the episode ends{{blocked_note}} |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth` (metres), `res.proprio` (one row per frame). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, {{action_dim}}), one {{step_name}} per row
```
Measured cost here: about {{ms_single}} ms per control step in one-row calls asking for one camera, {{ms_images}} ms
with {{images_what}}, {{ms_batch}} ms per step in chunks of 10 rows asking for one camera (video="none" each time).

{{proprio_text}}

{{standard_action_layout}}
