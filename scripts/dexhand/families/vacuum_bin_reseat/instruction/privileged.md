# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin `task.json` `wrist_stage.origin`) and
the left hand (the right hand's mirror image) on `left_wrist_stage` (origin `task.json` `left_wrist_stage.origin`).
Both are needed as in the real task: one hand steadies the vacuum (or works the button) while the other handles the
bin. The stages and the fingers are position actuated in the physics engine under native force bounds; the vacuum
body, the dust bin and the release button move only through contact and their passive dynamics (the button is a spring-loaded
slide). The controller runs at 50 Hz, with twenty 1 ms physics substeps.

{{HANDS}}
## Scene and frames
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m; the
source scene's values). The tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button
(nearly its full 6 mm) lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction
0.55, so pushing the catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's bridge, so the seated bin cannot be
lifted straight out: its top has to tilt out from under the lip, which the raised tooth prevents. The vacuum-body frame is the body frame of `vacuum_body`; the seated bin pose in that frame is
`task.json` `checker.seat_pos` (metres) and `checker.seat_rot` (row-major 3 x 3). Cameras: `overview` (the counter
from the front left) and `closeup` (the latch and the bin).

## Action layout
Each row is one 50 Hz control holding a position target for every actuator, in native actuator order:

- `sharpa` (56 values): 0-5 the right stage `wrist_x, wrist_y, wrist_z` (metres, offsets from its origin, world axes)
  and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion); 6-27 the 22 right Sharpa Wave
  finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`; 28-33 the left stage `left_wrist_x` ... `left_wrist_rz`
  (same convention, its hand mounted without rotation); 34-55 the 22 left finger targets `left_thumb_CMC_FE` ...
  `left_pinky_DIP`.
- `wuji` (52 values): 0-5 the right stage, 6-11 the left stage, 12-31 the right Wuji Hand 2.2 fingers
  `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`, 32-51 the left
  Wuji fingers in the same order (`l_wuji_l_...`); `s.actuator_names` is authoritative.

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 56)` for `sharpa` or `(T, 52)`
for `wuji`, at most {{MAX_ROWS}} rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.

## Tooling
```python
from rcb_dexhand import Session
s = Session("vacuum_bin_reseat")                # default hand: DEXHAND_HAND or "sharpa"
s = Session("vacuum_bin_reseat", hand="wuji")   # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # seat error, button travel, catch clearance, contacts, speeds
s.status()                                      # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                     # twenty 1 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save / restore the full simulator and predicate state
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate (the same code grades your archive). `s.features()` reports the quantities of the predicate: `seat_distance_m`,
`seat_angle_rad`, `button_travel_m`, `released_in_seat`, `catch_behind_tooth_m`, `hand_contacts`, the bin and vacuum
speeds and `body_displacement_m`.
