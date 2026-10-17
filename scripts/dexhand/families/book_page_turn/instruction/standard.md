# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin stand (at the world origin, facing +x; shoulders at (0, +-0.2215, 1.121)) with
two 7-joint arms and a dexterous hand on each wrist; both arms and both hands may be used. Every arm and finger joint
is a position servo in the physics engine under native force bounds (arm servos: stiffness 700 N m/rad, damping
48 N m s/rad, the arms' own torque limits and **no gravity compensation**, so a held target sags slightly under the
arm's weight unless your targets account for it). Lifting, carrying and laying the page down require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps. The book is not attached to anything: it rests
on the desk under gravity and friction, and a push on its pages moves it unless something holds it.

## Scene
World frame: z up, metres and radians, +x forward from the robot stand, +y to the robot's left. The desk top is the
plane z = 0.78 m (desk x in [0.22, 0.82] m, y in [-0.26, 0.26] m). The board book lies open on the desk as one free
body (`book_spine`, nothing anchors it): its spine runs along the world x axis through y = 0, from x = 0.434 to
x = 0.586 (centre x = 0.51). Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm thick laminated board of 16 g;
the right-hand boards extend from the spine toward -y (the robot's right; fore-edge at y = -0.152), the left-hand
boards toward +y (fore-edge at y = +0.152). Boards hinge at the spine about the world x axis (`<board>_binding`,
passive friction 0.002 N m and damping 0.006 N m s/rad) on a small vertical binding compliance
(`<board>_binding_compliance`, 200 N/m). Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left
stack, leaf 1 on top), leaf 2 9.0 mm, leaf 3 7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm
(right stack, leaf 2 on top), both covers 0.6 mm. **Every board lies flat on its stack, 0.2 mm above the board below
it**: the top board's fore-edge face (1.2 mm tall, at y = -0.152, top at z = 0.7884) sits directly above leaf 3's.
Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf hinge angles are measured from the flat right-hand
position for right-hand boards (0 = flat right, pi = flat left) and from the flat left-hand position for left-hand
boards (negative = lifted toward the right). At the start the right hand (frame `wrist_stage` / `right_hand_C_MC`,
palm up, index straight) is at about (0.47, -0.44, 0.93) and the left arm hangs parked beside the stand.

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
`rows` is `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order
(the row layouts below), radians. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most
10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. Actuator
targets are clipped to the published joint limits and clipping is reported. Quaternions in measured poses use WXYZ;
world z is up and the desk top is at z = 0.78 m. Cameras are overview, closeup, front and top, at 640 x 480.

Row layout, `sharpa` (58): 0-6 left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); 7-13 the same right-arm joints
(`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE, left_thumb_CMC_AA,
left_thumb_MCP_FE, left_thumb_MCP_AA, left_thumb_IP, left_index_MCP_FE, left_index_MCP_AA, left_index_PIP,
left_index_DIP`, the same four for middle and ring, then `left_pinky_CMC, left_pinky_MCP_FE, left_pinky_MCP_AA,
left_pinky_PIP, left_pinky_DIP`; 36-57 the right Sharpa Wave fingers in the same order (`right_...`).
Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji fingers `l_wuji_l_THJ0..THJ3` (thumb),
`l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle), `l_wuji_l_RFJ0..RFJ3` (ring), `l_wuji_l_LFJ0..LFJ3`
(little); 34-53 the right Wuji fingers in the same order (`r_wuji_r_...`). The frozen start row of each hand variant
(arm targets and finger targets) is the robot's `joint_target` proprioception right after a reset.

Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links (both wrists); no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
