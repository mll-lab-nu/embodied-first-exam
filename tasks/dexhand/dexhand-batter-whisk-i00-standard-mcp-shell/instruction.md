# DexHand · Whisk batter in a bowl, drain and set the whisk down (standard-mcp-shell)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a counter with a steel bowl of
batter (DexHand, MuJoCo). Pick up the balloon whisk, whisk the batter in the bowl, drain the whisk over the bowl and lay
it down on the counter. The whisk starts at rest, leaning on the bowl rim with its handle end on the counter; both hands
start open. The right hand uses the whisk; the left hand may steady the bowl. The robot runs as a service you reach
through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real
hardware.

## Goal
Success: in this order: the whisk is picked up and held clear of the bowl and the counter; its head goes into the batter
and circles the bowl at least five full times without leaving the batter (leaving it earlier starts the count again); it
hangs head-down over the bowl for half a second to drain; then it is laid down on the counter, roughly flat and away
from the bowl, and the hands have let go and it lies still for a second. Partial completion never counts. The episode
ends as soon as the task is done.

The episode ends at once as a failure if the bowl tips, slides or lifts; if, after the pickup, the whisk is dropped,
touches the counter or loses the hand's contact for more than a moment before it is placed; if it is tossed rather than
laid down once placed; if the bowl or the whisk touches the floor, falls below the counter top or leaves the work area;
or if the physics becomes unstable. Before the pickup the whisk may be nudged or slide off the rim. Later actions cannot
undo a failure.

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
robot base frame is the Marvin stand origin (the floor point under its torso): +X the way the robot faces, +Y to its
left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand: 22 joints, no
end-effector pose); left (arm: 7 joints, no end-effector pose); right (arm: 7 joints, no end-effector pose); left_hand
(hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`, `side`.

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

This robot: Two 7-joint arms (parts left, right) and two hands (left_hand, right_hand), all joint positions: no
end-effector pose command and no inverse kinematics; the measured hand-mount pose comes back as ee. The arm servos have
no gravity compensation (a held target sags about 1 cm at the hand under load). A one-hand task keeps the other arm
parked at its start targets. Every column is a position target (servo); grasping and carrying work only through contact.
The parts follow the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20
finger joints per hand) the columns differ: use execute_trajectory space native with the order in spec
action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured
poses are in the world frame of the task text, quaternions wxyz.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, radians: columns 0-6 the left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, 7-13 the right arm `..._R_J1` ... `..._R_J7`, then the left hand's and the
right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ...
`left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per
hand, `l_wuji_*` then `r_wuji_*`). Actuator targets are clipped to the published joint limits and clipping is reported.
`dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each
row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.68
m; the bowl starts centred at (0.58, 0.0) m. Cameras are overview, closeup and side, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand on
each wrist. Every arm and finger joint is a position servo in the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags by about 1 cm at the
hand under load unless your targets account for it). The bowl and the whisk move only through contact with the hands,
the arms, each other and the counter. The controller runs at 50 Hz, with ten 2 ms physics substeps. World frame: metres
and radians, +z up, +x forward from the robot stand, +y to the robot's left.

The right arm/hand picks up and uses the whisk; the left arm/hand may steady the bowl.

### Scene
The episode starts with both hands open above the counter and the arms in a ready pose; holding the current targets
keeps it. The whisk rests against the bowl rim with its handle end on the counter; the left hand may steady the bowl.

## Others
- The batter is not simulated: it exerts no force on the whisk.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 4,000 control steps (80 s of simulated time) per episode; an episode that reaches them without success
  has failed.
