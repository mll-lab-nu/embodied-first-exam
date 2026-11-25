# RoboCasa365 · TurnOnToasterOven (realtime)

## Task
Turn on the toaster oven by setting its timer.

## Goal
Success: the toaster oven's timer is set, its knob turned well up from zero. The episode ends as soon as the task is
done.

Keep the script that drives the robot at `/app/output/gen.py`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: it ends as soon as the task is done, after 3000 control steps (150 s of robot time), when your
  time is up or on a simulator error; what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout; the service only tells
  you that the episode ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"failed"`, `"error"`).

## Robot Interface
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa365, robosuite / MuJoCo).
The robot runs as a service you reach only through its client, as if it were real hardware, on a clock that does not
stop while you think: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects and waits until the scene is ready (about a minute) |
| `r.spec()` | `GET /spec` | `control_dt` (0.05 s), `timing`, the action layout and limits, the cameras (intrinsics), `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `control_steps`, `done`, `reason`, `running`, `planned_steps`, `lag_s`, `episode`, `resets_left` |
| `r.submit("joint_position", A, dt=0.05, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 13 channels `dt` apart, from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |

One call returns at most 3000 images. A watch is refused with a 429 while the images in flight (pending watches and
answers not read yet) would exceed it or 8 of them are outstanding; a `submit` or a `get_obs()` without seconds is never
refused for its images: its answer then comes without its frames and `meta["frames_skipped"]` is set. The answers come
back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[camera]`, `res.frames`
/ `res.video`, `res.depth`, `res.proprio`. Once the episode has ended, `submit` raises `EpisodeOver`.

### Actions
- Action `joint_position`: the robot's native controller command, one row per control step (`control_dt` = 0.05 s). 13
  channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint limits in
  `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1 opens);
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
- The episode starts paused, on the starting state, holding still. Its clock starts at your first `submit` (or
  `get_obs(seconds=s)`) and from then on the robot runs one control step every 0.1 s of wall-clock time, whether or not
  you send anything, until the episode ends. Between your commands it executes what you planned; when the plan runs out
  it holds still (velocity channels zero, targets, grip and mode kept). Nothing pauses for you.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  `res.meta["control_steps"]` is the number of steps run so far in this episode, `res.meta["plan_end_step"]` where the
  plan now ends. A chunk covers at most 10 s of robot time; `at` may be up to `spec()["timing"]["max_ahead_steps"]`
  steps ahead, so plan a longer movement in several chunks (`at=0`, `at=200`, ...).
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]`); in a gap before `at`
  the last row in force is repeated, velocity channels included.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile. `cameras=[]` skips the images (the fastest call); rendering takes about 0.12 s a
  camera on the service's CPU and the robot does not wait for it.

## Others
- The kitchen moves on too: the timer knob, once set, slowly turns back by itself.
- One turn of yours (a model response, a tool call) takes seconds: write a controller (Python in your container, with
  numpy and the client) that plans or streams the commands, in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground; use your turns to read what
  happened and improve the program while the episode runs.
- Do not end your session early: while the episode runs, it can still succeed.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
