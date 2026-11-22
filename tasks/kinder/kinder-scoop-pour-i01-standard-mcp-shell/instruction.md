# KinDER · scoop-pour (standard-mcp-shell)

## Task
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). Move all 50 small dark-red cubes from the yellow bin into the green bin; a scoop is in the
scene. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the
service's own client, as if it were real hardware: one live episode.

## Goal
Success: all 50 cubes are inside the green bin, below its rim. The episode ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's own sensors: its two cameras (with their calibration), its joint encoders and
  the base's odometry; no object poses, no scene layout, no score; the episode ends when the task is done, and the
  service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is on the floor under the middle of the base as it stands at the start of the call: +X the way the base
faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm:
gripper). Cameras: `robot_base`, `robot_wrist`.

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

This robot: The base and the arm take one action type, delta (11 numbers, one row per 0.1 s control step), sent with
execute_trajectory space native, action_type delta: base_x, base_y = metres to move the base in the odometry frame
(where the base stood when the episode began: +x the way it faced then, +y to its left), together at most 0.1 a step;
base_yaw = radians to turn it (+ = counter-clockwise), at most 0.1 a step; `arm_1` .. `arm_7` = radians added to each
arm joint's measured angle, at most 0.1 a step; gripper = 0 open .. 1 closed (a command, not a change). Each step's
targets are the measured pose plus the row; a row of zeros with the gripper as it is holds the robot. To go forward
along the current heading yaw (base_yaw in proprio_now), each row has base_x = s cos(yaw), base_y = s sin(yaw) for a
step length s. At most 100 rows (10 s) a call; the episode has 1000 control steps (100 s of robot time) in all, and
watching for some seconds uses them too. The state has no hand pose: describe_robot's spec_file gives each arm joint's
axis and a point on it (the base frame, every joint at 0), the gripper's grasp point and the robot cameras' poses.
Nothing plans a way or avoids anything.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.depth`
(metres), `res.proprio` (one row per frame). One call returns at most 3000 images. Values outside the bounds are clipped
and reported in `meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Once the
episode has ended, `submit` raises `EpisodeOver`. Time per call, on a lightly loaded host: about 117.3 ms per control
step in one-row calls asking for one camera, 97.8 ms with both cameras' images (and the wrist's depth), 78.1 ms per step
in chunks of 10 rows asking for one camera (`video="none"` each time).

### Actions
One action type, `delta`: 11 numbers per row, one 10 Hz control step, in the order of
`spec()["action_types"]["delta"]["layout"]`; at most 100 rows a call:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`:
  how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums
  are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).

### Observations
- Cameras: `robot_base` on the base and `robot_wrist` on the arm's last link (which also gives depth), RGB 480 × 640,
  each with its calibration.
- The proprioception (`obs.meta["proprio"]`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw`
  (the odometry frame: where the base started, x the way it faced, y left, z up), `base_vx`, `base_vy`, `base_yaw_rate`,
  `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed
  limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.
- The robot's own facts, as its documentation would give them, are in `r.spec()`: each arm joint's axis, position and
  limits, the gripper's grasp point, each camera's field of view and pose; nothing about where anything else is.
- When the episode has ended, `meta["reason"]` says why: `"success"`, `"failed"` when its control steps ran out, or
  `"error"` after a simulator error.

### Time
Time moves only inside calls: running your actions and holding the last command while you watch (`get_obs(seconds=s)`,
at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while you think; an observation
without seconds is free.

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
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: the episode ends after 1000 control steps (100 s of robot time); the task has to be done by then.
