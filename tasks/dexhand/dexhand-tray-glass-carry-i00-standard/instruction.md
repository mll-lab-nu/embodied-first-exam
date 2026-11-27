# DexHand · Carry a tray with two filled glasses around a bottle to the other counter (standard)

## Task
Carry the serving tray with the two filled glasses from the source counter to the receiving counter.

## Goal
Success: in this order, the tray is lifted off the source counter with both glasses standing on it; it is carried around
the steel bottle and set down in the middle of the receiving counter, level and turned the same way as at the start,
both glasses still on it; then no hand touches the tray or a glass, the glasses stand upright, and everything is still
for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A glass tilts far enough to spill, or slides off its place on the tray.
- The steel bottle touches the tray, a glass or a hand.
- After lift-off, the tray touches the source counter again.
- The tray touches the receiving counter away from its middle (no dragging).
- The tray or a glass is dropped.
- The tray tilts steeply.
- The tray or a glass goes below the counter tops, touches the floor or leaves the work area.
- The physics becomes unstable.

Each step of the Goal before the last one counts at the moment it happens.

When you are done, send `/finish` to end the episode and get it graded. Everything else is judged on the state at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded. No reset is possible after
  `/finish`.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no score, no success
  signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
Two dexterous hands, each on its own six-axis wrist stage (no arm), above a serving tray (DexHand, MuJoCo). The robot
runs as a service you reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
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
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `hold(s)` holds the current targets
and records those steps. `get_obs()` only observes the current state. Forward kinematics uses only the robot's own
links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()`
before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps
running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state. You can call it
during a running episode, which it abandons, or after one has ended. It takes no simulated time and returns the start's
images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]`
and `meta["resets_left"]` count the episodes. `meta["control_steps"]` counts the current episode's control steps,
`meta["control_steps_total"]` those of all episodes.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (units: the six stage slides
`l_wrist_x, l_wrist_y, l_wrist_z, r_wrist_x, r_wrist_y, r_wrist_z` in metres, every other entry in radians): the left
wrist stage `l_wrist_x, l_wrist_y, l_wrist_z` (metres, displacement from the stage base at (0.35, 0.272, 1.15) m) and
`l_wrist_rx, l_wrist_ry, l_wrist_rz` (radians, serial XYZ hinges), the right wrist stage `r_wrist_x ... r_wrist_rz`
(stage base at (0.35, -0.272, 1.15) m), then the left hand's and the right hand's finger targets in radians. `D` is 56
for `sharpa` (22 Sharpa Wave finger joints per hand, `l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`,
`r_hand_thumb_CMC_FE ... r_hand_pinky_DIP`) and 52 for `wuji` (20 Wuji Hand 2.2 finger joints per hand,
`l_wuji_l_THJ0..3 ... l_wuji_l_LFJ0..3`, `r_wuji_r_THJ0..3 ... r_wuji_r_LFJ0..3`). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening.

Every row holds both stages' targets and both hands' finger targets (layout below).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both wrist poses and current targets; object poses, contacts are not served (`r.status()` reports whether the episode is
done and why it ended). Quaternions in measured poses use WXYZ; world z is up and both counter tops are at z = 0.88 m.
Cameras are overview, side, top and handle_left, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for `wuji`)
and the exact order. Two hands of the selected model, each on its own six-axis wrist stage (no arm): the left hand at
the +y end of the tray, the right hand at the -y end.

### Robot
You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The left hand hangs above the +y end of the tray, the right hand above the -y end,
fingers pointing down and palms facing the tray. Stages and fingers are position actuated in the physics engine under
native force bounds; lifting, carrying and setting down the tray require physical contact. The controller runs at 50 Hz,
with ten 2 ms physics substeps.

Each stage's `x, y, z` targets are displacements (metres, along the world axes) from its base: the left stage's at
(0.35, 0.272, 1.15) m, the right stage's at (0.35, -0.272, 1.15) m; the rotations are serial XYZ hinges at the wrist
(radians).

## Others
- The work area is too low to lift the tray over the steel bottle.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode, then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
