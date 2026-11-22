# MuJoCo Playground · ALOHA single peg insertion (standard-mcp-shell)

## Task
An ALOHA 2 bimanual robot (two ViperX 300s arms facing each other across a table; MuJoCo Playground's scene, in MuJoCo).
A blue socket (a square tube, open at one end, a red wall at the back) and a red peg lie on the table. Pick up the
socket with one arm and the peg with the other, lift both, and insert the peg's end into the socket's open end. The
robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's
own client, as if it were real hardware: one live episode.

## Goal
Success: the peg's end is inside the socket, on the socket's axis and pushed in well past its open end; a peg pushed all
the way in counts. What counts is how things stand at the end of the episode: a success reached earlier and lost by the
end does not count, so finish in the state you want graded and stop sending commands. The episode runs until your time
is up.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the scene's world frame (z up), not either arm's base: no part here takes an end-effector pose;
metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, no end-effector pose,
gripper); right (arm: 6 joints, no end-effector pose, gripper). Cameras: `overhead_cam`, `teleoperator_pov`,
`wrist_cam_left`, `wrist_cam_right`.

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

This robot: The arms take joint positions only: there is no end-effector pose command and no kinematics service here, so
reaching a point means choosing joint angles (each joint's limits are in describe_robot). The state's gripper value
comes from the finger's measured opening, so it stops short of 1 when the fingers close on an object. The two wrist
cameras move with the arms; the overhead and teleoperator cameras are fixed. One episode, no reset: the state at the end
of your time is graded, so finish in the pose you want graded and keep it.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # camera names
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> float16 metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joint positions, velocities, current targets
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]                              # see below
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold the targets and watch for 2 s (max 30)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 14) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```

One call returns at most 3000 images.

### Actions
Action type `joint_position` (14): per arm `waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate, gripper`;
rows are `dt` apart (a multiple of `control_dt`), each held (`interpolate="hold"`) or ramped from the previous row
(`"linear"`, default) over its control steps; clipped to the limits in the spec. A chunk covers at most 10 s.

### Observations
`meta["proprio"]` (`layout`, `now`): the joint positions, velocities and current targets. `meta["task"]` is the task's
target (`target_pos`, and `target_quat_wxyz` where it has one). Calibration: `meta["cameras"][cam]` holds `intrinsic_cv`
(pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x right, y up, the camera looks along -z; the
viewpoint the image is rendered from), for the state at the end of that call (the `last` image and the last frame of
every stack). Depth is the distance along the viewing axis, in metres. The overhead and teleoperator cameras are fixed.
The two wrist cameras move with the arms (`spec["cameras"][cam]["moving"]`): for them a response with several frames
also carries one pose per frame, `res.raw["cam2world_gl/<cam>"]["data"]`, float64 `(n_frames, 4, 4)`. `intrinsic_cv` is
`[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]` for the 320 x 240 image; fx and fy differ for the overhead and wrist cameras
(their sensor is wider than the image): use both.

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
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
