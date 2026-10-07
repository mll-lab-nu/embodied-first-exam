# KinDER task, instance i00 — STANDARD MODE (robot as a service)

You control a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a Kinova Gen3 7-DoF
arm and a Robotiq 2F-85 gripper -- **as if it were real hardware**: the simulator runs in a service you cannot open,
and you reach it only through a client. **Task:** move all 30 small dark-red cubes from the yellow bin into the green bin; a scoop is in the scene. The task succeeds the moment every cube's centre is inside the green bin, at least 1 cm from each of its inner walls and at least 0.5 cm below its rim.

## Rules (real-robot rules)
- **One episode; a reset only where `spec()` grants one.** The episode starts when the service comes up. It ends
  when the task succeeds, after 1000 control steps (100 s of robot time), when your time is up, or on a simulator
  error; nothing else ends it.
  `spec()["budget"]["reset"]` is 0 in the standard configuration. (A run that grants N resets says so there; then
  `r.reset()` starts a new episode from the same starting state (abandoning the running one, or after one has
  ended), only the last episode is graded, and a success ends the run.)
- **Time moves only inside calls.** `submit` runs your actions, and `get_obs(seconds=s)` holds the last command for
  s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think;
  `get_obs()` with no seconds is free.
- **No privileged state, no score.** You get the robot's own sensors: its two cameras (RGB, 480×640: `robot_base` on the base, `robot_wrist` on the arm's last link, which also gives depth), its joint encoders (the arm's angles and velocities, the gripper) and the base's odometry (where it is relative to where it started). Not where anything else is, not
  the goal check: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"` when its control steps ran out, or `"error"` after a simulator error).
  `spec()` gives the robot's own facts, as its documentation would: each arm joint's axis, position and limits, the
  gripper's grasp point, each camera's field of view and pose.
- There is nothing to hand in: the service records the episode, replays it and grades the replay. Keep the script
  that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run
  the same way, so do not stop early: while the episode runs, it can still pass.

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
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
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
Measured cost here: about 58.4 ms per control step in one-row calls asking for one camera, 62.9 ms
with both robot cameras' images (and the wrist's depth), 49.1 ms per step in chunks of 10 rows asking for one camera (video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw` (the odometry frame: where the base started, x the way it faced, y left), `base_vx`, `base_vy`, `base_yaw_rate`, `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.

Each row of a `delta` chunk is 11 numbers, one 10 Hz control step, in the order of `spec()["action_types"]["delta"]["layout"]`:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).
