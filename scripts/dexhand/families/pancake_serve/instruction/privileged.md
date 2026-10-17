# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand
on each wrist (robot id `marvin-bimanual-sharpa-wave`); the right arm and hand do the task and the left arm stays
parked beside the torso. Every arm and finger joint is a position servo in the physics engine under native force
bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target
sags by about 1 cm at the hand under load unless your targets account for it). The turner is held only by finger and
palm contact, and the pancake moves only through contact with the turner, the pan and the plate. The controller runs
at {{CONTROL_HZ}} Hz, with twenty 1 ms physics substeps per control. World frame: metres and radians, +z up, +x
forward from the robot stand, +y to the robot's left.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The turner is not in a hand at the start: as in the source scene it rests on the counter in
front of the plate, at about (0.76, -0.30, 0.878) m with its handle toward -y (handle end and blade base on the counter,
the handle 16 to 30 mm above it); pick it up first. It is held only by contact (there is no weld or attachment).
Physics runs at 1 ms steps, twenty per 50 Hz control.

{{HANDS}}
## Action layout
Each row is one 50 Hz control with a position target for every actuator, in model order (`s.actuator_names`):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (each name + `_target`); columns 7-13: the right arm `..._R_J1` to `..._R_J7`;
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers (`l_wuji_*`, vendor order), columns 34-53 the
  right Wuji fingers (`r_wuji_*`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start open, the right arm holding its hand
above the counter and the left arm parked (`task.json` `initial_qpos` and `initial_targets` per hand, a settled
state); `s.hold_action()` at reset returns the start targets and keeps that pose.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
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
