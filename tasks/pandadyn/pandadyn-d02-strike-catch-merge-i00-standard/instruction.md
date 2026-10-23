# Panda Dynamic Scenes · Strike, catch and merge two balls (D02) — STANDARD MODE (robot as a service, eai-standard/2.1)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, and you reach it only through a client. You get one client, one episode at a
time and 3 resets.
**Task:** Two small balls wait behind closed shutters near the top of two parallel inclined lanes. The shutters open by themselves, the first shortly after the start and the second a few seconds later, and each released ball rolls down its lane and flies off the open lower end. The left Panda's paddle must touch each ball after the ball has flown free. The right Panda's cup must catch the first ball and carry it away from the catch point without losing it. The cup must then catch the second ball while still holding the first, and finally put both balls into a fixed basin, where they must come to rest with the cup no longer touching them.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It carries a flat rigid paddle, 0.14 m long (2 x `tool_half`, `tool_half` = 0.07 m), 0.05 m tall and 12 mm thick. A side adapter runs forward from the hand and then sideways to the paddle's -y end. The tool frame is the paddle's centre, with x normal to its faces, y along its length and z up. The hand's TCP sits 0.12 m behind the paddle centre (tool -x), 0.14 m to the tool -y side and 0.04 m above it. Start: paddle centre at (0.10, -0.21, 0.22), orientation identity (faces normal to world x, length along world y). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It carries an open-top square cup, 0.14 m x 0.14 m inside (2 x `tool_half`), with four 0.055 m high, 5 mm thick walls and a 5 mm floor, held by an adapter on its tool -x wall. The tool frame is the centre of the cup floor's inner surface, z up out of the cup. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Start: cup frame at (0.19, 0.17, 0.18), quaternion (0, 0, 0, 1) (yawed 180 deg: tool x = world -x, tool y = world -y, cup upright). Role labels (panda-0 / panda-1) by phase: first_redirect striker / receiver; first_catch cleared_striker / catcher; loaded_cup_relocation preparing_striker / loaded_carrier; second_redirect striker / loaded_receiver; second_catch cleared_striker / two_ball_catcher; both_delivery cleared_partner / deliverer. On both arms the tool's adapter runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as `self_collision` (both grippers start fully open, at 0.08 m).

Two identical small orange balls (radius 16 mm) start at rest: ball1 in the lane on the -y side, ball2 in the lane on the +y side. Each lane is a straight grey gravity channel with a 70 mm wide, low-friction floor and 22 mm side walls. The lanes are open at both ends, stand on posts above the table and slope down toward +x. Near the upper end of each lane an amber shutter blocks the ball, and a small fixed housing block stands beside each shutter. The shutters are motor-driven and lift by themselves: ball1's shutter opens shortly after the start and ball2's a few seconds later (the exact time varies from instance to instance). Each released ball rolls down its lane and leaves the lower end in free flight. A fixed blue open-top basin, 0.16 m x 0.16 m inside and 0.075 m deep, stands on posts above the table. Nothing else moves by itself. The table top is the world's z = 0 plane.

**Goal geometry.** All goal geometry is relative to the cup, the paddle or the basin.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they do not wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and
every second of an `observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you
think. A call that runs control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and
returns what the cameras saw. The episode lasts at most **25 s of robot time** (the task's horizon,
2500 control steps): when it is reached before the task is complete, the task has failed. At t = 0 both balls are still at rest behind their shutters. The first shutter opens a fraction of a second later, so ball1 is rolling almost immediately. The second shutter opens on its own a few seconds later, whether or not the first ball has been handled.

## Success
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **first_redirect**: At some moment during this phase, ball1 has flown free (touching nothing at all) for more than 0.025 s. After that, it touches the left paddle (panda-0's tool). Where the ball goes after the touch is not checked.
2. **first_catch**: ball1 enters the right cup (panda-1's tool) from above and is retained. The entry: after touching nothing for at least 0.025 s, the ball's centre passes downward through the plane 0.071 m above the cup floor (wall height 0.055 m + radius 0.016 m, in the cup's frame). At that crossing the centre must be within 0.054 m (`tool_half` - radius) of the cup centre along both cup x and cup y. From then on the ball must stay contained in the cup for 0.18 s without interruption. Contained in the cup means all of the following, in the cup's frame: |x| and |y| of the ball centre below 0.0628 m (`tool_half` - 0.45 x radius); height above the cup floor between 0.012 m and 0.0531 m; in contact with the cup within the last 25 ms; moving at less than 0.09 m/s relative to the cup (including the cup's rotation). The free-flight time counts only from the start of this phase. The cup's position when this phase completes is recorded as the catch position.
3. **loaded_cup_relocation**: With ball1 contained in the right cup (as defined in first_catch), the cup's tool-frame origin is more than 0.06 m from the recorded catch position.
4. **second_redirect**: At some moment during this phase, ball2 has flown free (touching nothing) for more than 0.025 s; only free flight while this phase is active counts. After that, ball2 touches the left paddle. Where the ball goes after the touch is not checked.
5. **second_catch**: ball2 enters the right cup from above and is retained exactly as in first_catch. That is: an entry after at least 0.025 s of free flight (counted from the start of this phase), crossing downward through the plane 0.071 m above the cup floor within 0.054 m of the cup centre on both axes, then contained in the cup for 0.18 s without interruption. At that moment ball1 must also be contained in the cup.
6. **both_delivery**: Both balls are contained in the basin and neither touches the cup, for 0.7 s without interruption. Contained in the basin means all of the following, in the basin's frame (origin at the centre of its floor's top surface, axes = world axes): |x| and |y| of the ball centre below 0.0728 m (0.08 - 0.45 x radius); height above the basin floor between 0.012 m and 0.0731 m; in contact with the basin within the last 25 ms; speed below 0.09 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`; `meta["reason"]`: `success`, `failed`, or `error` after a simulator error; the `submit` that
ended it also names the failure in `meta["why"]`).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during loaded_cup_relocation, second_redirect and second_catch, ball1's centre leaves the cup's interior footprint or drops low. In the right cup's frame, that is |x| or |y| greater than 0.07 m (`tool_half`), or more than 0.01 m below the cup floor surface (`first_ball_spill`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The paddle and the cup may touch only the two balls. Neither tool may touch the lanes or their support posts, the shutters or their housing blocks, the basin or its posts, the table, or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their tools must never touch each other, and a tool must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
