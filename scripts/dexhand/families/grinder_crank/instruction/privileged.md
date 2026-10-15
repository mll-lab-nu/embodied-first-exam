# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands of the same model, each mounted on its own six-DoF wrist positioning stage (three
prismatic and three serial revolute joints, no arm): a right hand and a left hand. The stages and the fingers are
position actuated in the physics engine under native force bounds; holding the grinder and turning the crank require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first twelve entries are the wrist-stage targets, identical for both hand models:
`right_wrist_x, right_wrist_y, right_wrist_z, right_wrist_rx, right_wrist_ry, right_wrist_rz`, then the same six for
`left_wrist_*`. `x, y, z` are metres in the world frame (the stage body sits at the world origin, so these are the world
position of the hand's wrist root); `rx, ry, rz` are radians of serial XYZ joints, not a quaternion. The finger targets
follow in native actuator order, in radians, right hand first:

- `sharpa`: 56 values, the twelve wrist targets, 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`, then 22 left targets `left_thumb_CMC_FE` ... `left_pinky_DIP`. The left Sharpa Wave is the right
  model reflected in y.
- `wuji`: 52 values, the same twelve wrist targets, 20 right Wuji Hand 2.2 targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`, then the manufacturer's left hand
  `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hand models start from the same wrist targets; the
frozen start pose of each model is in `task.json` (`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 56)` for `sharpa` or `(T, 52)`
for `wuji`, at most {{MAX_ROWS}} rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.

## Tooling
```python
from rcb_dexhand import Session
s = Session("grinder_crank")                 # default hand model: DEXHAND_HAND or "sharpa"
s = Session("grinder_crank", hand="wuji")    # explicit hand model
s.hand, s.action_dim, s.actuator_names       # selected model, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, stage, crank angle, tilt, slide, contacts ...
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full integration and verdict state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.70 m;
the crank axis is the grinder's own axis (vertical at the start), 0.175 m above its base, and the knob starts at
(0.45, -0.08, 0.89) m. "Clockwise" is seen from above, i.e. a negative rotation about the grinder's +z axis.
