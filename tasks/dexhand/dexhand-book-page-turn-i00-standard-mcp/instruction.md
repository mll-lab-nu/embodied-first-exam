# DexHand · Turn one page of a board book (standard-mcp)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms may be used), at a desk
(DexHand, MuJoCo). Turn one page of the board book lying open on the desk in front of the robot: it shows pages 4 (left)
and 5 (right). Turn the next right-hand board, leaf 2 (printed pages 5 and 6), over the spine onto the left stack so
that the book shows pages 6 and 7, and take the robot off the book. Every board starts flat on its stack, so the robot
has to separate the top board from the board under it itself. The robot runs as a service you reach only through the
`efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: the turned board lies flat on the left-hand stack, so that the book shows pages 6 and 7, every other board and
both covers lie as they started, no part of the robot touches the book, and the board stays still for a second. A partly
turned page never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the book is shoved, lifted or turned on the desk, a second page turns, a cover
moves far (the book closing), a part of the book drops below the desk top, or the physics becomes unstable. Later
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
`native`): the robot base frame is the Marvin stand origin (the floor point under its torso): +X the way the robot
faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand:
22 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose); right (arm: 7 joints, no end-effector
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`, `front`, `top`.

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
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the desk top is at z = 0.78 m.
Cameras are overview, closeup, front and top, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand (at the world origin, facing +x; shoulders at (0, +-0.2215, 1.121)) with two
7-joint arms and a dexterous hand on each wrist; both arms and both hands may be used. Every arm and finger joint is a
position servo in the physics engine under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad,
the arms' own torque limits and no gravity compensation, so a held target sags slightly under the arm's weight unless
your targets account for it). Lifting, carrying and laying the page down require physical contact. The controller runs
at 50 Hz, with ten 2 ms physics substeps. The book is not attached to anything: it rests on the desk under gravity and
friction, and a push on its pages moves it unless something holds it.

The robot stands at the world origin facing +x; at the start the left arm is parked and the right hand is palm up beside
the book; both arms may be used.

The frozen start row of each hand variant (arm targets and finger targets) is the robot's `joint_target` proprioception
right after a reset.

### Scene
World frame: z up, metres and radians, +x forward from the robot stand, +y to the robot's left. The desk top is the
plane z = 0.78 m (desk x in [0.22, 0.82] m, y in [-0.26, 0.26] m). The board book lies open on the desk as one free body
(`book_spine`, nothing anchors it): its spine runs along the world x axis through y = 0, from x = 0.434 to x = 0.586
(centre x = 0.51). Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm thick laminated board of 16 g; the right-hand
boards extend from the spine toward -y (the robot's right; fore-edge at y = -0.152), the left-hand boards toward +y
(fore-edge at y = +0.152). Boards hinge at the spine about the world x axis (`<board>_binding`, passive friction 0.002 N
m and damping 0.006 N m s/rad) on a small vertical binding compliance (`<board>_binding_compliance`, 200 N/m).
Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left stack, leaf 1 on top), leaf 2 9.0 mm, leaf 3
7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm (right stack, leaf 2 on top), both covers 0.6 mm.
Every board lies flat on its stack, 0.2 mm above the board below it: the top board's fore-edge face (1.2 mm tall, at y =
-0.152, top at z = 0.7884) sits directly above leaf 3's. Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf
hinge angles are measured from the flat right-hand position for right-hand boards (0 = flat right, pi = flat left) and
from the flat left-hand position for left-hand boards (negative = lifted toward the right). At the start the right hand
(frame `wrist_stage` / `right_hand_C_MC`, palm up, index straight) is at about (0.47, -0.44, 0.93) and the left arm
hangs parked beside the stand.

## Others
- The book is free on the desk: eight rigid laminated boards and two covers on passive binding hinges with friction and
  a little give. A push on its pages moves it unless something holds it.

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
