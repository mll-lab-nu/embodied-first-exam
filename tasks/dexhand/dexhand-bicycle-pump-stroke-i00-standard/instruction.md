# DexHand · Inflate a tire with a portable bicycle pump (standard)

## Task
Pump up the bicycle tire: push the pump's hose head onto the valve and close its lock, pump the handle 28 full strokes,
then open the lock, pull the head off and let go of the pump.

## Goal
Success: in this order, the hose head is pushed fully onto the valve and its thumb lock closed; with the head connected
and locked, the handle is pumped at least 28 full strokes (pushed nearly all the way down and let back up nearly to the
top; shallower strokes do not count); the thumb lock is opened and the head pulled back off the valve; then the handle
rests at the top and the pump stands upright and still, with no part of the robot touching the pump or the head, for a
second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The pump tips over, slides or lifts off its spot.
- The pump falls below the bench top or touches the floor.
- Before the 28 strokes are done, the connected head is pulled back or its lock is opened.
- The head is pulled back while its lock is still closed (open the lock first).
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
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a bench (DexHand, MuJoCo). The robot runs as a service you reach through its client or its MCP tools,
as if it were real hardware.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all position targets in radians: the 14
Marvin arm joints (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values; then the
right arm `..._R_J1` ... `..._R_J7`), then the left hand's and the right hand's finger joints. `D` is 58 for `sharpa`
(22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s.
Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no
scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`). The left arm is parked;
only the right arm and hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the bench top is at z = 0.70
m. Cameras are overview, closeup, wide and front, at 640 x 480. Camera RGB and calibrated depth from `overview`
(default) and `closeup` (aimed at the pump), the robot's own joint positions, velocities, actuator efforts, hand pose
and current targets, and robot-link forward kinematics. The service does not report the pump pose, the head or lever
position, the piston depth, the stroke count, the tire pressure or contacts: judge the handle and the pump from the
images and depth. At the end of an episode the meta reports `done` and why it ended.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds;
arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags under the
arm's weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

### Scene
The pump stands near world (0.42, 0.08) with its T handle about 0.45 m above the bench at rest; the disconnected hose
head sits at the wheel rim near world (0.546, -0.12, 0.747) with its thumb-lock lever pointing up, and seats by sliding
17.5 mm toward the rim along (-0.981, 0, -0.196).

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
- Steps: at most 5,000 control steps (100 s of simulated time) per episode, then the episode ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
