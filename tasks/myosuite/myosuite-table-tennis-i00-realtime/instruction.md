# MyoSuite · table_tennis (realtime)

## Task
Return the served ball: after it bounces once on your half, hit it once with the paddle so that it lands on the
opponent's half, with no second paddle touch and no second bounce on your half.

## Goal
Success: after the serve bounces once on your half, you hit the ball once with the paddle and it then lands on the
opponent's half, with no second paddle touch and no second bounce on your half. This counts once it has happened, even
if the episode then ends as a failure. It ends as a failure on any other outcome of the rally or if the ball falls
toward the floor.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded.
- You get only the cameras and the body's own proprioception (joint positions, velocities and actuator torques, muscle
  activations and lengths): no object, ball, opponent or goal poses, no success signal.

## Robot Interface
The MyoArm with torso, a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor
(MyoSuite, MuJoCo), driven only through its actuators (273 muscles and 2 other actuators): there is no joint-level
controller. The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware, on a
clock that does not stop while you think.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the body's facts: the actuators' order (`action_types["actuators"]["layout"]`), `control_dt` (0.01 s), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("actuators", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 275 commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the body now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); returns the start's frames |
```python
from rcb_client import Robot
import numpy as np
r = Robot()
rows = -np.ones((80, 275))                  # 0.8 s of commands, one row per control step
res = r.submit("actuators", rows, dt=0.01, interpolate="hold", at=0, cameras=[])   # starts the clock
while not r.status()["done"]:
    ...                                          # or stream: r.submit("actuators", a[None], cameras=[]) each step
```

One call returns at most 3000 images. No call is refused for its images. While 8 answers with images are still waiting
to be read, a `submit` or a `get_obs()` answers without its frames and sets `meta["frames_skipped"]`. The answers are
binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`), `res.last[camera]`
(the last frame), `res.frames` or `res.video` (what the cameras recorded), `res.proprio` (proprioception rows). A
malformed request raises `ValueError` and changes nothing.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`,
  `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. `submit`
  answers at once, as the endpoint does. The clock does not wait for a tool call, and a call also takes your harness's
  own time; each result's `tool_s` is the tool's part.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
Action type `actuators` (275): 275 real numbers per control step, one per actuator in order: 273 muscles and 2
non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a
= -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994). Activation follows excitation with a first-order delay (~10
ms up, ~40 ms down). Muscles only pull, and one muscle can cross several joints. A muscle's force also depends on its
length and velocity. The non-muscle actuators: `pelvis_x` (index 273): normalized: a in [-1, 1] maps linearly onto [-1,
0.05] (position of joint pelvis_x); `pelvis_y` (index 274): normalized: a in [-1, 1] maps linearly onto [-1, 1]
(position of joint pelvis_y). Columns in `spec()["action_types"]["actuators"]["layout"]` order; rows `dt` apart,
`interpolate="linear"` (default: a straight line from the commands in force) or `"hold"`; the realtime client sends them
as float64. The control rate is 100 Hz (5 physics substeps).

### Observations
Your whole interface to the body. Cameras: `topview`, `default`, `close_up`, `hand_top`, `hand_bottom`,
`hand_side_inter`, `hand_side_exter`, `plam_lookat` (640x480, default `default`), rendered on the service's GPU in a few
milliseconds each; `cameras=None` means every camera, so name the ones you need. Each proprioception row
(`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `q_<joint>`, `qd_<joint>`,
`act_<muscle>`, `len_<muscle>` (m), `effort_<joint>` (the actuators' generalized force on the joint).

### Time and streaming
- Slowdown: S = 1. The world runs at 1/S of real speed: one control step (10 ms of robot time) every S x 10 ms of
  wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.
- Time does not stop. An episode starts paused, on the frozen starting state, with every command at -1 (muscles
  relaxed). Its clock starts at your first `submit` and from then on the simulator runs at 100 Hz of robot time (S = 1),
  one control step every 10 ms of wall-clock time, whether or not you send anything, until the episode ends. Between
  your commands it executes what you planned, then holds the last commands you sent; nothing pauses for you, not your
  thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds; the
  whole rally takes about a second. Drive the body with a program: a controller of your own (Python in your container,
  with numpy and the client) that plans or streams the commands, started in the background
  (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) or in the foreground if it ends with the episode. Use your turns
  to start episodes, read what happened, and improve the program.
- `submit` answers at once, with the body as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step). They replace whatever was planned from `at` on
  and keep what is planned before it. When the plan runs out, the last commands are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode, so the next step has that number. `res.meta["proprio"]["now"]` is the
  proprioception now. `res.meta["plan_end_step"]` is where the plan now ends.
- Open loop: plan a whole movement at once (`dt` a multiple of 0.01 s; a chunk covers at most 10 s), from step `at = 0`
  for the episode's start: `r.submit("actuators", rows, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock
  and runs exactly those rows from the first step; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit("actuators", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped; `res.meta["late_steps"]` counts
  them. The rest of the chunk applies from the next step.
- `get_obs()` reads the body now; `get_obs(last_s=n)` returns, without waiting, what the cameras recorded over the last
  n seconds (the body keeps executing its plan). `spec()["timing"]` states all this; `r.status()` shows `running` and
  `lag_s`.
- `r.reset()` puts the body, the ball and the scene back on the same frozen starting state and starts a new episode,
  paused until your next `submit`, either abandoning the running episode or after one has ended. Once an episode has
  ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset.
- Here the rally is fast: the serve reaches you and the rally is decided within about 1.2 s of robot time after the
  clock starts (an episode that does nothing ends after 121 control steps).

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: the episode ends after 3 s of robot time.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
