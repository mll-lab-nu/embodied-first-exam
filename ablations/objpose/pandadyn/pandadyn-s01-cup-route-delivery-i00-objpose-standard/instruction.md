# Panda Dynamic Scenes · Cup catch, route pour, rebound recatch and cart delivery (S01) (standard)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). An orange ball is thrown upward at the start and comes back down near the
robot. Catch it in the open cup the Panda holds, pour it into the designated one of two raised gravity channels, let it
roll down that channel by itself, drop off its end and bounce off the tilted rebound plate below it, catch it in the cup
again while it flies, and finally put it into a cart that slides back and forth on a rail, where it must rest while the
cart is still moving. The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue square cup closed on all four sides: inner
0.14 m x 0.14 m, walls 0.028 m high and 5 mm thick, floor 5 mm thick. The tool frame is the centre of the cup's inner
floor (top surface of the bottom plate), z up out of the opening, x and y along the walls. A rigid dark-grey adapter on
the cup's -x side joins it to the hand: a horizontal bar 0.035 m above the floor (tool-frame x from -0.152 to -0.058)
and a short vertical post at the middle of the -x wall (rising 7 mm above the rim and protruding 6 mm into the cup);
both are part of the tool. The Panda TCP is at (-0.12, 0, 0.04) in the tool frame, so with the cup level the gripper
points straight down just behind the cup's -x wall. At the start the cup is level (tool axes aligned with the world
axes), its frame origin at (-0.16, -0.32, 0.23). The tool's adapter runs between the gripper's fingertips: closing the
gripper to less than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision
with its own tool (the gripper starts fully open, at 0.08 m).

A small orange ball (radius 18 mm) is thrown upward at t = 0 and falls back down within the first second. Two identical,
parallel gravity channels are raised on posts above the table: open-topped grey troughs 0.35 m long with a 0.12 m wide
floor between 55 mm high side walls, both running in the -y direction and very nearly level. Route 0 is the channel
nearer the robot base, route 1 the farther one. Each channel's upstream (+y) end is closed by an orange end stop; beyond
its downstream (-y) end, a little lower, sits an orange rebound plate (0.11 m x 0.13 m, 16 mm thick), tilted so that a
ball dropping onto it bounces onward in -y into open space; the plates are very bouncy. A blue open box (the cart, 0.15
m x 0.15 m inside, 0.06 m deep) rides on a straight rail along the world x axis and moves slowly back and forth along it
for the whole episode, slowing to a stop at each end of its stroke. The table top is the world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. The simulated clock advances only through your calls: every row you send and every second you
watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs
control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the
cameras saw. The episode lasts at most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached
before the task is complete, the task has failed. The ball is already flying upward at t = 0 and lands in under a
second, so watch the first frames in short steps. The cart keeps moving back and forth for the whole episode and slows
to a stop at the ends of its stroke. The two channels look the same and nothing marks the designated one: Goal says
which.

## Goal
Success: the cup catches the falling ball; it pours the ball into the designated channel, at this instance route 1, the
channel farther from the robot's base (+x side), which nothing in the images marks; the ball rolls down by itself, drops
off the end and bounces off that channel's rebound plate; the cup catches it again in flight; finally the ball rests in
the cart, out of the cup, for about 0.7 s while the cart moves. A catch means the ball drops into the cup from above
after flying free and stays there, not a bounce. The task fails at once if the ball touches the other channel, or if
between the pour and the rebound it touches the table or the cup.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the cup (including its adapter) may touch anything, and it may touch only
  the ball: touching the channels, end stops, rebound plates, the cart or its rail, or the table is forbidden. No other
  part of the robot, the fingers included, may touch anything, the ball included. In every task the arm never touches
  itself, no robot part touches the table or the floor, a robot part other than an allowed one touches nothing, a tool
  touches only what the task allows, and no contact presses deep into anything;
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
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
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
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 30 % (acceleration) and
  2 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
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

### This run: privileged state queries
This run lets you query the simulator's state.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The kinds are
  `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`, `articulation` (a door,
  a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas region). The list is fixed for
  the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the current
  values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox` [[min x,
    y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the task
  is done.

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
