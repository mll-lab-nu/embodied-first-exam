# IKEA MuJoCo · SVALLET work lamp (standard-mcp)

## Task
Two 6-DoF ViperX 300 s arms (MuJoCo Menagerie ALOHA), each with its own parallel gripper, at a table (RoboARC's IKEA
furniture-assembly suite, MuJoCo). Press the lamp shade's key down into the socket on top of the stand column until the
spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats. The robot runs as a service
you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: the shade's key is pressed into the socket on top of the stand column with the spring jaw snapped over it, and
the bulb is screwed fully up into the shade's socket; the stand rests upright on the bench as it started, the robot
touches no lamp part, and everything is at rest. Do not force parts into one another: a simulator breakdown (parts
pressed deep into each other) ends the episode at once, without success. When all of this holds, the service checks it
once more after holding your last command for a second more (on a copy: the robot does not move); if it still holds, the
episode ends as a success, and if not, the episode goes on and you can still fix it.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: the left arm's base link (the origin of the service's frame), +X that arm's forward
direction, +Z up; the right arm's base pose in it is spec robot_spec.base.right; metres, radians, quaternions `wxyz`,
gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, end-effector pose, gripper); right (arm: 6 joints, end-effector
pose, gripper). Cameras: `cam_high`, `cam_low`, `cam_left_wrist`, `cam_right_wrist`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The arms take joint targets only: an end-effector goal is solved with the service's inverse kinematics
(damped least squares on the robot model, no collision checking, within 1 mm and 0.01 rad) and sent as joint rows.
Control runs at 400 Hz (2.5 ms per control step). Arm joint targets move at most at the arm's joint speed limits (spec
robot_spec.controller); a faster request takes the control steps it needs. The gripper command switches at the row.
Grasps are physical: friction from the finger contacts, nothing attaches a part to a gripper. The episode ends by itself
at the first settled success (the task's requirements hold, no robot link touches any part and every part is at rest,
then again after the last row is held 1 s more), on a simulator breakdown (reason sim_breakdown) or when your time is
up; there is no step budget and nothing to signal. The gripper value in the state is the command in force;
gripper_opening_m is the measured opening. Actuator forces (proprio_now, *_effort) rise when an arm pushes on something.

### Observations
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand,
  looking at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in
  the spec's `["cameras"]`, the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (the spec's `["proprio_layout"]`, groups in the spec's `["proprio_groups"]`): per arm the 6 joint
  positions and velocities, the gripper opening (m), the tool-frame pose (`left_gripper` / `right_gripper` (between the
  fingertips): x y z + qw qx qy qz, world frame), the applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`left_base_link`) on its mounting, +z up, x along that arm's
  forward direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and
  `/kinematics` are all in it; no positions of the scene are given. The spec's `["robot_spec"]["base"]` gives the right
  arm's base pose in it (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces
  on parts, the success check itself.

## Others
- The shade's barb pushes a spring jaw open, which snaps back over it. The bulb's thread (right-hand, 1.5 mm pitch)
  advances only by turning and seats on the socket's stop; both connections lock once seated. The cable is not modelled.
- Parts move only through contact with the robot, gravity and the scene's own mechanism.
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
