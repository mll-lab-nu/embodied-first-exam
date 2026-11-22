# LIBERO-MAX · libero_goal · target relocation (standard-mcp)

## Task
A Franka Panda arm at a table (LIBERO on robosuite / MuJoCo). Open the top layer of the drawer and put the bowl inside.
The scene changes once while you work (Others). The robot runs as a service you reach only through the `efe-robot` MCP
tools, as if it were real hardware: one live episode.

## Goal
Success: the bowl is inside the cabinet's top drawer. The episode ends as soon as the task is done, and that episode, as
it ran, is graded.

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
`native`): the robot base frame: at the arm's mount, +X forward across the table, +Y the robot's left, +Z up; its axes
are parallel to LIBERO's world axes; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm:
end-effector pose (stepped by its delta controller), gripper). Cameras: `agentview`, `wrist`.

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

This robot: The arm takes end-effector deltas only (LIBERO's operational-space controller, 20 Hz): move_robot reaches a
hand pose to within about 1 cm and 0.05 rad by repeated measured steps; execute_trajectory space ee_delta sends per-step
deltas. The gripper is open or closed (gripper >= 0.5 closes); it takes about 0.4 s to close or open, so give it a
gripper-only goal before moving off with a grasped object. The reported gripper value is the last command; the finger
positions (finger_left, finger_right, m) are in proprio_now. Native action ee_delta: [dx, dy, dz, drx, dry, drz, grip],
each in [-1, 1], one row per 0.05 s step: 1.0 = 0.05 m / 0.5 rad of hand-target motion in the world frame (whose axes
are the base frame's), grip +1 closes, -1 opens. The cameras' intrinsics and poses at the start (cam2world_gl, OpenGL
axes, world frame) are in describe_robot's spec_file; each action's result carries the current ones (cameras_now; the
wrist camera moves with the hand).

### Observations
- Two cameras: `agentview` fixed in front of the robot, `wrist` on the hand; RGB 256×256, depth on request; their
  intrinsics and pose in the spec's `cameras` at the start; every action's reply carries the current ones in
  the tool result's `cameras_now`.
- Proprioception (the spec's `proprio_layout`): `eef_x/y/z` (m) and `eef_qw/qx/qy/qz` (the hand), `finger_left`,
  `finger_right` (m), `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `cmd_*` (the last action).
- World frame: metres; the robot's base is at (-0.66, 0, 0.912) facing +x: x forward (across the table), y to the
  robot's left, z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks
  along its -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels (upright images).

### Episode
Time moves only inside calls: a submitted chunk runs its control steps, and holding still (`observe(seconds=s)`) runs
`s` seconds of them; between calls the robot waits, frozen, while you think, and reading the cameras without `seconds`
takes no time. Whether the episode has ended is in the tool result's `done`, and why in the tool result's `reason`:
`"success"`, `"failed"` at the step cap, `"error"` after a simulator error.

## Others
- The scene can change while you work: once during the episode, when your gripper first gets close to one of the task's
  objects, the scene changes: an object or a receptacle may be moved, an obstacle or a few other objects may appear, a
  camera may shift, or the lighting, the colours or the image noise may change. Nothing tells you when; the task and its
  success check stay the same, so keep checking what the cameras show. A moved object or receptacle jumps there alone:
  what already rests in or on it stays where it was.
- Ending your session early ends the run as the time limit does: do not stop early.

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
- Resources: 3 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 9,000 control steps (450 s of robot time); at the cap the episode ends and is graded as it stands.
