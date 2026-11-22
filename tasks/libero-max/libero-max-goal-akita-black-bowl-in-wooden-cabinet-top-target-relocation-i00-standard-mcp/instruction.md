# LIBERO-MAX · libero_goal — instance i00 — STANDARD MODE, MCP TOOLS ONLY (robot as a service)

You control a simulated **Franka Panda** arm (LIBERO on robosuite / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through the `efe-robot` tools. **Task: Open the top layer of the drawer and put the bowl inside.**

The scene can change while you work: once during the episode, when your gripper first gets close to one of the task's
objects, the scene changes (as in LIBERO-MAX): an object or a receptacle may be moved, an obstacle or a few other
objects may appear, a camera may shift, or the lighting, the colours or the image noise may change. Nothing tells you
when; the task and its success check stay the same, so keep checking what the cameras show. A moved object or
receptacle jumps there alone: what already rests in or on it stays where it was.

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You may write and run code to compute; every robot command and observation must
go through the efe-robot MCP tools; code must not contact the simulator. Each robot command or observation is a tool
call you make yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is
checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and pass its path
as `rows_file` to `execute_trajectory`. The robot service and its rules are as described in this text; where it names
calls of the Python client `rcb_client.py`, which is not installed for your code here, use the tool that does the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: at the arm's mount, +X forward across the table, +Y the robot's
left, +Z up; its axes are parallel to LIBERO's world axes. Space `native` sends rows in the robot's own action types
exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Franka Emika Panda on a fixed mount with a two-finger gripper, driven by LIBERO's operational-space
controller (end-effector deltas)): arm (arm: end-effector pose (stepped by its delta controller), gripper). Cameras:
`agentview`, `wrist`.

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
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** The arm takes end-effector deltas only (LIBERO's operational-space controller, 20 Hz):
move_robot reaches a hand pose to within about 1 cm and 0.05 rad by repeated measured steps; execute_trajectory space
ee_delta sends per-step deltas. The gripper is open or closed (gripper >= 0.5 closes); it takes about 0.4 s to close or
open, so give it a gripper-only goal before moving off with a grasped object. The reported gripper value is the last
command; the finger positions (finger_left, finger_right, m) are in proprio_now. Native action ee_delta: [dx, dy, dz,
drx, dry, drz, grip], each in [-1, 1], one row per 0.05 s step: 1.0 = 0.05 m / 0.5 rad of hand-target motion in the
world frame (whose axes are the base frame's), grip +1 closes, -1 opens. The cameras' intrinsics and poses at the start
(cam2world_gl, OpenGL axes, world frame) are in describe_robot's spec_file; each action's result carries the current
ones (cameras_now; the wrist camera moves with the hand).

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds, after
  9000 control steps (450 s of robot time; a technical cap so that the episode's video can be
  rendered in its time limit), when your time is up, or on a simulator error. `spec()["budget"]["reset"]` is 0.
- **Time moves only inside calls.** `submit` runs your actions and `get_obs(seconds=s)` holds still for `s` seconds;
  both use up control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see two cameras (`agentview` fixed in front of the robot, `wrist` on the hand;
  RGB 256×256, depth on request) with their intrinsics and pose (`spec()["cameras"]` at the start;
  every submit response carries the current ones in `meta["cameras_now"]`) and the robot's own state. Not the objects'
  poses, not the goal or the success check: the service only tells you that the episode ended and why
  (`meta["done"]`, `meta["reason"]`: `"success"`, `"failed"` at the step cap, `"error"` after a simulator error).
- There is nothing to hand in: the service records the episode and grades it as it ran.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so
  do not stop early.
- Do not use LIBERO's demonstrations, LIBERO-MAX's policies or any published solution.

## Scoring
LIBERO's own success check for this task: all of
- `akita_black_bowl_1` is in `wooden_cabinet_1_top_region` (LIBERO's In: `akita_black_bowl_1`'s origin lies inside the region's box, whose floor counts 1 cm lower, and it touches the region's object)
The service ends the episode the moment it holds (`reason = "success"`): that episode, as it ran, is graded (nothing
is replayed).

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
Its docstring is the full reference (the client is not installed for your code: the `efe-robot` tools stand for it; its examples come from another benchmark: the numbers here and in `spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.05 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold still and watch for `seconds` (at most 30) |
| `r.submit("ee_delta", A, dt=0.05, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 7 numbers `dt` seconds apart (a multiple of 0.05; a chunk covers at most 10 s); stops early when the episode ends |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`,
`cameras_now`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (rows).
```python
from rcb_client import Robot
r = Robot()
res = r.submit("ee_delta", A, dt=0.05, cameras=["agentview"], video="none")   # A: (T, 7)
```
- Action `ee_delta` (7, float64, each clipped to [-1, 1]): LIBERO's native operational-space control (OSC_POSE). Per
  control step the hand's target moves by `[dx, dy, dz]` × 0.05 m and turns by `[drx, dry, drz]` × 0.5
  rad (axis-angle, world frame); `grip` +1 closes, -1 opens the gripper. With `dt = 0.05` each row is one control step;
  `get_obs(seconds=s)` holds still (zero motion, the gripper as last commanded).
- Proprioception (`spec()["proprio_layout"]`): `eef_x/y/z` (m) and `eef_qw/qx/qy/qz` (the hand), `finger_left`,
  `finger_right` (m), `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `cmd_*` (the last action).
- World frame: metres; the robot's base is at (-0.66, 0, 0.912) facing +x: x forward (across the table), y to the robot's
  left, z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along its
  -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels (upright images).
- Measured cost here: about 20 ms of simulation per control step, plus about 70 ms per camera image.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **10 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
