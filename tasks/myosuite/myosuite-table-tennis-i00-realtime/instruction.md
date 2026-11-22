# MyoSuite · table_tennis (realtime)

## Task
The MyoArm with torso, a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor
(MyoSuite, MuJoCo), driven only through its actuators (273 muscles and 2 other actuators): there is no joint-level
controller. You stand at a table-tennis table holding a paddle in the right hand; a ball is served toward you from the
far side. Here the rally is fast: the serve reaches you and the rally is decided within about 1.2 s of robot time after
the clock starts (an episode that does nothing ends after 121 control steps). Return the served ball: hit it with the
paddle so that it lands on the opponent's half of the table (MyoChallenge 2025 TableTennis). The robot runs as a service you reach only through its client, as if it were real hardware, on a clock that does not stop while you think.

## Goal
Success: after the serve has bounced on your half, the paddle hits the ball once and the ball then lands on the
opponent's half, with no second paddle touch and no further bounce on your half. The episode ends as soon as the task is
done; it ends as a failure on any other outcome of the rally, when the ball falls low, and after 3 s of simulated time.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- No privileged state: you get the camera images (with their calibration) and the body's own proprioception (joint
  positions, velocities and actuator torques, muscle activations and lengths); no object, ball, opponent or goal poses;
  the episode ends when the task is done, and the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the body's facts: the actuators' order (`action_types["actuators"]["layout"]`), `control_dt` (0.01 s), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("actuators", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 275 commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the body now, or what the cameras saw over the next `seconds` |
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

One call returns at most 3000 images. A watch is refused with a 429 while the images in flight (pending watches and
answers not read yet) would exceed it or 8 of them are outstanding; a `submit` or a `get_obs()` without seconds is never
refused for its images: its answer then comes without its frames and `meta["frames_skipped"]` is set. The answers are
binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`), `res.last[camera]`
(the last frame), `res.frames` or `res.video` (what the cameras saw during a watch), `res.proprio` (proprioception
rows). A malformed request raises `ValueError` and changes nothing.

### Actions
Action type `actuators` (275): 275 real numbers per control step, one per actuator in order: 273 muscles and 2
non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a
= -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10
ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and
velocity. The non-muscle actuators: `pelvis_x` (index 273): normalized: a in [-1, 1] maps linearly onto [-1, 0.05]
(position of joint pelvis_x); `pelvis_y` (index 274): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of
joint pelvis_y). Columns in `spec()["action_types"]["actuators"]["layout"]` order; rows `dt` apart,
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
  relaxed). Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator runs at 100
  Hz of robot time (S = 1), one control step every 10 ms of wall-clock time, whether or not you send anything, until the
  episode ends. Between your commands it executes what you planned, then holds the last commands you sent; nothing
  pauses for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds; the
  whole rally takes about a second. Drive the body with a program: a controller of your own (Python in your container,
  with numpy and the client) that plans or streams the commands, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the episode. Use
  your turns to start episodes, read what happened, and improve the program.
- `submit` answers at once, with the body as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last commands are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (`dt` a multiple of 0.01 s; a chunk covers at most 10 s), from step `at = 0`
  for the episode's start: `r.submit("actuators", rows, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock
  and runs exactly those rows from the first step; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit("actuators", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the body now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the body keeps executing its plan). `spec()["timing"]` states all this; `r.status()`
  shows `running` and `lag_s`.
- `r.reset()` puts the body, the ball and the scene back on the same frozen starting state and starts a new episode,
  paused until your next `submit`, either abandoning the running episode or after one has ended. Once an episode has
  ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
