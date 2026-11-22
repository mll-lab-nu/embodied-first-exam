# YAMLab · PutPotOnCooktop-v0 (standard-mcp)

## Task
Two I2RT YAM arms with parallel two-finger grippers on a workstation table (YAMLab's bimanual setup, Isaac Sim). Lift
the pot with **both** arms (both grippers holding it), put it down on the cooktop, upright, and let go with both
grippers. The scene has the pot and the cooktop on the table. The robot runs as a service you reach only through the
`efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: both grippers hold the pot between their finger pads and lift it clear of the table for a moment; then the pot
stands upright on the cooktop, resting on it, released by both grippers, for about a second. The steps count in this
order, each for good once done. An object falling off the table ends the episode as a failure. The episode ends as soon
as the task is done.

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
`native`): the robot base frame: midway between the two arm bases at their mounting height, +X forward towards the far
side of the table, +Y towards the left arm, +Z up; the left arm's base is at (0, +0.305, 0) and the right arm's at (0,
-0.305, 0); metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, end-effector
pose, gripper); right (arm: 6 joints, end-effector pose, gripper). Cameras: `top`, `left_wrist`, `right_wrist`.

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

This robot: At the start both arms are at their home pose (all joints 0, grippers open) with the tool frames pointing
forward (+X). The gripper value in the state is the finger target in force; gripper_opening_m is the measured opening
(0.095 m fully open; a gripper closed on an object stops above 0). Joint efforts (left_joint1_effort ...) in proprio_now
grow when an arm pushes on something. A joint goal for one arm also re-sends the other arm's measured joints. The
episode ends by itself at the first control step where the task's check holds.

### Observations
- Cameras (640×480 each): `top` (static, above the table looking down at the workspace), `left_wrist` and `right_wrist`
  (on each arm's wrist; they move: every frame comes with its pose).
- In the spec: `robot_spec` (joints and their limits, grippers, controller gains, tool frames, the arm bases), `world`
  (frame, units, wxyz), `proprio_groups` (joint_pos, tcp_pose, gripper_cmd, joint_vel, gripper_opening, joint_effort).

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
- Resources: 5 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 100,000 control steps (1/30 s each, about 56 min of
  simulated time), graded as it stands. The service runs 60-120 control steps per second, so long watches can reach it.
