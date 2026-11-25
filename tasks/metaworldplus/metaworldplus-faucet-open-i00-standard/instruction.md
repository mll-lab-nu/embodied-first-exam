# MetaWorld+ · faucet-open (standard)

## Task
Turn the faucet on.

## Goal
Success: the faucet handle is turned to open, its end at the target point. What counts is how things stand at the end of
the episode.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions,
  Meta-World's scripted policies, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras, the robot's own sensor readings and the task's target point: no object poses, no success
  signal.

## Robot Interface
A Sawyer arm at a table (Meta-World, MuJoCo). The robot runs as a service you reach only through its client, as if it
were real hardware: one live episode.

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
  stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [-0.15, 0.5]; the hand follows it. `grip` drives the two fingers (+1
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
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
