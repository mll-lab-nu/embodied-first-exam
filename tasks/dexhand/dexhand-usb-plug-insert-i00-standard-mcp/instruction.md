# DexHand · Plug a USB cable into a hub port (standard-mcp)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), in front of a desk (DexHand, MuJoCo). Connect the USB cable to the hub: a four-port USB hub rests free on
the desk with its ports facing the desk's front edge (world -y), and the cable's USB-A plug lies on its side on the
desk, with its 0.5 m cable. Pick up the plug, turn it so its polarized (top) face points up, and insert it into port 4,
the rightmost port (hub-local x = +33 mm), then let go. The robot runs as a service you reach only through the
`efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the plug is grasped by the thumb and at least one other finger and lifted off the desk; it is
pushed nearly all the way into port 4, straight and top face up; then it stays seated with the hand off the plug, its
cable and the hub, still for a second. A plug in any other port never counts. The episode ends as soon as the task is
done.

The episode ends at once as a failure if the hub is moved or tilted; the plug falls below the desk top; the plug or the
hub leaves the work area; the cable's far USB-B end falls off the desk; an arm link, the robot's stand or torso, or the
parked left hand touches anything (the desk, the floor, the hub, the plug or the cable, the working hand or another
robot part); the plug is dropped after it was grasped (no hand on it or its cable while it is not engaged in a port, and
it falls or lies on the desk or the floor); or the physics becomes unstable. Later actions cannot undo a failure.

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
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`.

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
wrist pose (`wrist_stage`, the right hand's mount on the arm flange) and current targets; object poses, contacts are not
observable (`r.status()` only reports whether the episode ended and whether it succeeded). Quaternions in measured poses
use WXYZ; world z is up, the desk top is at z = 0.70 m and its front edge at y = -0.114 m. Cameras are overview and
closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The robot stands on the floor in front of the desk, right of the hub (base centre at x = 0.93, y =
-0.52 on the floor at z = -0.20, facing the desk at yaw 135 deg, i.e. toward world (-1, +1)/sqrt(2); shoulders at z =
1.021 m, 1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by
the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native
force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target
sags under the arm's weight unless your targets account for it). Grasping, carrying, inserting and releasing require
physical contact. Only the working right hand may touch the desk and the task objects: any contact of an arm link, the
stand or torso, or the parked left hand with anything fails the episode at once (`robot_collision`). The controller runs
at 50 Hz, with ten 2 ms physics substeps.

### Scene
- Desk: top at z = 0.70 m (0.90 m above the floor at z = -0.20), front edge at y = -0.114 m (world frame, z up, metres
  and radians); its two front legs stand back under the top (x 0.32, y 0.00 and x 1.08, y 0.46), clear of the robot's
  base plate.
- Hub: the original four-port USB hub (103 x 30 x 10 mm, 21.8 g) rests free on the desk on rubber pads, its port face
  flush with the desk's front edge and facing -y; it is not fixed or held. Ports 1-4 are at hub-local x = -27, -7, +13,
  +33 mm; port 4 (the target) is the rightmost seen from the front. Its own upstream cable is drawn lying on the desk
  and has no physics.
- Plug: a free USB-A plug (7 g; metal shell 12.0 x 4.5 x 12 mm, housing 15 x 20 x 8 mm, strain relief) lying on its side
  on the desk, with a passive 0.5 m cable (20 ball-jointed links, 15 g) ending in a free USB-B plug on the desk. The
  plug frame origin is the centre of the shell tip; its +y axis points out of the shell (insertion direction) and +z is
  the polarized top face. Inserted correctly, the plug's +y aligns with the hub's +y and +z with the hub's +z.
- Ports are open rectangular cavities 12.5 x 4.8 x 12 mm (0.25 mm clearance per side across, 0.15 mm in height); the
  receptacle tongue and contacts are visual only, and there are no retention springs: a seated plug stays by friction
  and its own weight.
- Cameras: `overview` (desk, hub and plug from the front left) and `closeup` (the hub's port face).

## Others
- The ports are open cavities with generous clearance and no retention springs: a seated plug stays in by friction and
  its own weight.

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
