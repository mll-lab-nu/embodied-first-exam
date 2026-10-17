# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand of the same model on each
wrist: a right hand and a left hand. The arm joints and the fingers are position actuated in the physics engine under
native force bounds; holding the grinder and turning the crank require physical contact. The controller runs at 50 Hz,
with ten 2 ms physics substeps. The stand faces +x behind the counter on the floor (z = -0.1 m), its base origin at
(-0.085, 0, 0) m (shoulders 1.121 m above it, at y = +-0.2215 m); any contact of an arm, torso or stand link with
anything ends the episode (`robot_collision`).

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist poses and current targets. An episode ends at the first success
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets in
radians (left arm `SHOULDER_PITCH_L_J1_target` ... `WRIST_ROLL_L_J7_target`, then the right arm `..._R_J1_target` ...
`..._R_J7_target`), then the finger targets in radians, left hand first. `D` is 58 for `sharpa` (22 + 22 Sharpa Wave
finger joints `left_thumb_CMC_FE` ... `left_pinky_DIP`, `right_thumb_CMC_FE` ... `right_pinky_DIP`; the left Sharpa Wave
is the right model reflected in y) and 54 for `wuji` (20 + 20 Wuji Hand 2.2 finger joints `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). Arm servos: kp 700 N m/rad, kv 48, force limits
108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity compensation; each hand sits rigidly on its arm's
flange. Actuator targets are clipped to the published joint limits and clipping is
reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation
holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper
opening. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.70 m. "Clockwise" is
seen from above. Cameras are overview, closeup and top, at 640 x 480. Requests can return RGB frames or mp4, with
depth `none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce
cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and
records those steps. Calling it without seconds only observes the current state. Forward kinematics uses only the
robot's own links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect
`r.status()` before continuing. Crash recovery resumes the same journaled episode, without a reset, and the
wall-clock budget keeps running.
