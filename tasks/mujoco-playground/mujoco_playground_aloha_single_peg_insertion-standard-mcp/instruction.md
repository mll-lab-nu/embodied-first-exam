# MuJoCo Playground · ALOHA single peg insertion (standard-mcp)

## Task
An ALOHA 2 bimanual robot (two ViperX 300s arms facing each other across a table; MuJoCo Playground's scene, in MuJoCo).
A blue socket (a square tube, open at one end, a red wall at the back) and a red peg lie on the table. Pick up the
socket with one arm and the peg with the other, lift both, and insert the peg's end into the socket's open end. The
robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: the peg's end is inside the socket, on the socket's axis and pushed in well past its open end; a peg pushed all
the way in counts. What counts is how things stand at the end of the episode: a success reached earlier and lost by the
end does not count, so finish in the state you want graded and stop sending commands. The episode runs until your time
is up.

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
`native`): the robot base frame is the scene's world frame (z up), not either arm's base: no part here takes an
end-effector pose; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, no
end-effector pose, gripper); right (arm: 6 joints, no end-effector pose, gripper). Cameras: `overhead_cam`,
`teleoperator_pov`, `wrist_cam_left`, `wrist_cam_right`.

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

This robot: The arms take joint positions only: there is no end-effector pose command and no kinematics service here, so
reaching a point means choosing joint angles (each joint's limits are in describe_robot). The state's gripper value
comes from the finger's measured opening, so it stops short of 1 when the fingers close on an object. The two wrist
cameras move with the arms; the overhead and teleoperator cameras are fixed. One episode, no reset: the state at the end
of your time is graded, so finish in the pose you want graded and keep it.

### Observations
the tool result's `proprio` (`layout`, `now`): the joint positions, velocities and current targets. The tool result's
`task` is the task's target (`target_pos`, and `target_quat_wxyz` where it has one). Calibration: `meta["cameras"][cam]`
holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x right, y up, the camera
looks along -z; the viewpoint the image is rendered from), for the state at the end of that call (the `last` image and
the last frame of every stack). Depth is the distance along the viewing axis, in metres. The overhead and teleoperator
cameras are fixed. The two wrist cameras move with the arms (the spec's `["cameras"][cam]["moving"]`): for them a
response with several frames also carries one pose per frame, `res.raw["cam2world_gl/<cam>"]["data"]`, float64
`(n_frames, 4, 4)`. `intrinsic_cv` is `[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]` for the 320 x 240 image; fx and fy differ
for the overhead and wrist cameras (their sensor is wider than the image): use both.

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
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
