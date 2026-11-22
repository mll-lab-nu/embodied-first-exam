# Panda Dynamic Scenes · Clear the blocker, recover and bank into the goal (S03) (standard)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). A square puck slides toward the robot over an almost frictionless table at
the start. First touch it with the paddle; then strike it so that, sliding free of the paddle, it hits a sliding blocker
bar that obstructs the way to the goal fast enough to push it aside along its rail. Let the puck slide back across a
recovery line by itself, strike it a second time, and make it bank off the rail designated for this episode (one of two
rails, coloured green; the other is grey) without touching the other rail, and then cross the goal line while the
blocker is still pushed aside. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue upright paddle: a box 12 mm thick (tool x)
x 0.10 m wide (tool y) x 50 mm tall (tool z), centred at the tool frame origin; its striking faces are normal to the
tool x axis. A rigid dark-grey adapter behind the paddle (on its -x side) joins it to the hand: a horizontal bar 0.035 m
above the tool origin (tool-frame x from -0.132 to -0.038), a short vertical post at x = -0.05 reaching down to z =
-0.005, and a 12 mm square bridge from the post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to
0.021); all of it is part of the tool, and paddle and adapter form one rigid piece. The Panda TCP is at (-0.12, 0, 0.04)
in the tool frame, so with the paddle upright the gripper points straight down. At the start the paddle is upright with
tool axes aligned with the world axes (faces normal to world x), its centre at (0.03, -0.20, 0.045), so its lower edge
is 0.02 m above the table. The tool's adapter runs between the gripper's fingertips: closing the gripper to less than
about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision with its own tool
(the gripper starts fully open, at 0.08 m).

An orange square puck (44 mm x 44 mm, 24 mm tall) slides over the table toward the robot (-x) at t = 0. The table
surface and the puck are nearly frictionless and the puck is bouncy, so it keeps sliding and rebounds off walls. A blue
blocker bar (140 mm long, 30 mm thick, 64 mm tall), set at an angle to the axes, stands on the table on a passive,
unpowered sliding joint along the world y axis; it starts at one end of its travel, so it can only be pushed toward +y,
and it obstructs the route to the goal. Three fixed walls, 70 mm tall, stand on the table: a long side rail (0.34 m)
running along x on the robot's right (-y side) of the play area, a short end rail (0.20 m) running along y on the
robot's side of the play area, and an orange backstop (0.20 m) running along y behind the goal line. One of the two
rails is designated for this episode's final bank shot and is coloured green; the other is grey. The goal itself is not
a physical object but a line segment on the table (see world goals). Nothing else moves by itself. The table top is the
world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. The simulated clock advances only through your calls: every row you send and every second you
watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs
control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the
cameras saw. The episode lasts at most 35 s of robot time (the task's horizon, 3500 control steps): when it is reached
before the task is complete, the task has failed. The puck is already sliding toward the robot at t = 0 and reaches the
paddle's area within the first second. It does not stop by itself: after each contact it keeps sliding and bouncing
between the walls. The designated rail is the green one.

## Goal
Success: the paddle touches the puck; then it strikes it so that the puck, sliding free of the paddle for a moment, hits
the blocker bar fast enough to push it well aside along its rail; the puck slides back across the recovery line (x =
0.16) by itself; the paddle strikes it a second time, and after that last touch it banks off the designated rail, at
this instance the short end rail on the robot's side of the play area (coloured green), touches no other rail, and
crosses the goal line (x = 0.46, around y = 0.06) moving away from the robot, not touching the paddle, with the blocker
still pushed aside. The task fails at once if the paddle touches the blocker, if the puck meets the blocker too soon
after leaving the paddle (pushed rather than struck), or if it crosses the goal line after touching the other rail,
without the bank, touching the paddle or with the blocker back in the way.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 35 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the paddle (including its adapter) may touch anything, and it may touch
  only the puck: touching the blocker, either rail, the backstop or the table is forbidden. No other part of the robot,
  the fingers included, may touch anything, the puck included. In every task the arm never touches itself, no robot part
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
  scene back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a
  new episode, abandoning the running one or after one has ended. Only the last episode is graded: an episode you reset
  away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode then
  running is the one graded. Do not stop early: while the episode runs, or a reset is left, the run can still pass.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the service tells you only that an episode has ended and why (a success, a failure or a
  simulator error).
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`). Its docstring (`help(rcb_client)`) lists the calls and their
arguments; the robot facts it names as examples are another robot's: this robot's are in `r.spec()` and below.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, `max_watch_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | runs `A`, rows of 8 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | the current frames (free, no time passes), or hold the last targets and watch for `seconds` (at most 30) |
| `r.reset(cameras=None, include_depth=False)` | a new episode from the frozen starting state (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows: one at the call's start,
one every 1/`video_fps` s of robot time, one at its end). `video_fps` (1..30, default 10) sets how many frames a call
returns. One call returns at most 3000 images. A malformed request raises `ValueError` and runs nothing; once an episode
has ended, `submit` raises `EpisodeOver` (409) and `get_obs` still answers (no time passes). `cameras=None` (or `[]`)
means both: name the one you need. `video="none"` returns only the last frame (the fastest call).

How an episode ended: `meta["done"]`, `meta["reason"]` (`success`, `failed`, or `error` after a simulator error); the
`submit` that ended it names the failure in `meta["why"]`. `r.reset()` returns the new start's frames and
proprioception; `meta["episode"]` and `meta["resets_left"]` count the episodes. If the service crashes, a call fails
with a connection error (or a 5xx): it restarts and resumes the same episode (never a reset) in the state after the last
call it completed, which you may not have received. `r.status()` answers again once it is back; check `control_steps`
before you continue (`spec()["on_service_error"]`).

```python
from rcb_client import Robot
import numpy as np
r = Robot()
obs = r.get_obs(cameras="overview")                                    # the robot at the frozen start (no time passes)
q0 = np.asarray(obs.meta["proprio"]["now"])
rows = ...                                                             # (T, 8) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", cameras="closeup", video="frames", video_fps=25)
res.frames["closeup"], res.proprio, res.meta["done"], res.meta["reason"]
if res.meta["done"] and not res.meta["reason"] == "success":
    r.reset()                                                          # a new episode (while resets are left)
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
