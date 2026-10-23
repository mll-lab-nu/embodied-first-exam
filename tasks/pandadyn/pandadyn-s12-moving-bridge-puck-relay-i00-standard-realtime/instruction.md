# Panda Dynamic Scenes · Spinning bridge puck relay and goal (S12) — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, you reach it only through a client, and like the real world it does not wait
for you: once an episode is running, the scene and the robot move while you think.
**Task:** At the start a square puck slides fast along a raised source lane towards the Panda, and the paddle hangs just above its path. Strike the puck while it is still sliding at 0.25 m/s or more so that it slides onto a platform (the bridge) that turns continuously about a vertical axis, and from the bridge onto an exit lane. Intercept it there with the paddle, let it separate, strike it again, and send it along the exit lane through the doorway of a swinging gate that opens and closes by itself, without touching the gate, and on across a goal line, without the paddle touching it as it crosses and with the gate still open.

**Slowdown: S = 3.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms = 30 ms of wall-clock time (this simulator cannot keep up with real time on the service's CPUs; S is
the task's, from its measured speed). `spec()["timing"]["slowdown"]` states it.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a paddle: a flat rigid plate 12 mm thick, 0.10 m wide (2 x `tool_half`) and 50 mm tall, whose face normal is the tool frame's x axis. The tool frame is the paddle's centre. A rigid grey adapter behind the paddle (tool -x side) joins it to the hand: a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool link. In the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the paddle is upright with identity orientation (faces along world x, width along world y), centre at (-0.08, -0.15, 0.10): its lower edge, at z = 0.075, is above the incoming puck's path. The tool's adapter runs between the gripper's fingertips: closing the gripper to less than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as `self_collision` (the gripper starts fully open, at 0.08 m).

The puck is an orange square block 44 mm x 44 mm x 24 mm thick, quite bouncy. At t = 0 it is sliding fast towards the robot on the source lane, a low, very slippery orange slab, and passes under the parked paddle. If nothing touches it, it slows down and stops on the lane within about a second, beyond the paddle's start position. Next to the lane's end, a blue rectangular platform (the bridge, 0.20 m x 0.10 m, 20 mm thick) turns continuously about a vertical axis through its centre at a steady slow rate, clockwise seen from above. Its top is 2 mm lower than the source lane. Beyond it lies the exit lane, a second slippery orange slab 2 mm lower again. Near the exit lane's far end a motor-driven gate swings on a vertical hinge at one side edge of the lane: an amber blade 0.12 m long and 55 mm tall with a small knob on its free end, its lower edge just clear of the lane. Closed, the blade spans the whole lane. The motor swings it open (its free end moving downstream), holds it open briefly and swings it closed again, on a fixed cycle of a few seconds, open for about a second each time. Past the end of the exit lane, on the table, is the goal line, with a static orange wall (the backstop, 0.14 m wide, 8 cm tall) behind it. The table top is the world's z = 0 plane.

**Goal geometry.** Doorway line: x = 0.37 (world), crossed towards +x with the puck's centre within 0.055 m of y = 0.12, with the gate at 1.0 rad or more. Gate angle threshold at the goal crossing: more than 0.20 rad. Goal line: x = 0.48 (world), crossed towards +x with the puck's centre within 0.045 m of y = 0.12, after the doorway.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and
they do not wait for the robot. **Time does not stop**: an episode starts paused, on the frozen starting state, the arms
holding their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the
simulator runs one control step (10 ms of robot time) every 30 ms of wall-clock time, whether or not you send
anything, until the episode ends. Between your commands each arm executes what you planned, then holds its last targets;
nothing pauses for you, not your thinking, not your tool calls. The episode lasts at most **32 s of robot time**
(the task's horizon, 3200 control steps, about 96 s of wall-clock time): when it is reached
before the task is complete, the task has failed. At t = 0 the puck is already sliding fast towards the robot; if untouched it passes under the paddle and comes to rest on the source lane within about a second, and it is fast enough for incoming_strike only during roughly its first 0.4 s. The bridge turns and the gate cycles open and closed the whole time.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **incoming_strike**: The paddle touches the puck for the first time while the puck still slides fast: its horizontal speed on the physics step before that first contact must be at least `strike_min_speed` = 0.25 m/s. A first contact with a slower puck fails the task (strike_on_slow_puck).
2. **physical_bridge_transfer**: During this phase the puck touches the bridge platform at least once. After that, at some step, the puck touches the exit lane while not touching the bridge.
3. **exit_interception**: The paddle touches the puck.
4. **second_strike**: In this phase the puck first loses contact with the paddle, at time t_s (the first step of the phase without paddle contact; t_s is not reset afterwards). Later the paddle touches the puck again at a time more than 0.035 s after t_s.
5. **closing_gate_goal**: During this phase the puck must not touch the gate at all: any contact fails the task (puck_touched_gate). When the puck's centre crosses the doorway line x = 0.37 (world) moving towards +x between two consecutive physics steps within 0.055 m of y = 0.12, the gate's angle must be at least `gate_pass_angle` = 1.0 rad; otherwise the task fails (gate_not_open_at_doorway). The phase completes when the puck's centre then crosses the goal line x = 0.48 moving towards +x within 0.045 m of y = 0.12, after such a passage through the doorway, while the puck does not touch the paddle and the gate's angle is more than 0.20 rad. This completes the task. A goal-line crossing that fails any of these checks ends the task as a failure (closed_gate_or_carried_puck).

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- in incoming_strike, the paddle's first contact with the puck comes when the puck's horizontal speed (on the physics step before) is below 0.25 m/s (`strike_on_slow_puck`);
- in closing_gate_goal, the puck touches the gate (`puck_touched_gate`);
- in closing_gate_goal, the puck crosses the doorway line (x = 0.37 towards +x, |y - 0.12| < 0.055 m) while the gate's angle is below 1.0 rad (`gate_not_open_at_doorway`);
- in closing_gate_goal, the puck crosses the goal line (as defined there) while touching the paddle, or while the gate's angle is 0.20 rad or less, or without having passed the doorway with the gate open (`closed_gate_or_carried_puck`);
- the task's horizon is reached: 32 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the paddle may touch the puck, and the paddle may touch nothing but the puck: not the lanes, the bridge, the gate, the backstop or the table. No other part of the robot (fingers, hand, links, base) may touch anything. In every task: the two arms (and their tools) never touch each other
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
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
