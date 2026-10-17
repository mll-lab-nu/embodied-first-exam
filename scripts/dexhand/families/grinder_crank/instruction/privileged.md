# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand of the same model on each
wrist: a right hand and a left hand. The arm joints and the fingers are position actuated in the physics engine under
native force bounds; holding the grinder and turning the crank require physical contact. The controller runs at 50 Hz,
with ten 2 ms physics substeps. The stand faces +x behind the counter on the floor (z = -0.1 m), its base origin at
(-0.085, 0, 0) m (shoulders 1.121 m above it, at y = +-0.2215 m); any contact of an arm, torso or stand link with
anything ends the episode (`robot_collision`).

{{HANDS}}
## Action layout
Each row is one 50 Hz control: the 14 Marvin arm joint targets (radians) `SHOULDER_PITCH_L_J1_target,
SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target,
WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`, then the same seven for the right arm (`..._R_J1_target` ...
`..._R_J7_target`), then the finger targets in native actuator order, in radians, left hand first:

- `sharpa`: 58 values, the 14 arm targets, 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`,
  then 22 right targets `right_thumb_CMC_FE` ... `right_pinky_DIP`. The left Sharpa Wave is the right model reflected
  in y.
- `wuji`: 54 values, the same 14 arm targets, 20 left Wuji Hand 2.2 targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the manufacturer's right hand `r_wuji_r_THJ0..3` ...
  `r_wuji_r_LFJ0..3`.

Arm servos: kp 700 N m/rad, kv 48 N m s/rad, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no
gravity compensation. Each hand sits rigidly on its arm's flange (bodies `right_wrist_stage` / `left_wrist_stage`:
fingers along the flange +z, palm normal +x, thumb +y for the right hand). No IK primitive is supplied. Every target
must lie within `s.model.actuator_ctrlrange`; the frozen start pose (arm joints; open fingers) is in `task.json`
(`initial_targets`).

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
