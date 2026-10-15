# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
pushing the pump handle requires physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, measured from the stage origin at world (0.6, 0.0, 0.7)) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion; all zero = palm facing down, fingers
pointing to world +y, thumb toward world -x). The finger targets follow in native actuator order, in radians:

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
s = Session("bicycle_pump_stroke")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("bicycle_pump_stroke", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # strokes, piston depth, pressure, pump pose/speed, contacts, failure
s.status()                                       # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()` and `s.status()` report `strokes`, `piston_depth_m`, `tire_gauge_pa`, `stage` (completed stages:
1 = six strokes, 2 = pressure target, 3 = released hold), `released_hold_steps`, `pump_tilt_rad`,
`pump_displacement_m`, `pump_lift_m`, `pump_speed_m_s`, `handle_speed_m_s`, `hand_pump_contacts` and, after a failure,
`failure` / `failure_detail`. Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete
geometry, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. The bench top is at z = 0.70 m; the
pump body is `pump` (free joint `pump_free`), its piston slide `piston_extension` (0.20 m = handle up, at rest) and the
T handle geom `t_handle`.
