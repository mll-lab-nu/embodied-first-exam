# DexHand · Serve a pancake from a frying pan with a spatula (standard-mcp)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (the right arm and hand do the
task; the left arm stays parked), at a counter (DexHand, MuJoCo). Serve the pancake from the frying pan onto the plate
using the kitchen turner (spatula), which rests on the counter in front of the plate: pick it up first (both hands start
open). Only the turner may move the pancake: slide its blade under the pancake, lift it out of the pan on the blade,
carry it to the plate, set it down in the plate and withdraw the turner. The robot runs as a service you reach only
through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the pancake rides on the turner's blade alone, lifted and roughly level, for a moment; it is
carried over the plate on the blade; then it lies flat in the plate near its middle, touching only the plate, with the
turner withdrawn, and is still for a second. Skipping or reordering a stage never counts. The episode ends as soon as
the task is done.

The episode ends at once as a failure, with no grace period, if the pancake touches the counter top or the floor, falls
freely, or drops below the counter top; any part of the robot touches the pancake; the turner touches the floor, falls
out of the hand or drops below the counter top; the pan or the plate is moved or tipped; the pancake, pan, plate or
turner leaves the work area; or the physics becomes unstable. Later actions cannot undo a failure.

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
`native`): the robot base frame is the Marvin stand origin (the floor point under its torso): +X the way the robot
faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand:
22 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose); right (arm: 7 joints, no end-effector
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`, `side`.

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

This robot: Two 7-joint arms (parts left, right) and two hands (left_hand, right_hand), all joint positions: no
end-effector pose command and no inverse kinematics; the measured hand-mount pose comes back as ee. The arm servos have
no gravity compensation (a held target sags about 1 cm at the hand under load). A one-hand task keeps the other arm
parked at its start targets. Every column is a position target (servo); grasping and carrying work only through contact.
The parts follow the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20
finger joints per hand) the columns differ: use execute_trajectory space native with the order in spec
action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured
poses are in the world frame of the task text, quaternions wxyz.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.85
m. Cameras are overview, closeup and side, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand on
each wrist; the right arm and hand do the task and the left arm stays parked beside the torso. Every arm and finger
joint is a position servo in the physics engine under native force bounds; arm servos have stiffness 700 N m/rad,
damping 48 N m s/rad and no gravity compensation (a held target sags by about 1 cm at the hand under load unless your
targets account for it). The turner is held only by finger and palm contact, and the pancake moves only through contact
with the turner, the pan and the plate. The controller runs at 50 Hz, with twenty 1 ms physics substeps per control.
World frame: metres and radians, +z up, +x forward from the robot stand, +y to the robot's left.

### Scene
A 22 cm non-stick frying pan (0.90 kg, free on the counter) holds one cooked pancake (0.06 kg, about 140 mm across and
9.5 mm thick); an empty ceramic plate (0.48 kg, free, rim radius 0.128 m) stands beside it on an oak counter whose top
is at z = 0.85 m; the pan rests centred at (0.50, 0.10) and the plate at (0.76, 0.18). The OXO flexible kitchen turner
(0.15 kg) rests on the counter in front of the plate, at about (0.76, -0.30, 0.878) m with its handle toward -y (handle
end and blade base on the counter, the handle 16 to 30 mm above it). Friction is high for the hand on the turner (1.2)
and for the pancake on the plate (0.60), lower for the pancake on the pan (0.45) and low for the pancake and the pan on
the blade (0.20); objects on the counter have 0.7.

The episode starts with both hands open and the turner resting on the counter; holding the start targets keeps that
pose.

## Others
- The pancake is one rigid coherent disk (no bending or tearing); the turner's thin blade bends through three passive
  spring hinges. The turner is held only by finger and palm contact, and the pancake moves only through contact with the
  turner, the pan and the plate.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`reset_episode()`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
