# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous hand on each wrist. The right
arm and its hand suffice for the task; the left arm starts parked beside the stand (hanging straight down) and may stay
there (using it is allowed; every robot contact counts as hand contact). Every arm and finger joint is a position servo inside MuJoCo (implicitfast, 2 ms physics step). Arm servos have
stiffness 700 N m/rad, damping 48 N m s/rad and the arms' own torque limits (shoulder 108, elbow 66, wrist 18 N m), and
**no gravity compensation**: a held target sags by about 1 cm at the hand unless your targets account for it. Pushing,
pressing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 arm joint targets (left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the same right-arm joints `..._R_J1` ... `..._R_J7`, radians), then
the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per
hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`,
`l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). Only the right arm and hand are needed; keep the left arm at its start
targets. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.78 m. Cameras are overview, closeup and throat, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links (arms and hands); no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.

## Scene (frozen instance, world frame)
World frame: z up, metres and radians. The floor is at z = 0. The robot's stand origin is at (0.58, -0.66, 0.10) with
its base plate on the floor, beside the desk's -y edge, facing the desk diagonally (heading 135 deg: toward -x and +y);
the right shoulder is at about (0.737, -0.503, 1.221) and the left at (0.423, -0.817, 1.221); the right hand's mount
starts at (0.80, -0.22, 1.02) with the fingers pointing down. The desk top is at z = 0.78 m and spans x 0.25-0.99 m, y -0.36-0.36 m
(friction: paper on paper 0.4, paper on desk 0.15, paper on the chrome anvil and stop 0.1). The NOVUS B2-style desk
stapler is a free body (0.173 kg) whose base origin is at (0.575, -0.100, 0.783) with its nose toward +x (the source
scene's pose). Its anvil top is at z = 0.795 m; the staple point (base frame (0.063, 0, 0.012) m) is at
(0.638, -0.100, 0.795) in the reset pose. A steel paper stop (insertion guide) stands behind the anvil: its front face
is at base-frame x = 0.0525 m (world x = 0.6275 m) for |y - y_base| <= 0.012 m, z 0.790-0.800 m; a stack whose corner
is fed against it puts the staple point about 10.5 mm inside both edges. The handle with its driver blade turns on one
passive hinge about the base-frame y axis at (-0.052, 0, 0.020): return spring 7.0 N m/rad with 0.115 rad preload
against the open stop (0 rad), bottom stop 0.1701 rad (the blade 0.2 mm into a three-sheet stack lying on the anvil).
The handle top is about 6.6 cm above the desk; pressed 8 cm in front of the hinge, the head needs about 10 N to start
moving and about 25 N at the bottom stop. The magazine is rigid with the base.

The three sheets are rigid A5 plates (0.210 x 0.148 m, 0.5 mm thick, 2.5 g each), indexed bottom (0) to top (2). At
reset they rest as a loose, misaligned stack: the bottom sheet's (-x, -y) corner lies on the anvil mouth in front of
the paper stop, its +x edge on the desk; sheets 1 and 2 are shifted 4 mm and 8 mm toward +x. Rest poses (centre; all
three pitched 0.0733 rad about +y, i.e. the -x end raised, yaw 0): sheet 0 (0.7440, -0.0360, 0.7879),
sheet 1 (0.7480, -0.0356, 0.7881), sheet 2 (0.7520, -0.0364, 0.7883).

Simplifications relative to the source scene (T36), stated plainly: the sheets start with the corner already at the
throat mouth instead of lying flat on the desk (rigid thin sheets cannot be picked up from a flat desk by the modelled
fingertips; the hand only slides the stack in); the paper stop is an added part (the real NOVUS B2 has none; it squares
the stack, which the fingertips cannot do on their own against a flat desk); staple legs, piercing and clinching are
not simulated: "stapled" means the head pressed through its full stroke onto the aligned, inserted stack and released;
the sheets are 0.5 mm thick rigid plates (the source's sheets are 0.1 mm), with the real A5 size and mass.
