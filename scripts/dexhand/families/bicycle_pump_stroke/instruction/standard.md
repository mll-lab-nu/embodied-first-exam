# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and hand
alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target sags under the arm's
weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical contact.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

{{HANDS}}
{{RESETS}}
## What you observe
Camera RGB and calibrated depth from `overview` (default) and `closeup` (aimed at the pump), the robot's own joint
positions, velocities, actuator efforts, hand pose and current targets, and robot-link forward kinematics. The
service does not report the pump pose, the head or lever position, the piston depth, the stroke count, the tire
pressure or contacts: judge the
handle and the pump from the images and depth. At the end of an episode the meta reports `done`, `success` and a
failure category; the graded verdict is the replay's (see the task text).

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all position targets in radians: the
14 Marvin arm joints (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values;
then the right arm `..._R_J1` ... `..._R_J7`), then the left hand's and the right hand's finger joints. `D` is 58 for
`sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE`
... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). The arm servos have no gravity compensation. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the bench top is at z = 0.70 m. The pump stands near world (0.42, 0.08) with its
T handle about 0.45 m above the bench at rest; the disconnected hose head sits at the wheel rim near world
(0.546, -0.12, 0.747) with its thumb-lock lever pointing up, and seats by sliding 17.5 mm toward the rim along
(-0.981, 0, -0.196). Cameras are overview, closeup, wide and front, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
