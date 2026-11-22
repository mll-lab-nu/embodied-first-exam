# Panda Dynamic Scenes · Conveyor pick, carriage load, braking and dock unload (S07) (realtime)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). At the start a small cube (the part) rides along a powered roller conveyor,
and a shallow carriage is already coasting along a frictionless rail. Grasp the part with the gripper while it is moving
and lift it; set it on the moving carriage and let go while the carriage is still moving; then grip the carriage's
vertical handle with both fingers and bring the carriage to a stop, with the part still on it, before it reaches the end
of its rail; grasp the part again and lift it off the carriage; finally set it down in a fixed dock and leave it there
at rest. The robot runs as a service you reach only through its client, as if it were real hardware, on a clock that does not stop while you think. Slowdown: S = 4: the world runs at 1/S of real speed, one control step
(10 ms of robot time) every 40 ms of wall-clock time (`spec()["timing"]["slowdown"]`).

### Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x), with no tool: the bare Panda hand and its two parallel fingers. The
task's tool frame is the Panda TCP (between the fingertips). At the start the TCP is at (-0.13, -0.11, 0.21) with
orientation wxyz (0, 1, 0, 0): the gripper points straight down, the hand's x axis along world x, the fingers closing
along world y; the fingers start 0.048 m apart (each at 0.024 m). The action's last element is the total finger opening
(0 to 0.08 m); in this task the gripper's motion is not time-synchronised with the arm joints' trajectory.

An orange cube, the part (36 mm edge), lies on a roller conveyor (20 grey rollers of 6 mm radius and 0.136 m length,
axes along x, 12.5 mm apart, on a dark frame) whose powered rollers carry it along +y toward the conveyor's end from t =
0; if nothing takes it, it reaches the end after a few seconds and falls off. A blue carriage (a shallow tray 0.17 m
along x by 0.11 m inside, 9 mm walls, with a vertical blue handle 28 mm x 36 mm x 76 mm outside its +x wall) runs on a
straight rail along y; it has no motor and no friction and is already coasting along +y at t = 0, and it keeps going
until something stops it or it reaches the end of its rail. A blue open box, the dock (0.13 m x 0.12 m inside, 0.04 m
deep), stands fixed just above the table. The table top is the world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. Time does not stop: an episode starts paused, on the frozen starting state, the arms holding
their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator
runs one control step (10 ms of robot time) every 40 ms of wall-clock time, whether or not you send anything, until the
episode ends. Between your commands each arm executes what you planned, then holds its last targets; nothing pauses for
you, not your thinking, not your tool calls. The episode lasts at most 25 s of robot time (the task's horizon, 2500
control steps, about 100 s of wall-clock time): when it is reached before the task is complete, the task has failed. At
t = 0 the part is already travelling along the conveyor toward its end, and the carriage is already coasting along its
rail; neither stops by itself (the part falls off the conveyor's end; the carriage reaching the end of its rail fails
the task).

## Goal
Success: both fingers grasp the part while it still rides the conveyor and lift it (above about 0.2 m); the part is set
on the moving carriage and let go while the carriage still moves; then both fingers grip the carriage's vertical handle
(the handle only) and bring the carriage to a stop, the part still on it, before it reaches the end of its rail; the
part is grasped again and lifted off the carriage (above about 0.2 m); finally it is set down in the dock and left there
at rest for about half a second. The task fails at once if the carriage reaches an end of its rail before it is stopped,
or if the part falls off during the braking and the regrasp.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the two fingers may touch anything, and only the part and the carriage's
  moving body (its tray and handle). Every other contact of the robot is forbidden: the hand and arm links may touch
  nothing (not even the part or the carriage), and the fingers must not touch the conveyor (rollers or frame), the
  carriage's rail and base, the dock or the table. In every task the arm never touches itself, no robot part touches the
  table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows,
  and no contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state (the scene is rebuilt, about a second) and starts a new episode, paused
  until your next command, abandoning the running one or after one has ended. Only the last episode is graded: an
  episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
  the episode then running is the one graded. Do not stop early: while the episode runs, or a reset is left, the run can
  still pass.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the service tells you only that an episode has ended and why (a success, a failure or a
  simulator error).
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.3`, realtime mode). Its docstring (`help(rcb_client)`) is the full
reference.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `timing`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | plans `A`, rows of 8 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | a new episode from the frozen starting state, paused (at most 3 in all); returns the start's frames |

One call returns at most 3000 images. A watch is refused with a 429 while the images in flight (pending watches and
answers not read yet) would exceed it or 8 of them are outstanding; a `submit` or a `get_obs()` without seconds is never
refused for its images: its answer then comes without its frames and `meta["frames_skipped"]` is set. The answers are
binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows). A malformed request raises
`ValueError` and changes nothing. `cameras=None` means both: name the one you need, or `[]` for none.

How an episode ended: `meta["done"]`, `meta["reason"]` (`success`, `failed`, or `error` after a simulator error); the
`submit` that ended it names the failure in `meta["why"]`. `r.reset()` returns the new start's frames and
proprioception; `meta["episode"]` and `meta["resets_left"]` count the episodes. If the service crashes, a call fails
with a connection error: it restarts and resumes the same episode, paused (never a reset). `r.status()` answers again
once it is back; check `control_steps` before you continue.

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
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the episode. Use
  your turns to start episodes, read what happened, and improve the program.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a movement at once (rows `dt` apart, a multiple of 0.01 s; a chunk covers at most 10 s of robot time),
  from step `at = 0` for the episode's start:
  `r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly
  those rows from the first step; plan the next chunk with its own `at` (at most `spec()["timing"]["max_ahead_steps"]`
  steps ahead of the next one) before the plan runs out.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot and the cameras now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time
  run and returns what the cameras saw meanwhile (the robot keeps executing its plan). Rendering a camera takes 10-150
  ms on the service's GPU, time the simulator is not stepping: ask only for the cameras you need. `spec()["timing"]`
  states all this; `r.status()` shows `running` and `lag_s`.

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
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 3 resets, each a new episode from the same frozen starting state; only the last episode is graded.
