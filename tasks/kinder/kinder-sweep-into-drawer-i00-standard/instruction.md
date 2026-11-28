# KinDER · sweep-into-drawer (standard)

## Task
Get the five small cubes on top of the kitchen island into the middle drawer of the island's top row. There is a wiper
you can use.

## Goal
Success: all five cubes are inside that drawer, away from its left and right walls.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the robot's own sensors: its two cameras (with their calibration), its joint encoders and the base's
  odometry; no object poses, no scene layout, no score, no success signal.

## Robot Interface
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/3.0`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or with `last_s=n` the frames recorded over the last n seconds; no time passes |
| `r.hold(seconds, cameras=None, video="mp4")` | `POST /submit` | hold the last command for `seconds` of robot time and return the video, like a submit |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.depth`
(metres), `res.proprio` (one row per frame). One call returns at most 3000 images. Values outside the bounds are
clipped, not refused, and `meta["clipped"]` reports them. A malformed request raises `ValueError` and runs nothing. Once
the episode has ended, `submit` raises `EpisodeOver`. Time per call, on a lightly loaded host: about 29.8 ms per control
step in one-row calls asking for one camera, 31.0 ms with both cameras' images (and the wrist's depth), 18.6 ms per step
in chunks of 10 rows asking for one camera (`video="none"` each time).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and returns
  the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`, `.npy`,
  `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

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
- When the episode has ended, `meta["reason"]` says why: `"finished"` after your finish, `"step_limit"` when its control
  steps ran out, or `"error"` after a simulator error.

### Time
Time moves only inside calls: running your actions and holding the last command (`hold(s)`) use up the episode's control
steps. Between calls the robot waits, frozen, while you think; an observation is free.

## Limits
- Time: 1800 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 1,000 control steps (100 s of robot time), then the episode ends. The task has to be done by then.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
