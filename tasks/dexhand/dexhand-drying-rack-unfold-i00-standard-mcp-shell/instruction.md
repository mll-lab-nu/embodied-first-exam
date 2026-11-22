# DexHand · Unfold a folding sweater dryer and stand it on its legs (standard-mcp-shell)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a kitchen counter (DexHand, MuJoCo). Set up the folding
sweater dryer on the counter: it starts fully folded and stored underside up, its four legs folded between the two frame
halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and
stand it on its four feet, then let go. The robot runs as a service you reach through the `efe-robot` MCP tools, their
Python client `efe_robot` or the service's own client, as if it were real hardware.

## Goal
Success: the rack is open flat with all four legs open, stands upright on its four feet with no other part on the
counter, and the hand has let go of it and it stands still for a second. A partly open rack, a rack on fewer than four
feet or a rack that is still held never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the rack is dropped, pushed off the counter (or lifted far above it), touches
the floor or the counter cabinet, or, once it stands, falls over or collapses; or if the physics becomes unstable. Later
actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the scene's world frame (+Z up; the wrist stage is fixed in it): the coordinates of the task text;
metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 6 joints, no end-effector pose);
right_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `side`, `closeup`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: One dexterous hand on a wrist stage: move the stage (part arm) and the fingers (part right_hand) with joint
positions. Every column is a position target (servo); grasping and carrying work only through contact. The parts follow
the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per
hand) the columns differ: use execute_trajectory space native with the order in spec action_types.joint_position.layout.
Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured poses are in the world frame of the task
text, quaternions wxyz.

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
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets
`wrist_x, wrist_y, wrist_z` (metres, offsets of the hand mount from the stage origin (0.62, 0, 0.75) m along the world
axes; ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ
joints; rx and rz [-3.3, 3.3], ry [-1.6, 1.6]), then the finger targets in radians. `D` is 28 for `sharpa` (22 Sharpa
Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints
`r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets
are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets; the rack's joint angles and pose are not published, so you judge the rack from the
cameras. Quaternions in measured poses use WXYZ; world z is up, the counter top is at z = 0.75 m and spans x in [-0.13,
1.37] m, y in [-0.48, 0.48] m; the folded rack starts near (0.30, 0.0). Cameras are overview, side and closeup, at 640 x
480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands hang from the same six-axis wrist stage (origin above the counter), with the same wrist
joints, ranges, gains and start targets.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, turning and releasing the rack require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are offsets of the hand mount from the stage origin (0.62, 0, 0.75) m
along the world axes (ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]); `wrist_rx, wrist_ry, wrist_rz` are serial
XYZ joint angles (radians; rx and rz [-3.3, 3.3], ry [-1.6, 1.6]); at zero rotation the hand hangs palm down with the
fingers along +x and the thumb toward +y.

At zero rotation the hand hangs palm down with the fingers along +x and the thumb toward +y.

### Scene
The rack is a folding sweater dryer: two rectangular frame halves (each 0.33 m x 0.65 m, 0.205 kg) joined by a passive
pole hinge on the side rims (0 rad = open flat, pi rad = folded), each half with two offset 0.098 m legs on passive
hinges (0 rad = folded flat, 1.745 rad = 100 degrees = open stop, no latch: the stop lies 10 degrees past vertical, so
the standing rack's weight keeps an open leg open). The woven net is drawn only and has no collision. The rack is a free
body of 0.51 kg and starts fully folded and stored underside up, its legs sandwiched between the halves.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
