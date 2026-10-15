# RoboCasa365 · TurnOnToasterOven — STANDARD-REALTIME MODE (robot as a service; time does not stop)

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa365's `TurnOnToasterOven` kitchen task (robosuite, MuJoCo).
**Task: Turn on the toaster oven by setting the timer.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open, you reach it
only through a client, and like real hardware it does not wait for you: once an episode is running, the robot (and the
kitchen: the timer knob, once set, turns back by itself (1/3000 of its range per simulated second)) moves on while you think.

**Slowdown: S = 2.** The world runs at 1/S of real speed: one control step (0.05 s of robot time) every
S x 0.05 s = 0.1 s of wall-clock time. `spec()["timing"]["slowdown"]` states it.

## Rules (real-robot rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, holding still. Its clock starts at
  your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs one control step every 0.1 s of
  wall-clock time, whether or not you send anything, until the episode ends. Between your commands it executes what you
  planned; when the plan runs out it holds still (velocity channels zero, targets, grip and mode kept). Nothing pauses
  for you, not your thinking, not your tool calls.
- **Drive it with a program.** One turn of yours (a model response, a tool call) takes seconds: write a controller (Python
  in your container, with numpy and the client) that plans or streams the commands, in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground; use your turns to start
  episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends at the first control step after which the environment's success check holds
  (success), after 3000 control steps (150 s of robot time; failed), when your time is up, or
  on a simulator error. You have **10 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it
  says 0, there is no reset and the one episode is the run). `r.reset(cameras=[])` rebuilds the same frozen starting state
  (it takes about 15-20 s) and starts a new episode, paused until your next `submit`, either abandoning the running
  episode or after one has ended. Reset with `cameras=[]` and ask for images afterwards: the service holds image
  requests back for about four times as long as the last request that rendered took, and a reset that renders counts
  as one (so after `r.reset()` with cameras, images come back only about a minute later). Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until
  you reset. **Only the last episode is graded**: an episode you reset away is never graded, a success ends the run at
  once (no reset after it), and when your time is up the episode then running is the one graded.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth) and the robot's own state:
  joints, end effector, the command in force, and each camera's current pose. No object poses, no scene layout, no
  success signal: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"`, `"error"`).
- There is nothing to hand in: the service records every control step it ran, replays the last episode in a fresh
  simulator and grades the replay. Keep the controller at `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
The episode is graded by the environment's own success check for `TurnOnToasterOven` (`_check_success`, run twice after every
control step, as in the privileged verifier) on the state after its last control step; the episode ends the moment it
holds. The fresh replay of the recorded episode, the commands the robot actually executed at each control step, must
succeed as well and end in the same state.

The check for `TurnOnToasterOven` requires that the timer knob is at 0.1 or more of its range (normalised) at the end; a set timer slowly runs down.

## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  `res.meta["control_steps"]` is the number of steps run so far in this episode, `res.meta["plan_end_step"]` where the
  plan now ends. A chunk covers at most 10 s of robot time; `at` may be up to `spec()["timing"]["max_ahead_steps"]`
  steps ahead, so plan a longer movement in several chunks (`at=0`, `at=200`, ...).
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]`); in a gap before
  `at` the last row in force is repeated, velocity channels included.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and
  returns what the cameras saw meanwhile. `cameras=[]` skips the images (the fastest call); rendering takes about 0.12
  s a camera on the service's CPU and the robot does not wait for it.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Its docstring is the full reference (`python -c "import rcb_client; help(rcb_client)"`).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects and waits until the scene is ready (about a minute) |
| `r.spec()` | `GET /spec` | `control_dt` (0.05 s), `timing`, the action layout and limits, the cameras (intrinsics), `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `control_steps`, `done`, `reason`, `running`, `planned_steps`, `lag_s`, `episode`, `resets_left` |
| `r.submit("joint_position", A, dt=0.05, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 13 channels `dt` apart, from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=[])` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); `cameras=[]`: no images (see Rules) |

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[camera]`,
`res.frames` / `res.video`, `res.depth`, `res.proprio`.
- Action `joint_position`: the robot's native controller command, one row per control step (`control_dt` = 0.05 s).
  13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint limits in `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the limits.
- Cameras: robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand (320 x 240, mounted on the robot; intrinsics in `spec()["cameras"]`). Each proprioception row ends with
  every camera's current pose, `cam_<camera>_x, _y, _z` (position, m) and `_r00 .. _r22` (the camera-to-world rotation,
  row by row; OpenGL axes: x right, y up, looking along -z).
- World frame: metres, z up.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
