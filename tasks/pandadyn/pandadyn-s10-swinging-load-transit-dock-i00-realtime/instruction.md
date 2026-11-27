# Panda Dynamic Scenes · Swinging load transit and dock (S10) (realtime)

## Task
Grip the carrier's bar and damp the swinging pendulum. Carry it through the two waypoints without touching the obstacle
block, stop at the second and damp the swing again, then lower it slowly until the pendulum's ball rests in the dock,
still holding the bar.

## Goal
Success: both fingers grip the bar and damp the swing until the pendulum hangs nearly still; still gripped, the bar's
centre is carried past waypoint A and to waypoint B, where it brakes to rest; the leftover swing is damped again;
finally the carrier is lowered slowly until the pendulum's ball rests centred in the dock, the swing settled and the bar
still gripped.

The steps count only in this order. Once a step is done, it stays done. The task is done when its last step is done, and
it stays done even if a failure ends the episode afterwards. The task fails, and the episode ends at once, when:
- the carrier or its pendulum touches the obstacle block;
- the carrier drops out of the grip;
- the pendulum's ball comes into the dock too fast;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: only the fingers may touch anything, and only the carrier's bar;
- an arm touches itself, a robot part touches the table or the floor, or a contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits (Robot Interface, Safety).

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state and starts a new episode, paused until your next command. Rebuilding the
  scene takes about a second. You can reset while an episode runs (it is abandoned) or after one has ended. Only the
  last episode is graded: an episode you reset away is never graded. Do not stop early: while the episode runs, or a
  reset is left, the run can still pass.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). The robot runs as a service you reach through its client or its MCP tools,
as if it were real hardware, on a clock that does not stop while you think. Slowdown: S = 2: the world runs at 1/S of
real speed, one control step (10 ms of robot time) every 20 ms of wall-clock time (`spec()["timing"]["slowdown"]`).

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.3`, realtime mode). Its docstring (`help(rcb_client)`) is the full
reference.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `timing`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | plans `A`, rows of 8 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | the robot now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |
| `r.reset(cameras=None, include_depth=False)` | a new episode from the frozen starting state, paused (at most 3 in all); returns the start's frames |

One call returns at most 3000 images. No call is refused for its images. While 8 answers with images are still waiting
to be read, a `submit` or a `get_obs()` answers without its frames and sets `meta["frames_skipped"]`. The answers are
binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras recorded), `res.depth[camera]` (with
`include_depth=True`, metres), `res.proprio` (proprioception rows). A malformed request raises `ValueError` and changes
nothing. `cameras=None` means both: name the one you need, or `[]` for none.

`meta["done"]` and `meta["reason"]` tell how an episode ended. `meta["reason"]` is `finished` after your finish,
`failed`, `step_limit` at the step cap, or `error` after a simulator error. The `submit` that ended the episode names
the failure in `meta["why"]`. `r.reset()` returns the new start's frames and proprioception; `meta["episode"]` and
`meta["resets_left"]` count the episodes. If the service crashes, a call fails with a connection error. The service then
restarts and resumes the same episode, paused (never a reset). `r.status()` answers again once it is back; check
`control_steps` before you continue.

```python
from rcb_client import Robot
import numpy as np
r = Robot()
q0 = np.asarray(r.get_obs(cameras=[]).meta["proprio"]["now"])          # the robot at the frozen start (no time passes)
rows = ...                                                             # (T, 8) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0, cameras=[])   # starts the clock
while not r.status()["done"]:
    ...                                                                # plan the next chunk (at=...) or stream rows
