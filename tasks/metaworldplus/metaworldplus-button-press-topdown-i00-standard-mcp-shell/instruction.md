# MetaWorld+ · button-press-topdown — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

A **Sawyer** arm stands at a table: Meta-World's `button-press-topdown-v3` environment (MuJoCo). **Task: Press the button downward from above.**
The scene is one frozen instance of Meta-World's own randomization.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

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
closed. Base frame of this robot: the robot base frame: at the arm's base link (world origin, table-top height), +X
forward across the table (world +y), +Y the robot's left (world -x), +Z up. Space `native` sends rows in the robot's own
action types exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Rethink Sawyer arm with a two-finger gripper, hand driven by Meta-World's mocap target (position deltas,
fixed wrist orientation)): arm (arm: end-effector pose (stepped by its delta controller), gripper). Cameras: `front`,
`left`, `right`, `topview`.

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
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The hand is moved with execute_trajectory space native, action_type ee_delta: rows [dx, dy, dz,
grip], each in [-1, 1], one row per 0.0125 s control step (the default dt); dx, dy, dz move the hand's target by 1 cm
per step per unit in the world frame (x = the robot's right, i.e. base -Y; y = forward, i.e. base +X; z up), kept inside
x in [-0.5, 0.5], y in [0.4, 1.0], z in [0.05, 0.5]; the hand follows the target within a few steps; grip +1 closes, -1
opens. The wrist orientation is fixed. proprio_now holds tcp_x/y/z (the point between the fingertips, world frame),
gripper_opening (0 closed .. 1 open) and mocap_x/y/z (the hand's target). The four cameras are fixed.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration), the
  robot's own state and the task's target point. No object poses, no success signal.
- Your only budget is the time limit (`## Time limit`). `meta["time_left_s"]` is the service's count of it, from your first
  request to the service: it never runs out before your time does, so plan by it. There is nothing to hand in: the
  service records the episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the
  record.
- Do not use Meta-World's scripted policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then applies Meta-World's own success check for `button-press-topdown-v3` to the
live episode's state **after the last executed control step**. A success reached earlier and then lost does not count:
end in the state you want graded and stop submitting.

For `button-press-topdown-v3` the check is: The button's top is within 2.4 cm of the target point in height; only z is compared (the button is pushed down). ("The target point" is `meta["task"]["target_pos"]`; everything the
check needs to hold must hold in that final state.)

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # front, left, right, topview
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]["target_pos"]                # the task's target point (world frame)
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_delta", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 4)
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `ee_delta` (4: `dx, dy, dz, grip`, float64, each clipped to [-1, 1]) is Meta-World's native action, applied
  once per control step (`control_dt` = 0.0125 s). The hand's target moves by `[dx, dy, dz]` × 1 cm per control step
  and stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [0.05, 0.5]; the hand follows it. `grip` drives the two fingers (+1 closes, -1 opens). The wrist does
  not rotate. Rows are `dt` apart (a multiple of `control_dt`); with `dt = control_dt` each row is one native action.
  A chunk covers at most 10 s.
- `get_obs(seconds=s)` holds the hand still (zero motion, same grip) while physics runs for `s` seconds; those control
  steps are part of the episode.
- Proprioception (`meta["proprio"]["layout"]`): `tcp_x/y/z` (the point between the fingertips), `gripper_opening`
  (0 closed … 1 open), `mocap_x/y/z` (the hand's target), the arm joints' positions and velocities, the finger joints'
  positions, and `cmd_*` (the last action).
- World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at z = 0. Quaternions are w x y z. The four cameras are fixed.
- Calibration: `meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world,
  OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from). Depth is the
  distance along the viewing axis, in metres.

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **5 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
