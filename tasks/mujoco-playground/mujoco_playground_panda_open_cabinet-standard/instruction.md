# MuJoCo Playground · Panda open cabinet (standard)

## Task
A Franka Panda arm (MuJoCo Playground's scene, in MuJoCo). It stands in front of a green handle on a slide (the handle
moves only along x, from x = 0.5 m towards the robot), with a shelf behind a barrier; a red target sphere marks where
the handle should end up. Grasp the handle and pull it along its slide to the target. The robot runs as a service you
reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: the handle has been pulled along its slide to the target and is there, close to it. What counts is how things
stand at the end of the episode: a success reached earlier and lost by the end does not count, so finish in the state
you want graded and stop sending commands. The episode runs until your time is up.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
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
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 8) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```

One call returns at most 3000 images.

### Actions
Action type `joint_position` (8): `actuator1..7` joint targets (rad), `actuator8` finger opening (0..0.04 m); rows are
`dt` apart (a multiple of `control_dt`), each held (`interpolate="hold"`) or ramped from the previous row (`"linear"`,
default) over its control steps; clipped to the limits in the spec. A chunk covers at most 10 s.

### Observations
`meta["proprio"]` (`layout`, `now`): the joint positions, velocities and current targets. `meta["task"]` is the task's
target (`target_pos`, and `target_quat_wxyz` where it has one). Calibration: `meta["cameras"][cam]` holds `intrinsic_cv`
(pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x right, y up, the camera looks along -z; the
viewpoint the image is rendered from), for the state at the end of that call (the `last` image and the last frame of
every stack). Depth is the distance along the viewing axis, in metres. The four cameras are fixed.

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
