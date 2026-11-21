# KinDER task, instance i01 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a Kinova Gen3 7-DoF
arm and a Robotiq 2F-85 gripper -- **as if it were real hardware**: the simulator runs in a service you cannot open,
and you reach it only through a client. **Task:** get the fifty small dark-red cubes scattered on the floor into the translucent grey box marked on the floor at the end of the kitchen island (the free-standing white-topped counter) nearest the robot; a wiper stands on the floor near the cubes. The task succeeds the moment all fifty cubes' centres are inside that box. Measured at the start, in the odometry frame (below): the grey box's centre is at x = 0.51 m, y = 0.06 m, 0.5 m from the centre of the base and 7° to the left of the way it faces; it is 0.475 m along x by 0.85 m along y, from the floor to 0.1 m up, its sides turned about 3° clockwise (seen from above) from the frame's axes.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: on the floor under the middle of the base as it stands at the start of the call: +X
the way the base faces, +Y to its left, +Z up. Space `native` sends rows in the robot's own action types exactly as the
sections below describe them (their frame, units and gripper values).

**This robot** (TidyBot++ mobile manipulator (KinDER, MuJoCo): a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq
2F-85 gripper, driven by per-step changes): arm (arm: gripper). Cameras: `robot_base`, `robot_wrist`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The base and the arm take one action type, delta (11 numbers, one row per 0.1 s control step),
sent with execute_trajectory space native, action_type delta: base_x, base_y = metres to move the base in the odometry
frame (where the base stood when the episode began: +x the way it faced then, +y to its left), together at most 0.1 a
step; base_yaw = radians to turn it (+ = counter-clockwise), at most 0.1 a step; arm_1 .. arm_7 = radians added to each
arm joint's measured angle, at most 0.1 a step; gripper = 0 open .. 1 closed (a command, not a change). Each step's
targets are the measured pose plus the row; a row of zeros with the gripper as it is holds the robot. To go forward
along the current heading yaw (base_yaw in proprio_now), each row has base_x = s cos(yaw), base_y = s sin(yaw) for a
step length s. At most 100 rows (10 s) a call; the episode has 1000 control steps (100 s of robot time) in all, and
watching for some seconds uses them too. The state has no hand pose: describe_robot's spec_file gives each arm joint's
axis and a point on it (the base frame, every joint at 0), the gripper's grasp point and the robot cameras' poses.
Nothing plans a way or avoids anything.

## Rules (real-robot rules)
- **No reset: one episode.** The episode starts when the service comes up. It ends when the task succeeds, after
  1000 control steps (100 s of robot time), when your time is up, or on a simulator error; nothing else ends it.
  No other episode follows (`spec()["budget"]["reset"]` is 0, and it is authoritative), and **this episode is graded**: a success ends the run at once, and when your time is up it is graded as it stands. Once it has ended, `submit` raises `EpisodeOver`.
- **Time moves only inside calls.** `submit` runs your actions, and `get_obs(seconds=s)` holds the last command for
  s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think;
  `get_obs()` with no seconds is free.
- **No privileged state, no score.** You get the robot's own sensors: its two cameras (RGB, 480×640: `robot_base` on the base, `robot_wrist` on the arm's last link, which also gives depth), its joint encoders (the arm's angles and velocities, the gripper) and the base's odometry (where it is relative to where it started). Not where anything else is, not
  the goal check: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"` when its control steps ran out, or `"error"` after a simulator error).
  `spec()` gives the robot's own facts, as its documentation would: each arm joint's axis, position and limits, the
  gripper's grasp point, each camera's field of view and pose.
- There is nothing to hand in: the service records the episode and grades it as it ran. Keep the script
  that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run
  the same way, so do not stop early: while the episode runs, the run can still pass.

## Scoring
The run passes iff the episode reaches the goal above, as KinDER's own goal check judges it, within 1000
control steps (`reason = "success"`); that live episode is the verdict. There is no partial credit.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth` (metres), `res.proprio` (one row per frame). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
Measured cost here, on a lightly loaded host (slower when the host is busy): about 49.9 ms per control step in
one-row calls asking for one camera, 53.4 ms with both robot cameras' images (and the wrist's depth), 45.9 ms per step in chunks of 10 rows
asking for one camera (video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw` (the odometry frame: where the base started, x the way it faced, y left), `base_vx`, `base_vy`, `base_yaw_rate`, `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.

Each row of a `delta` chunk is 11 numbers, one 10 Hz control step, in the order of `spec()["action_types"]["delta"]["layout"]`:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
