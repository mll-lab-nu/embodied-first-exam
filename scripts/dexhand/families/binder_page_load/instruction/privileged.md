# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene and modelling notes
The binder is free on the desk: back cover (with the ring mechanism near its spine edge) towards +x, spine and front
cover on passive hinges towards -x. Its two toggle plates carry the three ring halves on each side; an over-centre
housing spring (a passive spatial tendon) holds them either closed (0 rad) or open (0.60 rad), and the plates and the
two booster paddles are coupled by the binder's internal linkage (passive joint couplings, never attached to the hand).
Pressing a booster paddle down opens the rings; pushing the plates back past the over-centre point (for example by
pressing the raised inner edges of the open plates down) closes them.
Simplifications, stated plainly: the pages are rigid 0.8 mm cardstock plates (paper bending, creasing and tearing are
not modelled; the holes are octagonal openings 6.35 mm across flats); as in the source scene the two sheets start loose and
flat on the desk (a hand can drag a page so that its far edge overhangs the desk edge, then pinch it); the binder geometry is
an authored reconstruction (Avery 05806 dimensions), not manufacturer CAD.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world-aligned offsets from `wrist_base`) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
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
s = Session("binder_page_load")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("binder_page_load", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # toggle angles, threaded/linked holes, contacts, page poses
s.status()                                      # success, done, reason, steps, stage (0..4), total_stages, hold_steps
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "rings", "pages"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m, the
binder starts at (0.48, 0.00, 0.705) with its back cover towards +x, and the pages lie flat on the desk with their middle hole centres at
`task.json` `page_xy` (0.71, 0.22) and (0.71, -0.025), z = 0.7004 m (page frame: origin at the middle hole centre, +x
across the sheet away from the holes, +z the printed face); the desk's +x edge is at x = 0.98 m. The wrist-stage targets are offsets from `task.json` `wrist_base` (0.62, 0.00, 0.70); at zero wrist
rotation the fingers point down (-z) and the palm faces +x.
