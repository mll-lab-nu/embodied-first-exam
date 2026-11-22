# Panda Dynamic Scenes · Moving fixture unlock (D11) (standard)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). The left gripper starts
around the handle of a free, hand-held fixture: a short channel with a ball inside, closed at its front by a
spring-loaded latch gate, with a square socket on its side above the latch's push button. The left arm must grip the
fixture and move it off its stand. While the fixture is still moving, the right arm must insert its peg into the socket,
press the latch button down with the peg until the gate opens, and then pull the peg back out while the left hand keeps
holding the fixture. The ball must then leave the fixture through its outlet while the outlet is lined up with the top
of a fixed inclined chute, run down the chute and come to rest in a basin at the chute's foot. The fixture must never be
dropped. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x), no tool: its tool
frame is the gripper TCP (the point between the fingertips). It starts with the TCP at (-0.063, 0, 0.285), pointing
straight down (TCP x = world +x, fingers closing along world y). Its fingers start open 0.0175 m each (0.035 m total
aperture), straddling the fixture's 34 mm wide handle without gripping it. For this arm the finger servo is stiffer than
the default (finger PD gains kp 1875 N/m and kd 8 instead of 300 and 12; the force is still capped at 15 N per finger).
Its fingers also follow their own trajectory, not synchronized with the arm joints. panda-1 (right): base at (0.74,
0.22, 0), yaw pi (facing -x). Its tool is a square peg, 16 x 16 mm in section and 70 mm long, hanging straight down from
the tool frame: the tool frame is at the peg's top end and the tip is at tool-frame (0, 0, -0.07). A grey adapter on the
hand side joins the peg: a horizontal bar from the hand (0.035 m above the tool frame, tool x from -0.152 to -0.058), a
short post at tool x = -0.07 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the peg's back face (x
from -0.064 to -0.008, z from -0.012 to 0, along the peg's top 12 mm); peg and adapter form one rigid tool link. With
the peg vertical the hand points straight down and the peg's top is 0.12 m ahead of the gripper TCP along tool x and
0.04 m below it. Start: tool frame at (0.12, 0.15, 0.40), peg vertical, rotated 180 deg about z (tool x = world -x), so
the tip is at (0.12, 0.15, 0.33). On panda-1 the peg's adapter runs between the fingertips: closing that gripper to less
than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a collision with its own
tool (it starts fully open, at 0.08 m).

The fixture is a free rigid body, not attached to anything. At the start it rests level on a small orange stand plate
carried by two thin grey posts. It is a blue channel running along x: a flat floor between two side walls 56 mm apart
and 45 mm high. At its back (-x) end is a small handle block (16 mm along x, 34 mm wide, 28 mm tall). At its front (+x)
end the floor stops short of the walls' ends, leaving an exit opening. An orange spring-loaded latch closes this exit
with a 20 mm high gate standing just beyond the floor's end. The latch slides along the fixture's own vertical axis by
up to 26 mm. Its push button sits right under a square socket (28 mm opening, 30 mm tall, 16 mm walls) that is fixed to
the fixture beside the channel's front end on its +y side, above the wall. Pushing the button down lowers the gate below
the floor and opens the exit, and a spring pushes the latch back up when released. An orange ball (radius 16 mm) lies
loose on the channel floor behind the gate. Fixed in the scene are a grey inclined chute (an open channel, 66 mm wide
inside, 22 mm walls) running downhill toward +x, and at its lower end a blue open basin (0.13 m along x by 0.12 m
inside, 40 mm deep). Nothing moves by itself. The table top is the world's z = 0 plane.

### Time in this scene
The simulated clock advances only through your calls: every row you send and every second you watch runs control steps
(10 ms each); between calls the world is frozen, however long you think. A call that runs control steps runs them all
(unless the episode ends during it), whatever happens meanwhile, and returns what the cameras saw. The episode lasts at
most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached before the task is complete, the
task has failed. Nothing moves at t = 0: the fixture rests on its stand with the ball inside and the left fingers open
around its handle. The latch springs back up toward closed whenever the peg stops pressing it.

## Goal
Success: the left gripper grips the fixture's body and moves it off its stand, keeping it moving; while it moves, the
right arm inserts its peg into the socket, presses the latch button down with the peg until the gate opens, and pulls
the peg back out, the left hand still holding the fixture; then the ball leaves through the outlet while the outlet is
lined up with the top of the chute (just above the chute's upper end, on its centre line, the fixture pointing down the
chute), runs down the chute and rests in the basin at its foot for about 0.7 s. The task fails at once if the fixture is
dropped, or if the ball leaves the fixture other than through the outlet lined up with the chute.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The fingers of either arm may touch the fixture body (channel, handle, socket)
  and the ball, but not the latch (gate, bar, button). The right peg tool (whole tool link, adapter included) may touch
  the fixture body, the latch and the ball. Nothing on either robot may touch the stand, the chute, the basin or the
  table. No other robot part (hand or arm links) may touch anything. The two arms and their tools may never touch each
  other, and no arm may touch itself. In every task an arm never touches itself, no robot part touches the table or the
  floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows, and no
  contact presses deep into anything;
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
