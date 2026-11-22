# Panda Dynamic Scenes · Swinging load transit and dock (S10) (standard)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). A carrier rests on two small ledges between the gripper's open fingers. It
is a short bar with a pendulum (a rod ending in a ball) hanging from a hinge under it, and the pendulum is already
swinging. Grip the bar with both fingers and damp the swing. Carry the carrier, still gripped, through two waypoints
without letting the carrier or its pendulum touch a block obstacle, brake to rest at the second waypoint, and damp the
residual swing again. Finally lower it slowly until the pendulum's ball rests centred in a dock, with the swing settled
and the bar still gripped. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame
(the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand
along the fingers. At the start the TCP is at (-0.03, -0.14, 0.36), exactly at the carrier bar's centre, with the
gripper pointing straight down (orientation wxyz (0, 1, 0, 0)). The fingers close along world y and start partly open,
at 0.016 m each (aperture 0.032 m), straddling the 30 mm wide bar. The action's last component is the total aperture, 0
to 0.08 m. In this task the finger servo is stiffer (kp 800, kd 8), and finger motion is not time-synchronised with the
arm joints.

The carrier is a free rigid assembly, not attached to the robot or the scene. Its bar is blue-grey, 0.12 m long (along
world x at the start), 0.03 m wide and 18 mm thick. A pendulum hangs from a hinge just under the bar's middle: a grey 12
mm square rod, 0.15 m long, ending in an orange ball (the bob) of radius 22 mm. The hinge lets the pendulum swing only
in the vertical plane along the bar's length, with almost no friction. At t = 0 the bar rests on two thin static ledges
(on posts), and the pendulum is let go from an angle, so it is already swinging. A static orange block obstacle (0.08 m
x 0.12 m x 0.11 m tall) stands on the table. A static blue open box (the dock: 0.104 m x 0.10 m inside, walls 55 mm
high) is placed low over the table. The table top is the world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. The simulated clock advances only through your calls: every row you send and every second you
watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs
control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the
cameras saw. The episode lasts at most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached
before the task is complete, the task has failed. The pendulum is already swinging at t = 0 and keeps swinging until the
gripper's motion damps it. The carrier is free: it only rests on the two ledges, so if the fingers let go it falls.

## Goal
Success: both fingers grip the bar and damp the swing until the pendulum hangs nearly still for a moment; still gripped,
the bar's centre is carried past waypoint A (-0.05, 0.04, 0.38) and to waypoint B (0.0, 0.15, 0.37), where it brakes to
rest; the leftover swing is damped again; finally the carrier is lowered slowly until the pendulum's ball rests centred
in the dock, the swing settled and the bar still gripped, for about half a second. The task fails at once if the carrier
or its pendulum touches the obstacle block, if the carrier drops out of the grip, or if the ball comes into the dock too
fast.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. No tool is mounted. Only the finger links (fingers and finger pads) may touch
  anything, and only the carrier bar. Touching the pendulum (rod or bob) with a finger is forbidden. So is touching the
  ledges, the obstacle, the dock or the table. No other part of the robot (hand, links, base) may touch anything. The
  pendulum is expected to touch the dock; neither the bar nor the pendulum may touch the obstacle. In every task the arm
  never touches itself, no robot part touches the table or the floor, a robot part other than an allowed one touches
  nothing, a tool touches only what the task allows, and no contact presses deep into anything;
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
