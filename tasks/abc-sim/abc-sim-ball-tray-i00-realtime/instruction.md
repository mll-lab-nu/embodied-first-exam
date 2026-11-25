# ABC Sim · ball-tray balancing (realtime)

## Task
Hold the tray by both handles, one gripper on each, and keep the ball on the tray until the episode ends.

## Goal
Success: you keep holding both handles, one gripper on each, with the ball on the tray, through the whole countdown that
starts once both handles are gripped. The episode ends as soon as the countdown completes. It ends as a failure the
moment the ball leaves the tray or a handle is let go during the countdown.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and efforts, gripper
  openings, tool-frame poses): no object poses, no scene layout; the episode ends when the task is done, and the service
  tells you that it ended and why.

## Robot Interface
A bimanual robot in ABC Sim (MuJoCo): two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side
by side at the near edge of a table, facing +x (the left arm is the one at +y). The robot runs as a service you reach
only through its client, as if it were real hardware, on a clock that does not stop while you think: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action layout (`action_types["joint_position"]["layout"]`), `control_dt` (0.034 s), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` |
| `r.submit("joint_position", A, dt=0.034, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 14 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |

Once the episode has ended, `submit` raises `EpisodeOver`. One call returns at most 3000 images. A watch is refused with
a 429 while the images in flight (pending watches and answers not read yet) would exceed it or 8 of them are
outstanding; a `submit` or a `get_obs()` without seconds is never refused for its images: its answer then comes without
its frames and `meta["frames_skipped"]` is set. The answers are binary (RCB1) and come back decoded: `res.meta` (the
counters, `done`, `reason`, `proprio["now"]`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what
the cameras saw during a watch), `res.proprio` (proprioception rows). A malformed request raises `ValueError` and
changes nothing.

### Actions
Action type `joint_position` (14): 14 numbers per control step:
`[left_joint1..6, left_gripper, right_joint1..6, right_gripper]` -- each arm's six joint position targets (rad) and its
gripper opening (0 = closed, 1 = open, each finger 0.0475 m from closed; up to 1.042). The joints and grippers are
position servos that track the targets (MuJoCo position actuators with damping and force limits); a target outside a
joint's range is clamped to it, and the simulator rounds every command to float32. One control step = 17 physics steps
of 2 ms = 0.034 s (29.4 Hz). Columns in `spec()["action_types"]["joint_position"]["layout"]` order; rows `dt` apart,
`interpolate="linear"` (default: a straight line from the targets in force) or `"hold"`; the realtime client sends them
as float64.

### Observations
Cameras: `top` (above and behind the arms, looking down at the table), `left` and `right` (wrist cameras on the arms),
`overhead`, `left_side`, `right_side` (640x480, default `top`), rendered on the service's GPU in a few milliseconds
each; `cameras=None` means every camera, so name the ones you need. Each proprioception row has, in
`spec()["proprio_layout"]` order: `q_<entry>` (the 14 action coordinates measured), `qd_<entry>`, the two gripper
openings (m), each arm's tool centre point (x y z, `wxyz`), `effort_<entry>`.

### World frame
The table's frame: x forward (away from the arms' bases), y to the left as the arms face the table, z up; metres,
radians, quaternions `wxyz`. Directions are as the arms face the table: left = +y, right = -y, behind = +x (farther from
the arms), in front = -x (nearer to them). No positions of the scene are given.

### Time and streaming
- Slowdown: S = 1. The world runs at 1/S of real speed: one control step (0.034 s of robot time) every S x 0.034 s of
  wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.
- Time does not stop. The episode starts paused, on the frozen starting state, with the robot holding its starting pose.
  Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator runs at 29.4 Hz of
  robot time (S = 1), one control step every 0.034 s of wall-clock time, whether or not you send anything, until the
  episode ends. Between your commands it executes what you planned, then holds the last targets you sent; nothing pauses
  for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds. Drive
  the robot with a program: a controller of your own (Python in your container, with numpy and the client) that plans or
  streams the targets, started in the background (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) or in the
  foreground if it ends with the episode. Use your turns to read what happened and improve the program while the episode
  runs.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (`dt` a multiple of 0.034 s; a chunk covers at most 10 s), from step `at = 0`
  for the episode's start: `r.submit("joint_position", rows, dt=0.034, interpolate="hold", at=0, cameras=[])` starts the
  clock and runs exactly those rows from the first step; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps
  ahead.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, computed from the
  proprioception or images the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the robot keeps executing its plan). `spec()["timing"]` states all this; `r.status()`
  shows `running` and `lag_s`.

## Others
- While the countdown runs, the ball gets light pushes along the tray, in a direction that drifts from push to push.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
