# DexToolBench · red brush · sweep_right (MuJoCo) — LIMITED MODE (robot as a service)

A KUKA iiwa 14 arm with a 22-joint **Sharpa HA4** dexterous hand stands next to a table with a **red brush** on it.
**Task:** pick up the red brush and move it through the demonstrated motion (a sweep to the right): bring it to each
of the **38 goal poses in order** (the green ghost tool shows the current goal). This is task `brush / red_brush /
sweep_right` of DexToolBench (SimToolReal), run here in plain MuJoCo.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration) plus the
  robot's own joint positions, velocities and targets. No object poses, no success predicate.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use pretrained manipulation policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The current goal counts as reached when all 8 corners of the tool's grasp box (0.141 × 0.030 × 0.027 m, scaled by
1.5, in the tool's frame) are within **1.5 cm** of the same corners at the goal pose; then the next goal becomes
current. In this mode goals have **no time limit** (the benchmark gives each goal 10 s; here you get one episode and no reset). The episode ends when every goal is reached, when your time is up, or after **360,000 control steps (100 min of robot time)**.
**reward = goals reached / 38** (partial credit). Full success = all 38.

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/2.1`)
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
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 29) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Actions `joint_position` (29: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in `spec["action_types"]["joint_position"]["layout"]`)); rows are `dt` apart (a multiple of `control_dt`), each held
  (`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
  limits in the spec. A chunk covers at most 10 s.
- `meta["task"]` = the current goal (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`, `steps_left_on_goal`
(the benchmark shows the controller the current goal, as SimToolReal's deployment does). The episode **ends** when every
goal is reached or at the step limit (`spec["max_control_steps"]`); after that the service answers 409.
`steps_left_on_goal` is null: no goal has a time limit here.
