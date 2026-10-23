# Panda Dynamic Scenes · Pendulum energy relay (D08) — STANDARD MODE (robot as a service, eai-standard/2.1)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, and you reach it only through a client. You get one client, one episode at a
time and 3 resets.
**Task:** A passive pendulum (a rod with a ball-shaped bob) hangs between the two arms, each of which holds a flat paddle. The left arm must actively push the pendulum so that it swings out toward the right arm. The right arm must catch it while it is still swinging fast and brake it, taking at least 60 % of its swing energy out, then actively drive it back so that it swings out toward the left arm, no longer touching it. The left arm must then touch it again, and the pendulum must end up hanging almost straight down and almost still, and stay that way for one second without the right paddle touching it.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each hand carries the same rigid 'fork' paddle: one flat vertical blade, 12 mm thick, 0.14 m wide (2 x `tool_half`, 0.07 at this instance) and 50 mm tall. A grey adapter on the hand side joins the blade: a horizontal bar from the hand (0.035 m above the tool origin, tool x from -0.152 to -0.058), a short post at tool x = -0.07 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the blade's back face (x from -0.064 to -0.006, z from 0.009 to 0.021); blade and adapter form one rigid tool link. The tool frame is the centre of the blade: x is the blade normal (pointing away from the arm's own base), y runs along the blade's width, z is up. With the tool level the hand points straight down and the blade centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. Start: left tool frame at (-0.04, -0.02, 0.21), axes aligned with the world (blade normal +x); right tool frame at (0.28, 0.02, 0.21), rotated 180 deg about z (blade normal -x, facing the left arm). Both arms use the default motion profile (the joint trajectory generator at 55 % of the Panda's acceleration limits and 5 % of its jerk limits); wrist joints 5-7 use higher damping gains (24, 20, 14 instead of 12, 10, 7). Role labels per phase (left, right): left_excitation: exciter, preparing_brake; right_braking: cleared_exciter, brake; right_return_impulse: preparing_receiver, return_driver; left_recovery: brake, cleared_driver; low_energy_hold: damping_support, cleared_partner. On both arms the tool's adapter runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as `self_collision` (both grippers start fully open, at 0.08 m).

A passive pendulum hangs between the two arms from a grey stand: a blue rod (18 mm square cross-section, 0.22 m from the hinge to the bob centre) ending in an orange ball-shaped bob (radius 26 mm). Its hinge axis is horizontal and parallel to world y, so it swings in the vertical x-z plane, toward one arm or the other. The hinge has no motor, no friction and no damping, so once set swinging the pendulum keeps swinging until something takes the energy out. The stand (a horizontal bearing arm reaching to the hinge and an upright post down to the table, plus a small blue block just under the hinge) lies on the +y side of the swing plane, leaving the swing plane open. At t = 0 the pendulum hangs almost straight down and almost at rest. There is nothing else in the scene. The table top is the world's z = 0 plane.

