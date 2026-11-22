# RoboCasa · OpenDrawer (standard)

## Task
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa, robosuite / MuJoCo).
Open the right drawer. The robot runs as a service you reach only through its client, as if it were real hardware: one
live episode.

## Goal
Success: the right drawer is pulled all the way open. What counts is how things stand at the end of the episode: a
success reached earlier and lost by the end does not count, so finish in the state you want graded and stop sending
commands.

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
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_delta", A, cameras=cams[:1], video="mp4")   # A: (T, 12) rows, one per control step
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs for `s`
seconds; those control steps are part of the episode. One call returns at most 3000 images.

### Actions
- Action `ee_delta`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion per
  control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); `grip` (+1 closes,
  -1 opens); `base_x, base_y, base_yaw` -- the mobile base's target velocities in its own frame (1.0 = 1 m/s for
  `base_x` / `base_y` and 1.5 rad/s for `base_yaw`; force-limited velocity servos, so the base may lag the target);
  `torso` -- the torso lift, a joint-position controller with delta input (each step sets the lift's height target to
  its current height + 0.05 m × the value, so 1.0 = 5 cm per step; lift range 0–0.34 m); `hybrid_mode` (> 0: base mode,
  the arm's goal moves with the base; <= 0: arm mode, the default -1). Every channel is clipped to [-1, 1]. Rows are
  `dt` apart (default and minimum: `control_dt`; a chunk covers at most 10 s).
- World frame: metres, z up.

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
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
