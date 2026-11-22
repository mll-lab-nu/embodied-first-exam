# Panda Dynamic Scenes · Moving ramp relay (D05) (standard)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). An orange ball rests in
the left Panda's cup, and the right Panda holds a straight channel that is open at both ends. The left arm must pass the
ball into the inlet part of the channel. The ball must then leave the channel by its outlet end while the outlet is
moving (at least 0.10 m/s) and be caught again in free flight by the left cup. The relay is then repeated with the
channel held at a clearly different orientation from the first time. After the second catch, the left cup must deliver
the ball into a fixed basin, where it must come to rest. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It carries an open-top square cup, 0.14 m x 0.14 m inside,
with four 0.055 m high, 5 mm thick walls and a 5 mm floor, held by an adapter on its tool -x wall. The tool frame is the
centre of the cup floor's inner surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Start:
(-0.04, -0.14, 0.23), orientation identity (upright). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It
carries a straight channel, open at both ends and 0.28 m long. It has a flat floor 72 mm wide and 8 mm thick and two
side walls 40 mm high and 8 mm thick. A side adapter holds it at the middle of its tool +y wall. The tool frame is the
centre of the floor's top surface: x runs along the channel (the +x end is the outlet, the -x half the inlet side), y
across it, z up. The TCP sits 0.12 m along tool -x, 0.12 m along tool +y and 0.04 m above the tool frame. Start: (0.18,
0.10, 0.24), quaternion (0, 0, 0, 1) (yawed 180 deg: level, outlet end toward world -x). On both arms the tool's adapter
runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers touch the adapter,
which ends the episode as a collision with its own tool (both grippers start fully open, at 0.08 m).

An orange ball (radius 18 mm) rests at a slightly random spot on the floor of the left arm's cup. A fixed blue open-top
basin, 0.15 m x 0.15 m inside and 0.06 m deep, stands on posts above the table. Nothing moves by itself; once the ball
is in the channel, it rolls under gravity. The table top is the world's z = 0 plane.

### Time in this scene
The simulated clock advances only through your calls: every row you send and every second you watch runs control steps
(10 ms each); between calls the world is frozen, however long you think. A call that runs control steps runs them all
(unless the episode ends during it), whatever happens meanwhile, and returns what the cameras saw. The episode lasts at
most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached before the task is complete, the
task has failed. Nothing moves at t = 0: the ball rests in the left cup. Once the ball is in the channel it rolls on its
own toward whichever end is lower, and it leaves the outlet within moments.

## Goal
Success: the left cup passes the ball into the inlet half of the channel; the ball leaves the channel by its outlet end
while the outlet is moving and is caught again in free flight by the left cup; the relay is repeated with the channel
held at a clearly different orientation from the first time; after the second catch the left cup delivers the ball into
the basin, where it rests out of the cup for about 0.7 s. A catch means the ball drops into the cup from above after
flying free and stays there, not a bounce. The task fails at once if the ball leaves the outlet while the outlet moves
too slowly.

The steps count only in this order, and a step once done stays done. The episode ends by itself when the task has failed
(a success does not end it: `### This run: no success signal`); the task fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The cup and the channel may touch only the ball. They must not touch each other,
  the basin or its posts, the table or the robot pedestals. No other robot part, the fingers included, may touch
  anything. The two arms and their tools must never touch each other, so the ball has to pass between cup and channel
  without the two tools touching. A tool must not touch its own arm. In every task an arm never touches itself, no robot
  part touches the table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what
  the task allows, and no contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a
  new episode, abandoning the running one or after one has ended. Only the last episode is graded: an episode you reset
  away is never graded, and when your time is up the episode then running is the one graded. Do not stop early: while
  the episode runs, or a reset is left, the run can still pass.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`). Its docstring (`help(rcb_client)`) lists the calls and their
arguments; the robot facts it names as examples are another robot's: this robot's are in `r.spec()` and below.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, `max_watch_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | runs `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | the current frames (free, no time passes), or hold the last targets and watch for `seconds` (at most 30) |
| `r.reset(cameras=None, include_depth=False)` | a new episode from the frozen starting state (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows: one at the call's start,
one every 1/`video_fps` s of robot time, one at its end). `video_fps` (1..30, default 10) sets how many frames a call
returns. One call returns at most 3000 images. A malformed request raises `ValueError` and runs nothing; once an episode
has ended, `submit` raises `EpisodeOver` (409) and `get_obs` still answers (no time passes). `cameras=None` (or `[]`)
means both: name the one you need. `video="none"` returns only the last frame (the fastest call).

How an episode ended: `meta["done"]`, `meta["reason"]` (`failed`, or `error` after a simulator error); the `submit` that
ended it names the failure in `meta["why"]`. `r.reset()` returns the new start's frames and proprioception;
`meta["episode"]` and `meta["resets_left"]` count the episodes. If the service crashes, a call fails with a connection
error (or a 5xx): it restarts and resumes the same episode (never a reset) in the state after the last call it
completed, which you may not have received. `r.status()` answers again once it is back; check `control_steps` before you
continue (`spec()["on_service_error"]`).

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
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 3 resets, each a new episode from the same frozen starting state; only the last episode is graded.
