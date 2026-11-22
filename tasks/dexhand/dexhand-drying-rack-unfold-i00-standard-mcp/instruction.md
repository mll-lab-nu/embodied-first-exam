# DexHand · Unfold a folding sweater dryer and stand it on its legs (standard-mcp)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a kitchen counter (DexHand, MuJoCo). Set up the folding
sweater dryer on the counter: it starts fully folded and stored underside up, its four legs folded between the two frame
halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and
stand it on its four feet, then let go. The robot runs as a service you reach only through the `efe-robot` MCP tools, as
if it were real hardware.

## Goal
Success: the rack is open flat with all four legs open, stands upright on its four feet with no other part on the
counter, and the hand has let go of it and it stands still for a second. A partly open rack, a rack on fewer than four
feet or a rack that is still held never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the rack is dropped, pushed off the counter (or lifted far above it), touches
the floor or the counter cabinet, or, once it stands, falls over or collapses; or if the physics becomes unstable. Later
actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the scene's world frame (+Z up; the wrist stage is fixed in it): the coordinates of
the task text; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 6 joints, no
end-effector pose); right_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `side`, `closeup`.

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
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: One dexterous hand on a wrist stage: move the stage (part arm) and the fingers (part right_hand) with joint
positions. Every column is a position target (servo); grasping and carrying work only through contact. The parts follow
the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per
hand) the columns differ: use execute_trajectory space native with the order in spec action_types.joint_position.layout.
Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured poses are in the world frame of the task
text, quaternions wxyz.

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
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for
`wuji`) and the exact order. Both hands hang from the same six-axis wrist stage (origin above the counter), with the
same wrist joints, ranges, gains and start targets.

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
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`reset_episode()`), each a new episode from the same starting state.
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
