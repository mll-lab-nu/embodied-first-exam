# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The stand rests on the floor (z = 0) beside the counter's -y edge, with its base origin at world
(0.147, -0.591, 0.10), facing +y (shoulders 1.121 m above the base origin, at z = 1.221 m; the right shoulder is on
the +x side). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and
hand alone, and no other part of the robot may touch anything. Every arm and finger joint is a position servo inside
the physics engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no
gravity compensation** (a held target sags under the arm's weight unless your targets account for it). Grasping,
carrying, brushing and releasing require physical contact. The controller runs at {{CONTROL_HZ}} Hz, with ten 2 ms
physics substeps. The frozen reset lets the boot, the clods, the brush and the arms settle for 0.5 s before control 1.

{{HANDS}}
## Action layout
Each row is one 50 Hz control and holds a position target for every actuator, in radians:

- `sharpa` (58 values): 0-6 the left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
  WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`; keep them at the parked start
  values), 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`), 14-35 the 22 left Sharpa Wave finger targets
  `left_thumb_CMC_FE` ... `left_pinky_DIP`, 36-57 the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets, 14-33 the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, 34-53 the 20 right ones
  (`r_wuji_r_...`, same order).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`): the right hand starts open, palm down, fingers pointing +y, above the brush (hand frame at about
(0.68, -0.35, 1.115)). The right hand's frame is the body `wrist_stage` on the right flange (fingers along its +z,
palm normal +x, thumb +y), which forward kinematics of the arm joints places in the world.

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
z = 1.292 m with the toe towards -x and the sole centre at (0.53, 0.10); the clod start poses and the robot base
pose (`marvin`) are in `task.json`.
