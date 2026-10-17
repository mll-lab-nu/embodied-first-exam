# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at {{CONTROL_HZ}} Hz, with
ten 2 ms physics substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin `task.json` `stage_origin`, along the world
axes) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion). At zero wrist angles the palm
faces down, the fingers point along +x and the thumb is on the +y side. The finger targets follow in native actuator
order, in radians:

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
s = Session("stool_brace_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("stool_brace_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # stage flags, per-dowel depth/lateral/axis, contacts, speeds, failure
s.status()                                      # success, done, reason, steps, stage, total_stages (4)
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save / restore the full physics and verdict state
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "side"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The table top is at
z = 0.74 m; the lower side frame is centred at `task.json` `lower_frame_pos`, the opposite side frame at
`upper_frame_pos` (upside down) and the brace at `brace_pos` (lying along x). Bore entries and dowel tips are MuJoCo sites
(`<frame>_leg_<m|p>_b<k>_entry`, `<rail>_tip_<m|p>`).
