# RoboCasa · PnPCounterToSink — STANDARD MODE (robot as a service)

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa's `PnPCounterToSink` kitchen task (robosuite, MuJoCo).
**Task: Pick the apple from the counter and place it in the sink.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then replays the recorded episode in a fresh simulator and applies
the environment's own success check for `PnPCounterToSink` to the state **after the last executed control step**; it must hold
in the live episode and in the replay. A success reached earlier and then lost does not count: end in the state you
want graded and stop submitting.

What `PnPCounterToSink`'s check requires (RoboCasa @ 756598a), all on that final state:
- The object's centre is inside the sink basin.
- The gripper's grip site (between the fingertips) is more than 25 cm from the object's centre: let go and move the hand away.
A "centre" is a body's origin; "touches" means a MuJoCo contact.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
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
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `ee_delta`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). 12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion per control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's target velocities in its own frame (1.0 = 1 m/s for `base_x` / `base_y` and 1.5 rad/s for `base_yaw`; force-limited velocity servos, so the base may lag the target); `torso` -- the torso lift, a joint-position controller with delta input (each step sets the lift's height target to its current height + 0.05 m × the value, so 1.0 = 5 cm per step; lift range 0–0.34 m); `hybrid_mode` (> 0: base mode, the arm's goal moves with the base; <= 0: arm mode, the default -1). Every channel is clipped to [-1, 1]. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs
  for `s` seconds; those control steps are part of the episode.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- World frame: metres, z up.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
