# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene facts (world frame, metres and radians, z up)
- Worktop: top at z = 0.65, spanning x in [0.28, 1.08], y in [-0.50, 0.50].
- Fan (free body on four rubber feet, 2.15 kg with its clips): body frame starts at (0.73, 0.18, 0.952) with the cage
  axis along world -x. The rear rim (radius 0.1845, wire radius 0.0018) lies in the plane x = 0.73.
- Clip hinges (fixed to the fan; hinge axis tangential to the rim; angle 0 closed over both rims, 1.40 open, the
  elastic detent's over-centre point at 0.70): 45 deg (0.734, 0.3128, 1.0848), 135 deg (0.734, 0.0472, 1.0848),
  225 deg (0.734, 0.0472, 0.8192), 315 deg (0.734, 0.3128, 0.8192). All four clips start open at 1.40 (as in the source
  scene). A closed lower clip (225 or 315 deg) forms an open-topped U channel that can carry the guard's rim; an upper
  clip only counts when it locks at or after the first seated control.
- Front guard (rigid, 0.185 kg): rim radius 0.1845 (wire radius 0.0018), dish 0.047 deep toward the operator, a hub
  cap of radius 0.043 and height 0.022 at its centre (front face 0.057 in front of the rim plane), centre of mass
  0.018 in front of the rim plane on the axis. It starts flat on the worktop, dome up, rim centre at
  (0.48, -0.275, 0.6518).
- Seat: the guard is seated with its centre at (0.72635, 0.18, 0.952), i.e. 3.65 mm in front of the rear-rim plane,
  axis along world -x; the stage-1 tolerances in the task text are measured from this pose in the fan's frame.
- Wrist stage: targets are world positions x in [-0.2, 1.0], y in [-0.6, 0.6], z in [0.35, 1.55] and serial XYZ
  angles in [-3.14, 3.14]; it starts at (0.40, 0.00, 0.95, 3.0, 0, 0) (palm down, fingers along +x).
- Cameras (640 x 480): `overview` at (-0.06, -0.84, 1.40) looking at (0.60, -0.07, 0.84), fovy 45; `closeup` at
  (0.20, -0.27, 1.22) looking at (0.72, 0.17, 1.00), fovy 55.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
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
wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the worktop is at z = 0.65 m. Cameras are overview and closeup, at 640 x 480 (poses in the scene facts above). The service
serves no object pose, contact or clip angle: measure the guard, the fan and the clips through the cameras and depth.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
