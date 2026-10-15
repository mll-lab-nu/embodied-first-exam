# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The stages and the fingers are position actuated in the physics engine under native
force bounds; the frame moves only through contact, gravity and its two passive ring hinges, so lifting, carrying,
hooking and releasing all require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene (world frame: metres, z up, x pointing into the wall)
- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre
  of its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The two hands hang palm-inward beside the frame's side rails, fingers pointing down, thumbs toward the wall.

{{HANDS}}
## Action layout
Each row is one 50 Hz control: the left stage `l_wrist_x, l_wrist_y, l_wrist_z` (metres) and `l_wrist_rx, l_wrist_ry,
l_wrist_rz` (radians, serial XYZ joints, not a quaternion), the right stage (`r_wrist_x` ... `r_wrist_rz`), then the
left hand's finger targets and the right hand's, in radians:

- `sharpa`: 56 values, 22 Sharpa Wave finger targets per hand: `l_hand_thumb_CMC_FE` ... `l_hand_pinky_DIP`, then
  `r_hand_thumb_CMC_FE` ... `r_hand_pinky_DIP`. The right hand is the genuine Sharpa Wave right hand; the left hand is a
  declared mirror image of it (the right model reflected across its palm's sagittal plane, same joints, ranges and
  force limits), not a separate manufacturer left-hand model.
- `wuji`: 52 values, 20 Wuji Hand 2.2 finger targets per hand: `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3,
  l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for `r_wuji_r_` (the manufacturer's left and right models).

Stage targets are offsets from each stage's fixed base, left (0.49, 0.33, 1.15) and right (0.49, -0.33, 1.15): slides
within +-0.8 m, hinges within +-1.6 rad. Every target must lie within `s.model.actuator_ctrlrange`. Both hands use the
same stages, ranges, gains and start targets; the frozen start targets are all zero (`task.json` `initial_targets`).

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
s = Session("picture_hang")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("picture_hang", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.status()                                # success, done, reason, failure_detail, steps, stage (0-3), total_stages,
                                          # hold_steps, features (frame pose, threaded rings, hook load shares,
                                          # contacts, roll, tilt, speeds)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the full physics and verdict state
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "front", "side", "hook_closeup"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, the failure checks
and the predicate (`task.json` `predicate` holds every threshold).
