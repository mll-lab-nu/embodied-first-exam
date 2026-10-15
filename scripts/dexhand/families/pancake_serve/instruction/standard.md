# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
the turner is held only by finger and palm contact, and the pancake moves only through contact with the turner, the
pan and the plate. The controller runs at {{CONTROL_HZ}} Hz, with twenty 1 ms physics substeps per control.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The episode starts with the turner already held in a settled power grasp: the frozen reset places
the hand, turner, pan, plate and pancake in a state that was reached by closing the fingers on the handle and letting
the whole scene settle under physics; the turner is held only by contact (there is no weld or attachment), so opening
the fingers drops it. Physics runs at 1 ms steps, twenty per 50 Hz control.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
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
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). The episode starts with the turner in a settled grasp; holding the start finger targets keeps
it. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of
0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear
interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured poses
use WXYZ; world z is up and the counter top is at z = 0.85 m. Cameras are overview, closeup and side, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
