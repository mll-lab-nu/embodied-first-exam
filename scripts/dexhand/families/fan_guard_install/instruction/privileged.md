# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene facts (world frame, metres and radians, z up)
- Worktop: top at z = 0.65, spanning x in [0.28, 1.08], y in [-0.50, 0.50].
- Fan (free body on four rubber feet, 2.15 kg with its clips): body frame starts at (0.73, 0.18, 0.952) with the cage
  axis along world -x. The rear rim (radius 0.1845, wire radius 0.0018) lies in the plane x = 0.73.
- Clip hinges (fixed to the fan; hinge axis tangential to the rim; angle 0 closed over both rims, 1.40 open, the
  elastic detent's over-centre point at 0.70): 45 deg (0.734, 0.3128, 1.0848), 135 deg (0.734, 0.0472, 1.0848),
  225 deg (0.734, 0.0472, 0.8192), 315 deg (0.734, 0.3128, 0.8192). All four clips start open at 1.40 (as in the source
  scene). A closed lower clip (225 or 315 deg) forms an open-topped U channel that can carry the guard's rim; an upper
  clip only counts when it locks at or after the first seated control.
- Front guard (rigid, 0.185 kg): rim radius 0.1845 (wire radius 0.0018), dish 0.047 deep toward the operator, a hub
  cap of radius 0.043 and height 0.022 at its centre (front face 0.057 in front of the rim plane), centre of mass
  0.018 in front of the rim plane on the axis. It starts flat on the worktop, dome up, rim centre at
  (0.48, -0.275, 0.6518).
- Seat: the guard is seated with its centre at (0.72635, 0.18, 0.952), i.e. 3.65 mm in front of the rear-rim plane,
  axis along world -x; the stage-1 tolerances in the task text are measured from this pose in the fan's frame.
- Wrist stage: targets are world positions x in [-0.2, 1.0], y in [-0.6, 0.6], z in [0.35, 1.55] and serial XYZ
  angles in [-3.14, 3.14]; it starts at (0.40, 0.00, 0.95, 3.0, 0, 0) (palm down, fingers along +x).
- Cameras (640 x 480): `overview` at (-0.06, -0.84, 1.40) looking at (0.60, -0.07, 0.84), fovy 45; `closeup` at
  (0.20, -0.27, 1.22) looking at (0.72, 0.17, 1.00), fovy 55.

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
s = Session("fan_guard_install")                # default hand: DEXHAND_HAND or "sharpa"
s = Session("fan_guard_install", hand="wuji")   # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # seat errors, clip angles, contacts, guard speed, failure details
s.status()                                      # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `geometry.py`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry,
failure checks and predicate. In privileged mode you may read the complete simulator state (object poses, contacts,
clip angles, `s.features()`); the scene facts above are the frozen values.
