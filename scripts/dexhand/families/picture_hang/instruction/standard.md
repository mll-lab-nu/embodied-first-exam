# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand on each wrist. The arm joints and the fingers are position actuated in the physics engine under native force bounds;
the frame moves only through contact, gravity and its two passive ring hinges, so lifting, carrying,
hooking and releasing all require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene (world frame: metres, z up, x pointing into the wall)
- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19; the console stands on its two rear legs
  (x = 0.615) so that the robot stand's base plate fits under its front half.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre
  of its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The robot stand faces the wall (+x) in front of the console, its base origin at (0.18, 0.00, 0.20): it stands on a
  0.10 m plinth exactly under its base plate; the shoulders are 1.121 m above the base origin, at y = +-0.2215. Only
  the hands may touch anything: any contact of an arm, torso or stand link with the frame, the hooks, the wall, the
  console, the floor or the other hand ends the episode (`robot_collision`).
- At the start both hands hang palm-inward above the frame's side rails, fingers pointing down, thumbs toward the wall. With
  `sharpa` the right hand is the genuine Sharpa Wave right hand and the left hand is a declared mirror image of it (the
  right model reflected, same joints, ranges and force limits); with `wuji` both are the manufacturer's left and right
  Wuji Hand 2.2 models.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, both wrist poses and current targets; the frame's state is not
published, measure it with the cameras. An episode ends at the first success or the first failure (see the task text);
after that the service accepts no more actions until a reset (see `## Episodes and resets`). The service records every
action and watch step, then judges the graded episode as it ran (that is the verdict; nothing is replayed). Leave your
controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview", "hook_closeup"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements (tcp_pose: both palms, 7 columns each)
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets in
radians (left arm `SHOULDER_PITCH_L_J1_target` ... `WRIST_ROLL_L_J7_target`, then the right arm `..._R_J1_target` ...
`..._R_J7_target`), then the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa
Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`)
and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3,
l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for `r_wuji_r_`). Arm servos: kp 700 N m/rad, kv 48, force limits
108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity compensation; each hand sits rigidly on its arm's flange.
The start targets hold the hands above the frame with open fingers. Actuator targets are
clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ. Cameras are
overview, front, side and hook_closeup, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last`
or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration
for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it
without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
