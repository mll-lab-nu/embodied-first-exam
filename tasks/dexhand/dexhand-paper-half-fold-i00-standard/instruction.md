# DexHand · Fold a sheet of paper in half with a permanent crease (standard)

## Task
Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the
marked center line, take the hand away, and leave the folded sheet lying on the table.

## Goal
Success: the free half lies folded over onto the fixed half, its edge close to the fixed edge, with a crease along the
center line that stays when let go; the whole sheet is over the table top and not stretched; and the hand has been off
the paper for two seconds. The episode ends as soon as the task is done.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- Any part of the paper sinks well below the table top, for example bent down over the table edge.
- The paper leaves the work area.
- The paper is stretched.
- The physics becomes unstable.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no score; the episode
  ends when the task is done, and the service tells you that it ended and why.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage (no arm), at a table (DexHand, MuJoCo). The robot runs as a service you
reach only through its client, as if it were real hardware.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji" (set by the service)
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps (they count toward the 1500 controls). Calling it without seconds
only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the
same journaled episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, 28)` for `sharpa` or `(T, 26)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order:
`wrist_x, wrist_y, wrist_z` translations (metres), `wrist_rx, wrist_ry, wrist_rz` serial XYZ rotational joints
(radians), then the finger joints (radians). Actuator targets are clipped to the published joint limits and clipping is
reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation
holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper opening.

The first six targets of a row drive the wrist stage that carries the hand: `wrist_x`, `wrist_y`, `wrist_z` (metres,
world frame) and `wrist_rx`, `wrist_ry`, `wrist_rz` (radians, serial XYZ joints); the finger targets follow in the
hand's native actuator order.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets; paper state is not published. Quaternions in measured poses use WXYZ; world z is up.
Cameras are overview and side, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Sharpa starts in a near-edge pregrasp; Wuji starts at the same six wrist targets with its fingers
curled clear of the paper.

### Robot
A dexterous hand on a six-DoF wrist positioning stage is your robot. The wrist stage is position actuated in the physics
engine; folding and creasing need physical contact. Physics runs at 0.5 ms (40 substeps per 20 ms control), and the
controller runs at 50 Hz.

The wrist targets `wrist_x, wrist_y, wrist_z` are world positions of the hand mount (metres) and
`wrist_rx, wrist_ry, wrist_rz` serial XYZ joint angles (radians, not a quaternion).

### Scene
World frame, metres, z up.

- Table top at z = 0.30 m, spanning x from -0.345 to 0.135 m (the edge on the hand's side) and y from -0.30 to 0.30 m.
- The sheet starts flat at z = 0.3012 m, spanning x from 0 to 0.16 m and y from -0.05 to 0.05 m. The half with x <= 0.08
  m is glued down and never moves; the fold line is at x = 0.08 m (an orange guide line marks it). A fold brings the
  free edge (x = 0.16 m) back over the glued edge (x = 0): the free half rotates by more than 2.6 rad about the fold
  line, upward and over.
- The paper is a passive elastic/plastic sheet: it bends elastically about 0.5 rad beyond its rest shape and then
  yields, so a crease becomes permanent only when the paper is bent well past its current rest shape, and a fold that is
  merely held springs partly back when released. Contact compliance gives it an effective thickness of 0.7 mm.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 1,500 control steps (30 s of simulated time) per episode; an episode that reaches them without success
  has failed.
