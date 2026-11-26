# LIBERO-MAX · libero_spatial · visual-theme switch (standard)

## Task
Pick up the black bowl in the middle of the table and put it on the plate.

## Goal
Success: that bowl sits on the plate, near its middle. Success is judged on how things stand when the episode ends. It
ends when you call finish (Limits) or when your session ends. The robot never tells you whether you have succeeded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka Panda arm at a table (LIBERO on robosuite / MuJoCo). The robot runs as a service you reach through its client
or its MCP tools, as if it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`; its examples come from another benchmark: the numbers here and in
`spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.05 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or with `last_s=n` the frames recorded over the last n seconds; no time passes |
| `r.hold(seconds, cameras=None, video="mp4")` | `POST /submit` | hold still for `seconds` of robot time and return the video, like a submit |
| `r.submit("ee_delta", A, dt=0.05, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 7 numbers `dt` seconds apart (a multiple of 0.05; a chunk covers at most 10 s); stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("ee_delta", A, dt=0.05, cameras=["agentview"], video="none")   # A: (T, 7)
```

One call returns at most 3000 images. The answers come back decoded: `res.meta` (the counters, `done`, `reason`,
`proprio["now"]`, `clipped`, `cameras_now`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the
cameras saw during the call), `res.proprio` (rows). Measured cost here: about 20 ms of simulation per control step, plus
about 70 ms per camera image.

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
- Action `ee_delta` (7, float64, each clipped to [-1, 1]): LIBERO's native operational-space control (OSC_POSE). Per
  control step the hand's target moves by `[dx, dy, dz]` × 0.05 m and turns by `[drx, dry, drz]` × 0.5 rad (axis-angle,
  world frame); `grip` +1 closes, -1 opens the gripper. With `dt = 0.05` each row is one control step; `hold(s)` holds
  still (zero motion, the gripper as last commanded).

### Observations
- Two cameras: `agentview` fixed in front of the robot, `wrist` on the hand; RGB 256×256, depth on request; their
  intrinsics and pose in the spec's `cameras` at the start; every action's reply carries the current ones in
  `meta["cameras_now"]`.
- Proprioception (the spec's `proprio_layout`): `eef_x/y/z` (m) and `eef_qw/qx/qy/qz` (the hand), `finger_left`,
  `finger_right` (m), `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `cmd_*` (the last action).
- World frame: metres; the robot's base is at (-0.66, 0, 0.912) facing +x: x forward (across the table), y to the
  robot's left, z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks
  along its -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels (upright images).

### Episode
Time moves only inside calls: a submitted chunk runs its control steps, and holding still (`hold(s)`) runs `s` seconds
of them; between calls the robot waits, frozen, while you think, and reading the cameras (`get_obs()`, or
`get_obs(last_s=n)` for the last n seconds) takes no time. Whether the episode has ended is in `meta["done"]`, and why
in `meta["reason"]`: `"finished"` after your finish, `"step_limit"` at the step cap, `"error"` after a simulator error.

## Others
- Once during the episode, when the gripper first gets close to one of the task's objects, the scene changes without
  warning: an object, or the place it goes, may jump a short way, an obstacle or a few extra objects may appear, a
  camera may move, or the lighting, the colours or the image noise may change. The task stays the same, so keep watching
  the cameras. Something that jumps moves alone: whatever already rests in or on it stays where it was.
- Ending your session ends the episode as finish does: call finish when you are done.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 3 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 9,000 control steps (450 s of robot time); at the cap the episode ends and is graded as it stands.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
