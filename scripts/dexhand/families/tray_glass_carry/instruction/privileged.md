# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The left hand hangs above the +y end of the tray, the right hand above the -y end,
fingers pointing down and palms facing the tray. Stages and fingers are position actuated in the physics engine under
native force bounds; lifting, carrying and setting down the tray require physical contact. The controller runs at
{{CONTROL_HZ}} Hz, with ten 2 ms physics substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control and holds, in this order:

1. the left wrist stage: `l_wrist_x, l_wrist_y, l_wrist_z` (metres, displacement along the world axes from the stage
   base at (0.35, 0.272, 1.15) m) and `l_wrist_rx, l_wrist_ry, l_wrist_rz` (radians, serial XYZ hinges at the wrist);
2. the right wrist stage: `r_wrist_x ... r_wrist_rz` (same, stage base at (0.35, -0.272, 1.15) m);
3. the left hand's finger targets, then the right hand's finger targets, in radians:
   - `sharpa`: 56 values; 22 Sharpa Wave finger targets per hand, `l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, then
     `r_hand_thumb_CMC_FE ... r_hand_pinky_DIP` (the left hand is the mirrored Wave);
   - `wuji`: 52 values; 20 Wuji Hand 2.2 finger targets per hand, `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, ...,
     l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3 ... r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start with every target at 0 clipped into its
range (stages at their base pose, open hands).

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
s = Session("tray_glass_carry")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("tray_glass_carry", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names        # selected hand, row width and exact row order
s.hold_action()                               # current motor targets
s.model.actuator_ctrlrange                    # native target limits
s.model, s.data                               # privileged MuJoCo model and state
s.status()                                    # success, done, reason, steps, stage (0..3), hold_steps, features
s.step(row)                                   # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                 # save / restore the simulator and predicate state
s.render_frame("overview")                    # RGB uint8 (480, 640, 3); also "side", "top", "handle_left"
s.reset()                                     # exact frozen reset
s.replay(actions)                             # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
In this mode you may read the complete simulator state (`s.model`, `s.data`: object poses, contacts, velocities) and
the predicate progress (`s.status()`: `stage` 0 start, 1 lifted, 2 placed, 3 released and held; `hold_steps` counts
the 50-control release window; `reason` names the first failure). Read `/opt/tools/task.json`, `scene.py`,
`checker.py` and `runtime.py` for the complete geometry, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. Both counter tops are at z = 0.88 m;
the tray's body frame sits at the bottom centre of its floor, its long axis along world y.
