# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its base plate stands on the floor at z = 0); the
left arm is parked beside the torso and only the right arm and hand do the task. Arm joints and fingers are position
servos in the physics engine under native force bounds; pressing, sliding, pushing and releasing require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control in native actuator order (`s.actuator_names`), radians:

- `sharpa`: 58 values: the 7 left-arm joint targets `SHOULDER_PITCH_L_J1_target, SHOULDER_ROLL_L_J2_target,
  ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target, WRIST_YAW_L_J6_target,
  WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets (`..._R_J1_target` ... `..._R_J7_target`), then the 22
  left-hand and the 22 right-hand Sharpa Wave finger targets (`left_thumb_CMC_FE` ... `left_pinky_DIP`,
  `right_thumb_CMC_FE` ... `right_pinky_DIP`).
- `wuji`: 54 values: the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2 finger
  targets (`l_wuji_l_THJ0..3, FFJ0..3, MFJ0..3, RFJ0..3, LFJ0..3`, then the same for `r_wuji_r_`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm targets (`task.json`
`initial_targets`); keep the left arm parked (its start targets), it must not touch the letter or the envelope.

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
s = Session("envelope_letter_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("envelope_letter_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # corners in the envelope frame, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "mouth"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and predicate.
The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m. The robot's
base pose is `task.json` `marvin`; `s.data.xpos` / `s.data.xmat` of the body `right_hand_C_MC` (the hand root on the right
flange) give the hand's pose, and MuJoCo's Jacobians (`mujoco.mj_jacBody`) are available for your own inverse
kinematics (none is supplied). The envelope frame used by the predicate is the `envelope` body; the letter is the
`letter` body.
