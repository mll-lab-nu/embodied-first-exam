# KinDER task, instance i00 — STANDARD MODE (robot as a service)

You control a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a Kinova Gen3 7-DoF
arm and a Robotiq 2F-85 gripper -- **as if it were real hardware**: the simulator runs in a service you cannot open,
and you reach it only through a client. **Task:** put the six brown rods lying on the floor (30 cm long) into the row of eleven narrow cupboards standing side by side ahead of the robot, one rod each, each into a cupboard's 40 cm-tall compartment: taking the rods in order of their distance from where the centre of the robot's base starts, nearest first, they go into the 11th, 5th, 2nd, 8th, 4th and 1st cupboard of the row, counted from the robot's left as it faces the row at the start. The task succeeds the moment every rod's centre is inside its compartment: above that compartment's shelf, below the shelf over it, and within the cupboard's 10 cm width and 30 cm depth.

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds, after
  1000 control steps (100 s of robot time), when your time is up, or on a simulator error; nothing else ends it.
  You have **10 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no
  reset and the one episode is the run). `r.reset()` starts a new episode from the same starting state, with its own
  1000 control steps, either abandoning the running episode or after one has ended; it returns the start's
  frames. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset.
  **Only the last episode is graded**: a success ends the run at once, and when your time is up the episode then
  running is the one graded; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your actions, and `get_obs(seconds=s)` holds the last command for
  s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think;
  `get_obs()` with no seconds is free.
- **No privileged state, no score.** You get the robot's own sensors: its two cameras (RGB, 480×640: `robot_base` on the base, `robot_wrist` on the arm's last link, which also gives depth), its joint encoders (the arm's angles and velocities, the gripper) and the base's odometry (where it is relative to where it started). Not where anything else is, not
  the goal check: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"` when its control steps ran out, or `"error"` after a simulator error).
  `spec()` gives the robot's own facts, as its documentation would: each arm joint's axis, position and limits, the
  gripper's grasp point, each camera's field of view and pose.
- There is nothing to hand in: the service records every episode, replays the last one and grades the replay. Keep the script
  that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run
  the same way, so do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
The run passes iff the episode reaches the goal above, as KinDER's own goal check judges it, within 1000
control steps (`reason = "success"`), and a fresh replay of the recorded episode reaches it as well and ends in the
same state. There is no partial credit.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the starting state (at most 10 in all); returns the start's frames |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth` (metres), `res.proprio` (one row per frame). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
Measured cost here: about 14.2 ms per control step in one-row calls asking for one camera, 19.4 ms
with both robot cameras' images (and the wrist's depth), 10.0 ms per step in chunks of 10 rows asking for one camera (video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw` (the odometry frame: where the base started, x the way it faced, y left), `base_vx`, `base_vy`, `base_yaw_rate`, `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.

Each row of a `delta` chunk is 11 numbers, one 10 Hz control step, in the order of `spec()["action_types"]["delta"]["layout"]`:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
