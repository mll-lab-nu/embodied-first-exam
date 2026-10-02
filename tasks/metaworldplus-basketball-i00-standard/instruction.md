# MetaWorld+ · basketball — STANDARD MODE (robot as a service)

A **Sawyer** arm stands at a table: Meta-World's `basketball-v3` environment (MuJoCo). **Task: Pick up the ball and place it through the basketball hoop.**
The scene is one frozen instance of Meta-World's own randomization.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration), the
  robot's own state and the task's target point. No object poses, no success signal.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use Meta-World's scripted policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then replays the recorded episode in a fresh simulator and applies
Meta-World's own success check for `basketball-v3` to the state **after the last executed control step**; it must hold in
the live episode and in the replay. A success reached earlier and then lost does not count: end in the state you want
graded and stop submitting. The check measures the task's object (the hand, for reaching tasks) against
`meta["task"]["target_pos"]`, with a tolerance of a few centimetres.

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
