# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
the turner is held only by finger and palm contact, and the pancake moves only through contact with the turner, the
pan and the plate. The controller runs at {{CONTROL_HZ}} Hz, with twenty 1 ms physics substeps per control.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The episode starts with the turner already held in a settled power grasp: the frozen reset places
the hand, turner, pan, plate and pancake in a state that was reached by closing the fingers on the handle and letting
the whole scene settle under physics; the turner is held only by contact (there is no weld or attachment), so opening
the fingers drops it. Physics runs at 1 ms steps, twenty per 50 Hz control.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Each hand starts from a frozen settled grasp of the turner
(`task.json` `initial_qpos` and `initial_targets` per hand); `s.hold_action()` at reset returns the start targets.
Opening the fingers releases the turner.

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
s = Session("pancake_serve")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("pancake_serve", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names     # selected hand, row width and exact row order
s.hold_action()                            # current motor targets
s.model.actuator_ctrlrange                 # native target limits
s.model, s.data                            # privileged MuJoCo model and state
s.features()                               # pancake pose, contacts, plate distance, withdrawal, stage, failure details
s.status()                                 # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                # twenty 1 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)              # full simulator + verdict state, for search
s.render_frame("overview")                 # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                  # exact frozen reset
s.replay(actions)                          # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.85 m,
the pan rests centred at (0.50, 0.10) and the plate at (0.76, 0.18).
