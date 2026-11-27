# MuJoCo Playground · BarkourJoystick (realtime)

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over, even when it gets pushed.

## Goal
Success: the robot never falls, and through every command of the schedule its speed and turning follow that command
closely on average. A fall (the trunk tipping over, or dropping low) or a leg joint leaving its allowed range (Robot
Interface) ends the episode at once, as a failure. Success is judged on the whole run, and only an episode that lasts to
the end of the schedule can succeed.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded. No reset is possible after `/finish`.
- You get only the cameras and the robot's own sensors (joint positions, velocities and torques, the IMU, foot
  contacts): no world positions, no success signal.

## Robot Interface
Google's Barkour vB quadruped (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no
walking or balance controller. The robot runs as a service you reach through its client or its MCP tools, as if it were
real hardware, on a clock that does not stop while you think.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/3.0`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the joints' order and limits, `control_dt` (0.01 s), `max_control_steps`, `timing`, the cameras, `proprio_layout`, `budget`, `robot_spec` (home pose, gains), command_schedule |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 12 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); returns the start's frames |
```python
from rcb_client import Robot
import numpy as np
r = Robot()
q = np.array(list(r.spec()["robot_spec"]["home_pose"].values()))   # 12 targets, the `home` pose
while True:                                     # the first submit starts the clock
    res = r.submit("joint_position", q[None], cameras=[])
    if res.done:
        break
    q = ...                                     # from res.meta["proprio"]["now"]
```

One call returns at most 3000 images. No call is refused for its images. While 8 answers with images are still waiting
to be read, a `submit` or a `get_obs()` answers without its frames and sets `meta["frames_skipped"]`. The answers are
binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame, uint8 (240, 320, 3)), `res.frames` or `res.video` (what the cameras recorded),
`res.proprio` (proprioception rows). Values outside the limits are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and changes nothing.

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
Action type `joint_position` (12): front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee:
absolute targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the
actuators' own damping of 0.5 N m s/rad). Rows are `dt` apart (a whole multiple of the 0.01 s control period),
`interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s; values outside the limits
(`spec()["action_types"]["joint_position"]["lower"]` / `["upper"]`) are clipped.

The allowed joint ranges (leaving one ends the episode as a failure): abduction [-0.7, 0.52], hip [-1.0, 2.1], knee
[0.05, 2.1] rad.

### Observations
Cameras: `track` (follows the robot) and `realsense/rgb` (on its head) (320 x 240), rendered on the service's GPU;
`cameras=None` means every camera, so name the ones you need. Each proprioception row (`spec()["proprio_layout"]`) has
the 12 joint positions (action order), their velocities (`*_vel`) and torques (`*_effort`), the IMU (`gyro_*`, `acc_*`,
`gravity_*`, `linvel_*`; IMU frame: x forward, y left, z up), the foot contacts (`*_contact`: foot_front_left,
foot_hind_left, foot_front_right, foot_hind_right) and the joystick command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`).

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. The schedule is `spec()["command_schedule"]`; the proprioception's `cmd_vx`, `cmd_vy`, `cmd_wz` are the command in
force.

### Time and streaming
- Slowdown: S = 1. The world runs at 1/S of real speed: one control step (10 ms of robot time) every S x 10 ms of
  wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.
- Time does not stop. An episode starts paused, on the frozen starting state, the joints holding their starting targets.
  Its clock starts at your first `submit` and from then on the robot runs at 100 Hz of robot time, whether or not you
  send anything, until the episode ends. Between your commands it executes what you planned, then holds the last joint
  targets you sent; nothing pauses for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds, and a
  walking robot that is not balanced step by step falls within a second. Drive it with a program: a controller of your
  own (Python in your container, with numpy and the client) that runs a loop at the control rate, reads the
  proprioception and sends targets, started in the background (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) so
  that your session is free while it runs. Use your turns to start episodes, read what happened, and improve the
  program.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step). They replace whatever was planned from `at` on
  and keep what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode, so the next step has that number. `res.meta["proprio"]["now"]` is the
  proprioception now. `res.meta["plan_end_step"]` is where the plan now ends.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, and compute the next
  one from the proprioception it returns. `cameras=[]` skips the images (the fastest call); sending faster than 100 Hz
  only replaces the same step's target again.
- Open loop: send up to 10 s of rows at once (a chunk, `dt` a multiple of 0.01 s), with `at` = the step where it should
  take over; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped; `res.meta["late_steps"]` counts
  them. The rest of the chunk applies from the next step.
- `get_obs()` reads the robot now. `get_obs(last_s=n)` returns at once what the cameras recorded over the last n seconds
  (the robot keeps executing its plan). `r.status()` shows `running` and `lag_s`.
- `r.reset()` puts the robot back on the same frozen starting state and starts a new episode, paused until your next
  `submit`, either abandoning the running episode or after one has ended. Once an episode has ended, `submit` raises
  `EpisodeOver` (its message gives `resets_left`) until you reset.
- The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.

### Episode
The robot starts standing still at its `home` pose. The ground is flat. The episode lasts the whole schedule (10 s, 1000
control steps).

### Pushes
The torso is pushed 12 times at moments you are not told (half-sine pushes of up to 35 N lasting 0.05 s, in random
horizontal directions).

## Others
- Do not stop early: as long as the episode is still running, or you have a reset left, the run can still pass.

## Limits
- Time: 1800 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: the episode ends at the end of the schedule, after 10 s of robot time.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
