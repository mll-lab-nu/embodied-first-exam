# MuJoCo Playground · ALOHA single peg insertion — STANDARD MODE (robot as a service)

An **ALOHA 2** bimanual robot (two ViperX 300s arms facing each other across a table) has a **blue socket** (a square
tube, open on one end, red wall at the back) and a **red peg** in front of it.
**Task:** pick up the socket with one arm and the peg with the other, lift both, and **insert the peg's end into the
socket's open end**. This is MuJoCo Playground's `AlohaSinglePegInsertion`, run here in plain MuJoCo; the peg and socket
positions are randomized as in Playground, with a fixed seed.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration) plus the
  robot's own joint positions, velocities and targets. No object poses, no success predicate.
- Your wall-clock budget is 60 minutes. `meta["time_left_s"]` is counted from your first request to the service;
  approximate — the harness's own deadline is authoritative. There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use pretrained manipulation policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
At the **end of the trajectory** the peg's tip (site `peg_end2`) is within **5 mm** of the socket's axis (the line
through sites `socket_rear` and `socket_entrance`) and at least **25 % of the socket's depth inside** it
(axial parameter `t ≤ 0.75`, where t = 0 at the rear wall and 1 at the entrance). The service applies exactly this rule.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
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
- Actions `joint_position` (14: per arm `waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate, gripper`); rows are `dt` apart (a multiple of `control_dt`), each held
  (`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
  limits in the spec. A chunk covers at most 10 s.
- `meta["task"]` = the task's target (`target_pos`, and `target_quat_wxyz` where it has one). The episode runs until your
time is up; the **final state** is graded (so end in the pose you want graded, and keep it).
- Calibration: `meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world,
  OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from), for the state at the
  **end** of that call (the `last` image and the last frame of every stack). Depth is the distance along the viewing
  axis, in metres. The overhead and teleoperator cameras are fixed. The two wrist cameras move with the arms (`spec["cameras"][cam]["moving"]`):
  for them a response with several frames also carries one pose per frame, `res.raw["cam2world_gl/<cam>"]["data"]`,
  float64 `(n_frames, 4, 4)`.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
