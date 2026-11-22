# RoboWits · ball_into_bottle (standard-mcp)

## Task
A bimanual Marvin robot (two 7-DoF arms with Pika parallel grippers), in RoboWits' simulation (Genesis). Transfer the
ball from the blue container into the red bottle. The robot runs as a service you reach only through the `efe-robot` MCP
tools, as if it were real hardware: one live episode.

## Goal
Success: the small ball has come to rest deep inside the red bottle, down at its bottom (not caught near the mouth, not
fallen through the base), with nothing of the robot touching it; neither the ball nor the bottle has fallen off the
table. When all of this holds after a call, the service holds your last command within that call for about three seconds
(a second, then two seconds in which all of this must keep holding, with nothing moving); if it all holds through, the
episode ends as a success, and if not, it goes on. When your session ends, the same check runs once more after your last
command.

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
`native`): the robot base frame: the robot's base point (1.08 m above the world origin), +X away from the robot towards
the table, +Y to the robot's left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right
(arm: 7 joints, end-effector pose, gripper); left (arm: 7 joints, end-effector pose, gripper). Cameras: `ego`,
`wrist_right`, `wrist_left`.

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

This robot: The gripper value in the state is the commanded opening width (0.1 m = open, 0 = closed); gripper_opening_m
is the measured opening (a gripper closed on an object stops above 0). The wrist joints are limited to about +-60 deg,
so a vertical approach works only for finger-closing directions within about 60 deg of the +Y axis. Joint efforts
(Joint1_R_effort ...) in proprio_now rise when an arm pushes on something. The episode ends by itself once the goal
holds with the graded objects released and at rest through a short settle window.

### Observations
- Cameras: `ego` (static, above and behind the robot, looking at the table), `wrist_right` / `wrist_left` (on the
  wrists; they move, so use the pose that comes with each frame). Resolution 848×480. The spec's `["cameras"][cam]`
  gives the intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link)
  · `link_T_cam_cv`). A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z +
  cx, v = fy·Y/Z + cy; depth is that Z.
- The spec's `["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD
  gains and the tool frames; the spec's `["world"]` the frame conventions.

## Others
- Objects here: red bottle, funnel, ball container, small ball.
- The red bottle's base is thin in the simulator (its collision shape is about 3.5 mm thick, and the bottle is fixed to
  the table): a ball that falls fast down the bottle can pass through the base onto the table, which fails the task. In
  one measured case about half of the pours did: let the ball in slowly.
- The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about
  ±60° of the world y axis.

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
- Resources: 4 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps (1/30 s each, watches included),
  as a failure: no settle check runs after it.
