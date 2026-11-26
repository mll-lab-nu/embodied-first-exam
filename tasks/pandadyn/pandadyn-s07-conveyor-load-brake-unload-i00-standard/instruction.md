# Panda Dynamic Scenes · Conveyor pick, carriage load, braking and dock unload (S07) (standard)

## Task
Grasp the part from the moving conveyor, lift it about a hand's length and set it on the coasting carriage, letting go
while the carriage is moving. Then grip the carriage's handle and stop it, with the part still on it, before it reaches
the end of its rail; finally lift the part off and set it down in the dock.

## Goal
Success: both fingers grasp the part while it still rides the conveyor and lift it about a hand's length; the part is
set on the moving carriage and let go while the carriage still moves; then both fingers grip the carriage's handle (the
handle only) and bring the carriage to a stop, the part still on it; the part is grasped again and lifted about a hand's
length off the carriage; finally it is set down in the dock and left there at rest.

The steps count only in this order, and a step once done stays done: the task is done once its last step is, and it
stays done even when a failure ends the episode afterwards. The task fails, and the episode ends at once, when:
- the carriage reaches an end of its rail before it is stopped;
- the part falls off during the braking or the regrasp;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: only the fingers may touch anything, and only the part and the carriage's tray
  and handle;
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
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). The robot runs as a service you reach through its client or its MCP tools,
as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`). Its docstring (`help(rcb_client)`) lists the calls and their
arguments; the robot facts it names as examples are another robot's: this robot's are in `r.spec()` and below.

| call | what it does |
|---|---|
| `r = Robot()` | connects and waits until the scene is ready |
| `r.spec()` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | runs `A`, rows of 8 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
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
rows = ...                                                             # (T, 8) targets, one per control step
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

### Arms and tools
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x), with no tool: the bare Panda hand and its two parallel fingers. The
task's tool frame is the Panda TCP (between the fingertips). At the start the TCP is at (-0.13, -0.11, 0.21) with
orientation wxyz (0, 1, 0, 0): the gripper points straight down, the hand's x axis along world x, the fingers closing
along world y; the fingers start 0.048 m apart (each at 0.024 m). The action's last element is the total finger opening
(0 to 0.08 m); in this task the gripper's motion is not time-synchronised with the arm joints' trajectory.

### Episode clock
The scene is dynamic: from the episode's first control step on, things move by themselves, and they do not wait for the
robot. The simulated clock advances only through your calls: every row you send and every second you hold (`hold(s)`)
runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs control
steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the cameras saw.
The episode lasts at most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached before the
task is complete, the task has failed.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds,
the hand's speed and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the
numbers: the robot spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a
strike moves the arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

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
- Steps: the episode ends by itself after 25 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
