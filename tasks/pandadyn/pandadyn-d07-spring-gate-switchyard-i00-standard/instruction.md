# Panda Dynamic Scenes · Spring gate switchyard (D07) (standard)

## Task
Hold the gate by its handle with the left gripper, swing it open toward the right arm and keep holding it open. Hit the
puck deep into the pen with the right paddle; while it runs round, swing the gate over the other way, toward the left
arm, so that it stands open that way when the puck hits the side rail on the left arm's left. Then intercept the puck
with the right paddle and send it across the goal line in front of the middle of the backstop.

## Goal
Success: the left gripper holds the gate's handle with both fingers and swings the gate well open toward the right arm,
and from then on keeps holding the handle with the gate well away from its rest position (either way); the right paddle
hits the puck so that it runs deep into the pen; the gate stands open the other way, toward the left arm, at the moment
the puck hits the side rail on the left arm's left; the right paddle intercepts the returning puck; finally the puck
crosses the goal line in front of the middle of the backstop, not touching the paddle, with the gate still held well
open.

The steps count only in this order, and a step once done stays done: the task is done once its last step is, and it
stays done even when a failure ends the episode afterwards. The task fails, and the episode ends at once, when:
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: the fingers may touch only the puck and the gate's leaf and handle, the paddle
  may touch only the puck and must not touch its own arm, no other robot part may touch anything, and the two arms must
  never touch each other;
- an arm touches itself, a robot part touches the table or the floor, or a contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits (Robot Interface, Safety).

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a
  new episode, abandoning the running one or after one has ended. Only the last episode is graded: an episode you reset
  away is never graded. Do not stop early: while the episode runs, or a reset is left, the run can still pass.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). The robot runs as a
service you reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`). Its docstring (`help(rcb_client)`) lists the calls and their
arguments; the robot facts it names as examples are another robot's: this robot's are in `r.spec()` and below.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | runs `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | the current frames (free, no time passes), or with `last_s=n` the frames recorded over the last n seconds |
| `r.hold(seconds, cameras=None, video="mp4")` | hold the last targets for `seconds` of robot time and return the video, like a submit |
| `r.reset(cameras=None, include_depth=False)` | a new episode from the frozen starting state (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows: one at the call's start,
one every 1/`video_fps` s of robot time, one at its end). `video_fps` (1..30, default 10) sets how many frames a call
returns. One call returns at most 3000 images. A malformed request raises `ValueError` and runs nothing; once an episode
has ended, `submit` raises `EpisodeOver` (409) and `get_obs` still answers (no time passes). `cameras=None` (or `[]`)
means both: name the one you need. `video="none"` returns only the last frame (the fastest call).

How an episode ended: `meta["done"]`, `meta["reason"]` (`finished` after your finish, `failed`, `step_limit` at the step
cap, or `error` after a simulator error); the `submit` that ended it names the failure in `meta["why"]`. `r.reset()`
returns the new start's frames and proprioception; `meta["episode"]` and `meta["resets_left"]` count the episodes. If
the service crashes, a call fails with a connection error (or a 5xx): it restarts and resumes the same episode (never a
reset) in the state after the last call it completed, which you may not have received. `r.status()` answers again once
it is back; check `control_steps` before you continue (`spec()["on_service_error"]`).

```python
from rcb_client import Robot
import numpy as np
r = Robot()
obs = r.get_obs(cameras="overview")                                    # the robot at the frozen start (no time passes)
q0 = np.asarray(obs.meta["proprio"]["now"])
rows = ...                                                             # (T, 16) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", cameras="closeup", video="frames", video_fps=25)
res.frames["closeup"], res.proprio, res.meta["done"], res.meta["reason"]
if res.meta["done"]:
    r.reset()                                                          # a new episode (while resets are left)
```

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`,
  `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

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

### Arms and tools
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It has no tool and uses the stock Panda parallel gripper:
two fingers with a total opening of up to 0.08 m, fully open (0.04 m per finger) at reset. Its tool frame, reported as
`panda-0_tool_pose`, is the gripper TCP between the fingertips. At the start the TCP is at (0.04, -0.10, 0.16), pointing
straight down (quaternion (0, 1, 0, 0)), with the fingers closing along world y. panda-1 (right): base at (0.74, 0.22,
0), yaw pi (facing -x). It carries a flat rigid paddle, 0.10 m long, 0.05 m tall and 12 mm thick, on a rigid adapter on
its back (tool -x) side: a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post
at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from
-0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool link. The tool frame is the paddle
centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre and 0.04 m
above it. Paddle start: centre (0.30, -0.08, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg, faces normal to world x);
its lower edge is then 0.020 m above the table. On panda-1 the paddle's adapter runs between the fingertips: closing
that gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a
collision with its own tool (it starts fully open, at 0.08 m).

### Episode clock
The scene is dynamic: from the episode's first control step on, things move by themselves, and they do not wait for the
robot. The simulated clock advances only through your calls: every row you send and every second you hold (`hold(s)`)
runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs control
steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the cameras saw.
The episode lasts at most 35 s of robot time (the task's horizon, 3500 control steps): when it is reached before the
task is complete, the task has failed.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds,
the hand's speed and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the
numbers: the robot spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a
strike moves the arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

## Others
- The gate springs back toward its rest position whenever it is let go.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 3 resets, each a new episode from the same frozen starting state; only the last episode is graded.
- Steps: the episode ends by itself after 35 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
