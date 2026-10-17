# Panda Dynamic Scenes · Catch, self-toss, recatch and deliver (S09) — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, you reach it only through a client, and like the real world it does not wait
for you: once an episode is running, the scene and the robot move while you think.
**Task:** A ball is thrown high into the air when the episode starts and comes down near the robot. Catch it in the shallow cup the Panda holds, which has one open side. Bring the cup to a launch region and toss the ball straight up out of the cup with a real throw: it must leave the cup floor while rising. Move the cup sideways and catch the ball again. Finally, release it into an open box that slides back and forth along a rail, where it must settle while the box is moving.

**Slowdown: S = 2.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms = 20 ms of wall-clock time (this simulator cannot keep up with real time on the service's CPUs; S is
the task's, from its measured speed). `spec()["timing"]["slowdown"]` states it.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a shallow square 'toss cup': 0.12 m x 0.12 m inside (2 x `tool_half`), walls 15 mm high (`tool_height`) and 5 mm thick, floor 5 mm thick. The wall on the tool frame's +x side is missing, giving a permanently open pouring lip. The tool frame is the centre of the floor's top surface, z up out of the cup, x towards the open side. A fixed adapter bar connects the closed -x wall to the hand; in the tool frame the hand's TCP is at (-0.12, 0, +0.04), so the cup hangs 12 cm ahead of and 4 cm below the TCP. At the start the cup is level (identity orientation; open side facing world +x), centre at (0.03, -0.15, 0.22).

A small orange ball (radius 12 mm) is thrown upwards and towards the robot at t = 0. It rises high and falls back down near the cup within about the first second. A blue open box (the cart: 0.15 m x 0.15 m inside, 0.06 m deep) is the moving link of a straight rail along the world's y axis. It is driven back and forth the whole episode, slowly, and slowest where it turns around. There are no other objects. The table top is the world's z = 0 plane.

**Goal geometry.** Launch point (0.30, -0.10, 0.30) for the cup's tool frame, radius 2.5 cm.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and
they do not wait for the robot. **Time does not stop**: an episode starts paused, on the frozen starting state, the arms
holding their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the
simulator runs one control step (10 ms of robot time) every 20 ms of wall-clock time, whether or not you send
anything, until the episode ends. Between your commands each arm executes what you planned, then holds its last targets;
nothing pauses for you, not your thinking, not your tool calls. The episode lasts at most **25 s of robot time**
(the task's horizon, 2500 control steps, about 50 s of wall-clock time): when it is reached
before the task is complete, the task has failed. The ball is already in the air at t = 0 and comes down within about the first second, so watch it in short steps. The cart moves back and forth the whole time and is too slow for the last phase near its turning points. When the delivery can succeed therefore depends on how long the earlier phases took.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **initial_catch**: The ball first flies free (touching nothing) for at least 25 ms. It then enters the cup from above: its centre crosses downwards through the plane `tool_height` + `radius` = 0.027 m above the cup floor (cup frame) while within `tool_half` - `radius` = 0.048 m of the cup centre in both x and y of the cup frame. After that entry the ball stays in the cup for 0.18 s without interruption. In the cup frame this means: |x| and |y| < `tool_half` - 0.45 x `radius` = 0.0546 m; centre between `radius` - 4 mm = 0.008 m and `tool_height` - 0.12 x `radius` = 0.01356 m above the floor; touched by the cup within the last 25 ms; speed relative to the cup (at the ball's position) < 0.09 m/s.
2. **launch_region**: The cup's tool frame comes within 2.5 cm of the launch point (0.30, -0.10, 0.30). The ball is not checked here. The cup position at that moment is recorded as the launch height.
3. **self_toss**: All of the following, in this phase. (a) At some step the ball moves upwards faster than 0.2 m/s with its centre more than 0.06 m above the cup height recorded in launch_region. (b) A separation from the cup floor. On a step where the ball touches nothing, within 0.06 s after its last contact with the cup, and with its centre less than `radius` + 12 mm = 0.024 m above the cup floor (cup frame), three things hold. The ball rises faster than 0.2 m/s in the world. Its velocity relative to the cup floor (at the ball's position) along the cup's z axis is more than 0.03 m/s away from the floor. The cup's z axis is within 0.35 rad of vertical. (c) The ball then touches nothing (neither the cup nor anything else) from that separation on. Any contact cancels the separation and a new one is needed. At least 0.06 s after the separation, with (a) already recorded, the ball's centre is more than `tool_height` + `radius` = 0.027 m above the cup floor, both in the cup frame and in world height above the tool frame's origin. The cup position at the separation is recorded.
4. **displaced_recatch**: The cup catches the ball again by the same test as initial_catch: a fresh downward entry through the 0.027 m plane within 0.048 m of centre after at least 25 ms of free flight, then retention in the cup for 0.18 s without interruption. At a step where this catch holds, the cup's tool frame is more than 3 cm horizontally (in world x-y) from its position at the toss separation.
5. **moving_receiver_delivery**: The ball rests in the cart. In the cart's frame: |x| and |y| < 0.075 - 0.45 x `radius` = 0.0696 m; centre between 0.008 m and 0.06 - 0.12 x `radius` = 0.05856 m above the cart floor; touched by the cart within the last 25 ms; speed relative to the cart < 0.09 m/s. At the same time the ball does not touch the cup and the cart moves faster than 0.02 m/s, for 0.7 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the cup may touch the ball, and the cup may touch nothing but the ball: not the cart, its rail or base, and not the table. No other part of the robot (fingers, hand, links, base) may touch anything, including the ball. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `spec()["robot_spec"]["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Rules (real-robot rules)
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds of
  wall-clock time, which is many control steps here. Drive the robot with a program: a controller of your own (Python in
  your container, with numpy and the client) that plans or streams the targets, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the episode. Use
  your turns to start episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends on success, on a failure, when your time is up, or on a simulator error. You
  have **3 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset and the one
  episode is the run). `r.reset()` puts the robot and the scene back on the same frozen starting state (the scene is
  rebuilt, about a second) and starts a new episode, paused until your next `submit`, either abandoning the running
  episode or after one has ended. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives
  `resets_left`) until you reset. **Only the last episode is graded**: an episode you reset away is never graded, a
  success ends the run at once (no reset after it), and when your time is up the episode then running is the one graded.
  The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, fingers, hand TCP and tool poses, velocities, motor torques, the targets in force). No object poses, no success
  signal before the end: the service tells you that an episode ended and why (`meta["done"]`, `meta["reason"]`:
  `"success"`, `"error"` after a simulator error, else `"failed"`).
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it ran.
  Keep the program that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current. Do
  not stop early: while the episode runs, or a reset is left, the run can still pass.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode, paused
  (never a reset). `r.status()` answers again once it is back; check `control_steps` before you continue.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a movement at once (rows `dt` apart, a multiple of 0.01 s; a chunk covers at most 10 s of robot time),
  from step `at = 0` for the episode's start: `r.submit("joint_position", rows, dt=0.01, interpolate="hold", at=0,
  cameras=[])` starts the clock and runs exactly those rows from the first step; plan the next chunk with its own `at`
  (at most `spec()["timing"]["max_ahead_steps"]` steps ahead of the next one) before the plan runs out.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot and the cameras now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time
  run and returns what the cameras saw meanwhile (the robot keeps executing its plan). Rendering a camera takes 10-150 ms
  on the service's GPU, time the simulator is not stepping: ask only for the cameras you need. `spec()["timing"]` states
  all this; `r.status()` shows `running` and `lag_s`.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `timing`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 8 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows). A malformed request raises
`ValueError` and changes nothing.
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
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
calibration in `spec()["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
`cameras=None` means both: name the one you need, or `[]` for none.

### Action type
- `joint_position` (8 per row): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (a multiple of the 0.01 s control period); `interpolate="linear"` (default: a straight
  line from the targets in force) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed
  in `meta["clipped"]` (limits in `spec()["action_types"]["joint_position"]`). The realtime client sends the rows as
  float64, and the service executes them as sent.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 90 % (acceleration) and 2 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `spec()["robot_spec"]["servo"]` has the exact limits and gains.

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- `spec()["proprio_groups"]` names the proprio columns: `joint_pos` (per arm joint1..7, finger_left, finger_right), `tcp_pose`
  (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort` (motor torques), `tool_pose` (the
  task tool's frame), `target` (the targets in force). The arms are listed panda-0 first.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