## Time in this scene
The simulated clock advances **only through your calls**: every row of a `submit` and
every second of an `observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you
think. A call that runs control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and
returns what the cameras saw. The episode lasts at most **25 s of robot time** (the task's horizon,
2500 control steps): when it is reached before the task is complete, the task has failed. At t = 0 the pendulum hangs nearly still, and nothing moves until a paddle touches it. Once excited it swings freely without damping until a paddle takes the energy out, so judge where it is in its swing from consecutive frames.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_excitation**: the left paddle (any part of panda-0's tool link) touches the pendulum while that tool's centre-of-mass speed is above 0.03 m/s (an active push, recorded once); after that, the pendulum swings out toward the right arm beyond `minimum_excursion` = 0.18 rad (about 10.3 deg) from straight down, i.e. hinge angle q < -0.18 rad, bob displaced toward +x. The paddle may or may not still be touching the pendulum at that moment.
2. **right_braking**: the right paddle catches the swinging pendulum and brakes it. A catch starts at a step where the right paddle (any part of panda-1's tool link) touches the pendulum, the left paddle does not, the right paddle did not touch it on the previous physics step (a contact onset), and the pendulum's angular speed on the previous step was at least `brake_min_speed` = 1.0 rad/s; the swing energy E of that previous step is recorded. A catch is void once the left paddle touches the pendulum or more than `brake_window` = 0.5 s have passed since its start; a new catch then needs a new onset. The phase completes at a step during a valid catch where the right paddle touches the pendulum, its angular speed is below 0.45 rad/s, and its swing energy is at most (1 - `brake_energy_drop`) = 0.4 times the recorded energy. The swing energy is E = M g d (1 - cos q) + 0.5 I (dq/dt)^2, relative to hanging at rest, with the swinging link's mass M, the distance d of its centre of mass from the hinge axis and its moment of inertia I about that axis (the simulator's mass properties of the rod and bob).
3. **right_return_impulse**: the right paddle touches the pendulum while that tool's centre-of-mass speed is above 0.03 m/s (an active push, recorded once in this phase); after that, at a moment when the right paddle is not touching the pendulum, the pendulum is beyond `return_excursion` = 0.12 rad (about 6.9 deg) toward the left arm (q > 0.12 rad, bob displaced toward -x) and is still swinging further toward the left arm at more than 0.25 rad/s (dq/dt > +0.25 rad/s).
4. **left_recovery**: the left paddle touches the pendulum (any contact).
5. **low_energy_hold**: the pendulum is within 0.055 rad (about 3.2 deg) of hanging straight down (|q| < 0.055 rad) its angular speed is below 0.12 rad/s, and the right paddle does not touch it, for 1.0 s without interruption. The left paddle may touch it during the hold. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`; `meta["reason"]`: `success`, `failed`, or `error` after a simulator error; the `submit` that
ended it also names the failure in `meta["why"]`).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each paddle (blade and adapter, one rigid tool link) may touch only the swinging part of the pendulum (rod and bob). Neither paddle may touch the pendulum's stand (bearing arm, post, block under the hinge), the table or anything else. No other part of either robot, the fingers included, may touch anything. The two arms and their paddles may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
- **Episodes and resets.** The first episode starts when the service comes up. An episode ends on success, on a failure,
  when your time is up, or on a simulator error. You have **3 resets** (`spec()["budget"]["reset"]`, which is
  authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot and the scene
  back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a new
  episode, either abandoning the running episode or after one has ended; it returns the start's frames and
  proprioception. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives
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
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and
  simulated time are reported as cost.
- **If the service crashes**, a call fails with a connection error (or a 5xx): it restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.status()` answers
  again once it is back; check `control_steps` before you continue (`spec()["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring (`python -c "import rcb_client; help(rcb_client)"`) lists the calls and
their arguments; it is the client of every `eai-standard/2.1` service, so the robot facts it names as examples are not
this robot's: this robot's are in `r.spec()` and below. The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, `max_watch_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free, no time passes), or hold the last targets and watch for `seconds` (at most 30) |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows: one at the call's start, one
every 1/`video_fps` s of robot time, one at its end). `video_fps` (1..30, default 10) sets how many frames a call returns; a call may
return at most `spec()["max_frames_per_call"]` images. A malformed request raises `ValueError` and runs nothing; once an
episode has ended, `submit` raises `EpisodeOver` (409) and `get_obs` still answers (no time passes).
```python
from rcb_client import Robot
import numpy as np
r = Robot()
obs = r.get_obs(cameras="overview")                                    # the robot at the frozen start (no time passes)
q0 = np.asarray(obs.meta["proprio"]["now"])
rows = ...                                                             # (T, 16) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", cameras="closeup", video="frames", video_fps=25)
res.frames["closeup"], res.proprio, res.meta["done"], res.meta["reason"]
if res.meta["done"] and not res.meta["reason"] == "success":
    r.reset()                                                          # a new episode (while resets are left)
```
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
calibration in `spec()["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
`cameras=None` (or `[]`) means both: name the one you need. `video="none"` returns only the last frame (the fastest call).

### Action type
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (a multiple of the 0.01 s control period); `interpolate="linear"` (default: a straight
  line from the targets in force) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed
  in `meta["clipped"]` (limits in `spec()["action_types"]["joint_position"]`). The client sends the rows as float64, and
  the service executes them as sent. `observe` with `seconds > 0` keeps the last targets in force.
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
