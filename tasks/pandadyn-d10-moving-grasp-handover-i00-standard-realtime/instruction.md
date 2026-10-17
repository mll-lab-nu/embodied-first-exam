# Panda Dynamic Scenes · Moving grasp handover (D10) — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, you reach it only through a client, and like the real world it does not wait
for you: once an episode is running, the scene and the robot move while you think.
**Task:** A long bar-shaped part is already riding a powered roller conveyor when the episode starts. The left arm must grasp it with its gripper while it is still moving and lift it, then carry it, still moving, through a presentation point. It then hands the part over to the right arm: both grippers hold it at the same time, then the left gripper opens wide and lets go while the right one keeps holding it. Finally the right arm must lay the part into a long open slot that slides back and forth on a rail and let go of it, so that the part lies in the slot while the slot is moving.

**Slowdown: S = 6.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms = 60 ms of wall-clock time (this simulator cannot keep up with real time on the service's CPUs; S is
the task's, from its measured speed). `spec()["timing"]["slowdown"]` states it.

## Scene
Two Pandas with their standard two-finger grippers and no tool. panda-0 (left): base at (-0.55, -0.23, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x). Each arm's tool frame is its gripper TCP (the point between the fingertips). At the start both TCPs point straight down (TCP z = world -z, and TCP x = world +x for both arms), so the fingers close along world y. Left TCP at (-0.10, -0.10, 0.20); right TCP at (0.19, 0.16, 0.23). Both grippers start partly open at 0.024 m per finger (0.048 m total aperture). The action's last entry is the total aperture in [0, 0.08] m, and each finger moves at most 0.025 m/s. In this task the fingers follow their own trajectory, not synchronized with the arm joints, so an aperture change does not stretch the duration of the arm motion. Role labels per phase (left, right): moving_pickup: moving_grasper, preparing_receiver; moving_presentation: moving_donor, tracking_receiver; overlapping_grips: donor_grip, receiver_grip; donor_release: releasing_donor, sole_support; receiver_slot_delivery: cleared_donor, slot_deliverer.

An orange bar-shaped part (0.22 x 0.034 x 0.036 m, long axis along world x) lies across a short roller conveyor. The conveyor has 20 grey rollers (radius 6 mm, 136 mm long, axes along x, 12.5 mm apart along y) on a pedestal, all motor-driven so that their tops carry the part along +y. The part is longer than the rollers and overhangs them at both ends. At t = 0 the part is already moving along +y with the conveyor. The conveyor keeps running for the whole episode, and nothing stops the part at its end: a part that is not taken is carried off the end and falls. A blue open box, the 'slot' (0.25 m along x by 0.13 m along y inside, 0.06 m deep), rides a straight rail along y. The slot is driven back and forth along the rail in a smooth sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

**Goal geometry.** Presentation point (0.09, 0.05, 0.24) for the part's centre (moving_presentation). Lift height: part centre above z = 0.21 m (moving_pickup). Drop limit: part centre must stay at or above z = 0.13 m during moving_presentation, overlapping_grips and donor_release.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and
they do not wait for the robot. **Time does not stop**: an episode starts paused, on the frozen starting state, the arms
holding their starting joints. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the
simulator runs one control step (10 ms of robot time) every 60 ms of wall-clock time, whether or not you send
anything, until the episode ends. Between your commands each arm executes what you planned, then holds its last targets;
nothing pauses for you, not your thinking, not your tool calls. The episode lasts at most **25 s of robot time**
(the task's horizon, 2500 control steps, about 150 s of wall-clock time): when it is reached
before the task is complete, the task has failed. At t = 0 the part is already riding the conveyor toward its end and the slot is already moving; both keep going without any action, and the rollers spin for the whole episode. If the part is not grasped in time, it falls off the conveyor's end. The slot is too slow for the last phase near its turning points, so when the delivery can succeed depends on how long the earlier phases took.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_pickup**: the left gripper grips the part (both left-arm fingers, finger links or pads, are in contact with it) at a moment when the part moves faster than 0.025 m/s; this is recorded once. After that, with the left grip still holding, the part's centre rises above z = 0.21 m.
2. **moving_presentation**: while the left gripper still grips the part (both fingers in contact), the part's centre comes within 0.07 m of the presentation point (0.09, 0.05, 0.24) at a moment when the part moves faster than 0.015 m/s.
3. **overlapping_grips**: both grippers grip the part at the same time (both fingers of each hand in contact with it) for 0.08 s without interruption.
4. **donor_release**: the right gripper grips the part (both fingers in contact), no left-arm finger touches the part, and the left gripper is open wider than 0.065 m (sum of its two finger positions), all for 0.12 s without interruption.
5. **receiver_slot_delivery**: the part lies in the moving slot, and the slot moves along its rail faster than 0.02 m/s, for 0.7 s without interruption. The part touches the slot, and neither gripper grips it (a single finger may still touch it). In the slot's frame its centre is within 0.014 m of the slot centre along x (the slot's long axis), within 0.045 m along y, and between 0.01 m and 0.06 m above the slot floor. It moves at less than 0.05 m/s relative to the slot. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during moving_presentation, overlapping_grips or donor_release, the part's centre drops below z = 0.13 m (`handover_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** There are no tools. The fingers of either gripper (finger links and pads) may touch the part and nothing else: not the conveyor rollers or frame, not the slot or its rail, not the table. No other robot part (hand or arm links) may touch anything, the part included. The two arms may never touch each other, finger to finger included, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
