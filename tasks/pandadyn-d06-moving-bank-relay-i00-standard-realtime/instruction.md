# Panda Dynamic Scenes · Moving bank relay (D06) — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, you reach it only through a client, and like the real world it does not wait
for you: once an episode is running, the scene and the robot move while you think.
**Task:** A low-friction puck is already sliding toward the right arm at the start, through the first of two gaps in a row of posts across the table. The right Panda's paddle must strike it. The puck must then come back through that same gap and hit the left Panda's paddle, which acts as a rebound board. The right paddle strikes the puck a second time. The puck must then come back through the second gap and hit the left board again, with the board at a clearly different position and angle from the first rebound. Finally the puck must cross a goal line in front of a backstop wall on the right arm's side, without the right paddle touching it as it crosses.

**Slowdown: S = 3.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms = 30 ms of wall-clock time (this simulator cannot keep up with real time on the service's CPUs; S is
the task's, from its measured speed). `spec()["timing"]["slowdown"]` states it.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m for both arms), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x) and 0.04 m above it. Left paddle (the rebound board) start: centre (-0.015, 0.08, 0.045), orientation identity (faces normal to world x, length along world y). Right paddle start: centre (0.27, -0.11, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg). At the start height each paddle's lower edge is 0.020 m above the table. Role labels (panda-0 / panda-1) by phase: right_first_strike preparing_board / striker; left_first_rebound rebound_operator / preparing_receiver; right_recovery_strike changing_board / striker; left_changed_rebound rebound_operator / cleared_striker; terminal_goal board_support / cleared_striker.

A small orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction. At t = 0 it is already moving toward the right arm. Four short orange posts (24 mm x 50 mm, 60 mm tall) stand in a row across the table between the arms. The middle two overlap into a single block, so the row leaves two equal gaps, and the puck starts in line with the first gap. The posts are not bouncy. A long, very bouncy rail (70 mm tall) runs along the +y side of the course. A short backstop wall (0.14 m wide, 70 mm tall, not bouncy) stands behind the goal line on the right arm's side. All of these are fixed, and only the puck moves by itself. The table top is the world's z = 0 plane.

**Goal geometry.** Crossing lines for the puck's centre. Gap 0 line: x = 0.16 with |y + 0.01| < 0.048 m, crossed in -x. Gap 1 line: x = 0.16 with |y - 0.16| < 0.048 m, crossed in -x. Goal line: x = 0.42 with |y - 0.16| < 0.055 m, crossed in +x;.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and
they do not wait for the robot. **Time does not stop**: an episode starts paused, on the frozen starting state, the arms
holding their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the
simulator runs one control step (10 ms of robot time) every 30 ms of wall-clock time, whether or not you send
anything, until the episode ends. Between your commands each arm executes what you planned, then holds its last targets;
nothing pauses for you, not your thinking, not your tool calls. The episode lasts at most **25 s of robot time**
(the task's horizon, 2500 control steps, about 75 s of wall-clock time): when it is reached
before the task is complete, the task has failed. The puck is already sliding toward the right arm at t = 0 and keeps sliding for a long time, so it is moving from the very first frame. Any touch by the right paddle in the first phase completes it.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **right_first_strike**: The puck touches the right paddle. Any contact counts; there is no speed condition.
2. **left_first_rebound**: During this phase the puck's centre crosses the line x = 0.16 moving in -x, with |y - (-0.01)| < 0.048 m, i.e. back through gap 0. Moving in -x means x was >= 0.16 on the previous physics step and is < 0.16 now. After that crossing, the puck touches the left paddle. The left paddle's tool-frame pose (position and orientation) at that contact is recorded.
3. **right_recovery_strike**: The puck touches the right paddle more than 0.06 s after this phase began.
4. **left_changed_rebound**: During this phase the puck's centre crosses x = 0.16 moving in -x, with |y - 0.16| < 0.048 m, i.e. through gap 1. After that crossing, the puck touches the left paddle while two pose conditions hold. The paddle's tool-frame origin is more than 0.035 m from the recorded first-rebound position. And its orientation is rotated by more than 0.24 rad (about 13.8 deg) from the recorded orientation, i.e. |q . q_first| < cos 0.12. Contacts that do not meet the pose condition do not count, but they do not fail the task either.
5. **terminal_goal**: The puck's centre crosses x = 0.42 moving in +x, with |y - 0.16| < 0.055 m, while the puck is not touching the right paddle. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each paddle may touch only the puck. The paddles must not touch the posts, the rail, the backstop, the table or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their paddles must never touch each other, and a paddle must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
  have **10 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset and the one
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
- There is nothing to hand in: the service records every control step it ran, replays the last episode in a fresh
  process and grades the replay. Keep the program that drives the robot at `/app/output/gen.py` for the record: save it
  early and keep it current. Do not stop early: while the episode runs, or a reset is left, the run can still pass.
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
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows). A malformed request raises
`ValueError` and changes nothing.
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
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
calibration in `spec()["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
`cameras=None` means both: name the one you need, or `[]` for none.

### Action type
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (a multiple of the 0.01 s control period); `interpolate="linear"` (default: a straight
  line from the targets in force) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed
  in `meta["clipped"]` (limits in `spec()["action_types"]["joint_position"]`). The realtime client sends the rows as
  float64, and the service executes them as sent.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
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
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
