# DexHand · Stir milk into a mug of coffee with a teaspoon (standard)

## Task
Mix the milk into the coffee: stir it six times with the teaspoon, then lay the spoon on the worktop beside the mug.

## Goal
Success: in this order, with the spoon held between the thumb and another finger and its bowl down in the coffee, the
bowl circles the mug six full times (leaving the coffee before the sixth turn starts the count again); then the spoon
lies roughly flat on the worktop, at least a mug's width away from the mug and out of the hand, and spoon and mug are
still for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The mug tips, slides or is lifted.
- The spoon touches the floor, or touches the worktop before the six turns are done.
- The spoon is dropped (it cannot be caught again).
- The mug touches the floor.
- The spoon or the mug goes below the worktop, or the spoon leaves the work area.
- A fingertip dips into the coffee.
- An arm link, the stand or the parked left hand touches the mug, the spoon or the worktop.
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
- You get only the cameras and the robot's own sensor readings: no live object poses, no score, no success signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a stone worktop (DexHand, MuJoCo). The robot runs as a service you reach through its client or its MCP
tools, as if it were real hardware.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

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
# a new episode: POST /reset, or the MCP tool `reset` (this client has no reset() call)
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `hold(s)` holds the current targets
and records those steps. `get_obs()` only observes the current state. Forward kinematics uses only the robot's own
links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()`
before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps
running.

Resets: `POST /reset` (MCP tool `reset`) starts a new episode from the same starting state. You can call it during a
running episode, which it abandons, or after one has ended. It takes no simulated time and returns the start's images
and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and
`meta["resets_left"]` count the episodes. `meta["control_steps"]` counts the current episode's control steps,
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets (left
arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the right arm `..._R_J1` ... `..._R_J7`, radians), then the left
hand's finger targets and then the right hand's, in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per
hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). Actuator targets
are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for sharpa, 20 per hand for wuji); the left arm stays parked and
only the right arm and hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up, the worktop top is at z = 0.75 m
and the mug axis at x = 0.48 m, y = 0.015 m; the robot stand is at the world origin facing +x. Cameras are overview,
closeup and top, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a Tianji Marvin dual-arm stand (two 7-joint arms, a dexterous hand on each
wrist; the stand sits at the world origin facing +x, its plate on the floor at z = -0.1 m). The left arm starts parked,
hanging beside the torso, and should stay there. Every arm and finger joint is a position servo in the physics engine
under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad, no gravity compensation, so a held
target sags under the arm's weight unless your targets account for it); stirring and laying the spoon down require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

The left arm starts parked and should stay there; arm servos have no gravity compensation.

### Scene
The mug (inner radius 50 mm, 100 mm tall, 8 mm floor), a cream glazed mug with a rounded handle pointing +x, stands on
the stone worktop (top at z = 0.75 m, front edge at x = 0.25 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee
fills it to 64 mm above its base (z = 0.814 m). The teaspoon's start pose: position (0.452, -0.020, 0.874) m, quaternion
WXYZ (-0.399, 0.006, 0.032, 0.916). With the Wuji hand the spoon instead starts leaning in the mug (bowl on the mug
floor, handle on the rim) and the open hand hangs about 0.25 m above the mug; the task is the same. Cameras: `overview`
(front right of the mug, wide), `closeup` (front right, close) and `top` (looking down the mug axis).

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode, then the episode ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
