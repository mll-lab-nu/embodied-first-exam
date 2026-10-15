# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand
on each wrist (robot id `marvin-bimanual-sharpa-wave`); the right arm and hand do the task and the left arm stays
parked beside the torso. Every arm and finger joint is a position servo in the physics engine under native force
bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target
sags by about 1 cm at the hand under load unless your targets account for it). The turner is held only by finger and
palm contact, and the pancake moves only through contact with the turner, the pan and the plate. The controller runs
at {{CONTROL_HZ}} Hz, with twenty 1 ms physics substeps per control. World frame: metres and radians, +z up, +x
forward from the robot stand, +y to the robot's left.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The turner is not in a hand at the start: as in the source scene it rests on the counter in
front of the plate, at about (0.76, -0.30, 0.878) m with its handle toward -y (handle end and blade base on the counter,
the handle 16 to 30 mm above it); pick it up first. It is held only by contact (there is no weld or attachment).
Physics runs at 1 ms steps, twenty per 50 Hz control.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, radians: columns 0-6 the left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, 7-13 the right arm `..._R_J1` ... `..._R_J7`, then the left hand's and
the right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand) and 54 for `wuji`
(20 Wuji Hand 2.2 finger joints per hand). The episode starts with both hands open and the turner resting on the counter; holding the start
targets keeps that pose. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of
0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear
interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured poses
use WXYZ; world z is up and the counter top is at z = 0.85 m. Cameras are overview, closeup and side, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
