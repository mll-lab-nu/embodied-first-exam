# DexJoCo · bimanual_photograph (standard-mcp)

## Task
Two Franka Panda arms, each with a 16-joint Allegro hand (DexJoCo, MuJoCo). Hold the camera with the left hand in front
of the logo and press its shutter with the right hand. The camera lies on the table between the robots; the logo disk
stands at the far side of the table. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if
it were real hardware: one live episode.

## Goal
Success: the left hand holds the camera in front of the logo, about 0.4 m from it and about 0.3 m above the table,
looking straight at it (along +x), while something other than the camera, the right hand, presses its shutter button.
The episode ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (RGB, depth on request, with their calibration) and its own
  proprioception (joints, tcp poses, the current targets); no object poses, no scene layout, no score; the episode ends
  when the task is done, and the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: midway between the two arm bases (link0), +X forward towards the table, +Y to the left
(towards the left arm), +Z up; the right arm's base is at (0, -0.4, 0) and the left arm's at (0, +0.4, 0); metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right (arm: end-effector pose); right_hand (hand: 16
joints, no end-effector pose); left (arm: end-effector pose); left_hand (hand: 16 joints, no end-effector pose).
Cameras: `front`, `back`, `left`, `right`, `top0`, `handcam_rgb_right`, `handcam_rgb_left`, `cam_pos_z`.

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

This robot: The arms take flange pose targets (DexJoCo's own action: an operational-space controller with gravity
compensation; it lags a moving target and stops where contact blocks it). The hands take joint targets; a hand's
joint_positions in the state are the targets in force, the measured finger joints are in proprio_now (joint_pos group).
Arm joint targets are available as execute_trajectory space native with action type joint_position (the service turns
them into a flange target by forward kinematics). Cameras render on the CPU: ask only for the cameras you need. The
episode ends by itself at the first success or at a task failure.

### Observations
- Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb_right`, `handcam_rgb_left` (on the hand
  mounts; they move, so use the calibration that comes with each response; the spec's `["cameras"][cam]["mount"]` gives
  the static pose or the mount link), `cam_pos_z` (on an object of the scene and moves with it: images and depth only,
  no mount and no pose -- `extrinsic_cv` / `cam2world_gl` are null in the tool result's `cameras` and NaN per frame --
  because its pose would be that object's). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you
  need; `video="none"` makes a chunk fastest.
- Proprioception (`proprio_now`, its layout in the spec's `["proprio_layout"]`): the joints, the tcp poses
  (`tcp_pose`), the current targets (`tcp_target`, `hand_target`).
- When the episode has ended, the tool result's `done` is set and the tool result's `reason` says why.

### Frames and joint order
- World frame, metres, z up; the robots stand at low x and reach towards +x (right arm at y < 0, left arm at y > 0);
  each arm's base pose is in the spec's `["robot_spec"]["base"]`. No other world coordinates are given (the cameras are
  calibrated, depth is available). Quaternions are WXYZ.
- The tcp (`tcp_right`, `tcp_left`) is the hand's mounting flange (the spec's `["robot_spec"]["tcp"]`), not the
  fingertips.
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread,
  1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle
  4-7, index 8-11, thumb 12-15 (the joint names in the spec's `["proprio_layout"]` say which).

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
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no limit; actions and simulated time are reported, as cost.
