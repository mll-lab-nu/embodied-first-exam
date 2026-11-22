# DexHand · Open a jam jar and set the lid aside (standard-mcp)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a worktop (DexHand, MuJoCo). Open the jam jar with the right hand and set its lid aside on the
worktop: a filled glass jam jar stands upright on the worktop with its red twist-off steel lid closed. The robot runs as
a service you reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the lid is unscrewed (turned counter-clockwise, seen from above, until its lugs clear the
thread) while it still sits on the jar; it is lifted clear of the jar; then it stands upright on the worktop away from
the jar, the hand off the lid and the jar, the jar upright on the worktop, and both are still for a second. A partial
sequence never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the jar tips, slides or is lifted; the lid touches the worktop before it has
been lifted clear; the lid is dropped from the air (there is no time to catch it; a lid that tips over or falls flat on
the worktop has not dropped); the jar or the lid touches the floor, falls below the worktop top or leaves the worktop or
the work area; the lid is forced up through the thread; the parked left arm or the left hand touches the jar or the lid;
or the physics becomes unstable. Later actions cannot undo a failure.

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
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`, `side`, `wide`.

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
wrist pose and current targets. The service serves no jar or lid pose, contact, lid turn or stage; it reports only
whether the episode has ended and whether in success or failure. Quaternions in measured poses use WXYZ; world z is up,
+x points forward from the robot, the jar stands at (-0.22, -0.08) and the worktop top is at z = 0.75 m. Cameras are
overview, closeup, side and wide, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

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
- Nothing holds the jar: it stands on its own weight, and its glass-on-worktop friction resists only about 0.13 N m of
  twisting torque, so turn the lid without turning, sliding or tipping the jar. Any robot part touching the jar or the
  lid counts as the hand touching it.
- The closure is a lug thread made of contact geometry: four inclined ramps on the jar neck hold four lugs inside the
  lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive about +z,
  relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the
  gaps between the ramps (a turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without
  lifting, the lugs run into the next ramps, and turning clockwise from closed tightens and jams. The lid is lightly
  closed: no vacuum, seal adhesion or tightening torque.

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
