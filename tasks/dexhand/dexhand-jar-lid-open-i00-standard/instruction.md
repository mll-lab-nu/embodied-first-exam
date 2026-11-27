# DexHand · Open a jam jar and set the lid aside (standard)

## Task
Open the jam jar with the robot's right hand, then set the lid upright on the worktop, clear of the jar, and let go.

## Goal
Success: in this order, the lid is unscrewed counter-clockwise (seen from above) while it still sits on the jar, until
it comes loose; it is lifted clear of the jar; then it stands upright on the worktop away from the jar, the hand off the
lid and the jar, the jar upright on the worktop, and both are still for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The jar tips, slides or is lifted.
- The lid touches the worktop before it has been lifted clear.
- The lid is dropped from the air (a lid that tips over or falls flat on the worktop has not dropped).
- The jar or the lid touches the floor, falls below the worktop top or leaves the worktop or the work area.
- The lid is forced up through the thread.
- The parked left arm or the left hand touches the jar or the lid.
- The physics becomes unstable.

The steps before the last count as they happen.

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
stays parked), at a worktop (DexHand, MuJoCo). The robot runs as a service you reach through its client or its MCP
tools, as if it were real hardware.

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

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

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
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. The service serves no jar or lid pose, contact, lid turn or stage; it reports only
whether the episode has ended and why. Quaternions in measured poses use WXYZ; world z is up, +x points forward from the
robot, the jar stands at (-0.22, -0.08) and the worktop top is at z = 0.75 m. Cameras are overview, closeup, side and
wide, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist (the robot stands behind the worktop, its base centre at x = -0.56, y = 0.08 on the floor, facing +x;
shoulders at z = 1.121 m (1.221 m above the floor)). The left arm stays parked beside the torso with its hand open; the
task is done by the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine
under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a
held target sags under the arm's weight unless your targets account for it). Turning, lifting, carrying and releasing
the lid require physical contact, and the jar is held by nothing but its own weight and friction on the worktop. The
controller runs at 50 Hz, with ten 2 ms physics substeps. At reset the right hand hangs open, palm down, about 0.1 m
above the lid with its fingers along +x; the left arm is at its parked pose.

### Scene
The worktop top is at z = 0.75 and spans |x| <= 0.45, |y| <= 0.58 (world frame, metres, z up, +x forward from the
robot). The filled 297 ml glass jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.86) stands upright centred at
x = -0.22, y = -0.08; its red 64.8 mm twist-off steel lid weighs 32 g. Jar and lid are free rigid bodies.

## Others
- Nothing holds the jar down, and it turns easily on the worktop.
- The lid comes loose after about a sixth of a turn and lifts off only there: turned further, it catches on the thread
  again.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them ends there.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
