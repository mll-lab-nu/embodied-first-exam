# KinDER · scoop-pour (standard-mcp)

## Task
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). Move all 50 small dark-red cubes from the yellow bin into the green bin; a scoop is in the
scene. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one
live episode.

## Goal
Success: all 50 cubes are inside the green bin, below its rim. The episode ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's own sensors: its two cameras (with their calibration), its joint encoders and
  the base's odometry; no object poses, no scene layout, no score; the episode ends when the task is done, and the
  service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is on the floor under the middle of the base as it stands at the start of the call: +X
the way the base faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts:
arm (arm: gripper). Cameras: `robot_base`, `robot_wrist`.

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

This robot: The base and the arm take one action type, delta (11 numbers, one row per 0.1 s control step), sent with
execute_trajectory space native, action_type delta: base_x, base_y = metres to move the base in the odometry frame
(where the base stood when the episode began: +x the way it faced then, +y to its left), together at most 0.1 a step;
base_yaw = radians to turn it (+ = counter-clockwise), at most 0.1 a step; `arm_1` .. `arm_7` = radians added to each
arm joint's measured angle, at most 0.1 a step; gripper = 0 open .. 1 closed (a command, not a change). Each step's
targets are the measured pose plus the row; a row of zeros with the gripper as it is holds the robot. To go forward
along the current heading yaw (base_yaw in proprio_now), each row has base_x = s cos(yaw), base_y = s sin(yaw) for a
step length s. At most 100 rows (10 s) a call; the episode has 1000 control steps (100 s of robot time) in all, and
watching for some seconds uses them too. The state has no hand pose: describe_robot's spec_file gives each arm joint's
axis and a point on it (the base frame, every joint at 0), the gripper's grasp point and the robot cameras' poses.
Nothing plans a way or avoids anything.

### Observations
- Cameras: `robot_base` on the base and `robot_wrist` on the arm's last link (which also gives depth), RGB 480 × 640,
  each with its calibration.
- The proprioception (`proprio_now`) has, in the spec's `["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw`
  (the odometry frame: where the base started, x the way it faced, y left, z up), `base_vx`, `base_vy`, `base_yaw_rate`,
  `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed
  limit, about 0.98 when they close on nothing) and `gripper_vel`; the spec's `["proprio"]` gives the units.
- The robot's own facts, as its documentation would give them, are in the spec file (`describe_robot`): each arm joint's
  axis, position and limits, the gripper's grasp point, each camera's field of view and pose; nothing about where
  anything else is.
- When the episode has ended, the tool result's `reason` says why: `"success"`, `"failed"` when its control steps ran
  out, or `"error"` after a simulator error.

### Time
Time moves only inside calls: running your actions and holding the last command while you watch (`observe(seconds=s)`,
at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while you think; an observation
without seconds is free.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: the episode ends after 1000 control steps (100 s of robot time); the task has to be done by then.
