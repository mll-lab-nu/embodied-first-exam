# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a single dexterous hand mounted palm-down on a six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm, no second hand). The stage and the fingers are position actuated in the physics engine
under native force bounds; turning, lifting, carrying and releasing the lid require physical contact, and the jar is
held by nothing but its own weight and friction on the worktop. The controller runs at 50 Hz, with ten 2 ms physics
substeps. At reset the wrist targets are `(0, 0, 0.50)` m and `(0, 0, 0)` rad: the open hand hangs about 0.1 m above the
lid, fingers along +x.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. The service serves no jar or lid pose,
contact, lid turn or stage; it reports only whether the episode has ended and whether in success or failure
(`task_failure`, without the failure's name). An episode ends at the first success or the first failure (see the task
text); after that the service accepts no more actions until a reset (see `## Episodes and resets`). The service records every action and watch step, then replays the graded episode with the
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
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints; with `wrist_rx = wrist_ry = 0` the palm
faces down, the fingers point along +x and `wrist_rz` turns the hand about the vertical through the stage origin, about
4 cm below the palm), then the finger targets in radians. `D` is 28 for `sharpa` (22 Sharpa Wave finger joints
`right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`,
`r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up, the jar stands at the
origin and the worktop top is at z = 0.30 m. Cameras are overview, closeup and side, at 640 x 480. Requests can return
RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting
per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets
for up to 30 s and records those steps. Calling it without seconds only observes the current state. Forward kinematics
uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()`
and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without a reset, and the
wall-clock budget keeps running.
