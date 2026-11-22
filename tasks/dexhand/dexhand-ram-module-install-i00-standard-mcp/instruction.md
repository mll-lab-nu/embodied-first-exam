# DexHand · Install a desktop DDR4 RAM module (standard-mcp)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a bench (DexHand, MuJoCo). Install the DDR4 memory module into
the outer DIMM socket of the motherboard (socket_3, the slot nearest the board edge): the module stands upright in a
slotted anti-static foam holder on the bench, key notch towards +y; the motherboard is fixed in its service tray and the
socket's single moving latch starts open. Pick the module up, keep its keyed orientation, insert it straight into the
socket and press it home so that the passive latch snaps closed, then let go. The robot runs as a service you reach only
through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the module is lifted out of the holder, held by the thumb and at least one other finger; it sits
fully down in the target socket, straight and the right way round (a reversed module never counts); the latch has
snapped closed; then the hand is off the module and the latch, and the module stays seated, latched and still for a
second. A partial installation never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the module touches anything other than the hand, its foam holder or the target
socket (the bench, the service tray, the motherboard and its components, the other three sockets, the floor); is dropped
or falls freely (no drop-and-catch); drops below the bench top or is pushed into the socket's floor; leaves the work
area; or if the physics becomes unstable. Later actions cannot undo a failure.

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
end-effector pose); right_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `holder`, `socket`,
`socket_side`, `wide`.

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
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up, the bench top is at z = 0.825 m
and the target socket `socket_3` is at (0.576, 0.004, 0.8438) with its slot along world +y. Cameras are overview,
holder, socket, socket_side and wide, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for
`wuji`) and the exact order. Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges,
gains and start targets; the wrist targets are the world position (m) and serial XYZ angles (rad) of the hand mount.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are world positions of the hand mount (metres) and
`wrist_rx, wrist_ry, wrist_rz` serial XYZ joint angles (radians, not a quaternion).

## Others
- The socket's throat leaves little play: 1.66 mm for the 1.27 mm module.

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
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
