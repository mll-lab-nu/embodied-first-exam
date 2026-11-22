# Panda Dynamic Scenes · Strike, catch and merge two balls (D02) (realtime)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). Two small balls wait
behind closed shutters near the top of two parallel inclined lanes. The shutters open by themselves, the first shortly
after the start and the second a few seconds later, and each released ball rolls down its lane and flies off the open
lower end. The left Panda's paddle must touch each ball after the ball has flown free. The right Panda's cup must catch
the first ball and carry it away from the catch point without losing it. The cup must then catch the second ball while
still holding the first, and finally put both balls into a fixed basin, where they must come to rest with the cup no
longer touching them. The robot runs as a service you reach only through its client, as if it were real hardware, on a clock that does not stop while you think. Slowdown: S = 3: the world runs at 1/S of real speed, one
control step (10 ms of robot time) every 30 ms of wall-clock time (`spec()["timing"]["slowdown"]`).

### Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It carries a flat rigid paddle, 0.14 m long, 0.05 m tall
and 12 mm thick. A side adapter runs forward from the hand and then sideways to the paddle's -y end. The tool frame is
the paddle's centre, with x normal to its faces, y along its length and z up. The hand's TCP sits 0.12 m behind the
paddle centre (tool -x), 0.14 m to the tool -y side and 0.04 m above it. Start: paddle centre at (0.10, -0.21, 0.22),
orientation identity (faces normal to world x, length along world y). panda-1 (right): base at (0.74, 0.22, 0), yaw pi
(facing -x). It carries an open-top square cup, 0.14 m x 0.14 m inside, with four 0.055 m high, 5 mm thick walls and a 5
mm floor, held by an adapter on its tool -x wall. The tool frame is the centre of the cup floor's inner surface, z up
out of the cup. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Start: cup frame at (0.19, 0.17,
0.18), quaternion (0, 0, 0, 1) (yawed 180 deg: tool x = world -x, tool y = world -y, cup upright). On both arms the
tool's adapter runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers
touch the adapter, which ends the episode as a collision with its own tool (both grippers start fully open, at 0.08 m).

Two identical small orange balls (radius 16 mm) start at rest: ball1 in the lane on the -y side, ball2 in the lane on
the +y side. Each lane is a straight grey gravity channel with a 70 mm wide, low-friction floor and 22 mm side walls.
The lanes are open at both ends, stand on posts above the table and slope down toward +x. Near the upper end of each
lane an amber shutter blocks the ball, and a small fixed housing block stands beside each shutter. The shutters are
motor-driven and lift by themselves: ball1's shutter opens shortly after the start and ball2's a few seconds later (the
exact time varies from instance to instance). Each released ball rolls down its lane and leaves the lower end in free
flight. A fixed blue open-top basin, 0.16 m x 0.16 m inside and 0.075 m deep, stands on posts above the table. Nothing
else moves by itself. The table top is the world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. Time does not stop: an episode starts paused, on the frozen starting state, the arms holding
their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator
runs one control step (10 ms of robot time) every 30 ms of wall-clock time, whether or not you send anything, until the
episode ends. Between your commands each arm executes what you planned, then holds its last targets; nothing pauses for
you, not your thinking, not your tool calls. The episode lasts at most 25 s of robot time (the task's horizon, 2500
control steps, about 75 s of wall-clock time): when it is reached before the task is complete, the task has failed. At t
= 0 both balls are still at rest behind their shutters. The first shutter opens a fraction of a second later, so ball1
is rolling almost immediately. The second shutter opens on its own a few seconds later, whether or not the first ball
has been handled.

## Goal
Success: each ball, once it has flown free off its lane, is touched by the left paddle (where it goes after that is up
to you); the right cup catches the first ball and carries it well away from where it caught it, then catches the second
ball while still holding the first; finally both balls rest in the basin, the cup no longer touching them, for about 0.7
s. A catch means the ball drops into the cup from above after flying free and stays there, not a bounce. The task fails
at once if the first ball spills from the cup between its carry and the second catch.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The paddle and the cup may touch only the two balls. Neither tool may touch the
  lanes or their support posts, the shutters or their housing blocks, the basin or its posts, the table, or the robot
  pedestals. No other robot part, the fingers included, may touch anything. The two arms and their tools must never
  touch each other, and a tool must not touch its own arm. In every task an arm never touches itself, no robot part
  touches the table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what the
  task allows, and no contact presses deep into anything;
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
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | plans `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
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
rows = ...                                                             # (T, 16) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0, cameras=[])   # starts the clock
while not r.status()["done"]:
    ...                                                                # plan the next chunk (at=...) or stream rows
```

### Actions
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each
  arm's 8 values are its 7 absolute joint-position targets (rad, `panda_joint1..7`) and its total gripper aperture
  target (m, 0 = closed .. 0.08 = open; each finger moves at most 0.025 m/s). Rows are `dt` apart (a multiple of the
  0.01 s control period); `interpolate="linear"` (default: a straight line from the targets in force) or `"hold"`; a
  chunk may cover at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in
  `spec()["action_types"]["joint_position"]`). The service executes the rows as sent.
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
