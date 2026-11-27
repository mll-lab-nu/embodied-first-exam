# Panda Dynamic Scenes · Spinning bridge puck relay and goal (S12) (realtime)

## Task
Strike the incoming puck with the paddle while it is still sliding fast, so that it slides over the turning bridge onto
the exit lane. Stop it there, then strike it again through the doorway of the swinging gate while the gate is wide open,
without touching the gate, and across the goal line in front of the backstop.

## Goal
Success: the paddle's first touch strikes the puck while it still slides fast, so that it slides onto the turning bridge
and from the bridge onto the exit lane; the paddle intercepts it there, lets it separate and strikes it again; the puck
slides along the exit lane through the doorway of the swinging gate while the gate is wide open, never touching the
gate, and on across the goal line in front of the backstop, not touching the paddle and with the gate still open.

The steps count only in this order, and a step once done stays done: the task is done once its last step is, and it
stays done even when a failure ends the episode afterwards. The task fails, and the episode ends at once, when:
- the first touch comes when the puck has already slowed down;
- the puck touches the gate;
- the puck passes the doorway while the gate is not wide open;
- the puck crosses the goal line touching the paddle or with the gate closed;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: only the paddle may touch anything, and only the puck;
- an arm touches itself, a robot part touches the table or the floor, or a contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits (Robot Interface, Safety).

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state (the scene is rebuilt, about a second) and starts a new episode, paused
  until your next command, abandoning the running one or after one has ended. Only the last episode is graded: an
  episode you reset away is never graded. Do not stop early: while the episode runs, or a reset is left, the run can
  still pass.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). The robot runs as a service you reach through its client or its MCP tools,
as if it were real hardware, on a clock that does not stop while you think. Slowdown: S = 3: the world runs at 1/S of
real speed, one control step (10 ms of robot time) every 30 ms of wall-clock time (`spec()["timing"]["slowdown"]`).

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

How an episode ended: `meta["done"]`, `meta["reason"]` (`finished` after your finish, `failed`, `step_limit` at the step
cap, or `error` after a simulator error); the `submit` that ended it names the failure in `meta["why"]`. `r.reset()`
returns the new start's frames and proprioception; `meta["episode"]` and `meta["resets_left"]` count the episodes. If
the service crashes, a call fails with a connection error: it restarts and resumes the same episode, paused (never a
reset). `r.status()` answers again once it is back; check `control_steps` before you continue.

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
- `joint_position` (8 per row): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Rows are `dt` apart (a multiple of the 0.01 s control period); `interpolate="linear"` (default: a
  straight line from the targets in force) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped
  and listed in `meta["clipped"]` (limits in `spec()["action_types"]["joint_position"]`). The service executes the rows
  as sent.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and
  5 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
  control (PD + inverse dynamics, the Panda's torque and torque-rate limits). A new target replans from the current
  reference motion, so a target far away is reached smoothly, not in one step. `spec()["robot_spec"]["servo"]` has the
  exact limits and gains.
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
- Open loop: plan a movement at once (rows `dt` apart, a multiple of 0.01 s; a chunk covers at most 10 s of robot time),
  from step `at = 0` for the episode's start:
  `r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly
  those rows from the first step; plan the next chunk with its own `at` (at most `spec()["timing"]["max_ahead_steps"]`
  steps ahead of the next one) before the plan runs out.
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
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a paddle: a flat rigid plate 12 mm thick, 0.10 m
wide and 50 mm tall, whose face normal is the tool frame's x axis. The tool frame is the paddle's centre. A rigid grey
adapter behind the paddle (tool -x side) joins it to the hand: a horizontal bar 0.035 m above the tool origin (tool x
from -0.132 to -0.038), a vertical post at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the
post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool
link. In the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the paddle is upright with identity
orientation (faces along world x, width along world y), centre at (-0.08, -0.15, 0.10): its lower edge, at z = 0.075, is
above the incoming puck's path. The tool's adapter runs between the gripper's fingertips: closing the gripper to less
than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision with its own
tool (the gripper starts fully open, at 0.08 m).

### Episode clock
The scene is dynamic: from the episode's first control step on, things move by themselves, and they do not wait for the
robot. Time does not stop: an episode starts paused, on the frozen starting state, the arms holding their starting
joints. Its clock starts at your first `submit` and from then on the simulator runs one control step (10 ms of robot
time) every 30 ms of wall-clock time, whether or not you send anything, until the episode ends. Between your commands
each arm executes what you planned, then holds its last targets; nothing pauses for you, not your thinking, not your
tool calls. The episode lasts at most 32 s of robot time (the task's horizon, 3200 control steps, about 96 s of
wall-clock time): when it is reached before the task is complete, the task has failed.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds,
the hand's speed and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the
numbers: the robot spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a
strike moves the arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

## Others
- The puck is fast enough for the first strike only during the first fraction of a second.

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
- Steps: the episode ends by itself after 32 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
