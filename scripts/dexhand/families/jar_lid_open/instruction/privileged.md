# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a single dexterous hand mounted palm-down on a six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm, no second hand). The stage and the fingers are position actuated in the physics engine
under native force bounds; turning, lifting, carrying and releasing the lid require physical contact, and the jar is
held by nothing but its own weight and friction on the worktop. The controller runs at 50 Hz, with ten 2 ms physics
substeps. At reset the wrist targets are `(0, 0, 0.50)` m and `(0, 0, 0)` rad: the open hand hangs about 0.1 m above the
lid, fingers along +x.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). With `wrist_rx = wrist_ry = 0` the palm faces down, the fingers point along +x and the thumb along +y;
`wrist_rz` turns the hand about the vertical through the stage origin, which sits about 4 cm below the palm. The
finger targets follow in native actuator order, in radians:

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
s = Session("jar_lid_open")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("jar_lid_open", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, lid turn, clearance, contacts, tilts, speeds, failure details
s.status()                                # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the full physics and verdict state
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may observe everything in privileged mode: the MuJoCo model and state (`s.model`, `s.data`), `s.features()`
(stage, unwrapped lid turn, lid clearance above the rim, contacts, tilts, speeds, failure details) and renders from the
`overview`, `closeup` and `side` cameras. Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the
complete geometry (thread ramps and lugs included), failure checks and predicate. The world frame has z up; lengths
are in metres and angles in radians. The jar stands at the origin on the worktop, whose top is at z = 0.30 m; the lid
starts closed with its origin at z = 0.4009 m.
