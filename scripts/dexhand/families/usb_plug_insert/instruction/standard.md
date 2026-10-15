# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three world-axis prismatic joints, then
three serial revolute joints in a fixed rotated gimbal frame; no arm). The stage and the fingers are position actuated
in the physics engine under native force bounds; grasping, carrying, inserting and releasing require physical contact.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
- Desk: top at z = 0.70 m, front edge at y = -0.114 m (world frame, z up, metres and radians).
- Hub: the original four-port USB hub (103 x 30 x 10 mm, 21.8 g) rests free on the desk on rubber pads, its port face
  flush with the desk's front edge and facing -y; it is not fixed or held. Ports 1-4 are at hub-local
  x = -27, -7, +13, +33 mm; port 4 (the target) is the rightmost seen from the front. Its own upstream cable is drawn
  lying on the desk and has no physics.
- Plug: a free USB-A plug (7 g; metal shell 12.0 x 4.5 x 12 mm, housing 15 x 20 x 8 mm, strain relief) lying on its
  side on the desk, with a passive 0.5 m cable (20 ball-jointed links, 15 g) ending in a free USB-B plug on the desk.
  The plug frame origin is the centre of the shell tip; its +y axis points out of the shell (insertion direction)
  and +z is the polarized top face. Inserted correctly, the plug's +y aligns with the hub's +y and +z with the hub's +z.
- Ports are open rectangular cavities 12.5 x 4.8 x 12 mm (0.25 mm clearance per side across, 0.15 mm in height); the
  receptacle tongue and contacts are visual only, polarity is part of the success predicate, and there are no
  retention springs: a seated plug stays by friction and its own weight.
- Cameras: `overview` (desk, hub and plug from the front left) and `closeup` (the hub's port face).

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose (`right_hand_C_MC`, the hand mount) and current targets; object
poses, contacts and the verdict state are not observable (`r.status()` only reports whether the episode ended and
whether it succeeded). An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then replays the graded episode with the
recorded hand in two fresh processes. Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets `wrist_x, wrist_y,
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial X-Y-Z hinges in the fixed gimbal frame), then the
finger targets in radians. `D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`,
`r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits
and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured poses use WXYZ; world z is up, the desk top is at z = 0.70 m and its front
edge at y = -0.114 m. Cameras are overview and closeup, at 640 x 480. Requests can return RGB frames or mp4, with depth
`none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras,
fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those
steps. Calling it without seconds only observes the current state. Forward kinematics uses only the robot's own links;
no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
