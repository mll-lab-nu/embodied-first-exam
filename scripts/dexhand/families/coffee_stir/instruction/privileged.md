# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and right hand of a Tianji Marvin dual-arm stand (two 7-joint arms, a dexterous hand on each
wrist; the stand sits at the world origin facing +x, its plate on the floor at z = -0.1 m). The left arm starts parked,
hanging beside the torso, and should stay there. Every arm and finger joint is a position servo in the physics engine
under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad, no gravity compensation, so a held
target sags under the arm's weight unless your targets account for it); stirring and laying the spoon down require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
The mug, the coffee and the teaspoon are the approved T11 kitchen scene: a cream glazed mug with a rounded handle
(pointing +x) on a stone worktop (top at z = 0.75 m, front edge at x = 0.25 m), axis at x = 0.48 m, y = 0.015 m. The
source film (kinematic, without hands) starts with the spoon suspended above the rim; here the right hand holds the
teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, the bowl just above the mug (`task.json` `spoon_pos`, position and quaternion WXYZ, is the
settled start pose). The coffee is a visual surface only: it exerts no force, and the stirring is judged only from the
bowl's revolutions below that surface. Mug and spoon are free rigid bodies that move only through contact and gravity.
Cameras: `overview` (front right of the mug, wide), `closeup` (front right, close) and `top` (looking down the mug axis).

{{HANDS}}
## Action layout
Each row is one 50 Hz control, every actuator target in model order (radians):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); columns 7-13: the same right-arm joints (`..._R_J1` to
  `..._R_J7`);
- `sharpa` (58 values): then the 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`, then the
  22 right ones `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): then the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the 20 right ones (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start state of each hand (`task.json`
`initial_qpos`) and its start targets (`initial_targets`) are part of the task; `s.hold_action()` returns the current
targets.

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
s = Session("coffee_stir")                      # default hand: DEXHAND_HAND or "sharpa"
s = Session("coffee_stir", hand="wuji")         # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # bowl position (mug frame), revolutions, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "top"
s.snapshot(), s.restore(snap)                   # save / restore the full simulation and predicate state
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate (`s.features()` reports the quantities the predicate uses: `bowl_cup_frame`, `bowl_radius_m`,
`bowl_submerged`, `revolutions`, `hand_spoon_contacts`, `spoon_cup_contacts`, `spoon_worktop_contacts`,
`spoon_axis_tilt_deg`, `spoon_cup_clearance_m`, speeds, `cup_tilt_deg`, `cup_slide_m`, `rest_hold_steps`). The world frame has z up; lengths are in metres and angles in radians. The worktop top is at
z = 0.75 m and the mug axis at x = 0.48 m, y = 0.015 m; the spoon start pose is `task.json` `spoon_pos` (position,
quaternion WXYZ). The right hand's mount body is `wrist_stage` (on the right arm's flange); the robot stand is at the
world origin (`task.json` `marvin`).
