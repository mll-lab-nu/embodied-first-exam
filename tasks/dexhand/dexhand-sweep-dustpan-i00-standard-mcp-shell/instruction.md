# DexHand · Sweep debris into a held dustpan (standard-mcp-shell)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, over a floor (DexHand, MuJoCo).
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan: the robot starts with a broom held
in its right hand and a dustpan held in its left hand; the pan's entrance ramp rests on the floor next to six small
rigid pieces (packaging pieces, bottle caps, a wood chip and a crumpled-paper ball). Push the debris over the ramp with
the broom's bristles, then raise the dustpan. The robot runs as a service you reach through the `efe-robot` MCP tools,
their Python client `efe_robot` or the service's own client, as if it were real hardware.

## Goal
Success: every one of the six pieces has been touched by the broom's bristles, all six lie in the pan on its floor, and
the pan is held up off the floor with everything still for a second. Five of six pieces, an unlifted pan or a shorter
hold is not a success. The episode ends as soon as the task is done.

The episode ends at once as a failure if a piece leaves the floor work area; any part of the robot touches a piece
(sweep with the broom only); from 1.2 s on (the first 1.2 s are a settling period), a tool slips in or drops from its
hand; a tool is pressed by any robot part other than its own hand; the arms, torso or the two hands collide with each
other; or the simulation becomes unstable. Later actions cannot undo a failure.

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
(hand: 22 joints, no end-effector pose). Cameras: `overview`, `work`, `pan`, `side`.

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
end-effector pose command and no inverse kinematics; the measured palm poses come back as ee. The right hand starts
holding the broom and the left hand the dustpan; the start targets keep both grips. The control runs at 2000 Hz (one
physics step per control; describe_robot control_dt_s): move_robot and the spaces other than native send rows 0.02 s
apart, which the robot interpolates; the simulation runs slower than real time. Every column is a position target
(servo); grasping and carrying work only through contact. The parts follow the Sharpa Wave layout (describe_robot
spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per hand) the columns differ: use
execute_trajectory space native with the order in spec action_types.joint_position.layout. Rows are a multiple of 0.0005
s apart; a call covers at most 10 s. Measured poses are in the world frame of the task text, quaternions wxyz.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"], spec["action_types"]["joint_position"]["layout"]
obs = r.get_obs(cameras=["work"], depth=True)
obs.last["work"]               # RGB uint8 (480, 640, 3)
obs.last_depth["work"]         # z-depth in metres
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.0005, interpolate="hold", video="none")
r.fk(q)                        # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
The client sends rows as float32. Requests return at most 1,000 camera images; ask for fewer cameras or a lower
`video_fps` for long chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps;
without seconds it only observes. Forward kinematics covers the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the
same journaled episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `dt` must be a multiple of
`1 / spec["control_hz"]` (0.0005 s), at most 0.5 s; a chunk covers at most `spec["max_chunk_s"]` seconds. `hold` keeps
each row for `dt`; `linear` interpolates from the previous target. Targets are clipped to the published joint limits and
clipping is reported.

Every row holds both arms' joint targets and both hands' finger targets (layout below). Sharpa rows (58 targets): the 7
left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand Sharpa
Wave finger targets (radians). Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20
right-hand Wuji Hand 2.2 finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC
flexion, CMC abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both palm poses (`l_hand_palm`, `r_hand_palm`) and current targets. Object poses, contacts are not published. Cameras
are overview, work (the floor area and the pan), pan and side, 640 x 480, fixed in the world. Measured poses use WXYZ
quaternions; world z is up, metres, the robot base at the origin, the floor the plane z = -0.10 m.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order. This task uses two hands of one model on the two arms of a fixed robot: Sharpa Wave (default) or
Wuji Hand 2.2. With Wuji the start differs only in the finger joints and their targets: both Wuji hands start closed on
the same broom and dustpan (the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa
start), and the targets at the start keep them.

### Robot
The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its handle;
the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force bounds; the
broom, the dustpan and the debris move only through contact and gravity. At the start the current targets keep both
tools in the hands; the first 1.2 s are a settling period in which the grip is not yet judged. The simulator integrates
at 0.5 ms and every action row is one physics step, so rows are a 2000 Hz control. The service simulates slower than
real time (several seconds of CPU per simulated second).

## Others
- The broom, the dustpan and the debris are free bodies that move only through contact and gravity.

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
- Steps: at most 160,000 rows (one per 0.5 ms physics step) (80 s of simulated time) per episode; an episode that
  reaches them without success has failed.
