# EmbodiedSWE · put three eggs in the carton and close the lid, Unitree G1 (standard-mcp-shell)

## Task
A Unitree G1 humanoid with three-finger hands, its pelvis fixed, its arms and waist under EmbodiedSWE's Pink IK. Four
loose eggs lie on their sides on the left half of the table. On the right is a small four-cell egg carton fixed to the
table, with its hinged lid standing fully open. The carton has four distinct pockets in a 2 by 2 layout. In three
stages: pick eggs from the table one at a time, turn each upright, and place three eggs securely in three DISTINCT
carton pockets; then push the hinged lid closed over them. The fourth egg is a distractor and can stay on the table. The
robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's
own client, as if it were real hardware: one live episode.

## Goal
Success: three eggs sit upright (either end up) and settled in three different pockets of the carton, and the lid is
shut over them, everything at rest; the fourth egg may stay on the table. The episode ends as soon as the task is done,
at the end of the first call after which it holds (judged on the live simulator).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the pelvis: origin at the pelvis, +X the way the pelvis faces, +Y to the robot's left, +Z up
(levelled); metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: end-effector pose); right
(arm: end-effector pose); hands (hand: 14 joints, no end-effector pose). Cameras: `overview`, `head`.

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
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: Each arm takes its wrist pose (the left_wrist_yaw_link / right_wrist_yaw_link frame; the palm and fingers
extend beyond it). EmbodiedSWE's Pink IK solves the waist and both arms (17 joints) for the two wrist targets together,
so moving one wrist can shift the waist and the other arm a little. The pelvis is fixed to the world (the legs are
locked). The part hands takes the 14 Dex3 hand joint targets (rad) of both hands in the order describe_robot lists them
(each joint's name says its hand and finger): send all 14, copying the current targets (observe:
parts.hands.joint_positions) for the joints you leave alone. There is no single gripper value: close and open a hand
through its joint targets (their limits: describe_robot's spec_file, action_types.ee_pose.joint_limits); a target past a
joint's limit presses the joint against it. Each arm's gripper_opening_m is the distance from that hand's thumb tip to
the midpoint of its index and middle fingertips. The measured joint angles are in observe's proprio_now (its layout:
describe_robot's spec_file, proprio_layout). One episode, no reset; it ends by itself once the task is complete.

### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images (cameras × the frames captured: the
first, one every round(60 / `video_fps`) control steps and the last; a per-frame depth one more image; `video="none"`
captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no
cameras gets `overview`, `head` at 3 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.

### Actions
The action is `ee_pose` only, 28 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz`
each), then 14 hand joint targets (rad). Rows are streamed at the 60 Hz control rate with your `dt`;
`spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's
world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static) and `head` (on the torso, where the real G1 carries its
depth camera).

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 400,000 control steps (1.9 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
