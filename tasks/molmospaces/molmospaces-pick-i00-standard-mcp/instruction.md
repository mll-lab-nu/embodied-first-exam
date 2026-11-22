# MolmoSpaces · pick (standard-mcp)

## Task
A Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) in a simulated house (Ai2's MolmoSpaces,
MuJoCo). Pick up the pie. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were
real hardware: one live episode.

## Goal
Success: the robot holds the pie lifted above where it lay, touching nothing but the robot. What counts is how things
stand at the end of the episode: a success reached earlier and lost by the end does not count, so finish in the state
you want graded and stop sending commands. End the episode with `done` once the task holds; otherwise it ends at the
step limit (Limits) or when your time is up.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: the arm's fixed base (robot_spec.base.pose in describe_robot's spec_file), +X the way
the arm faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm:
7 joints, end-effector pose, gripper). Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`,
`randomized_zed2_analogue_1`, `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1`.

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
- `signal(kind, note)`: end the episode (`done`).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: One control step is 1/15.152 s; the episode ends after spec_file max_control_steps steps (303, the task's 20
s horizon), so keep moves short and direct. The arm takes joint positions; end-effector goals are solved by the
service's IK and sent as joint positions. gripper_opening_m is the measured distance between the fingertips.

### Observations
- Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`, `randomized_zed2_analogue_1`,
  `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1`; RGB, and depth when you ask for it (z-depth in metres, 0
  = no reading). Each camera's intrinsics and mount are in the spec's `["cameras"]`, and every response carries each
  camera's pose.
- Proprioception, what a real robot reports: joint positions, velocities and efforts, the gripper openings and the tool
  poses.

## Others
One control step is 0.066 s of simulated time. Simulated time advances only with your commands and with
`observe(seconds=...)`: while you think, the robot waits. The service's `time_left_s` counts from your first request to
it, so it never reaches 0 before your time is up: plan by it.

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
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 12 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 303 control steps (the benchmark's 20 s horizon); then the episode ends by itself and is graded as it
  stands.
