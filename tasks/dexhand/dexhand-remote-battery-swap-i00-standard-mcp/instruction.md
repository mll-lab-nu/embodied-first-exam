# DexHand · Replace the battery of a TV remote (standard-mcp)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a table (DexHand, MuJoCo). Replace the battery of the TV remote that lies on the table: its sliding
battery door is shut and latched over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on
the table and an empty receiving tray stands beside the remote. The robot runs as a service you reach only through the
`efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the door latch is released by pressing the door's spring-loaded thumb tab down, and the door
slid well open; the gray cell is out of the compartment, resting on the tray floor; the green cell lies seated in the
compartment slot on both cradle ribs, its + end at the gold contact; the door is slid shut and latched, the tab
released; then the hand is off everything and all of it is still for a second, the gray cell still in the tray, the
green cell seated and the door latched. Partial completion never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if a cell, the door, the remote or the tray falls below the table top, leaves the
work area or touches the floor; the remote or the tray slides or tilts; the gray cell touches the table top; the green
cell touches the table top again after it has been lifted; a cell drops (there is no grace period, and catching it later
does not undo it); the parked left arm or the left hand touches the remote, its door, the tray or a cell; or the physics
becomes unstable. Later actions cannot undo a failure.

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
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`, `top`.

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
wrist pose and current targets; object poses, contacts are not published; the service reports only whether the episode
ended (`done`, with reason `success` or `task_failure`). Quaternions in measured poses use WXYZ; world z is up and the
table top is at z = 0.30 m. Cameras are overview, closeup and top, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

### Robot
The left arm is parked; the right arm and hand do the task.

### Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m (the floor is at z = -0.55 m). The remote lies
flat at (0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on
four rubber feet (shell 160 x 64 mm, battery cavity 94 x 52 mm). Its battery door slides along the remote's -x direction
on a passive slide joint (travel 0 to 0.085 m, end stops at both ends, damping 0.1 N s/m, 0.08 N friction loss) and is
latched shut: a spring-loaded thumb tab on the door (18 x 18 mm, 3 mm proud of the door, a passive slide joint pressing
down 0 to 5 mm against a 120 N/m spring) carries a hook that sits just in front of a fixed latch stop at the remote's
rear end while the door is shut. The door opens only while the tab is pressed far enough (about 2.9 to 4.5 mm) for the
hook to pass under the stop; it re-latches when it is slid fully shut and the tab is released. Under the door is a
one-cell compartment: the slot centre is at (-0.020, 0.0, -0.00244) m in the remote frame, the gray cell lies there on
two low cradle ribs with its + end toward the gold contact at the slot's +x end (the silver - contact is at the -x end;
3 mm end play). The green replacement cell (a 23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on
the table at (0.115, -0.110, 0.307) with its + end pointing 20 degrees clockwise from world +x (seen from above). The
receiving tray (free rigid body, inner 74 x 64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). Modelling scope: the
compartment holds one cell; the source's compressible negative spring is not modelled (the terminals are fixed); there
is no electrical simulation. All objects move only through contact and these passive joints.

You control a fixed Tianji Marvin robot standing at the table (stand origin at (-0.45, 0.15, -0.45), facing +x) with two
7-joint arms and a dexterous hand on each wrist; the right arm and hand do the task, the left arm hangs parked beside
the torso (keep its targets). Every arm and finger joint is a position servo inside the physics engine under native
force bounds; the arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target
sags under the arm's weight unless your targets account for it). Grasping, carrying and releasing require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps per control.

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
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
