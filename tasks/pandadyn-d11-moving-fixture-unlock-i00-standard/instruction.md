# Panda Dynamic Scenes · Moving fixture unlock (D11) — STANDARD MODE (robot as a service, eai-standard/2.1)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, and you reach it only through a client. You get one client, one episode at a
time and 3 resets.
**Task:** The left gripper starts around the handle of a free, hand-held fixture: a short channel with a ball inside, closed at its front by a spring-loaded latch gate, with a square socket on its side above the latch's push button. The left arm must grip the fixture and move it off its stand. While the fixture is still moving, the right arm must insert its peg into the socket, press the latch button down with the peg until the gate opens, and then pull the peg back out while the left hand keeps holding the fixture. The ball must then leave the fixture, run down a fixed inclined chute and come to rest in a basin at the chute's foot. The fixture must never be dropped.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x), no tool: its tool frame is the gripper TCP (the point between the fingertips). It starts with the TCP at (-0.063, 0, 0.285), pointing straight down (TCP x = world +x, fingers closing along world y). Its fingers start open 0.0175 m each (0.035 m total aperture), straddling the fixture's 34 mm wide handle without gripping it. For this arm the finger servo is stiffer than the default (finger PD gains kp 1875 N/m and kd 8 instead of 300 and 12; the force is still capped at 15 N per finger). Its fingers also follow their own trajectory, not synchronized with the arm joints. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Its tool is a square peg, 16 x 16 mm in section and 70 mm long, hanging straight down from the tool frame: the tool frame is at the peg's top end and the tip is at tool-frame (0, 0, -0.07). A grey adapter (a horizontal bar from the hand and a short post) ends about 5 cm behind the peg on the hand side; peg and adapter form one rigid tool link. With the peg vertical the hand points straight down and the peg's top is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. Start: tool frame at (0.12, 0.15, 0.40), peg vertical, rotated 180 deg about z (tool x = world -x), so the tip is at (0.12, 0.15, 0.33). Role labels per phase (left, right): moving_fixture_presentation: fixture_support, tracking_pin; relative_pin_insertion: moving_fixture_support, pin_inserter; mechanical_latch_open: fixture_support, latch_operator; follow_and_withdraw: outlet_operator, withdrawing_pin; gravity_delivery: outlet_support, cleared_pin.

The fixture is a free rigid body, not attached to anything. At the start it rests level on a small orange stand plate carried by two thin grey posts. It is a blue channel running along x: a flat floor between two side walls 56 mm apart and 45 mm high. At its back (-x) end is a small handle block (16 mm along x, 34 mm wide, 28 mm tall). At its front (+x) end the floor stops short of the walls' ends, leaving an exit opening. An orange spring-loaded latch closes this exit with a 20 mm high gate standing just beyond the floor's end. The latch slides along the fixture's own vertical axis by up to 26 mm. Its push button sits right under a square socket (28 mm opening, 30 mm tall, 16 mm walls) that is fixed to the fixture beside the channel's front end on its +y side, above the wall. Pushing the button down lowers the gate below the floor and opens the exit, and a spring pushes the latch back up when released. An orange ball (radius 16 mm) lies loose on the channel floor behind the gate. Fixed in the scene are a grey inclined chute (an open channel, 66 mm wide inside, 22 mm walls) running downhill toward +x, and at its lower end a blue open basin (0.13 m along x by 0.12 m inside, 40 mm deep). Nothing moves by itself. The table top is the world's z = 0 plane.

**Goal geometry.** Drop limit: the fixture's frame origin must stay at or above z = 0.18 m.

## Time in this scene
The simulated clock advances **only through your calls**: every row of a `submit` and
every second of an `observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you
think. A call that runs control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and
returns what the cameras saw. The episode lasts at most **25 s of robot time** (the task's horizon,
2500 control steps): when it is reached before the task is complete, the task has failed. Nothing moves at t = 0: the fixture rests on its stand with the ball inside and the left fingers open around its handle. The latch springs back up toward closed whenever the peg stops pressing it.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_fixture_presentation**: the left gripper grips the fixture body (both left-arm fingers in contact with it; contact with the latch does not count), while the fixture's frame origin is more than 0.018 m away from where it started and the fixture's centre of mass moves faster than 0.005 m/s.
2. **relative_pin_insertion**: the peg is inserted into the socket while the fixture keeps moving, for 0.06 s without interruption. Measured in the fixture frame, the peg tip (tool-frame point (0, 0, -0.07)) is within 5 mm horizontally of the socket's axis and 10-35 mm below the socket's top face (insertion depth 0.01 m < depth < 0.035 m; the socket itself is 30 mm deep). Meanwhile the left gripper still grips the fixture body and the fixture's centre of mass moves faster than 0.003 m/s.
3. **mechanical_latch_open**: the latch is pressed down by more than 17 mm (latch joint q < -0.017 m) at a moment when the peg tool touches the latch.
4. **follow_and_withdraw**: the peg tip is more than 15 mm above the socket's top face, measured along the fixture's z axis only (depth < -0.015 m, any lateral position). At the same moment the peg tool does not touch the latch and the left gripper still grips the fixture body.
5. **gravity_delivery**: after this phase has begun, the ball touches the chute; a chute contact before this phase does not count. After that, the ball rests in the basin for 0.7 s without interruption. Rests means: in the basin's frame (origin at the inner floor centre) its centre is within 0.0528 m of the centre along both x and y (0.45 x radius inside a 0.06 m half-width square) and between 0.012 m and 0.0381 m above the floor; it has touched the basin within the last 25 ms; and its speed is below 0.09 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`; `meta["reason"]`: `success`, `failed`, or `error` after a simulator error; the `submit` that
ended it also names the failure in `meta["why"]`).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the fixture's frame origin (a point on the channel floor's top surface, 20 mm behind the floor's front edge) is below z = 0.18 m (`fixture_grasp_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The fingers of either arm may touch the fixture body (channel, handle, socket) and the ball, but not the latch (gate, bar, button). The right peg tool (whole tool link, adapter included) may touch the fixture body, the latch and the ball. Nothing on either robot may touch the stand, the chute, the basin or the table. No other robot part (hand or arm links) may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
