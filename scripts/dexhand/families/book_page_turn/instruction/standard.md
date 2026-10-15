# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, carrying and laying the page down require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps. The book is not attached to anything: it rests on the desk under gravity and friction.

## Scene
World frame: z up, metres and radians. The desk top is the plane z = 0.30 m (desk x in [-0.55, 0.55] m,
y in [-0.35, 0.45] m). The board book lies open on the desk as one free body (`book_spine`, nothing anchors it): its
spine runs along the world y axis through x = 0, y = 0. Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm
thick laminated board of 16 g; the right-hand boards extend from the spine toward +x, the left-hand boards toward -x,
and all boards span y in [-0.0762, 0.0762] m. Boards hinge at the spine about the y axis (`<board>_binding`, passive
friction 0.002 N m and damping 0.006 N m s/rad) on a small vertical binding compliance (`<board>_binding_compliance`,
200 N/m). Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left stack, leaf 1 on top), leaf 2
9.0 mm, leaf 3 7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm (right stack, leaf 2 on top), both
covers 0.6 mm. **Leaf 2's binding hinge has a lower stop at 0.07 rad (4 degrees): the board to turn rests on that
springback stop, so its fore-edge (x = 0.152 m) stands about 11 mm above leaf 3**; every other board lies flat on
its stack. Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf hinge angles are measured from the flat
right-hand position for right-hand boards (0 = flat right, pi = flat left) and from the flat left-hand position for
left-hand boards (negative = lifted toward the right).

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets `wrist_x, wrist_y,
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.30 m. The book's spine runs along the world y axis through
x = 0, y = 0; the right-hand pages extend toward +x (6 x 6 in boards, 0.152 m from the spine to the fore-edge), the
left-hand pages toward -x. Cameras are overview, closeup, front and top, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.
