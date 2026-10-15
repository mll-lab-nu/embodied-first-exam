# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The stand rests on the floor (z = 0) beside the counter's -y edge, with its base origin at world
(0.147, -0.591, 0.10), facing +y (shoulders 1.121 m above the base origin, at z = 1.221 m; the right shoulder is on
the +x side). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and
hand alone, and no other part of the robot may touch anything. Every arm and finger joint is a position servo inside
the physics engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no
gravity compensation** (a held target sags under the arm's weight unless your targets account for it). Grasping,
carrying, brushing and releasing require physical contact. The controller runs at {{CONTROL_HZ}} Hz, with ten 2 ms
physics substeps. The frozen reset lets the boot, the clods, the brush and the arms settle for 0.5 s before control 1.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all in radians: the 14 Marvin arm
joint targets (left arm J1-J7, keep them at the parked start values, then right arm J1-J7), then the left hand's and
the right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE`
... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger
joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). The
right hand starts open, palm down, fingers pointing +y, above the brush. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the counter top is at z = 0.886 m. The brush starts bristles-down on the counter at
(0.68, -0.28); the boot's sole plane is at about z = 1.292 m with the sole centre at (0.53, 0.10) and the toe towards
-x. Cameras are overview, closeup and side, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`,
`last` or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or
duration for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps.
Calling it without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK
primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