```

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
- `joint_position` (8 per row): `[joint1..7, aperture]`. Each arm has 8 values: its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open). Each finger moves at
  most 0.025 m/s. Rows are `dt` apart (a multiple of the 0.01 s control period). `interpolate` is `"linear"` (the
  default: a straight line from the targets in force) or `"hold"`. A chunk may cover at most 10 s. Out-of-limit values
  are clipped and listed in `meta["clipped"]`; the limits are in `spec()["action_types"]["joint_position"]`. The service
  executes the rows as sent.
- The servo: every control step, a jerk-limited trajectory generator (Ruckig) turns each arm's latest target into a
  smooth reference motion, with the joints synchronised to arrive together. That motion stays within 65 % of the Panda's
  joint speed limits, 55 % of its acceleration limits and 5 % of its jerk limits. The arm tracks that reference with
  torque control (PD + inverse dynamics, within the Panda's torque and torque-rate limits). A new target replans from
  the current reference motion, so a target far away is reached smoothly, not in one step.
  `spec()["robot_spec"]["servo"]` has the exact limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz.

### Observations
- World frame: metres, z up, the table top is the plane z = 0; quaternions are wxyz. Each arm's base pose is in the
  robot spec (`arms`).
- Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
  calibration in `spec()["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
- The proprio columns are named in `spec()["proprio_groups"]`: `joint_pos` (per arm joint1..7, finger_left,
  finger_right), `tcp_pose` (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort`
  (motor torques), `tool_pose` (the task tool's frame), `target` (the targets in force). The arms are listed panda-0
  first.

### Time and streaming
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds of
  wall-clock time, which is many control steps here. Drive the robot with a program: a controller of your own (Python in
  your container, with numpy and the client) that plans or streams the targets, started in the background
  (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) or in the foreground if it ends with the episode. Use your turns
  to start episodes, read what happened, and improve the program.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step). They replace whatever was planned from `at` on
  and keep what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode, so the next step has that number. `res.meta["proprio"]["now"]` is the
  proprioception now. `res.meta["plan_end_step"]` is where the plan now ends.
- Open loop: plan a movement at once. Rows are `dt` apart (a multiple of 0.01 s), a chunk covers at most 10 s of robot
  time, and step `at = 0` is the episode's start.
  `r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly
  those rows from the first step. Before the plan runs out, plan the next chunk with its own `at`, at most
  `spec()["timing"]["max_ahead_steps"]` steps ahead of the next control step.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped; `res.meta["late_steps"]` counts
  them. The rest of the chunk applies from the next step.
- `get_obs()` reads the robot and the cameras now; `get_obs(last_s=n)` returns, without waiting, what the cameras
  recorded over the last n seconds (the robot keeps executing its plan). Rendering a camera takes 10-150 ms on the
  service's GPU, time the simulator is not stepping: ask only for the cameras you need. `spec()["timing"]` states all
  this; `r.status()` shows `running` and `lag_s`.

### Arms and tools
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame
(the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand
along the fingers. At the start the TCP is at (-0.03, -0.14, 0.36), exactly at the carrier bar's centre, with the
gripper pointing straight down (orientation wxyz (0, 1, 0, 0)). The fingers close along world y and start partly open,
at 0.016 m each (aperture 0.032 m), straddling the 30 mm wide bar. The action's last component is the total aperture, 0
to 0.08 m. In this task the finger servo is stiffer (kp 800, kd 8), and finger motion is not time-synchronised with the
arm joints.

### Episode clock
The scene is dynamic: from the episode's first control step on, things move by themselves, and they do not wait for the
robot. Time does not stop: an episode starts paused, on the frozen starting state, the arms holding their starting
joints. Its clock starts at your first `submit` and from then on the simulator runs one control step (10 ms of robot
time) every 20 ms of wall-clock time, whether or not you send anything, until the episode ends. Between your commands
each arm executes what you planned, then holds its last targets; nothing pauses for you, not your thinking, not your
tool calls. The episode lasts at most 25 s of robot time (the task's horizon, 2500 control steps, about 50 s of
wall-clock time). If the horizon is reached before the task is complete, the task has failed.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits. These limits cover joint positions, joint
and finger speeds, the hand's speed and acceleration, joint accelerations and jerks, motor torques, and how fast the
torques change. The numbers are in the robot spec's `safety_limits`. The limits apply to the motion as measured,
whatever was commanded (a catch or a strike moves the arm too). The servo's own reference motion must also stay within
the same speed, acceleration and jerk limits.

### Goal points
- The waypoints are not marked. They are for the bar's centre, in the world frame: A (-0.05, 0.04, 0.38), then B (0.0,
  0.15, 0.37), each within a few centimetres.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 3 resets, each a new episode from the same frozen starting state; only the last episode is graded.
- Steps: the episode ends by itself after 25 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
