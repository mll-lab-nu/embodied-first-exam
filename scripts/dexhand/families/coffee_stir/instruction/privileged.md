# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, stirring and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene
The mug, the coffee and the teaspoon are the approved T11 kitchen scene: a cream glazed mug with a rounded handle
(pointing +x) on a stone worktop, a stainless teaspoon leaning in it (bowl on the mug floor near the +y wall, handle on
the -y rim, top end at about x = 0.48 m, y = -0.087 m, z = 0.905 m). The hand starts open about 0.3 m above the mug
with its fingers pointing down and its palm facing +y. The coffee is a visual surface only: it exerts no force, and
the stirring is judged only from the bowl's revolutions below that surface. Mug and spoon are free rigid bodies that
move only through contact and gravity. Cameras: `overview` (front right of the mug, wide), `closeup` (front right,
close) and `top` (looking down the mug axis).

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets; the frozen
finger start pose of each hand is in `task.json` (`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or `(T, 26)`
for `wuji`, at most {{MAX_ROWS}} rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.

## Tooling
```python
from rcb_dexhand import Session
s = Session("coffee_stir")                      # default hand: DEXHAND_HAND or "sharpa"
s = Session("coffee_stir", hand="wuji")         # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # bowl position (mug frame), revolutions, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "top"
s.snapshot(), s.restore(snap)                   # save / restore the full simulation and predicate state
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate (`s.features()` reports the quantities the predicate uses: `bowl_cup_frame`, `bowl_radius_m`,
`bowl_submerged`, `revolutions`, `hand_spoon_contacts`, `spoon_cup_contacts`, speeds, `cup_tilt_deg`, `cup_slide_m`,
`rest_hold_steps`). The world frame has z up; lengths are in metres and angles in radians. The worktop top is at
z = 0.75 m and the mug axis at x = 0.48 m, y = 0.015 m; the spoon start pose is `task.json` `spoon_pos` (position,
quaternion WXYZ). The wrist-stage targets are world coordinates of the hand mount within `task.json` `wrist_range`.
