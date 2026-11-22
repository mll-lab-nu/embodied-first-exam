# Panda Dynamic Scenes · Inertial cube flip, chute run and pocket recovery (S06) (standard)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). A cube rests on a raised launch surface. With a short push from the pusher
blade, tip it over so that the face that initially faces the robot (-x) ends up on top, the cube completing the tip by
its own momentum after the blade has let go, and let it settle. Then push the flipped cube onto an inclined chute, let
it slide down by itself, meet it with the blade on its downhill side near the chute's lower end, and bring it to rest in
the pocket at the bottom of the chute with the same face still on top. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
One Panda, base at (-0.40, 0, 0), yaw 0 (facing +x). Its hand carries a small blue pusher blade: a box 8 mm thick (tool
x) x 50 mm wide (tool y) x 12 mm tall (tool z), centred at the tool frame origin; its pushing faces are normal to the
tool x axis. The blade hangs from a rigid side adapter (part of the tool): from the hand a horizontal bar at tool z =
0.035 runs from tool x = -0.12 to 0 at tool y = +0.13, then along y to y = 0.019, ending in a short 12 mm x 12 mm post
at (0, 0.019) reaching down from z = 0.036 to z = 0 (the blade's mid-height); the post's foot meets the blade's +y end
(it spans y 0.013 to 0.025 and tool x -0.006 to 0.006, 2 mm proud of each pushing face), so blade, bars and post are one
rigid tool. The Panda TCP is at (-0.12, 0.13, 0.04) in the tool frame, so with the blade level the gripper points
straight down. At the start the blade is level (tool axes aligned with the world axes, pushing faces normal to world x),
its centre at (-0.05, -0.08, 0.179). The tool's adapter runs between the gripper's fingertips: closing the gripper to
less than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision with its
own tool (the gripper starts fully open, at 0.08 m).

An orange cube (44 mm edge) rests at t = 0 on a raised, flat orange launch surface (a slab 0.28 m along x by 0.18 m, on
posts), one face toward the robot. The launch surface's far (+x) edge meets the top of a straight inclined grey chute (a
trough with a 0.10 m wide floor and 22 mm side walls) that runs downhill in +x; the chute's top edge lies slightly below
the launch surface. At the chute's low end sits a blue shallow pocket (an open box 0.12 m x 0.12 m inside with 12 mm
walls), open on the side facing the chute, its floor flush with the chute's end. Friction is high enough that a cube at
rest on the chute stays put, but a cube already sliding on it keeps sliding and speeds up by itself. Nothing moves at t
= 0. The table top is the world's z = 0 plane.

### Time in this scene
The simulated clock advances only through your calls: every row you send and every second you watch runs control steps
(10 ms each); between calls the world is frozen, however long you think. A call that runs control steps runs them all
(unless the episode ends during it), whatever happens meanwhile, and returns what the cameras saw. The episode lasts at
most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached before the task is complete, the
task has failed. Nothing moves at t = 0: the cube rests on the launch surface with one face toward the robot. Once on
the chute the cube slides and speeds up by itself, and a cube entering the pocket fast can tumble onto another face.

## Goal
Success: the blade tips the cube over with a short push that ends before the cube is half-way over, the cube completing
the tip on its own and settling with its original -x face (the one that faced the robot) on top; it is pushed onto the
chute with that face still up and slides down by itself; the blade meets it on its downhill side near the chute's lower
end (past x = 0.32) while it still slides fast, after a long free slide; finally it rests in the pocket with the same
face on top for about half a second. The task fails at once if the blade touches the cube again after letting go and
before it has tipped past half-way.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the pusher (blade, adapter bars and post) may touch anything, and it may
  touch only the cube: touching the launch surface, the chute, the pocket or the table is forbidden. No other part of
  the robot, the fingers included, may touch anything, the cube included. In every task the arm never touches itself, no
  robot part touches the table or the floor, a robot part other than an allowed one touches nothing, a tool touches only
  what the task allows, and no contact presses deep into anything;
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
