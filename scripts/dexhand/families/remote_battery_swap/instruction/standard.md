# DexHand: {{TITLE}}

{{TASK_TEXT}}

## Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m (the floor is at z = -0.55 m). The remote lies
flat at (0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on
four rubber feet, at the approved scene's size (shell 160 x 64 mm, battery cavity 94 x 52 mm). Its battery door
slides along the remote's -x direction on a passive slide joint (travel 0 to 0.085 m, end stops at both ends, damping
0.1 N s/m, 0.08 N friction loss) and is latched shut: a spring-loaded thumb tab on the door (18 x 18 mm, 3 mm proud
of the door, a passive slide joint pressing down 0 to 5 mm against a 120 N/m spring) carries a hook that sits just in
front of a fixed latch stop at the remote's rear end while the door is shut. The door opens only while the tab is
pressed far enough (about 2.9 to 4.5 mm) for the hook to pass under the stop; it re-latches when it is slid fully
shut and the tab is released. Under the door is a one-cell compartment: the slot centre is at (-0.020, 0.0,
-0.00244) m in the remote frame, the gray cell lies there on two low cradle ribs with its + end toward the gold
contact at the slot's +x end (the silver - contact is at the -x end; 3 mm end play). The green replacement cell (a
23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on the table at (0.115, -0.110, 0.307) with its
+ end pointing 20 degrees clockwise from world +x (seen from above). The receiving tray (free rigid body, inner 74 x
64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). Modelling scope: the compartment holds one cell as in the source
scene; the source's compressible negative spring is not modelled (the terminals are fixed); there is no electrical
simulation. All objects move only through contact and these passive joints.

You control a fixed Tianji Marvin robot standing at the table (stand origin at (-0.45, 0.15, -0.45), facing +x) with
two 7-joint arms and a dexterous hand on each wrist; the right arm and hand do the task, the left arm hangs parked
beside the torso (keep its targets). Every arm and finger joint is a position servo inside MuJoCo 3.4.0 under native
force bounds; the arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held
target sags under the arm's weight unless your targets account for it). Grasping, carrying and releasing require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps per control.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets; object poses, contacts and the stage
conditions are not published; the service reports only whether the episode ended (`done`, with reason `success` or
`task_failure`). An episode ends at the first success
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets
(left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the right arm `..._R_J1` ... `..._R_J7`, radians), then the
left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per
hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). The left arm
is parked; the right arm and hand do the task. Actuator targets are clipped to the published joint limits and
clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the table top is at z = 0.30 m. Cameras are overview, closeup and top, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
