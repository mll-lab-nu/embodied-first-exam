# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its base plate stands on the floor at z = 0); the
left arm is parked beside the torso and only the right arm and hand do the task. Arm joints and fingers are position
servos in the physics engine under native force bounds; pressing, sliding, pushing and releasing require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, the hand root pose (`right_hand_C_MC`) and current targets. An episode ends at the first success
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (radians): the 7 left-arm joint targets
`SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets `SHOULDER_PITCH_R_J1_target ...
WRIST_ROLL_R_J7_target`, then the left-hand and the right-hand finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave
finger joints per hand, `left_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints
per hand, `l_wuji_l_THJ0` ... `r_wuji_r_LFJ3`). Keep the left arm at its start targets; only the right arm and hand do
the task. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.70 m. Cameras are overview, closeup and mouth (a low view of the envelope mouth), at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links (the robot base is at (1.15, -0.25, 0.10) m, facing -x); no IK
primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
