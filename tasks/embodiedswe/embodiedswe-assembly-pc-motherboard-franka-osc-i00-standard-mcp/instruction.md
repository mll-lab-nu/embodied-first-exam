# EmbodiedSWE · drive the seven motherboard bolts with an allen key, Franka (standard-mcp)

## Task
A Franka Panda arm with its parallel gripper, under EmbodiedSWE's operational-space (torque) controller. A gaming-PC
case lying on its side on a sturdy table, opening up, its motherboard facing the ceiling. The board carries 7 case-mount
screw holes, each backed by an M8 threaded insert in the case. Beside the case: 7 loose M8 allen (socket-head) bolts
lying in a row, and one long-series L-shaped allen key (its arm is long enough that the swinging handle clears the case
walls). Each bolt head carries a 7 mm hex socket. Every hole already holds its bolt hand-started upright, a few threads
in. Seat the key in a bolt's socket and drive the bolt down (turn clockwise while pressing) until it seats — then move
on to the next hole. A seated bolt locks in place. The robot runs as a service you reach only through the `efe-robot`
MCP tools, as if it were real hardware: one live episode.

## Goal
Success: all seven bolts are driven down and seated in their holes, standing upright; the bolts move only down their
holes as the key turns them clockwise, and each needs at least five more full turns. The episode ends as soon as the
task is done, at the end of the first call after which it holds (judged on the live simulator).

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
`native`): the robot base frame is the arm's base (panda_link0), at world (0.07, 0, 0) with the world's axes: +X
forward, +Y left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 2 joints,
end-effector pose). Cameras: `overview`, `wrist`.

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

This robot: The arm takes end-effector poses only, tracked by EmbodiedSWE's operational-space (torque) controller; its
seven joints take no direct command. The end-effector pose is the panda_hand frame, not the fingertips: the point midway
between the fingertips is 0.1034 m along the hand's own +Z (approach) axis from it, so for a top-down grasp put
panda_hand 0.1034 m above the grasp point. The arm's two joint_positions are the finger position targets (finger_1,
finger_2, metres each: 0 = closed, 0.04 = open): send both together, e.g. [0.04, 0.04] to open and [0.0, 0.0] to close;
a closed target on an object squeezes it. gripper_opening_m in the state is the measured distance between the finger
pads (about 0.08 fully open). The measured joint angles are in observe's proprio_now (its layout: describe_robot's
spec_file, proprio_layout). One episode, no reset; it ends by itself once the task is complete.

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static) and `wrist` (on the hand).

## Others
- The key holds in a firm pinch: close the fingers across its handle's hex and the grip locks; open wide to release.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
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
- Steps: at most 400,000 control steps (7.4 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
