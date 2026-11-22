# VLABench · heat_food (standard-mcp-shell)

## Task
A Franka Panda arm at a table (VLABench on MuJoCo). Please heat cooked_food from tray_seen: put it into microwave_seen,
close the microwave's door and press its start button (heating itself is not simulated). The robot runs as a service you
reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real
hardware: one live episode.

## Goal
Success: cooked_food from tray_seen is inside microwave_seen, the microwave's door is closed and its start button
pressed (the heating itself is not simulated). The episode ends as soon as the task is done, and that episode, as it
ran, is graded.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use VLABench's expert solutions, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: at the arm's mount, +X forward across the table (world +y), +Y the robot's left (world -x), +Z up;
metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, no end-effector pose,
gripper). Cameras: `forward`, `left`, `right`, `wrist`.

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

This robot: The arm takes absolute joint position targets only: native action joint_position is 9 numbers, the 7 joints
(rad) and then the two fingers' openings (m: 0 closed .. 0.04 open, set both alike); move_robot's gripper 0..1 sets both
fingers. Nothing enforces the arm's joint limits: stay inside the Panda's own (spec_file:
action_types.joint_position.panda_joint_limits_rad). The reported end-effector pose is the hand's tool point (tcp). A
closed grasp holds the finger targets at 0: the fingers stop on the object, so the reported gripper value (the measured
opening of one finger) stays below 1 while something is held. The cameras' intrinsics and poses (cam2world_gl, OpenGL
axes, world frame) are in describe_robot's spec_file.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`; its examples come from another benchmark: the numbers here and in
`spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.1 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.1, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 9 targets `dt` seconds apart (a multiple of 0.1; a chunk covers at most 10 s); stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.1, cameras=["forward"], video="none")   # A: (T, 9)
```

One call returns at most 3000 images. The answers come back decoded: `res.meta` (the counters, `done`, `reason`,
`proprio["now"]`, `clipped`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the cameras saw during
the call), `res.proprio` (rows). Measured cost here: about 40 ms of simulation per control step, plus about 15 ms per
camera image.

### Actions
- Action `joint_position` (9, float64): absolute position targets for VLABench's own actuators, the 7 arm joints (rad)
  and the 2 fingers (m, 0 closed … 0.04 open), each row held for its control steps (0.1 s, 100 physics steps each). The
  model sets no arm joint limits; stay inside the Panda's own,
  `spec()["action_types"]["joint_position"]["panda_joint_limits_rad"]`.

### Observations
- Four cameras: `forward`, `left`, `right` fixed, `wrist` on the hand; RGB 320×320, depth on request, each camera's
  intrinsics and pose in `spec()["cameras"]`.
- Proprioception (the spec's `proprio_layout`): `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `finger1_pos`,
  `finger2_pos` (m), `tcp_x/y/z` (m) and `tcp_qw/qx/qy/qz` (the hand's pose), `cmd_*` (the last command).
- World frame: metres; the robot's base is at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along its
  -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels.

### Episode
Time moves only inside calls: a submitted chunk runs its control steps, and holding still (`get_obs(seconds=s)`) runs
`s` seconds of them; between calls the robot waits, frozen, while you think, and reading the cameras without `seconds`
takes no time. Whether the episode has ended is in `meta["done"]`, and why in `meta["reason"]`: `"success"`, `"failed"`
at the step cap, `"error"` after a simulator error.

## Others
- Ending your session early ends the run as the time limit does: do not stop early.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 9,000 control steps (900 s of robot time); at the cap the episode ends and is graded as it stands.
