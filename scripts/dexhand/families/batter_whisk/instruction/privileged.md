# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand
on each wrist (robot id `marvin-bimanual-sharpa-wave`). Every arm and finger joint is a position servo in the physics
engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity
compensation** (a held target sags by about 1 cm at the hand under load unless your targets account for it). The bowl
and the whisk move only through contact with the hands, the arms, each other and the counter. The controller runs at
50 Hz, with ten 2 ms physics substeps. World frame: metres and radians, +z up, +x forward from the robot stand, +y to
the robot's left.

{{HANDS}}
## Action layout
Each row is one 50 Hz control with a position target for every actuator, in model order (`s.actuator_names`):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (each name + `_target`); columns 7-13: the right arm `..._R_J1` to `..._R_J7`;
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers (`l_wuji_*`, vendor order), columns 34-53 the
  right Wuji fingers (`r_wuji_*`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start open above the counter with the arms in a
ready pose (`task.json` `reset_state[<hand>]`: joint positions and start targets); `s.hold_action()` at reset keeps
that pose. The whisk does not start in a hand: it rests against the bowl rim with its handle end on the counter, where
it settles when released from the source scene's start pose (standing in the bowl). The left hand may steady the bowl
(for example while the right hand lifts the whisk off its rim); the success predicate does not require it.

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
s = Session("batter_whisk")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("batter_whisk", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, pickup/revolutions/drain/hold counters, contacts, bowl tilt/slide
s.status()                                # success, done, reason, steps, stage, total_stages (5)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the simulation and verdict state (planning)
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate, and `arm_rig.py` for the robot. The counter top is at z = 0.68 m (front edge x = 0.25 m), the bowl origin
(its outer bottom) starts at (0.58, 0.0, 0.6805) m, its rim is 78 mm above that origin; the whisk frame has its origin at
the wire tip and +z along the handle (handle from 230 mm to 345 mm); at reset the wire tip is at about (0.576, -0.005,
0.813) m and the handle points down to the counter toward (-0.30, -0.88, -0.36) (`task.json` `reset_state`).
