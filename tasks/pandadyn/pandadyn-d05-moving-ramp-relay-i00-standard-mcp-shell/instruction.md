# Panda Dynamic Scenes · Moving ramp relay (D05) (standard-mcp-shell)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). An orange ball rests in
the left Panda's cup, and the right Panda holds a straight channel that is open at both ends. The left arm must pass the
ball into the inlet part of the channel. The ball must then leave the channel by its outlet end while the outlet is
moving (at least 0.10 m/s) and be caught again in free flight by the left cup. The relay is then repeated with the
channel held at a clearly different orientation from the first time. After the second catch, the left cup must deliver
the ball into a fixed basin, where it must come to rest. The robot runs as a service you reach through the `efe-robot`
MCP tools, their Python client `efe_robot` or the service's own client, as if it were real hardware.

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

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
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
  away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode then
  running is the one graded. Do not stop early: while the episode runs, or a reset is left, the run can still pass.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the service tells you only that an episode has ended and why (a success, a failure or a
  simulator error).
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the scene's world frame, shared by both arms: origin on the table top (z = 0), +X from the left arm
(panda-0, at the -X end, facing +X) towards the right arm (panda-1, at the +X end, facing -X), +Y left as seen from the
left arm, +Z up; positions in the task text are already in this frame, and each arm's base pose is in describe_robot's
spec_file (robot_spec.arms); metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 7
joints, no end-effector pose); right (arm: 7 joints, no end-effector pose). Cameras: `overview`, `closeup`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: Each arm takes absolute joint-position targets (rad). Its servo turns every new target into a smooth,
jerk-limited motion (the joints arriving together, at most about 1.4 rad/s on joints 1-4 and 1.7 rad/s on joints 5-7)
and tracks it with torque control, so a far target is reached smoothly: move_robot with a short duration_s (e.g. 0.01)
sends the goal as one target and lets the servo set the pace, a longer duration_s ramps the target. There is no
end-effector pose command and no kinematics service: joints only. The scene moves by itself from the first control step,
and robot time passes only inside calls that move or wait (10 ms per control step; observe with seconds 0 is free), so
prepare a motion before sending it and use execute_trajectory (space joint, dt from 0.01 s) for timed sequences.
Positions in the task text are world coordinates (base_text says how they map to the base frame). describe_robot's
spec_file has robot_spec (base poses, joint, servo and safety limits) and proprio_groups for proprio_now (joint_pos,
tcp_pose, joint_vel, gripper_opening, joint_effort, tool_pose: world frame, quaternions wxyz; target: the targets in
force). Native rows (action type joint_position): per arm joint1..7 (rad) then the gripper aperture (m, 0 = closed ..
0.08 = open), panda-0 first.

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
