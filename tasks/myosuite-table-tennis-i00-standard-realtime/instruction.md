# MyoSuite · table_tennis — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control the **MyoArm with torso**, a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open, you reach it only through a client, and like the real world it does not wait for you: once an episode
is running, the body and the ball move while you think. You act only through its actuators (273 muscles and 2 other actuators).
**Task:** Return the served ball: hit it with the paddle so that it lands on the opponent's half of the table (MyoChallenge 2025 TableTennis P1's own success test on the ball's contact history: after the serve's bounce on your half, the paddle touches it once, then it touches the opponent's half, with no second paddle touch and no further bounce on your half). Failure (the episode ends): any other outcome of the rally, the ball falling below 0.3 m, or 3 s of simulated time.

You stand at a table-tennis table holding a paddle in the right hand; a ball is served toward you from the far side. Here the rally is fast: the serve reaches you and the rally is decided within about 1.2 s of robot time after the clock starts (an episode that does nothing ends after 121 control steps).

**Slowdown: S = 1.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every S x 10 ms of
wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.

## Rules (real-world rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, with every command at -1 (muscles
  relaxed). Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator runs at
  100 Hz of robot time (S = 1), one control step every 10 ms of wall-clock time, whether or not you send anything, until
  the episode ends. Between your commands it executes what you planned, then holds the last commands you sent; nothing
  pauses for you, not your thinking, not your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds;
  the whole rally takes about a second. Drive the body with a program: a controller of your own (Python in your
  container, with numpy and the client) that plans or streams the commands, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the episode. Use
  your turns to start episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends at the task's own success event, at its failure conditions (see the task),
  when your time is up, or on a simulator error. You have **10 resets** (`spec()["budget"]["reset"]`,
  which is authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the body,
  the ball and the scene back on the same frozen starting state and starts a new episode, paused until your next
  `submit`, either abandoning the running episode or after one has ended. Once an episode has ended, `submit` raises
  `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last episode is graded**: an episode you
  reset away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode
  then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
  `meta["resets_left"]` count the episodes.
- **No privileged state, no score.** You see what the cameras see (RGB, and depth on request) and the body's own
  proprioception: joint positions and velocities, muscle activations and lengths, the actuators' generalized force on
  each joint. No ball, paddle, table or goal poses, no success check: the service judges the episode and only
  tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a simulator error,
  else `"failed"`). `spec()` gives the body's own facts: the actuators, the joints and their limits, each camera's
  intrinsics and mounting.
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it ran
  (nothing is replayed). Keep the controller that drives the body at `/app/output/gen.py` for the record:
  save it early and keep it current.
- Do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Time and streaming
- `submit` answers at once, with the body as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last commands are held. `res.meta["control_steps"]`
  is the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]`
  the proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (`dt` a multiple of 0.01 s; a chunk covers at most 10 s), from step
  `at = 0` for the episode's start: `r.submit("actuators", rows, dt=0.01, interpolate="hold", at=0, cameras=[])`
  starts the clock and runs exactly those rows from the first step; `at` may be up to
  `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit("actuators", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the body now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the body keeps executing its plan). `spec()["timing"]` states all this; `r.status()`
  shows `running` and `lag_s`.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the body. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the body's facts: the actuators' order (`action_types["actuators"]["layout"]`), `control_dt` (0.01 s), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("actuators", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 275 commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the body now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch), `res.proprio`
(proprioception rows). A malformed request raises `ValueError` and changes nothing.
```python
from rcb_client import Robot
import numpy as np
r = Robot()
rows = -np.ones((80, 275))                  # 0.8 s of commands, one row per control step
res = r.submit("actuators", rows, dt=0.01, interpolate="hold", at=0, cameras=[])   # starts the clock
while not r.status()["done"]:
    ...                                          # or stream: r.submit("actuators", a[None], cameras=[]) each step
```
Cameras: `topview`, `default`, `close_up`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640x480, default `default`), rendered on the
service's GPU in a few milliseconds each; `cameras=None` means every camera, so name the ones you need.

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `q_<joint>`,
`qd_<joint>`, `act_<muscle>`, `len_<muscle>` (m), `effort_<joint>` (the actuators' generalized force on the joint).

### Action type `actuators` (275)
275 real numbers per control step, one per actuator in order: 273 muscles and 2 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `pelvis_x` (index 273): normalized: a in [-1, 1] maps linearly onto [-1, 0.05] (position of joint pelvis_x); `pelvis_y` (index 274): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of joint pelvis_y). Columns in `spec()["action_types"]["actuators"]["layout"]` order; rows `dt` apart, `interpolate="linear"`
(default: a straight line from the commands in force) or `"hold"`; the realtime client sends them as float64. The control rate
is 100 Hz (5 physics substeps).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
