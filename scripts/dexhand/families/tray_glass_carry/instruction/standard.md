# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The left hand hangs above the +y end of the tray, the right hand above the -y end,
fingers pointing down and palms facing the tray. Stages and fingers are position actuated in the physics engine under
native force bounds; lifting, carrying and setting down the tray require physical contact. The controller runs at
{{CONTROL_HZ}} Hz, with ten 2 ms physics substeps.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, both wrist poses and current targets; object poses, contacts and the
checker's progress are not served (`r.status()` reports whether the episode is done and why it ended). An episode ends at the first success
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (units: the six stage slides
`l_wrist_x, l_wrist_y, l_wrist_z, r_wrist_x, r_wrist_y, r_wrist_z` in metres, every other entry in radians): the left wrist stage `l_wrist_x,
l_wrist_y, l_wrist_z` (metres, displacement from the stage base at (0.35, 0.272, 1.15) m) and `l_wrist_rx, l_wrist_ry,
l_wrist_rz` (radians, serial XYZ hinges), the right wrist stage `r_wrist_x ... r_wrist_rz` (stage base at (0.35,
-0.272, 1.15) m), then the left hand's and the right hand's finger targets in radians. `D` is 56 for `sharpa` (22
Sharpa Wave finger joints per hand, `l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, `r_hand_thumb_CMC_FE ...
r_hand_pinky_DIP`) and 52 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3 ... l_wuji_l_LFJ0..3`,
`r_wuji_r_THJ0..3 ... r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is
reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation
holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper
opening. Quaternions in measured poses use WXYZ; world z is up and both counter tops are at z = 0.88 m. Cameras are
overview, side, top and handle_left, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last` or
`frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for
larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it
without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive
is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
