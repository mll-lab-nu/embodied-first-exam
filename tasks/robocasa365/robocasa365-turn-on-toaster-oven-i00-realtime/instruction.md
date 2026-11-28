# RoboCasa365 · TurnOnToasterOven (realtime)

## Task
Turn on the toaster oven by setting its timer.

## Goal
Success: the toaster oven's timer is set, its knob turned well up from zero.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa365, robosuite / MuJoCo).
The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware, on a clock that
does not stop while you think: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/3.0`, realtime mode. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects and waits until the scene is ready (about a minute) |
| `r.spec()` | `GET /spec` | `control_dt` (0.05 s), `timing`, the action layout and limits, the cameras (intrinsics), `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `control_steps`, `done`, `reason`, `running`, `planned_steps`, `lag_s`, `episode`, `resets_left` |
| `r.submit("joint_position", A, dt=0.05, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 13 channels `dt` apart, from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |

One call returns at most 3000 images. No call is refused for its images. While 8 answers with images are still waiting
to be read, a `submit` or a `get_obs()` answers without its frames and sets `meta["frames_skipped"]`. The answers come
back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[camera]`, `res.frames`
/ `res.video`, `res.depth`, `res.proprio`. Once the episode has ended, `submit` raises `EpisodeOver`.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and returns
  the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`, `.npy`,
  `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. `submit`
  answers at once, as the endpoint does. The clock does not wait for a tool call, and a call also takes your harness's
  own time; each result's `tool_s` is the tool's part.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- Action `joint_position`: the robot's native controller command, one row per control step (`control_dt` = 0.05 s). 13
  channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad), within the joint limits
  `lower` / `upper` in `spec["action_types"]["joint_position"]` (from `r.spec()`); `grip` (+1 closes, -1 opens);
  `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the
  torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the
  limits.

### Observations
- Cameras: robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand (320 x 240,
  mounted on the robot; intrinsics in `spec()["cameras"]`). Each proprioception row ends with every camera's current
  pose, `cam_<camera>_x, _y, _z` (position, m) and `_r00 .. _r22` (the camera-to-world rotation, row by row; OpenGL
  axes: x right, y up, looking along -z).
- World frame: metres, z up.

### Time and streaming
- Slowdown: S = 2. The world runs at 1/S of real speed: one control step (0.05 s of robot time) every S × 0.05 s = 0.1 s
  of wall-clock time. `spec()["timing"]["slowdown"]` states it.
- The episode starts paused, on the starting state, holding still. Its clock starts at your first `submit` and from then
  on the robot runs one control step every 0.1 s of wall-clock time, whether or not you send anything, until the episode
  ends. Between your commands it executes what you planned; when the plan runs out it holds still (velocity channels
  zero, targets, grip and mode kept). Nothing pauses for you.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  `res.meta["control_steps"]` is the number of steps run so far in this episode, `res.meta["plan_end_step"]` where the
  plan now ends. A chunk covers at most 10 s of robot time; `at` may be up to `spec()["timing"]["max_ahead_steps"]`
  steps ahead, so plan a longer movement in several chunks (`at=0`, `at=200`, ...).
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]`); in a gap before `at`
  the last row in force is repeated, velocity channels included.
- `get_obs()` reads the robot now. `get_obs(last_s=n)` returns at once what the cameras recorded over the last n
  seconds. `cameras=[]` skips the images (the fastest call); rendering takes about 0.12 s a camera on the service's CPU
  and the robot does not wait for it.

## Others
- One turn of yours (a model response, a tool call) takes seconds: write a controller (Python in your container, with
  numpy and the client) that plans or streams the commands, in the background
  (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) or in the foreground; use your turns to read what happened and
  improve the program while the episode runs.
- Do not end your session early: while the episode runs, it can still succeed.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 3,000 control steps, then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
