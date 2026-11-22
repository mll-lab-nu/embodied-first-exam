# RoboLab · white_mug_in_center_of_table (standard-mcp)

## Task
A Franka Panda arm with a Robotiq 2F-85 gripper at a table (NVIDIA RoboLab's DROID setup, Isaac Sim / PhysX). Put the
white mug in the center of the table. The robot runs as a service you reach only through the `efe-robot` MCP tools, as
if it were real hardware: one live episode.

## Goal
Success: the white mug stands at the centre of the table, touching it, and the gripper has let go of it. "The gripper"
means both fingers: an object that still touches either finger counts as held. The episode ends as soon as the task is
done, when your time is up, or on a simulator error. When your session ends with the episode still running, your last
command is held for 2 s more (30 control steps) while the task is still judged, so a release you sent last completes.

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
`native`): the robot base frame is the Franka base (panda_link0): +X forward towards the table, +Y to the robot's left,
+Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, end-effector pose,
gripper). Cameras: `egocentric_mirrored_camera`, `over_shoulder_left_camera`, `wrist_cam`.

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

This robot: The end-effector pose (goals and state) is the fingertip-centre tool frame; at the starting pose the gripper
points straight down. The gripper is binary (a value of 0.5 or more closes it) and switches at once; the reported
gripper value is the command, gripper_opening_m is the measured distance between the finger pads (about 0.085 m open,
about 0.002 m closed on nothing, more when closed on an object). An end-effector goal that also sets the gripper
switches the gripper at the start of the arm's motion: to grasp, reach first, then close the gripper in a separate
move_robot call. End-effector goals move in a straight line and do not avoid objects; each takes as long as the
controller needs (duration_s does not apply). The simulator runs at 15 control steps per simulated second and is slower
than real time. The episode ends by itself the moment the success condition holds.

### Observations
- Cameras: `egocentric_mirrored_camera` (static, facing the robot across the table, 864×480),
  `over_shoulder_left_camera` (static, over the robot's left shoulder, 1280×720) and `wrist_cam` (on the gripper,
  1280×720; it moves: each frame comes with its pose). Depth on request: z-depth in metres (1 mm steps), 0 = no reading,
  pixel-aligned with the RGB. Calibration: the spec's `["cameras"][cam]` has `intrinsic_cv` and `mount` (a static pose,
  or `wrist_cam` on link `base_link` with a fixed `link_T_cam_cv`).
- Proprioception (32 columns): joints, gripper, end-effector pose, velocities and drive efforts, in the groups of
  the spec's `["proprio_groups"]` (joint_pos, joint_vel, tcp_pose, gripper_opening, joint_effort).
- Robot and world facts: the spec's `["robot_spec"]` has the joints and their limits, the gripper, the controller gains
  and the tool frames; the spec's `["world"]` has the frame, units and quaternion order (wxyz).

## Others
- Objects here: an alphabet soup can, a milk carton, an orange juice carton, a smartphone, a Rubik's cube and a white
  mug.

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
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget (actions and simulated time are reported as cost); a technical cap ends the episode after
  100,000 control steps (1.9 h of simulated time), graded as it stands; at this service's speed (3-15 control steps/s)
  your time runs out long before.
