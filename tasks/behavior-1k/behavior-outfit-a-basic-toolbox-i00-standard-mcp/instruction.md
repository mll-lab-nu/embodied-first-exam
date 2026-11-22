# BEHAVIOR-1K · outfit_a_basic_toolbox (standard-mcp)

## Task
An R1Pro mobile bimanual robot in a simulated house (BEHAVIOR-1K: OmniGibson on Isaac Sim). Pack the toolbox in the
utility room. The drill, the pliers, the flashlight, the allen wrench and the screwdriver lie on the table there, next
to the toolbox. Put all five tools inside the toolbox, keep the toolbox on the table, and close it. The robot runs as a
service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: the drill, the pliers, the flashlight, the allen wrench and the screwdriver are inside the toolbox, and the
toolbox is closed and stands on the table. It counts only once the scene has settled: nothing the task names (a tool
included) is still in a gripper, and everything has come to rest. The episode ends as soon as the task is done. When
your session ends with the episode still running, the robot is held still for a few seconds more (your last command, the
base at 0), and a success that settles in that time counts.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- The robot can fall over: a fall ends the episode as a failure, and so does a simulator breakdown (a runaway or
  non-finite state of the robot or of an object, e.g. after the robot tumbles).
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is on the floor under the robot's base_link: +X the way the base faces, +Y to the
robot's left, +Z up (z = height above the floor); it moves with the base; metres, radians, quaternions `wxyz`, gripper 0
open .. 1 closed. Parts: left (arm: 7 joints, end-effector pose, gripper); right (arm: 7 joints, end-effector pose,
gripper); torso (torso: 4 joints, no end-effector pose); base (mobile: dx, dy, dyaw). Cameras:
`robot_r1:zed_link:Camera:0`, `robot_r1:left_realsense_link:Camera:0`, `robot_r1:right_realsense_link:Camera:0`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}` (the base: `{target: "base", dx, dy, dyaw}`); the
  parts move together and the call returns when the motion is done, with `reached` (the error per goal), a `failure`
  category if a goal was not reached, the state and a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: End-effector poses (goals and state) are the fingertip centre (TCP), midway between the two fingertips: 1.88
cm further along the fingers than the end-effector frame between the finger pads, where a grasped object is held (that
frame is the proprio eef_pose group and the native ee_pose action's frame). An end-effector goal is solved by the
robot's inverse kinematics from the current joints and moves only that arm, in joint space, without collision checking.
Grasping is assisted and the gripper is binary: closing holds what the finger pads touch, opening releases it. The
reported gripper value is 1 while the measured opening is below 9 cm (closed, or holding an object) and 0 when fully
open; gripper_opening_m is the measured opening. The torso (target torso) bends the upper body: keep the robot balanced,
a fall ends the episode as a failure. Success counts only once the scene has settled: release the objects, move the hand
clear, then wait a moment. Joint limits are in describe_robot's spec_file (robot_spec.joints). The native ee_pose action
type (execute_trajectory space native) re-solves both arms and the torso with a randomly seeded IK on every row. The
simulator runs about 7-11 control steps per second of wall time (30 control steps are one simulated second).

### Observations
- Cameras: `robot_r1:zed_link:Camera:0` (head; moves with the base and trunk), `robot_r1:left_realsense_link:Camera:0`
  and `robot_r1:right_realsense_link:Camera:0` (wrists), 224×224 each: RGB, and depth on request (z-depth in metres, 0 =
  no reading, pixel-aligned with the RGB). They all move, so always use the calibration that came with the image;
  intrinsics the spec's `["cameras"][cam]["intrinsic_cv"]`, mounting the spec's `["cameras"][cam]["mount"]` (parent link
  + fixed `link_T_cam_cv`). While the robot moves, a frame shows the scene 2 control steps before its step; the pose
  that comes with it is the one it was rendered with.
- Proprioception: joints, base pose, end-effector and fingertip poses, gripper openings, velocities and efforts, as
  named columns (the spec's `["proprio_layout"]`) in groups (the spec's `["proprio_groups"]`: joint_pos, joint_vel,
  joint_effort, gripper_opening, tcp_pose, eef_pose, base_pose, ...).
- Robot and world facts: the spec's `["robot_spec"]` has the joint names and real limits, the gripper stroke and open /
  close rule, the drive gains, the end-effector frame vs the fingertip centre (TCP, 1.88 cm further along the fingers),
  the base's per-step and speed limits; the spec's `["world"]` has the frame, units, quaternion order and camera axes.

## Others
- Before you finish, open the grippers, move clear and let the robot stand still for a moment (e.g.
  `observe(seconds=2.0)`).
- How the episode ended is in the tool result's `reason`: "success", "failure: the robot fell over", "failure: simulator
  breakdown" or `step_guard` (the runaway guard).
- For scale: the challenge's human teleoperators needed 355 s on average (10,638 control steps) for this task, and the
  simulator runs at ~7-11 control steps/s. Budget your time, drive before you reach, and check the tool result's `done`.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget (actions and simulated time are reported as cost); a runaway guard ends the episode at 200,000
  control steps (1.85 h of simulated time).
