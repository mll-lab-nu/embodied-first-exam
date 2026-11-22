# MetaWorld+ · basketball (standard-mcp-shell)

## Task
A Sawyer arm at a table (Meta-World, MuJoCo). Pick up the ball and place it through the basketball hoop. The robot runs
as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client,
as if it were real hardware: one live episode.

## Goal
Success: the ball is in the basketball hoop's ring, right above the target point. What counts is how things stand at the
end of the episode: a success reached earlier and lost by the end does not count, so finish in the state you want graded
and stop sending commands.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the camera images (with their calibration), the robot's own sensor readings and the
  task's target point; no object poses, no success signal.
- Write your own controller; do not use Meta-World's scripted policies, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: at the arm's base link (world origin, table-top height), +X forward across the table (world +y), +Y
the robot's left (world -x), +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm:
end-effector pose (stepped by its delta controller), gripper). Cameras: `front`, `left`, `right`, `topview`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: The hand is moved with execute_trajectory space native, action_type ee_delta: rows [dx, dy, dz, grip], each
in [-1, 1], one row per 0.0125 s control step (the default dt); dx, dy, dz move the hand's target by 1 cm per step per
unit in the world frame (x = the robot's right, i.e. base -Y; y = forward, i.e. base +X; z up), kept inside x in [-0.5,
0.5], y in [0.4, 1.0], z in [0.05, 0.5]; the hand follows the target within a few steps; grip +1 closes, -1 opens. The
wrist orientation is fixed. proprio_now holds tcp_x/y/z (the point between the fingertips, world frame), gripper_opening
(0 closed .. 1 open) and mocap_x/y/z (the hand's target). The four cameras are fixed.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`.

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
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

One call returns at most 3000 images. `get_obs(seconds=s)` holds the hand still (zero motion, same grip) while physics
runs for `s` seconds; those control steps are part of the episode.

### Actions
- Action `ee_delta` (4: `dx, dy, dz, grip`, float64, each clipped to [-1, 1]) is Meta-World's native action, applied
  once per control step (`control_dt` = 0.0125 s). The hand's target moves by `[dx, dy, dz]` × 1 cm per control step and
  stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [0.05, 0.5]; the hand follows it. `grip` drives the two fingers (+1
  closes, -1 opens). The wrist does not rotate. Rows are `dt` apart (a multiple of `control_dt`); with `dt = control_dt`
  each row is one native action. A chunk covers at most 10 s.

### Observations
- Proprioception (names as in the spec's proprio layout): `tcp_x/y/z` (the point between the fingertips),
  `gripper_opening` (0 closed … 1 open), `mocap_x/y/z` (the hand's target), the arm joints' positions and velocities,
  the finger joints' positions, and `cmd_*` (the last action).
- World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at z = 0.
  Quaternions are w x y z. The four cameras are fixed.
- Calibration (`obs.meta["cameras"]`, per camera): `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4
  camera-to-world, OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from).
  Depth is the distance along the viewing axis, in metres.
- The target point that Goal names is `target_pos` in `meta["task"]` (world frame), in every reply.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
