# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, brushing and releasing require physical contact. The controller runs at {{CONTROL_HZ}} Hz, with
ten 2 ms physics substeps. The frozen reset lets the boot, the clods and the brush settle for 0.5 s before control 1.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, relative to the stage origin at world (0.55, -0.10, 1.10)) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion; all zero = palm facing down, fingers
pointing +y, thumb on the -x side). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets with open
fingers (`task.json` `initial_targets`).

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
s = Session("boot_sole_brush")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("boot_sole_brush", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names       # selected hand, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, steps, stage, clods in tray/brushed, features
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full physics and predicate state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may read the full simulator state (`s.model`, `s.data`) and the files next to `rcb_dexhand.py`: `task.json`
(frozen geometry, clod start poses, every predicate threshold), `scene.py`, `checker.py` and `runtime.py` (the exact
failure checks and stages). The world frame has z up; lengths are in metres and angles in radians. The counter top
is at z = 0.886 m; the brush starts bristles-down on the counter at (0.68, -0.28); the boot's sole plane is at about
z = 1.292 m with the toe towards -x and the sole centre at (0.53, 0.10); the clod start poses are in `task.json`.
