# VLABench · heat_food — instance i00 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated **Franka Panda** arm (VLABench on MuJoCo) **as if it were real hardware**: the simulator runs in
a service you cannot open, and you reach it only through a client. **Task: Please heat cooked_food from tray_seen: put it into microwave_seen, close the microwave's door and press its start button (heating itself is not simulated).**

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
closed. Base frame of this robot: the robot base frame: at the arm's mount, +X forward across the table (world +y), +Y
the robot's left (world -x), +Z up. Space `native` sends rows in the robot's own action types exactly as the sections
below describe them (their frame, units and gripper values).

**This robot** (Franka Emika Panda on a fixed mount with a two-finger gripper, absolute joint and finger position
targets): arm (arm: 7 joints, no end-effector pose, gripper). Cameras: `forward`, `left`, `right`, `wrist`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the robot base frame that a camera sees at pixel (u, v)
  of its full-size image (u the column, v the row), or one per pixel of `pixels` [[u, v], ...]: from a new depth image
  of that camera and its calibration (no time passes). For a camera with depth and a known pose; for any other the error
  says so.
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
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The arm takes absolute joint position targets only: native action joint_position is 9 numbers,
the 7 joints (rad) and then the two fingers' openings (m: 0 closed .. 0.04 open, set both alike); move_robot's gripper
0..1 sets both fingers. Nothing enforces the arm's joint limits: stay inside the Panda's own (spec_file:
action_types.joint_position.panda_joint_limits_rad). The reported end-effector pose is the hand's tool point (tcp). A
closed grasp holds the finger targets at 0: the fingers stop on the object, so the reported gripper value (the measured
opening of one finger) stays below 1 while something is held. The cameras' intrinsics and poses (cam2world_gl, OpenGL
axes, world frame) are in describe_robot's spec_file.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds, after
  9000 control steps (900 s of robot time; a technical cap so that the episode's video can be
  rendered in its time limit), when your time is up, or on a simulator error. `spec()["budget"]["reset"]` is 0.
- **Time moves only inside calls.** `submit` runs your targets and `get_obs(seconds=s)` holds the last ones for `s`
  seconds; both use up control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no
  seconds is free.
- **No privileged state, no score.** You see four cameras (`forward`, `left`, `right` fixed, `wrist` on the hand; RGB
  320×320, depth on request, each camera's intrinsics and pose in `spec()["cameras"]`) and the robot's
  own state: joint angles and velocities, finger positions, the hand's pose (`tcp_*`) and the last command. Not the
  objects' poses, not the task's conditions or success check: the service only tells you that the episode ended and
  why (`meta["done"]`, `meta["reason"]`: `"success"`, `"failed"` at the step cap, `"error"` after a simulator error).
- There is nothing to hand in: the service records the episode and grades it as it ran. Keep the script that
  drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so
  do not stop early.
- Do not use VLABench's expert solutions or any published solution for this benchmark; write your own controller.

## Scoring
VLABench's own success check for `heat_food` (the task's termination condition). The service ends the episode the
moment it holds (`reason = "success"`); that live episode is the verdict.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; its examples come from another benchmark: the numbers here and in `spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.1 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.1, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 9 targets `dt` seconds apart (a multiple of 0.1; a chunk covers at most 10 s); stops early when the episode ends |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[cam]`
(the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.proprio` (rows).
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.1, cameras=["forward"], video="none")   # A: (T, 9)
```
- Action `joint_position` (9, float64): absolute position targets for VLABench's own actuators, the 7 arm joints (rad)
  and the 2 fingers (m, 0 closed … 0.04 open), each row held for its control steps (0.1 s, 100 physics steps each).
  The model sets no arm joint limits; stay inside the Panda's own, `spec()["action_types"]["joint_position"]
  ["panda_joint_limits_rad"]`.
- Proprioception (`spec()["proprio_layout"]`): `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `finger1_pos`,
  `finger2_pos` (m), `tcp_x/y/z` (m) and `tcp_qw/qx/qy/qz` (the hand's pose), `cmd_*` (the last command).
- World frame: metres; the robot's base is at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along
  its -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels.
- Measured cost here: about 40 ms of simulation per control step, plus about 15 ms per camera image.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **5 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
