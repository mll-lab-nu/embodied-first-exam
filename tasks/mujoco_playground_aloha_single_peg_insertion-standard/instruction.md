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
- Your only budget is the time limit (`## Time limit`). `meta["time_left_s"]` is the service's count of it, from your first
  request to the service: it never runs out before your time does, so plan by it. There is nothing to hand in: the
  service records the episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the
  record.
- Do not use pretrained manipulation policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
At the **end of the trajectory** the peg's tip (site `peg_end2`) is within **5 mm** of the socket's axis (the line
through sites `socket_rear` and `socket_entrance`) and **inside the socket, at least 12 mm from its open end**: the
axial parameter `t` is in `[-0.875, 0.75]`, where t = 0 at `socket_rear` (the middle of the tube), t = 1 at
`socket_entrance` (the open end; 48 mm per unit of t) and t = -0.833 at the inner face of the red rear wall (the cavity
is 88 mm deep; the lower bound leaves 2 mm for the contact's give). A peg pushed all the way in counts.
The service applies exactly this rule.

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
  float64 `(n_frames, 4, 4)`. `intrinsic_cv` is `[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]` for the 320 x 240 image; fx and fy
  differ for the overhead and wrist cameras (their sensor is wider than the image): use both.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
