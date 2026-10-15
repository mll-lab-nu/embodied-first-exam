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
s = Session("book_page_turn")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("book_page_turn", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names      # selected hand, row width and exact row order
s.hold_action()                             # current motor targets
s.model.actuator_ctrlrange                  # native target limits
s.model, s.data                             # privileged MuJoCo model and state
s.features()                                # leaf-2 angle and speed, other-leaf changes, contacts, book pose change
s.status()                                  # success, done, reason, steps, stage (0-4), total_stages
s.step(row)                                 # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)               # save / restore the full simulation and verdict state
s.render_frame("overview")                  # RGB uint8 (480, 640, 3); also "closeup", "front", "top"
s.reset()                                   # exact frozen reset (includes a fixed 0.5 s passive book settle)
s.replay(actions)                           # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.30 m; the
book's spine runs along the world y axis through x = 0, y = 0, the right-hand pages extend toward +x and the
left-hand pages toward -x. Leaf bodies are `leaf_0` ... `leaf_7` (leaf 0 and 1 on the left, 2 to 7 on the right,
leaf 2 on top), `left_cover`, `right_cover` and the spine `book_spine`.
